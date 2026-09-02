"""Announcement services.

Publishing is the interesting step: it flips the status *and* fans out
notifications. Both happen in one transaction, and the fan-out is deliberately
one notification per person rather than a shared row — a person marking an
announcement read must not mark it read for the whole batch.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify_many, students_of_batch, students_of_course

from .models import Announcement, AnnouncementStatus, Audience


@transaction.atomic
def create_announcement(*, actor: User, recipients=None, **fields: Any) -> Announcement:
    """Create in draft. Publishing is a separate, deliberate act."""
    fields.pop("status", None)
    announcement = Announcement(
        created_by=actor if getattr(actor, "pk", None) else None,
        status=AnnouncementStatus.DRAFT,
        **fields,
    )
    _validate(announcement)
    announcement.save()

    if announcement.audience == Audience.SELECTED and recipients:
        announcement.recipients.set(recipients)

    record(
        action=AuditAction.ANNOUNCEMENT_CREATED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={"title": announcement.title, "audience": announcement.audience},
        durable=False,
    )
    return announcement


@transaction.atomic
def update_announcement(
    *, announcement: Announcement, actor: User, recipients=None, **fields: Any
) -> Announcement:
    """Edit. The audience is fixed once published — see :func:`publish`."""
    fields.pop("status", None)
    if announcement.status == AnnouncementStatus.PUBLISHED:
        locked = {"audience", "course", "batch"}
        blocked = sorted(locked & set(fields))
        if blocked:
            raise ConflictError(
                {
                    field: ["The audience cannot change once it has been published."]
                    for field in blocked
                }
            )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(announcement, field) != value:
            setattr(announcement, field, value)
            changed.append(field)

    if recipients is not None and announcement.audience == Audience.SELECTED:
        announcement.recipients.set(recipients)
        changed.append("recipients")

    if not changed:
        return announcement

    _validate(announcement)
    announcement.save()

    record(
        action=AuditAction.ANNOUNCEMENT_UPDATED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={"title": announcement.title, "fields": sorted(set(changed))},
        durable=False,
    )
    return announcement


def audience_for(announcement: Announcement) -> list:
    """Who this announcement is for, right now.

    Resolved at publication rather than stored, so it reflects the roster as it
    stands. A student who joins the batch tomorrow sees the notice on the board;
    they do not retroactively receive yesterday's notification, which is the
    honest distinction between a noticeboard and a message.
    """
    if announcement.audience == Audience.EVERYONE:
        from apps.accounts.models import User as UserModel

        return list(UserModel.objects.filter(is_active=True))
    if announcement.audience == Audience.BATCH and announcement.batch_id:
        return students_of_batch(announcement.batch)
    if announcement.audience == Audience.COURSE and announcement.course_id:
        return students_of_course(announcement.course)
    if announcement.audience == Audience.SELECTED:
        return list(announcement.recipients.filter(is_active=True))
    return []


@transaction.atomic
def publish(*, announcement: Announcement, actor: User) -> Announcement:
    """Put it on the noticeboard, and tell the people it is for."""
    if announcement.status == AnnouncementStatus.PUBLISHED:
        raise ConflictError({"announcement": ["This announcement is already published."]})
    if announcement.status == AnnouncementStatus.ARCHIVED:
        raise ConflictError({"announcement": ["An archived announcement cannot be published."]})

    announcement.status = AnnouncementStatus.PUBLISHED
    announcement.published_at = timezone.now()
    announcement.save(update_fields=["status", "published_at", "updated_at"])

    told = notify_many(
        recipients=audience_for(announcement),
        kind=NotificationKind.ANNOUNCEMENT,
        title=announcement.title,
        body=announcement.body[:500],
        link_path="/announcements",
        resource_type="announcement",
        resource_id=announcement.pk,
    )

    record(
        action=AuditAction.ANNOUNCEMENT_PUBLISHED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={
            "title": announcement.title,
            "audience": announcement.audience,
            "notified": told,
        },
        durable=False,
    )
    return announcement


@transaction.atomic
def archive(*, announcement: Announcement, actor: User) -> Announcement:
    """Take it off the board. The notifications it produced stay."""
    announcement.status = AnnouncementStatus.ARCHIVED
    announcement.save(update_fields=["status", "updated_at"])
    record(
        action=AuditAction.ANNOUNCEMENT_ARCHIVED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={"title": announcement.title},
        durable=False,
    )
    return announcement


def _validate(announcement: Announcement) -> None:
    errors: dict[str, list[str]] = {}
    if announcement.audience == Audience.COURSE and not announcement.course_id:
        errors["course"] = ["Choose the course this is for."]
    if announcement.audience == Audience.BATCH and not announcement.batch_id:
        errors["batch"] = ["Choose the batch this is for."]
    if announcement.audience in (Audience.EVERYONE, Audience.SELECTED) and (
        announcement.course_id or announcement.batch_id
    ):
        errors["audience"] = ["This audience does not take a course or a batch."]
    if errors:
        raise ApplicationError(errors)

    try:
        announcement.full_clean(exclude=["created_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
