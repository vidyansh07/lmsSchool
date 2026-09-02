"""Class session access.

Sessions inherit their visibility from the batch — the same rule Phase 3
established, so there is one answer to "whose batch is this?" rather than two
that can drift.

The one addition is *taking a register*, which is narrower than managing a
batch: the trainer who teaches a class marks its attendance, and an
administrator or manager may correct it. §4.2 requires that a trainer cannot
touch attendance for an unrelated batch, and this is where that is decided.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import ClassSession


def visible_sessions(user) -> QuerySet[ClassSession]:
    """Every class the caller may see, as a queryset.

    Derived from `batch_access.visible_batches`, so a student sees the classes
    of batches they are enrolled on, a trainer sees the ones they teach, and an
    administrator sees everything — with no second copy of the rule.
    """
    return ClassSession.objects.with_related().filter(batch__in=batch_access.visible_batches(user))


def can_manage_session(user, session: ClassSession) -> bool:
    """Create, edit, cancel or reschedule a class.

    Administrators and managers, plus the trainer who teaches the batch — a
    trainer must be able to cancel their own class and record what they covered.
    """
    if has_capability(user, Capability.BATCH_MANAGE_SCHEDULE):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and session.batch.trainer_id == trainer.pk


def can_take_attendance(user, session: ClassSession) -> bool:
    """Mark or correct the register for this class.

    Deliberately *not* "any trainer": the trainer must be the one assigned to
    this batch. A trainer holding a session id for somebody else's class gets
    nothing.
    """
    if has_capability(user, Capability.ATTENDANCE_CORRECT_ANY):
        return True
    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False
    # The batch's current trainer, or the one who was frozen onto this session
    # when it was generated — a reassignment must not orphan an unmarked class.
    return trainer.pk in {session.batch.trainer_id, session.trainer_id}


def manageable_sessions(user) -> QuerySet[ClassSession]:
    base = ClassSession.objects.with_related()
    if has_capability(user, Capability.BATCH_MANAGE_SCHEDULE):
        return base
    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()
    return base.filter(batch__trainer=trainer)
