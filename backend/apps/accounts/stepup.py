"""Step-up authentication: proving it is still you before a dangerous act.

A signed-in session is enough for ordinary work. Locking a permission,
destroying a record, disabling somebody's second factor — those ask the
person to re-enter their password or a second factor within the last few
minutes. The proof is a timestamp in the session; the API refuses with
``403 step_up_required`` when it is missing or stale, and the interface opens
the step-up dialog in place and retries once.

Phase 2 built the password path. Phase 4 (ADR-05) added a second: an emailed
one-time code, verified by :mod:`apps.accounts.otp` — the same primitive
Phase 5 reuses at login time. Phase 5 adds the remaining two: a TOTP code
and a recovery code, both verified by :mod:`apps.accounts.mfa` against the
caller's own confirmed device. All four paths end the same way, through
:func:`grant`, and are reported through the same pair of audit events so
"did this account step up, and how?" has one answer regardless of which
proof was used.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.audit.services import AuditAction, AuditResult, record
from apps.common.middleware import client_ip

SESSION_KEY = "step_up_at"


class StepUpRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Confirm it is you before doing this."
    default_code = "step_up_required"


def is_fresh(request) -> bool:
    stamp = request.session.get(SESSION_KEY)
    if not stamp:
        return False
    # Local import: `apps.policies.resolver` is a leaf module with no import
    # back to `apps.accounts`, but keeping the edge inside the function (the
    # same discipline `step_up_with_email_code` already uses for `.otp`)
    # means this module's import order still does not depend on the policy
    # app being ready first.
    from apps.policies.resolver import policy

    minutes = policy("authentication", "step_up_minutes")
    return (timezone.now().timestamp() - float(stamp)) < minutes * 60


def grant(request) -> None:
    request.session[SESSION_KEY] = timezone.now().timestamp()
    request.session.modified = True


def step_up_with_password(request, password: str) -> None:
    """Re-enter the password to obtain a fresh step-up."""
    user = request.user
    if not password or not user.check_password(password):
        record(
            action=AuditAction.STEP_UP_FAILED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
            result=AuditResult.FAILURE,
            context={"method": "password"},
        )
        raise StepUpRequired("That password is not right.")
    grant(request)
    record(
        action=AuditAction.STEP_UP_SUCCEEDED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
        context={"method": "password"},
        durable=False,
    )


def step_up_with_email_code(request, code: str) -> None:
    """Verify an emailed one-time code (ADR-05) to obtain a fresh step-up.

    The code itself is checked, hashed and audited (``otp.verified`` /
    ``otp.failed``) by :func:`apps.accounts.otp.verify_email_code`; this
    wraps that call with the same ``STEP_UP_SUCCEEDED`` / ``STEP_UP_FAILED``
    bookkeeping :func:`step_up_with_password` keeps, so every step-up method
    reports through the one pair of events.
    """
    # Imported here, not at module scope: `apps.accounts.otp` imports
    # `apps.accounts.emails`, and keeping that edge local avoids tying this
    # module's import order to the model layer for something only two
    # functions need.
    from .otp import OtpPurpose, verify_email_code

    user = request.user
    verified = verify_email_code(
        user=user,
        purpose=OtpPurpose.STEP_UP,
        code=code or "",
        request_ip=client_ip(request),
    )
    if not verified:
        record(
            action=AuditAction.STEP_UP_FAILED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
            result=AuditResult.FAILURE,
            context={"method": "email_code"},
        )
        raise StepUpRequired("That code is not right or has expired.")
    grant(request)
    record(
        action=AuditAction.STEP_UP_SUCCEEDED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
        context={"method": "email_code"},
        durable=False,
    )


def step_up_with_totp(request, code: str) -> None:
    """Verify a TOTP code (ADR-05, Phase 5) against the caller's own
    confirmed device to obtain a fresh step-up. Same shape as
    :func:`step_up_with_email_code`: the code is checked and its replay
    guard updated by :func:`apps.accounts.mfa.verify_totp_code`, and this
    wraps that with the step-up bookkeeping."""
    from .mfa import verify_totp_code

    user = request.user
    verified = verify_totp_code(user=user, code=code or "")
    if not verified:
        record(
            action=AuditAction.STEP_UP_FAILED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
            result=AuditResult.FAILURE,
            context={"method": "totp"},
        )
        raise StepUpRequired("That code is not right.")
    grant(request)
    record(
        action=AuditAction.STEP_UP_SUCCEEDED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
        context={"method": "totp"},
        durable=False,
    )


def step_up_with_recovery(request, code: str) -> None:
    """Burn one recovery code (ADR-05, Phase 5) to obtain a fresh step-up —
    the last resort when the authenticator app and the inbox are both
    unavailable. Single-use, like every other use of a recovery code: this
    consumes it exactly as sign-in verification does."""
    from .mfa import consume_recovery_code

    user = request.user
    verified = consume_recovery_code(user=user, code=code or "")
    if not verified:
        record(
            action=AuditAction.STEP_UP_FAILED,
            actor=user,
            resource_type="user",
            resource_id=user.pk,
            result=AuditResult.FAILURE,
            context={"method": "recovery"},
        )
        raise StepUpRequired("That code is not right.")
    grant(request)
    record(
        action=AuditAction.STEP_UP_SUCCEEDED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
        context={"method": "recovery"},
        durable=False,
    )


_CODE_METHODS = {
    "totp": step_up_with_totp,
    "recovery": step_up_with_recovery,
}


def require_step_up(
    request,
    *,
    password: str | None = None,
    code: str | None = None,
    method: str | None = None,
) -> None:
    """Pass when the session's step-up is fresh; accept a password or a code
    inline (so a dialog can retry the original request with whichever the
    caller supplied) and refuse otherwise. ``method`` selects which kind of
    code — ``"totp"`` or ``"recovery"`` reach a confirmed device via
    :mod:`apps.accounts.mfa`; anything else (including omitted) is the
    Phase 4 emailed one-time code, so an existing caller needs no change."""
    if is_fresh(request):
        return
    if password is not None:
        step_up_with_password(request, password)
        return
    if code is not None:
        _CODE_METHODS.get(method, step_up_with_email_code)(request, code)
        return
    raise StepUpRequired()
