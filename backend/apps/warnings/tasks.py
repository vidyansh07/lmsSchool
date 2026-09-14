"""The weekly digest: every staff member's warnings, in their inbox on Monday.

In-app always; by email when their preferences allow, through the same
channel every other notification uses. Sent once a week (12d, "a weekly
digest rather than daily") because a warning that is still true next week
is worth a second nudge, and one that is true tomorrow is already on the
dashboard.
"""

from __future__ import annotations

from celery import shared_task

from apps.accounts.models import User, UserRole
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify

from . import services

DIGEST_ROLES = (
    UserRole.SUPERADMIN,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.COUNSELLOR,
    UserRole.TRAINER,
)


@shared_task(name="warnings.weekly_digest", ignore_result=True)
def weekly_digest() -> int:
    sent = 0
    for user in User.objects.filter(is_active=True, role__in=DIGEST_ROLES).iterator():
        warnings = services.warnings_for(user)
        if not warnings:
            continue
        errors = sum(1 for w in warnings if w["severity"] == "error")
        title = f"{len(warnings)} things need attention" + (f", {errors} today" if errors else "")
        notify(
            recipient=user,
            kind=NotificationKind.WARNING_DIGEST,
            title=title,
            body=services.digest_text(warnings),
            link_path="/admin/activity"
            if user.role in (UserRole.ADMIN, UserRole.SUPERADMIN)
            else "/",
        )
        sent += 1
    return sent
