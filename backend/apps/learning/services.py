"""The student's own learning surface — §7.5.

Continue-learning, recent lessons, bookmarks, notes, history and what is coming
up. Everything here reads the *existing* records — `LessonProgress`, the
calendar registry, the progress report — rather than keeping its own copies,
because a second source of "where was I?" is a second thing that can be wrong.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ApplicationError

from .models import LessonBookmark, LessonNote

#: How much history a student is shown at once. A learning history is a prompt,
#: not an archive; the full record lives in `LessonProgress`.
HISTORY_LIMIT = 20
UPCOMING_DAYS = 14


def continue_learning(enrollment) -> dict[str, Any] | None:
    """Where to pick up.

    The most recently opened lesson that is not finished; failing that, the
    first unfinished lesson in the course. A student who has finished everything
    gets ``None``, which the interface reads as "nothing to continue".
    """
    from apps.courses.models import Lesson, PublishStatus
    from apps.enrollments.models import LessonProgressStatus

    in_progress = (
        enrollment.lesson_progress.select_related("lesson", "lesson__module")
        .filter(status=LessonProgressStatus.IN_PROGRESS, lesson__status=PublishStatus.PUBLISHED)
        .order_by("-last_accessed_at")
        .first()
    )
    if in_progress is not None:
        return _lesson_payload(in_progress.lesson, last_at=in_progress.last_accessed_at)

    finished = set(
        enrollment.lesson_progress.filter(status=LessonProgressStatus.COMPLETED).values_list(
            "lesson_id", flat=True
        )
    )
    nxt = (
        Lesson.objects.filter(
            module__course_id=enrollment.course_id,
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        )
        .exclude(pk__in=finished)
        .select_related("module")
        .order_by("module__position", "position")
        .first()
    )
    return _lesson_payload(nxt) if nxt else None


def _lesson_payload(lesson, *, last_at=None) -> dict[str, Any]:
    return {
        "lesson_id": str(lesson.pk),
        "lesson_title": lesson.title,
        "module_title": lesson.module.title,
        "course_slug": lesson.module.course.slug,
        "last_accessed_at": last_at,
    }


def recent_lessons(enrollment, limit: int = 5) -> list[dict[str, Any]]:
    rows = enrollment.lesson_progress.select_related("lesson", "lesson__module").order_by(
        "-last_accessed_at"
    )[:limit]
    return [
        {
            **_lesson_payload(row.lesson, last_at=row.last_accessed_at),
            "status": row.status,
        }
        for row in rows
    ]


def learning_history(enrollment, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
    """What this student has done, most recent first."""
    rows = enrollment.lesson_progress.select_related("lesson", "lesson__module").order_by(
        "-last_accessed_at"
    )[:limit]
    return [
        {
            "lesson_title": row.lesson.title,
            "module_title": row.lesson.module.title,
            "status": row.status,
            "first_accessed_at": row.first_accessed_at,
            "last_accessed_at": row.last_accessed_at,
            "completed_at": row.completed_at,
        }
        for row in rows
    ]


def upcoming_work(user, days: int = UPCOMING_DAYS) -> list[dict[str, Any]]:
    """What is due soon, from the one calendar.

    Reads the same registry the calendar page does, so a deadline cannot appear
    in one place and not the other.
    """
    from apps.dashboards.calendar import EventKind, events_for

    wanted = {
        EventKind.ASSIGNMENT_DUE,
        EventKind.PROJECT_DUE,
        EventKind.QUIZ,
        EventKind.EXAM,
    }
    today = timezone.localdate()
    events = events_for(user, today, today + timedelta(days=days))
    return [
        {
            "kind": event.kind,
            "title": event.title,
            "start": event.start,
            "course_title": event.course_title,
            "batch_code": event.batch_code,
            "metadata": event.metadata,
        }
        for event in events
        if event.kind in wanted
    ]


# ---------------------------------------------------------------------------
# Bookmarks and notes
# ---------------------------------------------------------------------------


def _lesson_in_course(enrollment, lesson):
    if lesson.module.course_id != enrollment.course_id:
        raise ApplicationError({"lesson": ["That lesson is not part of this course."]})


@transaction.atomic
def set_bookmark(*, enrollment, lesson, note: str = "") -> LessonBookmark:
    _lesson_in_course(enrollment, lesson)
    bookmark, _created = LessonBookmark.objects.update_or_create(
        enrollment=enrollment, lesson=lesson, defaults={"note": note[:200]}
    )
    return bookmark


@transaction.atomic
def remove_bookmark(*, enrollment, lesson) -> None:
    LessonBookmark.objects.filter(enrollment=enrollment, lesson=lesson).delete()


@transaction.atomic
def set_note(*, enrollment, lesson, body: str) -> LessonNote | None:
    """Write a note, or clear it by writing nothing."""
    _lesson_in_course(enrollment, lesson)
    if not body.strip():
        LessonNote.objects.filter(enrollment=enrollment, lesson=lesson).delete()
        return None
    note, _created = LessonNote.objects.update_or_create(
        enrollment=enrollment, lesson=lesson, defaults={"body": body}
    )
    return note
