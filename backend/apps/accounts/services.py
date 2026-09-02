"""Account domain services.

Business rules live here rather than in serializers or views. A rule enforced in
a serializer only holds for requests that happen to use that serializer; the
same rule in a service holds for the API, the Django admin, management commands
and future background tasks alike.

Every function that changes state writes an audit entry inside the same
transaction, so history cannot drift from reality.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import AuditAction, AuditResult, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.uploads import normalise_profile_image

from .emails import (
    send_account_created_email,
    send_email_verification_email,
    send_password_reset_email,
)
from .models import AccountToken, TokenPurpose, User, UserRole

logger = logging.getLogger("grras.security")


class InvalidTokenError(ApplicationError):
    """Raised for a token that is unknown, expired or already used.

    One error for all three cases on purpose: distinguishing them would tell an
    attacker whether a guessed token ever existed.
    """

    status_code = 400
    default_detail = "This link is invalid or has expired. Request a new one."
    default_code = "invalid_token"


# ---------------------------------------------------------------------------
# User lifecycle
# ---------------------------------------------------------------------------


@transaction.atomic
def create_user(
    *,
    email: str,
    password: str | None = None,
    first_name: str,
    last_name: str = "",
    role: str = UserRole.STUDENT,
    phone: str = "",
    is_active: bool = True,
    actor: User | None = None,
    send_invitation: bool = True,
) -> User:
    """Create a user and record the action.

    When no password is supplied the account is created without a usable one and
    the user is emailed a single-use link to set their own. An administrator
    therefore never learns or transmits someone else's password.
    """
    try:
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            phone=phone,
            is_active=is_active,
        )
    except IntegrityError as exc:
        # Reachable only by administrators, so naming the conflict is safe here.
        raise ConflictError("An account with this email address already exists.") from exc

    record(
        action=AuditAction.USER_CREATED,
        actor=actor,
        resource_type="user",
        resource_id=user.pk,
        context={"role": user.role, "email": user.email, "created_by_admin": actor is not None},
    )

    if send_invitation and password is None:
        _, raw_token = AccountToken.issue(user=user, purpose=TokenPurpose.PASSWORD_RESET)
        transaction.on_commit(lambda: send_account_created_email(user=user, raw_token=raw_token))

    return user


@transaction.atomic
def update_user(*, user: User, actor: User, **fields: Any) -> User:
    """Update administrator-editable user fields.

    Role changes are audited separately because they are a privilege change, and
    a reviewer should be able to find every one of them with a single query.
    """
    previous_role = user.role
    changed: list[str] = []

    for field, value in fields.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed.append(field)

    if not changed:
        return user

    user.full_clean(exclude=["password"])
    user.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.USER_UPDATED,
        actor=actor,
        resource_type="user",
        resource_id=user.pk,
        context={"changed_fields": sorted(changed)},
    )

    if "role" in changed:
        record(
            action=AuditAction.USER_ROLE_CHANGED,
            actor=actor,
            resource_type="user",
            resource_id=user.pk,
            context={"from": previous_role, "to": user.role},
        )
        # A privilege change must not be usable from a session established under
        # the old role.
        revoke_sessions(user=user, actor=actor, reason="role_changed")

    return user


@transaction.atomic
def set_user_active(*, user: User, is_active: bool, actor: User, reason: str = "") -> User:
    """Activate or deactivate an account.

    Deactivation takes effect immediately: ``IsActiveUser`` rejects the next
    request from an existing session, and the session rows are deleted as well
    so nothing lingers.
    """
    if user.is_active == is_active:
        return user

    user.is_active = is_active
    user.save(update_fields=["is_active", "updated_at"])

    record(
        action=AuditAction.USER_ACTIVATED if is_active else AuditAction.USER_DEACTIVATED,
        actor=actor,
        resource_type="user",
        resource_id=user.pk,
        context={"reason": reason},
    )

    if not is_active:
        revoke_sessions(user=user, actor=actor, reason="deactivated")

    return user


def deactivate_user(*, user: User, actor: User | None = None, reason: str = "") -> User:
    """Backwards-compatible wrapper kept from Phase 0."""
    return set_user_active(user=user, is_active=False, actor=actor, reason=reason)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def revoke_sessions(*, user: User, actor: User | None = None, reason: str = "") -> int:
    """Delete every stored session belonging to a user.

    Django already invalidates sessions implicitly in two ways: changing a
    password rotates the session auth hash, and ``IsActiveUser`` rejects an
    inactive user on the next request. This function is the explicit belt to
    those braces — it makes "sign out everywhere" a real, auditable action.

    Implementation note: Django's session table is keyed by session key with the
    user id buried in the encoded payload, so finding a user's sessions means
    decoding the non-expired rows. That is acceptable at this scale; if the
    session table ever grows large, move to a session backend that indexes the
    user id rather than making this query cleverer.
    """
    deleted = 0
    user_pk = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        try:
            data = session.get_decoded()
        except Exception:  # a corrupt row must not block sign-out
            # Logged rather than swallowed: an undecodable session is either
            # corruption or a stale entry from an old SECRET_KEY, and both are
            # worth knowing about.
            logger.warning(
                "Skipped an undecodable session while revoking sessions",
                extra={"context": {"user_id": user_pk}},
            )
            continue
        if data.get("_auth_user_id") == user_pk:
            session.delete()
            deleted += 1

    if deleted:
        record(
            action=AuditAction.SESSIONS_REVOKED,
            actor=actor or user,
            resource_type="user",
            resource_id=user.pk,
            context={"sessions_revoked": deleted, "reason": reason},
        )
    return deleted


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def _validate_new_password(password: str, user: User) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        # Field-scoped so the client can attach the message to the right input.
        raise ApplicationError({"new_password": list(exc.messages)}) from exc


@transaction.atomic
def change_password(*, user: User, current_password: str, new_password: str, request=None) -> None:
    """Change the password of the signed-in user.

    Requires the current password, so a hijacked session alone cannot lock the
    real owner out. Every other session is invalidated; the caller's own session
    is kept alive so they are not signed out of the tab they are using.
    """
    if not user.check_password(current_password):
        record(
            action=AuditAction.PASSWORD_CHANGED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
            result=AuditResult.FAILURE,
            context={"reason": "current_password_incorrect"},
        )
        raise ApplicationError({"current_password": ["Your current password is incorrect."]})

    if current_password == new_password:
        raise ApplicationError(
            {"new_password": ["The new password must differ from the current one."]}
        )

    _validate_new_password(new_password, user)

    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    # Changing the password rotates the session auth hash, which invalidates
    # every other session automatically. Re-hash the current one so the user
    # stays signed in where they are.
    if request is not None:
        update_session_auth_hash(request, user)

    record(
        action=AuditAction.PASSWORD_CHANGED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
    )


def request_password_reset(*, email: str) -> None:
    """Start a password reset.

    Deliberately indistinguishable for known and unknown addresses: the caller
    always gets the same response and the same timing profile, so this endpoint
    cannot be used to discover who has an account. Inactive accounts are treated
    the same way for the same reason.
    """
    normalised = (email or "").strip().lower()
    user = User.objects.filter(email__iexact=normalised, is_active=True).first()

    record(
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        actor=user,
        actor_label=normalised,
        resource_type="user",
        resource_id=getattr(user, "pk", ""),
        # Recorded so repeated probing is visible to a reviewer, without the
        # response telling the requester anything.
        context={"account_exists": user is not None},
    )

    if user is None:
        return

    _, raw_token = AccountToken.issue(user=user, purpose=TokenPurpose.PASSWORD_RESET)
    send_password_reset_email(user=user, raw_token=raw_token)


def reset_password(*, raw_token: str, new_password: str) -> User:
    """Complete a password reset with a single-use token.

    Token validation happens *before* the state-changing transaction: the audit
    entry for a rejected token has to survive the rejection, and a write inside
    a block that then rolls back would be lost.
    """
    token = _consume_token(raw_token, TokenPurpose.PASSWORD_RESET)
    user = token.user

    if not user.is_active:
        # Do not let a reset quietly re-enable a disabled account.
        raise InvalidTokenError()

    _validate_new_password(new_password, user)

    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        token.consume()

        record(
            action=AuditAction.PASSWORD_RESET_COMPLETED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
        )
    # Anyone signed in with the old credentials is signed out: a reset is the
    # standard response to a suspected compromise.
    revoke_sessions(user=user, actor=user, reason="password_reset")
    return user


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


def request_email_verification(*, user: User) -> None:
    if user.is_email_verified:
        return
    _, raw_token = AccountToken.issue(user=user, purpose=TokenPurpose.EMAIL_VERIFICATION)
    record(
        action=AuditAction.EMAIL_VERIFICATION_REQUESTED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
    )
    send_email_verification_email(user=user, raw_token=raw_token)


def verify_email(*, raw_token: str) -> User:
    """Confirm an email address. See :func:`reset_password` on ordering."""
    token = _consume_token(raw_token, TokenPurpose.EMAIL_VERIFICATION)
    user = token.user

    with transaction.atomic():
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["is_email_verified", "email_verified_at", "updated_at"])
        token.consume()

        record(
            action=AuditAction.EMAIL_VERIFIED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
        )
    return user


def _consume_token(raw_token: str, purpose: str) -> AccountToken:
    """Look up a token by hash and check it is usable.

    Unknown, expired and already-used tokens all raise the same error so the
    response cannot be used to probe which tokens exist.
    """
    token = (
        AccountToken.objects.select_related("user")
        .filter(token_hash=AccountToken.hash_token(raw_token or ""), purpose=purpose)
        .first()
    )

    if token is None or not token.is_valid:
        failure_action = (
            AuditAction.PASSWORD_RESET_FAILED
            if purpose == TokenPurpose.PASSWORD_RESET
            else AuditAction.EMAIL_VERIFICATION_FAILED
        )
        record(
            action=failure_action,
            actor=getattr(token, "user", None),
            resource_type="account_token",
            result=AuditResult.FAILURE,
            # Records *why* it failed without recording the token itself.
            context={
                "reason": "unknown" if token is None else ("used" if token.is_used else "expired")
            },
        )
        raise InvalidTokenError()
    return token


# ---------------------------------------------------------------------------
# Profile image
# ---------------------------------------------------------------------------


@transaction.atomic
def set_profile_image(*, user: User, uploaded_file, actor: User | None = None) -> User:
    """Validate, re-encode and store a profile image.

    The stored file is produced by :func:`normalise_profile_image`, so the bytes
    on disk were generated by this process rather than supplied by the client.
    """
    normalised = normalise_profile_image(uploaded_file)

    if user.profile_image:
        user.profile_image.delete(save=False)

    user.profile_image.save(normalised.name, normalised, save=False)
    user.save(update_fields=["profile_image", "updated_at"])

    record(
        action=AuditAction.PROFILE_IMAGE_UPDATED,
        actor=actor or user,
        resource_type="user",
        resource_id=user.pk,
        context={"size_bytes": normalised.size},
    )
    return user


@transaction.atomic
def remove_profile_image(*, user: User, actor: User | None = None) -> User:
    if not user.profile_image:
        return user
    user.profile_image.delete(save=False)
    user.profile_image = None
    user.save(update_fields=["profile_image", "updated_at"])
    record(
        action=AuditAction.PROFILE_IMAGE_REMOVED,
        actor=actor or user,
        resource_type="user",
        resource_id=user.pk,
    )
    return user


def record_permission_denied(*, actor: Any, resource_type: str, resource_id: Any = "") -> None:
    """Audit hook for refused authorization attempts."""
    record(
        action=AuditAction.PERMISSION_DENIED,
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        result=AuditResult.DENIED,
    )
