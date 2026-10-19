"""Account serializers — input validation and output shaping only.

Serializers are scoped by *who is calling*, not just by resource. A student
updating themselves and an administrator updating that same student use
different serializers with different field lists, because the alternative —
one serializer with conditional logic — is where privilege-escalation bugs
live.
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.authorization.models import Role
from apps.common import bulk
from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .mfa import MfaMethod
from .models import User
from .roles import UserRole, allowed_role_transitions

PASSWORD_STYLE = {"input_type": "password"}


def _validate_password_strength(value: str) -> str:
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return value


class UserSerializer(serializers.ModelSerializer):
    """Public representation of a user.

    The field list is explicit: a wildcard would leak ``password``,
    ``is_superuser`` and permission internals the moment a field is added.
    """

    full_name = serializers.CharField(read_only=True)
    profile_image_url = serializers.SerializerMethodField()
    # The centre this account is bounded to — on every representation of a
    # user, because the administrator's record needs it as much as the
    # signed-in user's own does.
    # `default=None` on all three is load-bearing, not decoration: `branch` is
    # nullable, and `source="branch.id"` on a null relation raises
    # `AttributeError` — a 500 on the very first superadmin login.
    branch_id = serializers.CharField(source="branch.id", read_only=True, default=None)
    branch_code = serializers.CharField(source="branch.code", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    custom_role = serializers.CharField(source="custom_role.slug", read_only=True, default=None)
    custom_role_name = serializers.CharField(
        source="custom_role.name", read_only=True, default=None
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "custom_role",
            "custom_role_name",
            "is_active",
            "is_email_verified",
            "profile_image_url",
            "date_joined",
            "branch_id",
            "branch_code",
            "branch_name",
        )
        read_only_fields = fields

    def get_profile_image_url(self, obj: User) -> str | None:
        """Path to the authenticated image view, never a direct media path."""
        if not obj.profile_image:
            return None
        return f"/api/v1/users/{obj.pk}/profile-image/"


class CurrentUserSerializer(UserSerializer):
    """The signed-in user's own record, plus what the UI needs to render itself.

    ``capabilities`` is a convenience for the interface only. The backend
    re-checks every capability on every request; a client that lied about this
    list would gain nothing.
    """

    capabilities = serializers.SerializerMethodField()
    profile_type = serializers.SerializerMethodField()
    profile_id = serializers.SerializerMethodField()
    #: Whether a confirmed TOTP device exists (ERP Phase 5, ADR-05) — lets the
    #: settings screen offer "enable" or "manage/disable" without a second call.
    mfa_enabled = serializers.BooleanField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            "last_login",
            "email_verified_at",
            "capabilities",
            "profile_type",
            "profile_id",
            "mfa_enabled",
        )
        read_only_fields = fields

    def get_capabilities(self, obj: User) -> list[str]:
        return sorted(obj.capabilities)

    def get_profile_type(self, obj: User) -> str | None:
        if obj.role == UserRole.STUDENT and getattr(obj, "student_profile", None) is not None:
            return "student"
        if (
            obj.role in (UserRole.TRAINER, UserRole.MANAGER)
            and getattr(obj, "trainer_profile", None) is not None
        ):
            return "trainer"
        return None

    def get_profile_id(self, obj: User) -> str | None:
        if obj.role == UserRole.STUDENT:
            profile = getattr(obj, "student_profile", None)
        elif obj.role in (UserRole.TRAINER, UserRole.MANAGER):
            profile = getattr(obj, "trainer_profile", None)
        else:
            profile = None
        return str(profile.pk) if profile else None


class CredentialActionResultSerializer(serializers.Serializer):
    """Whether the mail service took the email, and what to tell the admin."""

    sent = serializers.BooleanField()
    detail = serializers.CharField()


class AdminUserDetailSerializer(UserSerializer):
    """Administrator view of a user. Still never exposes credential material."""

    can_administer = serializers.SerializerMethodField()
    allowed_role_transitions = serializers.SerializerMethodField()
    profile_type = serializers.SerializerMethodField()
    profile_id = serializers.SerializerMethodField()
    #: They have set a password of their own — they accepted the invitation
    #: and can sign in. Not the same as a verified email.
    invitation_accepted = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            "is_staff",
            "last_login",
            "email_verified_at",
            "created_at",
            "updated_at",
            "can_administer",
            "allowed_role_transitions",
            "profile_type",
            "profile_id",
            "invitation_accepted",
        )
        read_only_fields = fields

    def get_invitation_accepted(self, obj: User) -> bool:
        return obj.has_usable_password()

    def get_can_administer(self, obj: User) -> bool:
        """Whether the *caller* may change this account.

        Sent so the interface can show a read-only record instead of a form
        whose Save button is going to fail. Viewing is a wider permission than
        administering — an administrator may legitimately see that a superadmin
        exists — and without this the screen had no way to tell the difference,
        so it offered controls that could not work.

        It informs the interface; it does not enforce anything. The service
        layer answers the same question again on every write.
        """
        from apps.accounts.roles import can_administer

        request = self.context.get("request")
        return can_administer(getattr(request, "user", None), obj)

    def get_allowed_role_transitions(self, obj: User) -> list[str]:
        request = self.context.get("request")
        return list(allowed_role_transitions(getattr(request, "user", None), obj))

    def get_profile_type(self, obj: User) -> str | None:
        return CurrentUserSerializer().get_profile_type(obj)

    def get_profile_id(self, obj: User) -> str | None:
        return CurrentUserSerializer().get_profile_id(obj)


class AdminUserCreateSerializer(StrictModelSerializer):
    """Administrator creating an account.

    No password field on purpose: the new user receives a single-use link and
    chooses their own, so an administrator never handles someone else's
    credentials.

    ``branch`` is optional because for almost every caller it is ignored: a
    bounded administrator's own centre is forced onto the record whatever they
    send. It exists for the platform operator, who is bounded to no centre and
    must therefore name one — without it, the only role that can run more than
    one centre could not create a record in any of them.
    """

    email = serializers.EmailField(max_length=254)
    first_name = SafeCharField(max_length=100)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    phone = SafeCharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=UserRole.choices)
    #: A plain id rather than a `PrimaryKeyRelatedField`, which would validate
    #: against the whole `Branch` table and so tell any caller which ids name a
    #: real centre. Resolved in the view through `visible_branches`.
    branch = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "role", "is_active", "branch")

    def validate_email(self, value: str) -> str:
        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalised

    def validate_role(self, value: str) -> str:
        if value == UserRole.STUDENT:
            raise serializers.ValidationError(
                "Register students through Admissions so their student record is created too."
            )
        if value == UserRole.TRAINER:
            raise serializers.ValidationError(
                "Add trainers through Trainer onboarding so their trainer profile is created too."
            )
        return value


class AdminUserUpdateSerializer(StrictModelSerializer):
    """Administrator editing an account.

    ``email`` is here, and it is not an ordinary field: it is the login
    identifier. The service marks the new address unverified, ends existing
    sessions and sends a verification link — see `_handle_email_change`.

    ``is_active`` is still absent. Activation is a security control with its own
    audited endpoint, and it should not be possible to flip it as a side effect
    of correcting a phone number.

    ``is_email_verified`` is absent too, deliberately. An administrator may
    *revoke* verification (by changing the address) and may resend the link, but
    cannot mark an address verified by hand — that would be an administrator
    asserting a fact only the inbox owner can establish.
    """

    email = serializers.EmailField(required=False)
    first_name = SafeCharField(max_length=100, required=False)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True)
    phone = SafeCharField(max_length=20, required=False, allow_blank=True)
    #: The `updated_at` the form was loaded with. When given, a write based on
    #: an older copy is refused with 409 `stale_write` instead of overwriting.
    expected_updated_at = serializers.DateTimeField(required=False, write_only=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "expected_updated_at")


class UserRoleTransitionSerializer(StrictSerializer):
    """A governed role change, separate from ordinary account details."""

    role = serializers.ChoiceField(choices=UserRole.choices)
    custom_role = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Role.objects.filter(is_system=False),
        required=False,
        allow_null=True,
    )
    reason = SafeCharField(max_length=255, allow_blank=False)
    expected_updated_at = serializers.DateTimeField(required=False)


class SelfUserUpdateSerializer(StrictModelSerializer):
    """What a user may change about their own account.

    Note what is *not* here: ``role``, ``is_active``, ``is_staff``,
    ``is_superuser``, ``email``, ``is_email_verified`` and every timestamp.
    Because the base class rejects unknown fields, sending any of them returns
    400 naming the field rather than quietly discarding it.
    """

    first_name = SafeCharField(max_length=100, required=False)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True)
    phone = SafeCharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")


class LoginSerializer(StrictSerializer):
    """Login input. Unknown fields are rejected outright."""

    email = serializers.EmailField(max_length=254, trim_whitespace=True)
    password = SafeCharField(
        max_length=128, write_only=True, style=PASSWORD_STYLE, trim_whitespace=False
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class StepUpSerializer(StrictSerializer):
    """Step-up input: a password re-entry, or a code — exactly one, never
    both, never neither. ``method`` picks which kind of code (ADR-05 Phase
    5 extends the Phase 4 email-only code with TOTP and recovery, both
    verified against the caller's own confirmed device); it is meaningless
    — and rejected — alongside a password, and defaults to ``"email"`` when
    only ``code`` is sent, so an existing Phase 4 caller needs no change."""

    password = serializers.CharField(
        write_only=True, trim_whitespace=False, required=False, allow_blank=False
    )
    method = serializers.ChoiceField(
        choices=tuple(MfaMethod.choices), required=False, write_only=True
    )
    code = SafeCharField(write_only=True, max_length=16, required=False, allow_blank=False)

    def validate(self, attrs):
        password = attrs.get("password")
        code = attrs.get("code")
        if bool(password) == bool(code):
            raise serializers.ValidationError(
                "Provide either a password or a one-time code, not both."
            )
        if password and attrs.get("method"):
            raise serializers.ValidationError({"method": ["Not accepted alongside a password."]})
        if code:
            attrs["method"] = attrs.get("method") or MfaMethod.EMAIL
        return attrs


class MfaVerifySerializer(StrictSerializer):
    """Body of ``POST /auth/mfa/verify/``: which of the three factors, and
    the code for it. Used both to complete a pending sign-in and, for an
    already-authenticated caller, to obtain step-up — the view decides
    which by whether a pending-MFA session is present (ADR-05)."""

    method = serializers.ChoiceField(choices=tuple(MfaMethod.choices))
    code = SafeCharField(max_length=16, allow_blank=False)


class MfaTotpConfirmSerializer(StrictSerializer):
    """Body of ``POST /auth/mfa/totp/confirm/``: the 6-digit code from the
    authenticator app that was just scanned."""

    code = SafeCharField(max_length=6, allow_blank=False)


class MfaRequiredSerializer(serializers.Serializer):
    """The alternate ``200`` shape ``POST /auth/login/`` answers with when
    MFA applies (ADR-05) instead of the usual ``CurrentUserSerializer``."""

    mfa_required = serializers.BooleanField(read_only=True)
    methods = serializers.ListField(child=serializers.CharField(), read_only=True)
    expires_in = serializers.IntegerField(read_only=True)


class MfaEnrolSerializer(serializers.Serializer):
    """Response of ``POST /auth/mfa/totp/enrol/``."""

    secret_uri = serializers.CharField(read_only=True)
    secret = serializers.CharField(read_only=True)
    qr_svg = serializers.CharField(read_only=True)


class RecoveryCodesSerializer(serializers.Serializer):
    """Response carrying the ten recovery codes — shown exactly once, at
    confirmation and at regeneration, and never retrievable again."""

    recovery_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class PasswordChangeSerializer(StrictSerializer):
    current_password = SafeCharField(
        max_length=128, write_only=True, style=PASSWORD_STYLE, trim_whitespace=False
    )
    new_password = SafeCharField(
        max_length=128, write_only=True, style=PASSWORD_STYLE, trim_whitespace=False
    )

    def validate_new_password(self, value: str) -> str:
        return _validate_password_strength(value)


class PasswordResetRequestSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmSerializer(StrictSerializer):
    token = SafeCharField(max_length=128, write_only=True, trim_whitespace=True)
    new_password = SafeCharField(
        max_length=128, write_only=True, style=PASSWORD_STYLE, trim_whitespace=False
    )

    def validate_new_password(self, value: str) -> str:
        return _validate_password_strength(value)


class EmailVerificationConfirmSerializer(StrictSerializer):
    token = SafeCharField(max_length=128, write_only=True, trim_whitespace=True)


class SetActiveSerializer(StrictSerializer):
    """Activation/deactivation input.

    ``reason`` is recorded in the audit entry, which is what makes a
    deactivation reviewable months later.
    """

    is_active = serializers.BooleanField()
    reason = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class UserBranchSerializer(StrictSerializer):
    """Moving an account between centres.

    ``reason`` is what makes the move reviewable afterwards; the audit entry
    records it beside the two branch codes.
    """

    branch_id = serializers.UUIDField()
    reason = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class ProfileImageUploadSerializer(StrictSerializer):
    """Multipart upload.

    Only the size is checked here; format and content verification happen in
    ``apps.common.uploads`` where the bytes are actually inspected.
    """

    image = serializers.ImageField(write_only=True)


class DetailSerializer(serializers.Serializer):
    """Simple message envelope for actions with no resource body."""

    detail = serializers.CharField(read_only=True)


class CredentialActionSerializer(StrictSerializer):
    """Which link to send. Two named actions rather than a free-form string."""

    action = serializers.ChoiceField(choices=("password_reset", "email_verification"))


class SessionSerializer(serializers.Serializer):
    """One entry in a session list (ERP Phase 6, ADR-06).

    Never the raw session key or its hash — those never leave the server
    (rule §13). ``is_current`` is computed against whichever session made
    *this* request, passed in through the serializer context.
    """

    id = serializers.UUIDField(source="pk", read_only=True)
    device_label = serializers.CharField(read_only=True)
    ip = serializers.IPAddressField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    last_seen_at = serializers.DateTimeField(read_only=True)
    is_current = serializers.SerializerMethodField()

    def get_is_current(self, obj) -> bool:
        current_hash = self.context.get("current_session_key_hash")
        return bool(current_hash) and obj.session_key_hash == current_hash


class UserAuditEntrySerializer(serializers.Serializer):
    """One line of an account's history, shaped for reading.

    ``actor_label`` rather than a nested user: the person who made a change may
    since have been deleted, and the history should still say who it was. The
    audit log stores the label for exactly that reason.
    """

    id = serializers.UUIDField(read_only=True)
    action = serializers.CharField(read_only=True)
    action_label = serializers.SerializerMethodField()
    result = serializers.CharField(read_only=True)
    actor_label = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    context = serializers.JSONField(read_only=True)

    def get_action_label(self, obj) -> str:
        from apps.audit.models import AuditAction

        return AuditAction(obj.action).label if obj.action in AuditAction.values else obj.action


class UserBulkRequestSerializer(bulk.BulkTargetSerializer):
    """`POST /users/bulk/`: one action across many accounts."""

    ACTIONS = ("resend_invitation", "move_centre")

    action = serializers.ChoiceField(choices=ACTIONS)
    branch_id = serializers.UUIDField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["action"] == "move_centre":
            if not attrs.get("branch_id"):
                raise serializers.ValidationError({"branch_id": ["Choose the centre."]})
            if not (attrs.get("reason") or "").strip():
                raise serializers.ValidationError(
                    {"reason": ["Say why these accounts are moving; it goes in the audit trail."]}
                )
        return attrs


class AccountEmailSerializer(serializers.Serializer):
    kind = serializers.CharField()
    kind_label = serializers.CharField()
    sent = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)
    at = serializers.DateTimeField()


class InvitationStateSerializer(serializers.Serializer):
    sent_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    expired = serializers.BooleanField()


class CapabilitySerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class AdminUserRecordSerializer(AdminUserDetailSerializer):
    """One account's page: the detail fields plus where the account stands —
    the invitation, the last account email and whether it went, MFA, and what
    the person can do. Read for one account at a time (a few queries), never
    for a list."""

    mfa_enabled = serializers.BooleanField(read_only=True)
    invitation = serializers.SerializerMethodField()
    last_account_email = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    may_send_invitation = serializers.SerializerMethodField()

    class Meta(AdminUserDetailSerializer.Meta):
        fields = (
            *AdminUserDetailSerializer.Meta.fields,
            "mfa_enabled",
            "invitation",
            "last_account_email",
            "capabilities",
            "may_send_invitation",
        )
        read_only_fields = fields

    @extend_schema_field(InvitationStateSerializer(allow_null=True))
    def get_invitation(self, obj: User) -> dict | None:
        from django.utils import timezone

        from .models import AccountToken, TokenPurpose

        if obj.has_usable_password():
            return None
        token = (
            AccountToken.objects.filter(user=obj, purpose=TokenPurpose.INVITATION)
            .order_by("-created_at")
            .first()
        )
        if token is None:
            return None
        expired = token.used_at is not None or token.expires_at <= timezone.now()
        return {"sent_at": token.created_at, "expires_at": token.expires_at, "expired": expired}

    @extend_schema_field(AccountEmailSerializer(allow_null=True))
    def get_last_account_email(self, obj: User) -> dict | None:
        from apps.audit.models import AuditAction, AuditLog

        from .emails import KIND_LABEL

        row = (
            AuditLog.objects.filter(
                action__in=[AuditAction.CREDENTIAL_EMAIL_SENT, AuditAction.CREDENTIAL_EMAIL_FAILED],
                resource_type="user",
                resource_id=str(obj.pk),
            )
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return None
        context = row.context or {}
        kind = context.get("kind", "")
        return {
            "kind": kind,
            "kind_label": KIND_LABEL.get(kind, kind),
            "sent": row.action == AuditAction.CREDENTIAL_EMAIL_SENT,
            "error": context.get("error", ""),
            "at": row.created_at,
        }

    @extend_schema_field(CapabilitySerializer(many=True))
    def get_capabilities(self, obj: User) -> list[dict]:
        from apps.accounts.roles import Capability, effective_capabilities

        labels = dict(Capability.choices)
        return [
            {"code": code, "label": str(labels.get(code, code))}
            for code in sorted(effective_capabilities(obj))
        ]

    def get_may_send_invitation(self, obj: User) -> bool:
        from .services import may_send_invitation

        request = self.context.get("request")
        actor = getattr(request, "user", None)
        return bool(
            actor is not None
            and actor.pk != obj.pk
            and obj.is_active
            and not obj.has_usable_password()
            and may_send_invitation(actor, obj)
        )
