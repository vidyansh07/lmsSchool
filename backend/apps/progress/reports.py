"""The one course-progress calculation — §6.1 to §6.3.

    "Provide one backend-owned course progress calculation. Do not let
    different frontend screens calculate progress independently."

So there is exactly one function that answers "how far is this student?", it
lives here, and every screen and every rule reads it. A dashboard that divides
two numbers it happened to have is how two parts of a product come to disagree
about whether somebody has finished.

Shape
-----
:func:`progress_report` returns one dictionary per enrolment with a section per
kind of activity — lessons, modules, attendance, assignments, tests, projects,
the final examination. Each section carries the *numbers*, never a verdict;
:mod:`apps.progress.rules` turns numbers into pass or fail, because that is
configuration and this is arithmetic.

Everything counts published, live records only: a draft lesson an author is
still writing must not push a progress bar backwards, and a cancelled enrolment
is not a cohort member.

One student or four hundred
---------------------------
Every function here takes an optional :class:`~apps.progress.bulk.ProgressInputs`
— the database reads, already done for a set of enrolments. Called without one
it gathers for a single enrolment and behaves exactly as before; called with
one, a cohort report shapes four hundred rows from a fixed number of queries.
The arithmetic below is identical in both cases, which is the entire point:
a bulk path that recomputed anything would be a second progress calculation.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from apps.progress.bulk import ProgressInputs


def _percent(done: int, total: int) -> int:
    return round(done * 100 / total) if total else 0


def _inputs(enrollment, inputs: ProgressInputs | None) -> ProgressInputs:
    return inputs if inputs is not None else ProgressInputs.for_one(enrollment)


def lesson_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """§6.1 — how many published lessons this student has finished."""
    from apps.enrollments.models import LessonProgressStatus

    data = _inputs(enrollment, inputs)
    published = data.published_lessons.get(enrollment.course_id, [])
    published_ids = {lesson.pk for lesson in published}
    rows = data.lesson_progress_rows.get(enrollment.pk, [])

    on_published = [row for row in rows if row.lesson_id in published_ids]
    completed = [row for row in on_published if row.status == LessonProgressStatus.COMPLETED]

    # Ordered newest-access-first by the gatherer, so the first row is the
    # most recent. Taken from every row, not only published ones: "where you
    # left off" should not jump backwards because a lesson was unpublished.
    last = rows[0] if rows else None
    finished = [row for row in rows if row.status == LessonProgressStatus.COMPLETED]
    last_completed = max(
        (row.completed_at for row in finished if row.completed_at is not None), default=None
    )

    return {
        "total": len(published),
        "started": len(on_published),
        "completed": len(completed),
        "percent": _percent(len(completed), len(published)),
        "last_lesson_id": str(last.lesson_id) if last else None,
        "last_lesson_title": last.lesson.title if last else None,
        "last_accessed_at": last.last_accessed_at if last else None,
        "completed_at": last_completed,
    }


def module_progress(enrollment, inputs: ProgressInputs | None = None) -> list[dict[str, Any]]:
    """§6.2 — the same arithmetic, one row per module.

    Counted from the lessons and progress rows already gathered rather than with
    a grouped query per enrolment, because a course with thirty modules would
    otherwise cost thirty round trips on every dashboard render — and a cohort
    report would multiply that by the cohort.
    """
    from apps.enrollments.models import LessonProgressStatus

    data = _inputs(enrollment, inputs)
    modules = data.published_modules.get(enrollment.course_id, [])
    lessons = data.published_lessons.get(enrollment.course_id, [])
    completed_ids = {
        row.lesson_id
        for row in data.lesson_progress_rows.get(enrollment.pk, [])
        if row.status == LessonProgressStatus.COMPLETED
    }

    by_module: dict[Any, list] = {module.pk: [] for module in modules}
    for lesson in lessons:
        by_module.setdefault(lesson.module_id, []).append(lesson)

    rows = []
    for module in modules:
        module_lessons = by_module.get(module.pk, [])
        total = len(module_lessons)
        done = sum(1 for lesson in module_lessons if lesson.pk in completed_ids)
        rows.append(
            {
                "id": str(module.pk),
                "title": module.title,
                "position": module.position,
                "total_lessons": total,
                "completed_lessons": done,
                "percent": _percent(done, total),
                "is_complete": total > 0 and done >= total,
            }
        )
    return rows


def attendance_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    data = _inputs(enrollment, inputs)
    summary = data.attendance[enrollment.pk]
    return {
        "total": summary["total_sessions"],
        "attended": summary["attended"],
        "percent": summary["percentage"] or 0,
        "has_records": summary["total_sessions"] > 0,
        **{key: summary[key] for key in ("present", "late", "absent", "excused")},
    }


def assignment_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """How many of the published assignments this student has handed in and passed."""
    from apps.assignments.models import SubmissionStatus

    data = _inputs(enrollment, inputs)
    applicable = [
        assignment
        for assignment in data.assignments.get(enrollment.course_id, [])
        if assignment.applies_to_batch(enrollment.batch_id)
    ]
    total = len(applicable)
    if not total:
        return {"total": 0, "submitted": 0, "graded": 0, "passed": 0, "percent": 0}

    applicable_ids = {assignment.pk for assignment in applicable}
    submissions = [
        row
        for row in data.submissions.get(enrollment.pk, [])
        if row.assignment_id in applicable_ids
    ]
    # A student may have several attempts; the latest is the one that counts.
    latest: dict[Any, Any] = {}
    for row in submissions:
        current = latest.get(row.assignment_id)
        if current is None or row.attempt > current.attempt:
            latest[row.assignment_id] = row

    graded = [row for row in latest.values() if row.status == SubmissionStatus.GRADED]
    passed = [row for row in graded if row.is_passing]

    return {
        "total": total,
        "submitted": len(latest),
        "graded": len(graded),
        "passed": len(passed),
        "percent": _percent(len(latest), total),
    }


def test_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """Weekly tests: how many were sat, and the average across them."""
    data = _inputs(enrollment, inputs)
    applicable = data.assessments.get(enrollment.batch_id, [])
    total = len(applicable)
    if not total:
        return {"total": 0, "recorded": 0, "percent": 0, "average_percent": None, "passed": 0}

    applicable_ids = {assessment.pk for assessment in applicable}
    results = [
        row for row in data.results.get(enrollment.pk, []) if row.assessment_id in applicable_ids
    ]
    scored = [row for row in results if row.marks_obtained is not None]

    average = None
    if scored:
        obtained = sum((row.marks_obtained for row in scored), Decimal("0"))
        out_of = sum((row.assessment.max_marks for row in scored), Decimal("0"))
        if out_of:
            average = round(float(obtained) / float(out_of) * 100, 2)

    return {
        "total": total,
        "recorded": len(results),
        "percent": _percent(len(results), total),
        "average_percent": average,
        "passed": sum(1 for row in results if row.is_passing),
    }


def project_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    from apps.projects.services import required_project_progress

    data = _inputs(enrollment, inputs)
    progress = required_project_progress(enrollment, inputs=data)
    return {
        "required": progress["required"],
        "finished": progress["finished"],
        "outstanding": progress["outstanding"],
        "percent": _percent(progress["finished"], progress["required"]),
    }


def exam_progress(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """The final examination: whether one exists, was sat, and was passed.

    "Passed" reads the best graded attempt — a candidate allowed two sittings is
    judged on the better one, which is what an institution means by passing.
    """
    data = _inputs(enrollment, inputs)
    exams = data.exams.get(enrollment.batch_id, [])
    if not exams:
        return {"exists": False, "sat": False, "passed": None, "best_percent": None}

    exam_ids = {exam.pk for exam in exams}
    attempts = [
        attempt
        for attempt in data.attempts.get(enrollment.pk, [])
        if attempt.exam_id in exam_ids and attempt.total_score is not None
    ]
    if not attempts:
        return {"exists": True, "sat": False, "passed": False, "best_percent": None}

    best = max(attempts, key=lambda attempt: attempt.percentage or 0)
    return {
        "exists": True,
        "sat": True,
        "passed": bool(best.is_passing),
        "best_percent": best.percentage,
    }


def progress_report(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """Everything one student has done on one enrolment.

    The single source every screen and every completion rule reads.
    """
    data = _inputs(enrollment, inputs)
    return {
        "enrollment_id": str(enrollment.pk),
        "course_title": enrollment.course.title,
        "batch_code": enrollment.batch.code,
        "delivery_mode": enrollment.effective_delivery_mode,
        "lessons": lesson_progress(enrollment, data),
        "modules": module_progress(enrollment, data),
        "attendance": attendance_progress(enrollment, data),
        "assignments": assignment_progress(enrollment, data),
        "tests": test_progress(enrollment, data),
        "projects": project_progress(enrollment, data),
        "exam": exam_progress(enrollment, data),
    }


def progress_reports(enrollments) -> Iterator[tuple[Any, dict[str, Any]]]:
    """The same report for a cohort, at a query cost that does not grow with it.

    Yields ``(enrolment, report)`` pairs. Callers iterate rather than receiving a
    list so a report can stream rows to a download without holding the cohort in
    memory twice — though the gathered inputs themselves are held, which is why
    a caller should page rather than ask for an institution at once.

    A queryset gets ``select_related`` applied here. Every report reads
    ``enrollment.course.title`` and ``enrollment.batch.code``, so a cohort
    fetched without them would lazy-load two rows per student and quietly
    reintroduce the N+1 this function exists to remove.
    """
    if hasattr(enrollments, "select_related"):
        enrollments = enrollments.select_related("course", "batch")
    rows = list(enrollments)
    if not rows:
        return
    data = ProgressInputs(rows)
    for enrollment in rows:
        yield enrollment, progress_report(enrollment, data)
