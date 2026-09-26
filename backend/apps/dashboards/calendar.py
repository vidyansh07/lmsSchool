"""One calendar, many sources.

§10 asks for a single calendar abstraction rather than a separate calendar per
feature, and this is it. Every source is a function that takes a user and a date
range and returns :class:`CalendarEvent` objects; the registry composes them.

Adding assignment deadlines, quiz windows, exam dates or announcements later
means writing one function and appending it to :data:`EVENT_SOURCES`. No view,
no serializer and no frontend component changes — which is the whole point,
because the alternative is five calendars that disagree.

Every source is responsible for its own access control. There is no
"calendar sees everything" shortcut: a source resolves what the caller may see
using the same access layer the rest of the API uses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

#: How far ahead a caller may ask for at once. A calendar query is cheap per
#: day and expensive per year, so the window is bounded rather than trusted.
MAX_RANGE_DAYS = 120


class EventKind:
    CLASS = "class"
    BATCH_START = "batch_start"
    BATCH_END = "batch_end"
    COURSE_START = "course_start"
    COURSE_END = "course_end"
    ASSIGNMENT_DUE = "assignment_due"
    QUIZ = "quiz"
    EXAM = "exam"
    PROJECT_DUE = "project_due"
    ANNOUNCEMENT = "announcement"
    ACTIVITY_DUE = "activity_due"


@dataclass(frozen=True)
class CalendarEvent:
    """One thing that happens on a date, from any source."""

    kind: str
    title: str
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    location: str = ""
    batch_id: str | None = None
    batch_code: str = ""
    course_id: str | None = None
    course_title: str = ""
    trainer_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "all_day": self.all_day,
            "location": self.location,
            "batch_id": self.batch_id,
            "batch_code": self.batch_code,
            "course_id": self.course_id,
            "course_title": self.course_title,
            "trainer_name": self.trainer_name,
            "metadata": self.metadata,
        }


def _dates_between(start: date, end: date, weekday: int) -> Iterable[date]:
    """Every date in the range falling on the given weekday."""
    offset = (weekday - start.weekday()) % 7
    current = start + timedelta(days=offset)
    while current <= end:
        yield current
        current += timedelta(days=7)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def class_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Recurring classes, expanded into one event per occurrence.

    Expansion happens here rather than being stored: a weekly slot is a rule,
    and materialising a row per week would mean rewriting history every time a
    schedule changed.
    """
    from apps.batches.access import visible_batches
    from apps.batches.models import BatchSchedule, BatchStatus

    batches = visible_batches(user).exclude(status=BatchStatus.CANCELLED)
    schedules = (
        BatchSchedule.objects.filter(batch__in=batches, is_active=True)
        .select_related("batch", "batch__course", "batch__trainer__user", "trainer__user")
        .order_by("weekday", "start_time")
    )

    events: list[CalendarEvent] = []
    for schedule in schedules:
        batch = schedule.batch
        # Clip to the batch's own dates: a class cannot happen before the batch
        # starts or after it ends.
        window_start = max(start, batch.start_date)
        window_end = min(end, batch.end_date)
        if window_start > window_end:
            continue

        zone = _zone(schedule.timezone_name)
        trainer = schedule.trainer or batch.trainer
        trainer_name = trainer.user.full_name if trainer else ""

        for day in _dates_between(window_start, window_end, schedule.weekday):
            events.append(
                CalendarEvent(
                    kind=EventKind.CLASS,
                    title=f"{batch.course.title} — {batch.name}",
                    start=datetime.combine(day, schedule.start_time, tzinfo=zone),
                    end=datetime.combine(day, schedule.end_time, tzinfo=zone),
                    location=schedule.location,
                    batch_id=str(batch.pk),
                    batch_code=batch.code,
                    course_id=str(batch.course_id),
                    course_title=batch.course.title,
                    trainer_name=trainer_name,
                    metadata={
                        "schedule_id": str(schedule.pk),
                        "timezone": schedule.timezone_name,
                        "note": schedule.note,
                    },
                )
            )
    return events


def batch_milestone_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Batch start and end dates, as all-day markers."""
    from apps.batches.access import visible_batches
    from apps.batches.models import BatchStatus

    batches = visible_batches(user).exclude(status=BatchStatus.CANCELLED)
    events: list[CalendarEvent] = []

    for batch in batches:
        for day, kind, label in (
            (batch.start_date, EventKind.BATCH_START, "starts"),
            (batch.end_date, EventKind.BATCH_END, "ends"),
        ):
            if not (start <= day <= end):
                continue
            events.append(
                CalendarEvent(
                    kind=kind,
                    title=f"{batch.name} {label}",
                    start=datetime.combine(day, time.min, tzinfo=ZoneInfo("UTC")),
                    all_day=True,
                    batch_id=str(batch.pk),
                    batch_code=batch.code,
                    course_id=str(batch.course_id),
                    course_title=batch.course.title,
                )
            )
    return events


#: The registry. Append a source here to put a new kind of thing on everyone's
#: calendar; nothing else changes.
def _deadline_event(*, kind, title, when, scope, metadata=None) -> CalendarEvent:
    """A deadline, as an all-day marker on the day it falls.

    Deliberately all-day rather than at the exact minute: a deadline at 23:59
    rendered as a one-minute slot at the bottom of a day is a deadline nobody
    sees.
    """
    return CalendarEvent(
        kind=kind,
        title=title,
        start=when,
        end=when,
        all_day=True,
        batch_id=str(scope.batch_id),
        batch_code=scope.batch.code,
        course_id=str(scope.course_id),
        course_title=scope.course.title,
        metadata=metadata or {},
    )


@dataclass(frozen=True)
class _DeadlineScope:
    """One batch, and the course it runs, that a deadline can land on.

    A scope rather than an enrolment because a trainer or a manager has no
    enrolment row and still has deadlines to see (see :func:`_deadline_scopes`).
    It exposes the same four names an ``Enrollment`` does — ``batch``,
    ``batch_id``, ``course``, ``course_id`` — so every source below reads the
    same whoever is asking.
    """

    batch: Any
    course: Any

    @property
    def batch_id(self):
        return self.batch.pk

    @property
    def course_id(self):
        return self.course.pk


def _deadline_scopes(user, start: date, end: date) -> list[_DeadlineScope]:
    """Every batch whose deadlines belong on this caller's calendar.

    Every deadline source needs the same answer, so it is asked once.

    For a **student**, that is the enrolments which currently open a course —
    the same ``grants_access()`` test the rest of the product uses, so a
    suspended enrolment's deadlines leave the calendar along with the course.

    For **staff** it is the batches the access layer already grants them, and
    that branch is the whole of the defect this function replaced: the previous
    `_live_enrollments` resolved a *student profile*, found `None` for a trainer
    and returned an empty list, so all four deadline sources ran zero times —
    a trainer's calendar carried classes and activity dues and not one
    assignment, test, exam or project deadline for the batches they teach
    themselves. `visible_batches` is the same access function `class_events`
    and `batch_milestone_events` above already use, so a trainer sees their own
    batches, a manager their centre's, and nobody reaches a batch the access
    layer would not hand them.

    A staff scope is clipped to batches whose own dates overlap the window, for
    the same reason `class_events` clips each expansion to them: a course-wide
    assignment due next week is not a deadline for a cohort that finished last
    year.
    """
    from apps.batches import access as batch_access
    from apps.batches.models import BatchStatus
    from apps.enrollments.models import Enrollment

    student = batch_access.student_profile(user)
    if student is not None:
        rows = (
            Enrollment.objects.granting_access()
            .filter(student=student)
            .select_related("batch", "course")
        )
        return [
            _DeadlineScope(batch=row.batch, course=row.course)
            for row in rows
            if row.grants_access()
        ]

    batches = (
        batch_access.visible_batches(user)
        .exclude(status=BatchStatus.CANCELLED)
        .filter(start_date__lte=end, end_date__gte=start)
        .select_related("course")
    )
    return [_DeadlineScope(batch=batch, course=batch.course) for batch in batches]


def assignment_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Assignment deadlines — §7.4."""
    from apps.assignments.models import Assignment

    scopes = _deadline_scopes(user, start, end)
    if not scopes:
        return []
    # One query for the whole scope rather than one per batch: a manager's
    # scope is every batch in their centre, and this used to be a query each.
    rows = Assignment.objects.student_visible().filter(
        course_id__in={scope.course_id for scope in scopes},
        due_at__date__gte=start,
        due_at__date__lte=end,
    )
    events: list[CalendarEvent] = []
    for assignment in rows:
        for scope in scopes:
            if scope.course_id != assignment.course_id:
                continue
            if not assignment.applies_to_batch(scope.batch_id):
                continue
            events.append(
                _deadline_event(
                    kind=EventKind.ASSIGNMENT_DUE,
                    title=f"Due: {assignment.title}",
                    when=assignment.due_at,
                    scope=scope,
                    metadata={"assignment_id": str(assignment.pk), "code": assignment.code},
                )
            )
    return events


def assessment_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Weekly tests — §7.4."""
    from apps.assessments.models import Assessment

    scopes = _deadline_scopes(user, start, end)
    if not scopes:
        return []
    rows = Assessment.objects.student_visible().filter(
        batch_id__in={scope.batch_id for scope in scopes},
        scheduled_for__date__gte=start,
        scheduled_for__date__lte=end,
    )
    events: list[CalendarEvent] = []
    for assessment in rows:
        for scope in scopes:
            if scope.batch_id != assessment.batch_id:
                continue
            events.append(
                CalendarEvent(
                    kind=EventKind.QUIZ,
                    title=assessment.title,
                    start=assessment.scheduled_for,
                    end=assessment.scheduled_for,
                    batch_id=str(scope.batch_id),
                    batch_code=scope.batch.code,
                    course_id=str(scope.course_id),
                    course_title=scope.course.title,
                    metadata={"assessment_id": str(assessment.pk), "code": assessment.code},
                )
            )
    return events


def exam_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Examination windows — §7.4."""
    from apps.exams.models import Exam

    scopes = _deadline_scopes(user, start, end)
    if not scopes:
        return []
    rows = Exam.objects.student_visible().filter(
        batch_id__in={scope.batch_id for scope in scopes},
        opens_at__date__gte=start,
        opens_at__date__lte=end,
    )
    events: list[CalendarEvent] = []
    for exam in rows:
        for scope in scopes:
            if scope.batch_id != exam.batch_id:
                continue
            events.append(
                CalendarEvent(
                    kind=EventKind.EXAM,
                    title=exam.title,
                    start=exam.opens_at,
                    end=exam.closes_at or exam.opens_at,
                    batch_id=str(scope.batch_id),
                    batch_code=scope.batch.code,
                    course_id=str(scope.course_id),
                    course_title=scope.course.title,
                    metadata={"exam_id": str(exam.pk), "code": exam.code},
                )
            )
    return events


def project_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Project deadlines — §7.4."""
    from datetime import datetime as _datetime

    from django.utils import timezone as _timezone

    from apps.projects.models import Project

    scopes = _deadline_scopes(user, start, end)
    if not scopes:
        return []
    rows = Project.objects.student_visible().filter(
        course_id__in={scope.course_id for scope in scopes},
        end_date__gte=start,
        end_date__lte=end,
    )
    events: list[CalendarEvent] = []
    for project in rows:
        when = _timezone.make_aware(
            _datetime.combine(project.end_date, time(23, 59)),
            _timezone.get_current_timezone(),
        )
        for scope in scopes:
            if scope.course_id != project.course_id:
                continue
            if not project.applies_to_batch(scope.batch_id):
                continue
            events.append(
                _deadline_event(
                    kind=EventKind.PROJECT_DUE,
                    title=f"Project due: {project.title}",
                    when=when,
                    scope=scope,
                    metadata={"project_id": str(project.pk), "code": project.code},
                )
            )
    return events


def _activity_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Activity due dates (ERP Phase 9). Resolves its own access control
    through `apps.work.access` — the same `visible_activities`/
    `student_visible_activities` functions the list endpoint uses — never a
    raw unscoped query."""
    from apps.work import access as work_access
    from apps.work.models import OPEN_STATUSES

    window_start = datetime.combine(start, time.min, tzinfo=ZoneInfo("UTC"))
    window_end = datetime.combine(end, time.max, tzinfo=ZoneInfo("UTC"))

    student = work_access.caller_student_profile(user)
    rows = (
        work_access.student_visible_activities(student)
        if student is not None
        else work_access.visible_activities(user)
    )
    rows = rows.filter(
        due_at__isnull=False,
        due_at__gte=window_start,
        due_at__lte=window_end,
        status__in=OPEN_STATUSES,
    ).select_related("activity_type", "batch", "batch__course")

    events: list[CalendarEvent] = []
    for activity in rows:
        batch = activity.batch
        events.append(
            CalendarEvent(
                kind=EventKind.ACTIVITY_DUE,
                title=f"Due: {activity.title}",
                start=activity.due_at,
                end=activity.due_at,
                batch_id=str(batch.pk) if batch else None,
                batch_code=batch.code if batch else "",
                course_id=str(batch.course_id) if batch else None,
                course_title=batch.course.title if batch else "",
                metadata={
                    "activity_id": str(activity.pk),
                    "activity_type": activity.activity_type.slug,
                    "status": activity.status,
                    "student_id": str(activity.student_id),
                },
            )
        )
    return events


EVENT_SOURCES: list[Callable[[Any, date, date], list[CalendarEvent]]] = [
    class_events,
    batch_milestone_events,
    assignment_events,
    assessment_events,
    exam_events,
    project_events,
    _activity_events,
]


def events_for(user, start: date, end: date) -> list[CalendarEvent]:
    """Every event the caller may see in the range, sorted by start time.

    A failing source is logged and skipped rather than breaking the whole
    calendar: one broken feed should not blank out a person's timetable.
    """
    import logging

    logger = logging.getLogger("grras.calendar")
    collected: list[CalendarEvent] = []

    for source in EVENT_SOURCES:
        try:
            collected.extend(source(user, start, end))
        except Exception:
            logger.exception(
                "Calendar source failed", extra={"context": {"source": source.__name__}}
            )

    return sorted(collected, key=lambda event: (event.start, event.title))
