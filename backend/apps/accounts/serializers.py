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
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import User
from .roles import UserRole

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
            "is_active",
            "is_email_verified",
            "profile_image_url",
            "date_joined",
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

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            "last_login",
            "email_verified_at",
            "capabilities",
            "profile_type",
            "profile_id",
        )
        read_only_fields = fields

    def get_capabilities(self, obj: User) -> list[str]:
        return sorted(obj.capabilities)

    def get_profile_type(self, obj: User) -> str | None:
        if obj.role == UserRole.STUDENT:
            return "student"
        if obj.role == UserRole.TRAINER:
            return "trainer"
        return None

    def get_profile_id(self, obj: User) -> str | None:
        profile = getattr(obj, "student_profile", None) or getattr(obj, "trainer_profile", None)
        return str(profile.pk) if profile else None


class AdminUserDetailSerializer(UserSerializer):
    """Administrator view of a user. Still never exposes credential material."""

    can_administer = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = (
            *UserSerializer.Meta.fields,
            "is_staff",
            "last_login",
            "email_verified_at",
            "created_at",
            "updated_at",
            "can_administer",
        )
        read_only_fields = fields

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


class AdminUserCreateSerializer(StrictModelSerializer):
    """Administrator creating an account.

    No password field on purpose: the new user receives a single-use link and
    chooses their own, so an administrator never handles someone else's
    credentials.
    """

    email = serializers.EmailField(max_length=254)
    first_name = SafeCharField(max_length=100)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    phone = SafeCharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=UserRole.choices)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "role", "is_active")

    def validate_email(self, value: str) -> str:
        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalised


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
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "role")


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
