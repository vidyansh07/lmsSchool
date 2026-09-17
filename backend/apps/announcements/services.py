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
        locked = {"audience", "course", "batch", "role", "branch"}
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
        # A batch belongs to one centre, so its roster is already one centre's.
        return students_of_batch(announcement.batch)
    if announcement.audience == Audience.COURSE and announcement.course_id:
        # The course catalogue is institution-wide and its students therefore
        # are too, while a notice about one centre's sitting of it is not.
        # Telling everybody would hand the other centres by notification
        # precisely what `visible_announcements` keeps off their board — the
        # delivery half and the reading half of one rule, disagreeing.
        from .access import announcement_branch_id

        branch_id = announcement_branch_id(announcement)
        told = students_of_course(announcement.course)
        if branch_id is None:
            return told
        return [person for person in told if person.branch_id == branch_id]
    if announcement.audience == Audience.SELECTED:
        return list(announcement.recipients.filter(is_active=True))
    if announcement.audience == Audience.TRAINERS:
        from .access import announcement_branch_id

        return list(teaching_staff_of(announcement_branch_id(announcement)))
    if announcement.audience == Audience.ROLE and announcement.role_id:
        from .access import announcement_branch_id

        return list(role_holders_of(announcement.role, announcement_branch_id(announcement)))
    if announcement.audience == Audience.BRANCH and announcement.branch_id:
        from apps.accounts.models import User as UserModel

        return list(UserModel.objects.filter(is_active=True, branch_id=announcement.branch_id))
    return []


def role_holders_of(role, branch_id):
    """Everyone whose base role *kind* matches `role` (ERP Phase 19) — the
    generalisation of :func:`teaching_staff_of` to any role, not only
    trainer. Matched on `User.role` (the kind every account's authoritative
    role field always carries, custom role or not — see
    `apps.accounts.roles`'s own note that a custom role "adjusts the set,
    never the kind"), not on the exact `Role` row, so a custom role built on
    top of a kind is still reached. ``None`` means every centre."""
    from apps.accounts.models import User as UserModel

    people = UserModel.objects.filter(is_active=True, role=role.kind)
    if branch_id is not None:
        people = people.filter(branch_id=branch_id)
    return people


def teaching_staff_of(branch_id):
    """Everyone who teaches at a centre: trainer accounts, and the managers who
    hold a teaching profile (D-130). ``None`` means every centre."""
    from django.db.models import Q

    from apps.accounts.models import User as UserModel
    from apps.accounts.models import UserRole

    people = UserModel.objects.filter(is_active=True).filter(
        Q(role=UserRole.TRAINER) | Q(trainer_profile__isnull=False)
    )
    if branch_id is not None:
        people = people.filter(branch_id=branch_id)
    return people.distinct()


@transaction.atomic
def publish(*, announcement: Announcement, actor: User | None) -> Announcement:
    """Put it on the noticeboard, and tell the people it is for.

    `actor` is `None` for the one system-driven caller —
    `apps.announcements.tasks.publish_due` — the same "system, not nobody"
    shape `apps.work`'s own overdue/missed transitions already use for a
    beat-triggered state change; `apps.audit.services.record` accepts it.
    A draft published by a human and a scheduled one published by the beat
    task go through this exact same function, so the fan-out and the audit
    trail never drift between the two paths.
    """
    if announcement.status == AnnouncementStatus.PUBLISHED:
        raise ConflictError({"announcement": ["This announcement is already published."]})
    if announcement.status == AnnouncementStatus.ARCHIVED:
        raise ConflictError({"announcement": ["An archived announcement cannot be published."]})
    if announcement.status == AnnouncementStatus.CANCELLED:
        raise ConflictError(
            {"announcement": ["A cancelled announcement cannot be published; schedule it again."]}
        )

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


@transaction.atomic
def delete_announcement(*, announcement: Announcement, actor: User, reason: str) -> None:
    """Remove it from the board, reversibly (Phase 7).

    A genuine removal, not the ``archive`` lifecycle transition above: this is
    for a notice that should not have been published at all, and it goes
    through the same recycle bin as every other soft-deletable model rather
    than a bespoke "hidden" status.
    """
    from apps.common.deletion import soft_delete

    soft_delete(instance=announcement, actor=actor, reason=reason)


#: Which target field each audience requires. Mirrors
#: `announcement_audience_matches_target`'s own per-audience shape exactly,
#: so the service and the database constraint can never quietly drift apart
#: — including that constraint's own asymmetry: a `course`-audience notice
#: has never forbidden also naming a `batch` there for reference, and a
#: `batch`-audience one has never forbidden naming its `course`. That
#: looseness predates this phase (see the constraint's own `course`/`batch`
#: clauses, neither of which mentions the other field) and is preserved
#: here rather than tightened as a side effect of adding `role`/`branch`.
_AUDIENCE_TARGET_FIELD: dict[str, str] = {
    Audience.COURSE: "course",
    Audience.BATCH: "batch",
    Audience.ROLE: "role",
    Audience.BRANCH: "branch",
}
_ALSO_PERMITTED: dict[str, frozenset[str]] = {
    Audience.COURSE: frozenset({"batch"}),
    Audience.BATCH: frozenset({"course"}),
}


def _validate(announcement: Announcement) -> None:
    errors: dict[str, list[str]] = {}
    required = _AUDIENCE_TARGET_FIELD.get(announcement.audience)
    also_permitted = _ALSO_PERMITTED.get(announcement.audience, frozenset())
    for field in ("course", "batch", "role", "branch"):
        value = getattr(announcement, f"{field}_id")
        if field == required:
            if not value:
                errors[field] = [f"Choose the {field} this is for."]
        elif field in also_permitted:
            continue
        elif value:
            errors[field] = [f"This audience does not take a {field}."]
    if errors:
        raise ApplicationError(errors)

    try:
        announcement.full_clean(exclude=["created_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


@transaction.atomic
def schedule(*, announcement: Announcement, actor: User, publish_at) -> Announcement:
    """Draft → scheduled. `apps.announcements.tasks.publish_due` is what
    actually publishes it once `publish_at` has passed."""
    if announcement.status != AnnouncementStatus.DRAFT:
        raise ConflictError({"announcement": ["Only a draft announcement can be scheduled."]})
    if publish_at is None:
        raise ApplicationError(
            {"publish_at": ["publish_at is required to schedule an announcement."]}
        )
    if publish_at <= timezone.now():
        raise ApplicationError({"publish_at": ["publish_at must be in the future."]})

    announcement.status = AnnouncementStatus.SCHEDULED
    announcement.publish_at = publish_at
    announcement.save(update_fields=["status", "publish_at", "updated_at"])
    record(
        action=AuditAction.ANNOUNCEMENT_SCHEDULED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={"title": announcement.title, "publish_at": publish_at.isoformat()},
        durable=False,
    )
    return announcement


@transaction.atomic
def cancel_scheduled(*, announcement: Announcement, actor: User) -> Announcement:
    """Scheduled → cancelled. A cancelled announcement is not a draft again —
    scheduling a fresh attempt starts from an explicit new `schedule` call,
    same as `archive` never quietly reopens a notice as a draft."""
    if announcement.status != AnnouncementStatus.SCHEDULED:
        raise ConflictError({"announcement": ["Only a scheduled announcement can be cancelled."]})

    announcement.status = AnnouncementStatus.CANCELLED
    announcement.save(update_fields=["status", "updated_at"])
    record(
        action=AuditAction.ANNOUNCEMENT_CANCELLED,
        actor=actor,
        resource_type="announcement",
        resource_id=announcement.pk,
        context={"title": announcement.title},
        durable=False,
    )
    return announcement
