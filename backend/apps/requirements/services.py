"""Raising, answering and closing a trainer requirement."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import resolve_branch_for_new_record
from apps.announcements.services import teaching_staff_of
from apps.audit.services import AuditAction, record
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError, ConflictError
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify_many

from .models import RequirementReply, RequirementStatus, TrainerRequirement

LINK = "/requirements"


def _link(requirement: TrainerRequirement) -> str:
    return f"{LINK}?open={requirement.pk}"


@transaction.atomic
def raise_requirement(
    *,
    actor: User,
    title: str,
    details: str = "",
    batch=None,
    needed_by=None,
) -> TrainerRequirement:
    """Ask the teaching staff of a centre for something, and tell them."""
    if needed_by is not None and needed_by < timezone.localdate():
        raise ApplicationError({"needed_by": ["That date has already passed."]})

    branch = resolve_branch_for_new_record(
        actor=actor, branch=batch.branch if batch is not None else None
    )
    requirement = TrainerRequirement.objects.create(
        branch=branch,
        raised_by=actor,
        title=title.strip(),
        details=details.strip(),
        batch=batch,
        needed_by=needed_by,
    )

    told = notify_many(
        recipients=teaching_staff_of(branch.pk).exclude(pk=actor.pk),
        kind=NotificationKind.REQUIREMENT_RAISED,
        title=f"Requirement: {requirement.title}"[:200],
        body=requirement.details[:500],
        link_path=_link(requirement),
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
    )
    record(
        action=AuditAction.REQUIREMENT_RAISED,
        actor=actor,
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
        context={
            "title": requirement.title,
            "batch": requirement.batch.code if requirement.batch_id else "",
            "needed_by": needed_by.isoformat() if needed_by else "",
            "notified": told,
        },
    )
    return requirement


@transaction.atomic
def reply_to_requirement(
    *, requirement: TrainerRequirement, actor: User, message: str
) -> RequirementReply:
    """Answer on an open requirement. The raiser hears about a trainer's reply;
    the trainers who already answered hear about the raiser's."""
    if not requirement.is_open:
        raise ConflictError({"requirement": ["This requirement is closed."]})

    reply = RequirementReply.objects.create(
        requirement=requirement, author=actor, message=message.strip()
    )

    if actor.pk == requirement.raised_by_id:
        others = User.objects.filter(
            pk__in=requirement.replies.exclude(author=actor).values("author_id")
        )
    else:
        others = [requirement.raised_by]
    notify_many(
        recipients=others,
        kind=NotificationKind.REQUIREMENT_REPLIED,
        title=f"{actor.get_full_name()} replied on: {requirement.title}"[:200],
        body=reply.message[:500],
        link_path=_link(requirement),
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
    )
    record(
        action=AuditAction.REQUIREMENT_REPLIED,
        actor=actor,
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
        context={"title": requirement.title, "message": reply.message[:200]},
    )
    return reply


@transaction.atomic
def close_requirement(
    *,
    requirement: TrainerRequirement,
    actor: User,
    fulfilled_by=None,
    note: str = "",
) -> TrainerRequirement:
    """Settle it: fulfilled by a named trainer, or closed without one."""
    if not requirement.is_open:
        raise ConflictError({"requirement": ["This requirement is already closed."]})

    requirement.status = (
        RequirementStatus.FULFILLED if fulfilled_by is not None else RequirementStatus.CLOSED
    )
    requirement.fulfilled_by = fulfilled_by
    requirement.closed_at = timezone.now()
    requirement.closed_by = actor
    requirement.closing_note = note.strip()
    requirement.save(
        update_fields=[
            "status",
            "fulfilled_by",
            "closed_at",
            "closed_by",
            "closing_note",
            "updated_at",
        ]
    )

    who = list(User.objects.filter(pk__in=requirement.replies.values("author_id")))
    if fulfilled_by is not None:
        who.append(fulfilled_by.user)
    if requirement.raised_by_id != actor.pk:
        who.append(requirement.raised_by)
    outcome = (
        f"Fulfilled by {fulfilled_by.user.get_full_name()}"
        if fulfilled_by is not None
        else "Closed"
    )
    notify_many(
        recipients=[person for person in who if person.pk != actor.pk],
        kind=NotificationKind.REQUIREMENT_REPLIED,
        title=f"{outcome}: {requirement.title}"[:200],
        body=requirement.closing_note[:500],
        link_path=_link(requirement),
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
    )
    record(
        action=AuditAction.REQUIREMENT_CLOSED,
        actor=actor,
        resource_type="trainer_requirement",
        resource_id=requirement.pk,
        context={
            "title": requirement.title,
            "status": requirement.status,
            "fulfilled_by": fulfilled_by.trainer_id if fulfilled_by is not None else "",
            "note": requirement.closing_note,
        },
    )
    return requirement


def delete_requirement(*, requirement: TrainerRequirement, actor: User, reason: str) -> None:
    soft_delete(instance=requirement, actor=actor, reason=reason)


__all__ = [
    "close_requirement",
    "delete_requirement",
    "raise_requirement",
    "reply_to_requirement",
]
