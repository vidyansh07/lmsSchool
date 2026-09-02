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
def _deadline_event(*, kind, title, when, enrollment, metadata=None) -> CalendarEvent:
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
        batch_id=str(enrollment.batch_id),
        batch_code=enrollment.batch.code,
        course_id=str(enrollment.course_id),
        course_title=enrollment.course.title,
        metadata=metadata or {},
    )


def _live_enrollments(user):
    """The caller's enrolments that currently open a course.

    Every deadline source needs the same answer, so it is asked once.
    """
    from apps.batches import access as batch_access
    from apps.enrollments.models import Enrollment

    student = batch_access.student_profile(user)
    if student is None:
        return []
    rows = (
        Enrollment.objects.granting_access()
        .filter(student=student)
        .select_related("batch", "course")
    )
    return [row for row in rows if row.grants_access()]


def assignment_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Assignment deadlines — §7.4."""
    from apps.assignments.models import Assignment

    events: list[CalendarEvent] = []
    for enrollment in _live_enrollments(user):
        rows = Assignment.objects.student_visible().filter(
            course_id=enrollment.course_id, due_at__date__gte=start, due_at__date__lte=end
        )
        for assignment in rows:
            if not assignment.applies_to_batch(enrollment.batch_id):
                continue
            events.append(
                _deadline_event(
                    kind=EventKind.ASSIGNMENT_DUE,
                    title=f"Due: {assignment.title}",
                    when=assignment.due_at,
                    enrollment=enrollment,
                    metadata={"assignment_id": str(assignment.pk), "code": assignment.code},
                )
            )
    return events


def assessment_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Weekly tests — §7.4."""
    from apps.assessments.models import Assessment

    events: list[CalendarEvent] = []
    for enrollment in _live_enrollments(user):
        rows = Assessment.objects.student_visible().filter(
            batch_id=enrollment.batch_id,
            scheduled_for__date__gte=start,
            scheduled_for__date__lte=end,
        )
        for assessment in rows:
            events.append(
                CalendarEvent(
                    kind=EventKind.QUIZ,
                    title=assessment.title,
                    start=assessment.scheduled_for,
                    end=assessment.scheduled_for,
                    batch_id=str(enrollment.batch_id),
                    batch_code=enrollment.batch.code,
                    course_id=str(enrollment.course_id),
                    course_title=enrollment.course.title,
                    metadata={"assessment_id": str(assessment.pk), "code": assessment.code},
                )
            )
    return events


def exam_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Examination windows — §7.4."""
    from apps.exams.models import Exam

    events: list[CalendarEvent] = []
    for enrollment in _live_enrollments(user):
        rows = Exam.objects.student_visible().filter(
            batch_id=enrollment.batch_id, opens_at__date__gte=start, opens_at__date__lte=end
        )
        for exam in rows:
            events.append(
                CalendarEvent(
                    kind=EventKind.EXAM,
                    title=exam.title,
                    start=exam.opens_at,
                    end=exam.closes_at or exam.opens_at,
                    batch_id=str(enrollment.batch_id),
                    batch_code=enrollment.batch.code,
                    course_id=str(enrollment.course_id),
                    course_title=enrollment.course.title,
                    metadata={"exam_id": str(exam.pk), "code": exam.code},
                )
            )
    return events


def project_events(user, start: date, end: date) -> list[CalendarEvent]:
    """Project deadlines — §7.4."""
    from datetime import datetime as _datetime

    from django.utils import timezone as _timezone

    from apps.projects.models import Project

    events: list[CalendarEvent] = []
    for enrollment in _live_enrollments(user):
        rows = Project.objects.student_visible().filter(
            course_id=enrollment.course_id, end_date__gte=start, end_date__lte=end
        )
        for project in rows:
            if not project.applies_to_batch(enrollment.batch_id):
                continue
            when = _timezone.make_aware(
                _datetime.combine(project.end_date, time(23, 59)),
                _timezone.get_current_timezone(),
            )
            events.append(
                _deadline_event(
                    kind=EventKind.PROJECT_DUE,
                    title=f"Project due: {project.title}",
                    when=when,
                    enrollment=enrollment,
                    metadata={"project_id": str(project.pk), "code": project.code},
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
