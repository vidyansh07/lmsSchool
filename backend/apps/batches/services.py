"""Batch and schedule services.

Business rules live here, so they hold for the API, the admin, the seeder and
any future task.

Two rules carry the weight:

* **Status transitions are a table.** An unreachable transition is refused by
  ``TRANSITIONS`` rather than by whichever view remembered to check.
* **Conflicts are checked before every write.** A schedule that would double-book
  a trainer or a batch is rejected with the clash named, never silently saved.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError
from apps.common.identifiers import next_batch_code

from .conflicts import find_conflicts, trainer_conflicts_for_batch
from .models import Batch, BatchSchedule, BatchStatus

#: Allowed status transitions. Anything absent is refused.
#:
#: A cancelled batch is terminal: re-running it means creating a new batch, so
#: the cancelled one keeps its history and nobody's access silently returns.
TRANSITIONS: dict[str, frozenset[str]] = {
    BatchStatus.UPCOMING: frozenset({BatchStatus.ACTIVE, BatchStatus.CANCELLED}),
    BatchStatus.ACTIVE: frozenset({BatchStatus.COMPLETED, BatchStatus.CANCELLED}),
    BatchStatus.COMPLETED: frozenset({BatchStatus.ARCHIVED}),
    BatchStatus.CANCELLED: frozenset({BatchStatus.ARCHIVED}),
    BatchStatus.ARCHIVED: frozenset(),
}


class ScheduleConflictError(ApplicationError):
    """A schedule would double-book a trainer or a batch."""

    status_code = 409
    default_detail = "This class clashes with an existing one."
    default_code = "schedule_conflict"


class TransitionError(ApplicationError):
    default_detail = "That status change is not allowed."
    default_code = "invalid_transition"


def _apply(instance, fields: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for name, value in fields.items():
        if getattr(instance, name) != value:
            setattr(instance, name, value)
            changed.append(name)
    return changed


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------


@transaction.atomic
def create_batch(*, actor: User, **fields: Any) -> Batch:
    batch = Batch(code=next_batch_code(), created_by=actor, **fields)
    batch.full_clean(exclude=["code"])
    batch.save()

    # A batch created with a trainer already has a first stint. Recording it
    # here means the history is complete from the start, rather than beginning
    # only at the first *re*-assignment.
    if batch.trainer_id:
        from apps.sessions.services import record_trainer_assignment

        record_trainer_assignment(
            batch=batch, trainer=batch.trainer, actor=actor, note="Initial assignment."
        )

    record(
        action=AuditAction.BATCH_CREATED,
        actor=actor,
        resource_type="batch",
        resource_id=batch.pk,
        context={
            "code": batch.code,
            "name": batch.name,
            "course": batch.course.code,
            "capacity": batch.capacity,
            "trainer": str(batch.trainer_id) if batch.trainer_id else None,
        },
    )
    return batch


@transaction.atomic
def update_batch(*, batch: Batch, actor: User, **fields: Any) -> Batch:
    """Edit a batch.

    Reducing capacity below the number of seats already taken is refused: the
    alternative is a roster the batch cannot legally hold, and quietly evicting
    students is never the right default.
    """
    if "capacity" in fields:
        taken = batch.seats_taken()
        if fields["capacity"] < taken:
            raise ApplicationError(
                {
                    "capacity": [
                        f"{taken} student(s) already hold a seat. "
                        "Remove students before reducing the capacity below that."
                    ]
                }
            )

    changed = _apply(batch, fields)
    if not changed:
        return batch

    batch.full_clean(exclude=["code"])
    batch.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.BATCH_UPDATED,
        actor=actor,
        resource_type="batch",
        resource_id=batch.pk,
        context={"code": batch.code, "changed_fields": sorted(changed)},
    )
    return batch


@transaction.atomic
def assign_trainer(*, batch: Batch, trainer, actor: User) -> Batch:
    """Put a trainer on a batch, refusing timetable clashes.

    Checked here rather than on the next schedule edit, so the refusal names the
    class the trainer is already teaching.
    """
    if trainer is not None:
        if not trainer.user.is_active:
            raise ApplicationError({"trainer": ["That trainer's account is not active."]})

        clashes = trainer_conflicts_for_batch(batch, trainer)
        if clashes:
            raise ScheduleConflictError(
                {
                    "trainer": [conflict.detail for conflict in clashes],
                }
            )

    previous = batch.trainer_id
    batch.trainer = trainer
    batch.full_clean(exclude=["code"])
    batch.save(update_fields=["trainer", "updated_at"])

    # Written by the same action, so a reassignment cannot happen without the
    # history row that a trainer-activity report later depends on.
    from apps.sessions.services import record_trainer_assignment

    record_trainer_assignment(batch=batch, trainer=trainer, actor=actor)

    record(
        action=AuditAction.BATCH_TRAINER_ASSIGNED,
        actor=actor,
        resource_type="batch",
        resource_id=batch.pk,
        context={
            "code": batch.code,
            "from": str(previous) if previous else None,
            "to": str(trainer.pk) if trainer else None,
            "trainer_code": trainer.trainer_id if trainer else None,
        },
    )
    return batch


@transaction.atomic
def set_batch_status(*, batch: Batch, target: str, actor: User, note: str = "") -> Batch:
    """Move a batch through its lifecycle.

    Cancelling cascades: every live enrolment is cancelled too, because access
    is derived from the batch and leaving enrolments "active" on a cancelled
    batch would be a contradiction waiting to be read the wrong way.
    """
    if batch.status == target:
        raise TransitionError(f"The batch is already {target}.")
    if target not in TRANSITIONS.get(batch.status, frozenset()):
        allowed = ", ".join(sorted(TRANSITIONS.get(batch.status, []))) or "nothing"
        raise TransitionError(
            f"A {batch.status} batch cannot move to {target}. "
            f"Allowed from {batch.status}: {allowed}."
        )

    if target == BatchStatus.ACTIVE and batch.trainer_id is None:
        raise ApplicationError({"status": ["Assign a trainer before activating the batch."]})

    previous = batch.status
    batch.status = target
    batch.save(update_fields=["status", "updated_at"])

    record(
        action=AuditAction.BATCH_STATUS_CHANGED,
        actor=actor,
        resource_type="batch",
        resource_id=batch.pk,
        context={"code": batch.code, "from": previous, "to": target, "note": note},
    )

    if target == BatchStatus.CANCELLED:
        from apps.enrollments.services import cancel_enrollments_for_batch

        cancel_enrollments_for_batch(
            batch=batch, actor=actor, reason=note or "The batch was cancelled."
        )
    elif target == BatchStatus.COMPLETED:
        from apps.enrollments.services import complete_enrollments_for_batch

        complete_enrollments_for_batch(batch=batch, actor=actor)

    return batch


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def _guard_conflicts(schedule: BatchSchedule, batch: Batch) -> None:
    clashes = find_conflicts(schedule, batch=batch)
    if clashes:
        raise ScheduleConflictError(
            {
                "schedule": [conflict.detail for conflict in clashes],
                "conflicts": [conflict.as_dict() for conflict in clashes],
            }
        )


@transaction.atomic
def create_schedule(*, batch: Batch, actor: User, **fields: Any) -> BatchSchedule:
    schedule = BatchSchedule(batch=batch, **fields)
    schedule.full_clean()
    _guard_conflicts(schedule, batch)
    schedule.save()

    record(
        action=AuditAction.SCHEDULE_CREATED,
        actor=actor,
        resource_type="batch_schedule",
        resource_id=schedule.pk,
        context={
            "batch_code": batch.code,
            "weekday": schedule.weekday,
            "start": schedule.start_time.isoformat(),
            "end": schedule.end_time.isoformat(),
            "timezone": schedule.timezone_name,
        },
    )
    return schedule


@transaction.atomic
def update_schedule(*, schedule: BatchSchedule, actor: User, **fields: Any) -> BatchSchedule:
    changed = _apply(schedule, fields)
    if not changed:
        return schedule

    schedule.full_clean()
    _guard_conflicts(schedule, schedule.batch)
    schedule.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.SCHEDULE_UPDATED,
        actor=actor,
        resource_type="batch_schedule",
        resource_id=schedule.pk,
        context={"batch_code": schedule.batch.code, "changed_fields": sorted(changed)},
    )
    return schedule


@transaction.atomic
def delete_schedule(*, schedule: BatchSchedule, actor: User) -> None:
    batch_code, schedule_id = schedule.batch.code, schedule.pk
    weekday, start = schedule.weekday, schedule.start_time.isoformat()
    schedule.delete()

    record(
        action=AuditAction.SCHEDULE_DELETED,
        actor=actor,
        resource_type="batch_schedule",
        resource_id=schedule_id,
        context={"batch_code": batch_code, "weekday": weekday, "start": start},
    )
