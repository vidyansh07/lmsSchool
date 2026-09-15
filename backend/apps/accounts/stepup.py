"""Step-up authentication: proving it is still you before a dangerous act.

A signed-in session is enough for ordinary work. Locking a permission,
destroying a record, disabling somebody's second factor — those ask the
person to re-enter their password (Phase 2) or a second factor (Phase 5)
within the last few minutes. The proof is a timestamp in the session; the
API refuses with ``403 step_up_required`` when it is missing or stale, and
the interface opens the step-up dialog in place and retries once.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.audit.services import AuditAction, AuditResult, record

SESSION_KEY = "step_up_at"
#: Until the policy engine (Phase 3) makes it configurable.
FRESH_FOR_MINUTES = 10


class StepUpRequired(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Confirm it is you before doing this."
    default_code = "step_up_required"


def is_fresh(request) -> bool:
    stamp = request.session.get(SESSION_KEY)
    if not stamp:
        return False
    return (timezone.now().timestamp() - float(stamp)) < FRESH_FOR_MINUTES * 60


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


def require_step_up(request, *, password: str | None = None) -> None:
    """Pass when the session's step-up is fresh; accept a password inline
    (so a dialog can retry the original request with it); refuse otherwise."""
    if is_fresh(request):
        return
    if password is not None:
        step_up_with_password(request, password)
        return
    raise StepUpRequired()
