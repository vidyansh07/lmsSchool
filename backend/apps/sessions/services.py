"""Class session services.

Generation is the interesting part. Everything else is a small state machine.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.batches.models import Batch, BatchStatus
from apps.common.exceptions import ApplicationError

from .models import ClassSession, SessionStatus, TopicStatus, TrainerAssignmentHistory

#: How far ahead sessions may be generated in one call. Bounded because a
#: mistyped date should not create ten thousand rows.
MAX_GENERATION_DAYS = 366


class SessionTransitionError(ApplicationError):
    default_detail = "That status change is not allowed."
    default_code = "invalid_transition"


#: Allowed status transitions.
TRANSITIONS: dict[str, frozenset[str]] = {
    SessionStatus.SCHEDULED: frozenset(
        {
            SessionStatus.IN_PROGRESS,
            SessionStatus.COMPLETED,
            SessionStatus.CANCELLED,
            SessionStatus.RESCHEDULED,
        }
    ),
    SessionStatus.IN_PROGRESS: frozenset({SessionStatus.COMPLETED, SessionStatus.CANCELLED}),
    # Terminal: a class that happened, happened. Correcting a mistake means
    # correcting the attendance, not un-completing the class.
    SessionStatus.COMPLETED: frozenset(),
    SessionStatus.CANCELLED: frozenset({SessionStatus.SCHEDULED}),
    SessionStatus.RESCHEDULED: frozenset(),
}


def _dates_between(start: date, end: date, weekday: int):
    offset = (weekday - start.weekday()) % 7
    current = start + timedelta(days=offset)
    while current <= end:
        yield current
        current += timedelta(days=7)


@transaction.atomic
def generate_sessions(
    *, batch: Batch, actor: User, start: date | None = None, end: date | None = None
) -> dict[str, Any]:
    """Materialise classes from a batch's weekly schedule.

    Idempotent: a unique constraint on `(batch, date, start_time)` means
    re-running skips what already exists rather than duplicating it. That
    matters because this is the kind of command an operator runs twice.

    Existing sessions are never rewritten. If a schedule changes, past classes
    keep the time they were actually taught at — the schedule is the rule going
    forward, not a description of history.
    """
    if batch.status == BatchStatus.CANCELLED:
        raise ApplicationError({"batch": ["A cancelled batch has no classes to generate."]})

    window_start = max(start or batch.start_date, batch.start_date)
    window_end = min(end or batch.end_date, batch.end_date)
    if window_start > window_end:
        raise ApplicationError({"start": ["The window falls outside the batch's dates."]})
    if (window_end - window_start).days > MAX_GENERATION_DAYS:
        raise ApplicationError({"end": [f"Generate at most {MAX_GENERATION_DAYS} days at a time."]})

    schedules = list(batch.schedules.filter(is_active=True).select_related("trainer"))
    if not schedules:
        raise ApplicationError({"batch": ["This batch has no active classes in its timetable."]})

    # §8.1's academic calendar, applied: a term break must not silently produce
    # thirty classes nobody attends and thirty empty registers to explain later.
    from apps.academics.models import holiday_dates

    holidays = holiday_dates(window_start, window_end)

    created = 0
    skipped = 0
    on_holiday = 0

    for schedule in schedules:
        # The trainer is frozen per session at generation time, so reassigning
        # the batch later does not claim the new trainer taught old classes.
        trainer = schedule.trainer or batch.trainer

        for day in _dates_between(window_start, window_end, schedule.weekday):
            if day in holidays:
                on_holiday += 1
                continue
            session = ClassSession(
                batch=batch,
                schedule=schedule,
                session_date=day,
                start_time=schedule.start_time,
                end_time=schedule.end_time,
                timezone_name=schedule.timezone_name,
                trainer=trainer,
                location=schedule.location,
                created_by=actor,
            )
            try:
                with transaction.atomic():
                    session.save()
                created += 1
            except IntegrityError:
                # Already generated. Expected on a re-run.
                skipped += 1

    record(
        action=AuditAction.SESSIONS_GENERATED,
        actor=actor,
        resource_type="batch",
        resource_id=batch.pk,
        context={
            "batch_code": batch.code,
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "created": created,
            "skipped": skipped,
        },
    )
    return {
        "created": created,
        "skipped": skipped,
        "on_holiday": on_holiday,
        "from": window_start,
        "to": window_end,
    }


@transaction.atomic
def create_session(*, batch: Batch, actor: User, **fields: Any) -> ClassSession:
    """Add a one-off class outside the weekly pattern."""
    session = ClassSession(
        batch=batch,
        trainer=fields.pop("trainer", None) or batch.trainer,
        created_by=actor,
        **fields,
    )
    session.full_clean()
    try:
        session.save()
    except IntegrityError as exc:
        raise ApplicationError(
            {"session_date": ["A class already exists for that date and time."]}
        ) from exc

    record(
        action=AuditAction.SESSION_CREATED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": batch.code,
            "date": session.session_date.isoformat(),
            "start": session.start_time.isoformat(),
        },
    )
    return session


@transaction.atomic
def update_session(*, session: ClassSession, actor: User, **fields: Any) -> ClassSession:
    changed: list[str] = []
    for name, value in fields.items():
        if getattr(session, name) != value:
            setattr(session, name, value)
            changed.append(name)
    if not changed:
        return session

    session.full_clean()
    session.save(update_fields=[*changed, "updated_at"])
    record(
        action=AuditAction.SESSION_UPDATED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={"batch_code": session.batch.code, "changed_fields": sorted(changed)},
    )
    return session


@transaction.atomic
def set_session_status(
    *, session: ClassSession, target: str, actor: User, reason: str = ""
) -> ClassSession:
    if session.status == target:
        raise SessionTransitionError(f"The class is already {target}.")
    if target not in TRANSITIONS.get(session.status, frozenset()):
        allowed = ", ".join(sorted(TRANSITIONS.get(session.status, []))) or "nothing"
        raise SessionTransitionError(
            f"A {session.status} class cannot move to {target}. Allowed: {allowed}."
        )

    previous = session.status
    session.status = target
    fields = ["status", "updated_at"]
    if target == SessionStatus.CANCELLED:
        session.cancellation_reason = reason
        fields.append("cancellation_reason")
    session.save(update_fields=fields)

    record(
        action=AuditAction.SESSION_STATUS_CHANGED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": session.batch.code,
            "date": session.session_date.isoformat(),
            "from": previous,
            "to": target,
            "reason": reason,
        },
    )
    return session


@transaction.atomic
def reschedule_session(
    *,
    session: ClassSession,
    actor: User,
    new_date: date,
    new_start,
    new_end,
    reason: str = "",
) -> ClassSession:
    """Move a class to a new slot, keeping the original as a record.

    The original is marked ``RESCHEDULED`` rather than edited, so a register
    already taken against it stays attached to the class it describes, and the
    change is visible rather than silent.
    """
    if session.status not in (SessionStatus.SCHEDULED,):
        raise SessionTransitionError("Only a scheduled class can be rescheduled.")

    replacement = ClassSession(
        batch=session.batch,
        schedule=session.schedule,
        session_date=new_date,
        start_time=new_start,
        end_time=new_end,
        timezone_name=session.timezone_name,
        trainer=session.trainer,
        topic=session.topic,
        location=session.location,
        created_by=actor,
    )
    replacement.full_clean()
    try:
        replacement.save()
    except IntegrityError as exc:
        raise ApplicationError(
            {"new_date": ["A class already exists at that date and time."]}
        ) from exc

    session.status = SessionStatus.RESCHEDULED
    session.rescheduled_to = replacement
    session.cancellation_reason = reason
    session.save(update_fields=["status", "rescheduled_to", "cancellation_reason", "updated_at"])

    record(
        action=AuditAction.SESSION_RESCHEDULED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": session.batch.code,
            "from_date": session.session_date.isoformat(),
            "to_date": new_date.isoformat(),
            "replacement": str(replacement.pk),
            "reason": reason,
        },
    )
    return replacement


# ---------------------------------------------------------------------------
# Trainer assignment history
# ---------------------------------------------------------------------------


@transaction.atomic
def record_trainer_assignment(
    *, batch: Batch, trainer, actor: User, note: str = ""
) -> TrainerAssignmentHistory:
    """Close the previous stint and open a new one.

    Called from the batch trainer-assignment service, so the history is written
    by the same action that changes the batch — there is no way to reassign a
    trainer without leaving a record.
    """
    now = timezone.now()
    TrainerAssignmentHistory.objects.filter(batch=batch, ended_at__isnull=True).update(ended_at=now)
    return TrainerAssignmentHistory.objects.create(
        batch=batch, trainer=trainer, assigned_at=now, assigned_by=actor, note=note
    )


# ---------------------------------------------------------------------------
# Planned-versus-actual topics
# ---------------------------------------------------------------------------


@transaction.atomic
def plan_session_topic(*, session: ClassSession, actor: User, lesson) -> ClassSession:
    """Set what a class is meant to cover, ahead of the class itself.

    Kept separate from :func:`record_session_topic`: a plan is a prediction
    made in advance, by hand or by :func:`autoplan_batch`, and a class that
    ran differently should not silently erase it — the gap between the two is
    the whole point of `apps.progress.reports.timeline_progress`.
    """
    session.planned_lesson = lesson
    session.full_clean()
    session.save(update_fields=["planned_lesson", "updated_at"])

    record(
        action=AuditAction.SESSION_TOPIC_PLANNED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": session.batch.code,
            "date": session.session_date.isoformat(),
            "lesson_id": str(lesson.pk) if lesson else None,
        },
    )
    return session


@transaction.atomic
def record_session_topic(
    *, session: ClassSession, actor: User, lesson=None, status: str = TopicStatus.COMPLETED
) -> ClassSession:
    """Record what a class actually covered, once it has happened.

    `lesson` is optional: a class recorded as `SKIPPED` covered nothing, and
    forcing a lesson onto it would misdescribe what happened rather than
    document it.
    """
    session.actual_lesson = lesson
    session.topic_status = status
    session.full_clean()
    session.save(update_fields=["actual_lesson", "topic_status", "updated_at"])

    record(
        action=AuditAction.SESSION_TOPIC_RECORDED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": session.batch.code,
            "date": session.session_date.isoformat(),
            "lesson_id": str(lesson.pk) if lesson else None,
            "topic_status": status,
        },
    )
    return session


@transaction.atomic
def autoplan_batch(*, batch: Batch, actor: User) -> dict[str, Any]:
    """Assign a batch's unplanned classes the next uncovered lesson in order.

    The curriculum is a sequence — module position, then lesson position —
    and a batch's classes are a sequence too, so the obvious first plan is to
    pair them up in order. A session that already carries a hand-made plan is
    left untouched, and the lesson it uses is removed from the queue so it is
    never handed to a second class; this is what keeps a second call a no-op.
    Only published lessons are ever queued, and a cancelled or superseded
    (rescheduled-away) class is never given one, because neither will happen.
    """
    from apps.courses.models import Lesson, PublishStatus

    lessons = list(
        Lesson.objects.filter(
            module__course_id=batch.course_id, status=PublishStatus.PUBLISHED
        ).order_by("module__position", "position")
    )

    used_lesson_ids = set(
        ClassSession.objects.filter(batch=batch, planned_lesson_id__isnull=False).values_list(
            "planned_lesson_id", flat=True
        )
    )
    available = [lesson for lesson in lessons if lesson.pk not in used_lesson_ids]

    sessions = list(
        ClassSession.objects.filter(batch=batch, planned_lesson_id__isnull=True)
        .exclude(status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED))
        .order_by("session_date", "start_time")
    )

    planned = 0
    for session, lesson in zip(sessions, available, strict=False):
        plan_session_topic(session=session, actor=actor, lesson=lesson)
        planned += 1

    return {
        "planned": planned,
        "lessons_total": len(lessons),
        "unplanned_remaining": max(len(sessions) - len(available), 0),
    }
