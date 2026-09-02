"""Notification services — the one way the product speaks to somebody.

Every feature that needs to tell a person something calls :func:`notify` or
:func:`notify_many`. Nothing constructs a `Notification` directly, and nothing
sends mail directly, so the category rule, the preference check and the delivery
attempt cannot be forgotten by a future caller.

Failure never propagates. A notification is a courtesy attached to something
that already happened; if writing it fails, the grade was still awarded, and
turning that into a 500 would be strictly worse for the person being served.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from .channels import deliver
from .models import Notification, NotificationPreference, category_for

logger = logging.getLogger("grras.notifications")


def notify(
    *,
    recipient,
    kind: str,
    title: str,
    body: str = "",
    link_path: str = "",
    resource_type: str = "",
    resource_id: Any = "",
    send_email: bool = True,
) -> Notification | None:
    """Tell one person one thing.

    Returns the notification, or ``None`` if it could not be written — callers
    are not expected to check, and none of them do.
    """
    if recipient is None or not getattr(recipient, "pk", None):
        return None
    if not getattr(recipient, "is_active", False):
        # A deactivated account is not a person to notify, and mailing one is
        # how a suspended student learns something they should not.
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            kind=kind,
            category=category_for(kind),
            title=title[:200],
            body=body,
            link_path=link_path[:300],
            resource_type=str(resource_type)[:40],
            resource_id=str(resource_id or "")[:64],
        )
    except Exception:
        # Deliberately every exception, not just database errors: this is called
        # from inside grading, issuing and publishing, and none of those should
        # turn into a 500 because a notification could not be written.
        logger.exception("Could not write a notification", extra={"context": {"kind": kind}})
        return None

    if send_email:
        # After the surrounding transaction commits: a notification for work
        # that got rolled back is worse than a late one.
        transaction.on_commit(lambda: deliver(notification))
    return notification


def notify_many(*, recipients, **kwargs) -> int:
    """Tell several people the same thing. Returns how many were written."""
    written = 0
    seen: set = set()
    for recipient in recipients:
        if recipient is None or recipient.pk in seen:
            continue
        seen.add(recipient.pk)
        if notify(recipient=recipient, **kwargs) is not None:
            written += 1
    return written


def mark_read(*, notification: Notification) -> Notification:
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])
    return notification


def mark_all_read(*, user) -> int:
    return Notification.objects.for_user(user).unread().update(read_at=timezone.now())


def preferences_for(user) -> NotificationPreference:
    """The person's settings, created on demand with the defaults."""
    preference, _created = NotificationPreference.objects.get_or_create(user=user)
    return preference


def update_preferences(*, user, **fields) -> NotificationPreference:
    preference = preferences_for(user)
    for key, value in fields.items():
        setattr(preference, key, value)
    preference.save()
    return preference


# ---------------------------------------------------------------------------
# The audience helpers every caller shares
# ---------------------------------------------------------------------------


def students_of_batch(batch):
    """Active students on a batch, as users.

    Used by every fan-out. Written once so that "who is on this batch?" has one
    answer, and a suspended or cancelled student is excluded from all of them.
    """
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    rows = Enrollment.objects.filter(
        batch=batch, status__in=(EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED)
    ).select_related("student__user")
    return [row.student.user for row in rows]


def students_of_course(course):
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    rows = Enrollment.objects.filter(
        course=course, status__in=(EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED)
    ).select_related("student__user")
    return [row.student.user for row in rows]
