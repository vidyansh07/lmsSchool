"""Daily status report access control.

Same shape as `apps.assignments.access`, and for the same reason: a trainer
holds no global DSR capability. Their authority comes from teaching the
batch a report belongs to, resolved per record, so a report id from another
trainer's batch resolves to nothing rather than a 403 that confirms it exists.

Students hold nothing here at all. A status report is staff correspondence
about a class, not a record a student has any standing to read — unlike
attendance, where the register is partly about them.

Reviewing is deliberately its own function rather than a flag on
`can_write_dsr`. Holding `dsr.review` is necessary but not sufficient: a
manager who happens to be the trainer on record for this exact class must
still be refused, because "approved by the person who wrote it" is not a
review.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import DSR, EDITABLE_STATUSES


def visible_dsrs(user) -> QuerySet[DSR]:
    """Every report the caller may see, as a queryset."""
    base = DSR.objects.with_related()

    if has_capability(user, Capability.DSR_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        # The batches this trainer teaches now, not only the reports they
        # personally wrote — a trainer taking over a batch mid-course should
        # be able to read what their predecessor recorded.
        return base.filter(session__batch__trainer=trainer)

    # Students hold no view onto DSRs at all.
    return base.none()


def can_write_dsr(user, dsr: DSR) -> bool:
    """Create or edit the content of one report.

    The trainer who wrote it, while it is still theirs to change, or the
    holder of the override capability at any time (a manager correcting a
    typo after the fact does not need the report un-approved first).
    """
    if has_capability(user, Capability.DSR_MANAGE_ANY):
        return True

    trainer = batch_access.trainer_profile(user)
    if trainer is None or dsr.trainer_id != trainer.pk:
        return False
    return dsr.status in EDITABLE_STATUSES


def can_start_dsr(user, session) -> bool:
    """May the caller write the *first* report for this class?

    There is no `DSR` row yet to resolve a trainer from, so this mirrors
    `apps.sessions.access.can_take_attendance`: the batch's current trainer,
    or the one frozen onto the session at generation time, so a mid-course
    reassignment does not orphan a class nobody can report on.
    """
    if has_capability(user, Capability.DSR_MANAGE_ANY):
        return True

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False
    return trainer.pk in {session.trainer_id, session.batch.trainer_id}


def can_review_dsr(user, dsr: DSR) -> bool:
    """Approve, reject or send back one report.

    `dsr.review` is a capability, not a relationship, so it says nothing about
    *which* reports — a holder still cannot rule on their own.
    """
    if not has_capability(user, Capability.DSR_REVIEW):
        return False

    trainer = batch_access.trainer_profile(user)
    return trainer is None or trainer.pk != dsr.trainer_id
