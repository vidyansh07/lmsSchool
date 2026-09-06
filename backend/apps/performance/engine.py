"""The performance picture — one student, one trainer, or a whole batch.

    "Provide one backend-owned course progress calculation. Do not let
    different frontend screens calculate progress independently."

That rule from Phase 6 (see :mod:`apps.progress.reports`) applies here without
change: this module computes nothing that :mod:`apps.progress.reports` or
:mod:`apps.attendance.models` already compute. It reads their numbers, adds the
few figures that are genuinely new here — missed assignments, schedule
variance — and hands the result to :mod:`apps.performance.risk` for a verdict.

Null handling is a hard requirement throughout this module. Every numeric key
in the returned dictionaries is either a real number or ``None`` — never
``NaN``, never a string standing in for "unknown". A percentage computed from
zero of zero is not zero; it is "nothing to measure", and nothing to measure is
``None``. A caller reading these dictionaries should never have to write
``if "key" in result`` — the key is always there, and its value is always one
of the two honest answers: a number, or "there is nothing to report".

One student or four hundred
----------------------------
:func:`student_performance` computes for one enrolment; :func:`student_performance_bulk`
answers the same question for many, from the same
:class:`~apps.progress.bulk.ProgressInputs` gather that
:func:`apps.progress.reports.progress_reports` already uses for cohort
reporting. Nothing here re-queries per student — the query cost is fixed, not
proportional to the roster.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.academics.policies import policy_for
from apps.progress.bulk import ProgressInputs
from apps.progress.reports import progress_report

from . import risk


def _percent(part: int, whole: int) -> int | None:
    """A percentage, or ``None`` when there is nothing to divide by.

    Zero would claim "0% of nothing achieved", which reads as a failure when it
    means there was nothing to do — the same reasoning `apps.progress.reports`
    and `apps.reporting.metrics` both apply.
    """
    return round(part * 100 / whole) if whole else None


def _expected_progress_percent(batch, *, today=None) -> int | None:
    """How far through its published lessons a student *should* be by now,
    reading only the calendar a batch already carries.

    A straight-line read of the batch's own dates: none of the term done means
    0% expected, all of it done means 100%, and a point in between is that
    fraction of the way. It is deliberately naive — it does not know which
    lessons a trainer intends to cover which week — because that timetable does
    not exist anywhere in this system. What does exist is "this batch runs from
    here to here", and that is enough to notice a student who has opened
    nothing three weeks in.
    """
    today = today or timezone.localdate()
    if not batch.start_date or not batch.end_date:
        return None
    if today <= batch.start_date:
        return 0
    if today >= batch.end_date:
        return 100
    span = (batch.end_date - batch.start_date).days
    if span <= 0:
        return 100
    elapsed = (today - batch.start_date).days
    return round(elapsed * 100 / span)


def _missed_assignments(enrollment, data: ProgressInputs) -> dict[str, int]:
    """Published assignments applicable to this student, overdue, unsubmitted.

    Not a progress-report figure: `assignment_progress` counts submissions
    against every applicable assignment, whether or not it is due yet — right
    for "how much has this student handed in", wrong for risk, where handing
    something in next week is not yet a problem. This counts only the ones a
    student has run out of time on.

    Read from the same `ProgressInputs.assignments` / `.submissions` groups
    `apps.progress.reports.assignment_progress` reads, so a cohort call costs
    nothing extra here.
    """
    now = timezone.now()
    applicable = [
        assignment
        for assignment in data.assignments.get(enrollment.course_id, [])
        if assignment.applies_to_batch(enrollment.batch_id)
        and assignment.due_at is not None
        and assignment.due_at < now
    ]
    if not applicable:
        return {"missed": 0, "overdue_total": 0}

    applicable_ids = {assignment.pk for assignment in applicable}
    submitted_ids = {
        row.assignment_id
        for row in data.submissions.get(enrollment.pk, [])
        if row.assignment_id in applicable_ids
    }
    return {
        "missed": len(applicable_ids - submitted_ids),
        "overdue_total": len(applicable_ids),
    }


def _risk_numbers(enrollment, report: dict[str, Any], data: ProgressInputs) -> dict[str, Any]:
    """The subset of the report, plus the new figures, that the risk rules read."""
    attendance = report["attendance"]
    tests = report["tests"]
    lessons = report["lessons"]
    missed = _missed_assignments(enrollment, data)

    has_lessons = lessons["total"] > 0
    expected = _expected_progress_percent(enrollment.batch)
    variance = (expected - lessons["percent"]) if (has_lessons and expected is not None) else None

    return {
        "attendance": {"percent": attendance["percent"], "has_records": attendance["has_records"]},
        "assessment": {
            "average_percent": tests["average_percent"],
            "recorded": tests["recorded"],
            "total": tests["total"],
        },
        "assignments": {"missed": missed["missed"], "overdue_total": missed["overdue_total"]},
        "progress": {
            "actual_percent": lessons["percent"],
            "expected_percent": expected,
            "variance": variance,
            "has_lessons": has_lessons,
        },
    }


def student_performance(enrollment, inputs: ProgressInputs | None = None) -> dict[str, Any]:
    """Everything one student has done, scored, and is at risk of, on one enrolment.

    Built on `progress_report`, never a second calculation of the same numbers.
    """
    data = inputs if inputs is not None else ProgressInputs.for_one(enrollment)
    report = progress_report(enrollment, data)
    policy = policy_for(enrollment.course_id)

    attendance = report["attendance"]
    tests = report["tests"]
    assignments = report["assignments"]
    projects = report["projects"]
    lessons = report["lessons"]

    numbers = _risk_numbers(enrollment, report, data)
    risk_result = risk.evaluate(numbers, policy)

    # Each component contributes to the overall score only when there was
    # something to measure it from — the same "nothing to measure" rule the
    # risk rules follow. A course with no projects must not drag a student's
    # score down for a requirement that does not exist.
    components = [
        attendance["percent"] if attendance["has_records"] else None,
        tests["average_percent"],
        assignments["percent"] if assignments["total"] else None,
        projects["percent"] if projects["required"] else None,
        lessons["percent"] if lessons["total"] else None,
    ]
    measured = [value for value in components if value is not None]
    overall_score = round(sum(measured) / len(measured), 1) if measured else None

    return {
        "enrollment_id": str(enrollment.pk),
        "course_title": report["course_title"],
        "batch_code": report["batch_code"],
        "attendance": {
            "percent": attendance["percent"] if attendance["has_records"] else None,
            "total_sessions": attendance["total"],
            "attended": attendance["attended"],
            "has_records": attendance["has_records"],
        },
        "assessment": {
            "average_percent": tests["average_percent"],
            "sitting_percent": tests["percent"] if tests["total"] else None,
            "recorded": tests["recorded"],
            "total": tests["total"],
        },
        "assignments": {
            "percent": assignments["percent"] if assignments["total"] else None,
            "total": assignments["total"],
            "submitted": assignments["submitted"],
            "graded": assignments["graded"],
            "passed": assignments["passed"],
            "missed": numbers["assignments"]["missed"],
        },
        "projects": {
            "percent": projects["percent"] if projects["required"] else None,
            "required": projects["required"],
            "finished": projects["finished"],
        },
        "progress": {
            "percent": lessons["percent"] if lessons["total"] else None,
            "expected_percent": numbers["progress"]["expected_percent"],
            "variance": numbers["progress"]["variance"],
        },
        "overall_score": overall_score,
        "risk": risk_result,
        "counts": {
            "components_measured": len(measured),
            "risk_flags": risk_result["triggered_count"],
        },
    }


def student_performance_bulk(enrollments) -> dict[Any, dict[str, Any]]:
    """The same report for every requested enrolment, at a fixed query cost.

    Gathers one `ProgressInputs` for the whole set — exactly what
    `apps.progress.reports.progress_reports` does for cohort reporting — rather
    than calling `student_performance` unseeded once per row, which would cost
    a progress calculation's worth of queries per student.

    Every enrolment passed in is a key in the result, including one with no
    attendance, no assessments and no submissions at all: a brand-new student
    is a fully populated row of `None`s and zeroes, not a missing one.

    `enrollments` should be a queryset (so `select_related` can be applied) or
    a list already carrying `course` and `batch` — every report here reads
    both, and fetching them lazily per row would reintroduce the N+1 this
    function exists to remove.
    """
    if hasattr(enrollments, "select_related"):
        enrollments = enrollments.select_related("course", "batch")
    rows = list(enrollments)
    if not rows:
        return {}
    data = ProgressInputs(rows)
    return {enrollment.pk: student_performance(enrollment, data) for enrollment in rows}


# ---------------------------------------------------------------------------
# Trainer performance
# ---------------------------------------------------------------------------


def trainer_performance(trainer) -> dict[str, Any]:
    """What one trainer is carrying: their cohorts, their marking, their DSR record.

    Deliberately not a productivity score, in the same spirit as
    `apps.reporting.reports.trainer_activity`: these are counts and rates, not
    a ranking. Two figures are split into "pending" and "overdue" rather than
    one workload number, because they answer different questions a manager
    asks — "how much is there to do" and "how much of it is already late" —
    and collapsing them loses the second one.
    """
    from django.apps import apps as django_apps
    from django.db.models import Count

    from apps.assessments.models import Assessment, AssessmentResult
    from apps.assignments.models import AssignmentSubmission, SubmissionStatus
    from apps.batches.models import Batch
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.projects.models import FINISHED_STATUSES, StudentProject, WorkStatus
    from apps.sessions.models import ATTENDABLE_STATUSES, ClassSession

    # Cancelled enrolments never occupied a seat this trainer taught; pending
    # ones have not started yet. Everything else is a student this trainer has
    # actually been responsible for.
    counted_statuses = (
        EnrollmentStatus.ACTIVE,
        EnrollmentStatus.COMPLETED,
        EnrollmentStatus.SUSPENDED,
    )

    batch_ids = list(Batch.objects.filter(trainer=trainer).values_list("id", flat=True))
    batches_handled = len(batch_ids)

    if not batch_ids:
        return {
            "trainer_id": str(trainer.pk),
            "batches_handled": 0,
            "students_handled": 0,
            "attendance_submission_rate": None,
            "dsr_submission_rate": None,
            "dsr_submitted_count": None,
            "assignment_completion_percent": None,
            "assessment_completion_percent": None,
            "project_completion_percent": None,
            "student_average_score": None,
            "pending_work": {"assignments": 0, "projects": 0, "assessments": 0, "total": 0},
            "overdue_work": {"assignments": 0, "projects": 0, "assessments": 0, "total": 0},
            "counts": {"batches": 0, "students": 0, "sessions_taken": 0},
        }

    enrollment_rows = list(
        Enrollment.objects.filter(
            batch_id__in=batch_ids, status__in=counted_statuses
        ).select_related("course", "batch")
    )
    students_handled = len({row.student_id for row in enrollment_rows})

    # -- Attendance: classes this trainer actually took, register taken or not.
    sessions = ClassSession.objects.filter(trainer=trainer, status__in=ATTENDABLE_STATUSES)
    total_sessions = sessions.count()
    sessions_with_attendance = (
        sessions.filter(attendance__isnull=False).distinct().count() if total_sessions else 0
    )
    attendance_submission_rate = _percent(sessions_with_attendance, total_sessions)

    # -- Daily status reports. `apps.dsr` is being built alongside this
    # feature; on an environment where its model has not landed yet (or has a
    # shape this code does not expect), the figure is reported as `None`
    # rather than the endpoint failing outright.
    dsr_submission_rate = None
    dsr_submitted_count = None
    try:
        dsr_model = django_apps.get_model("dsr", "DSR")
    except LookupError:
        dsr_model = None
    if dsr_model is not None and total_sessions:
        try:
            dsr_submitted_count = (
                dsr_model.objects.filter(session__in=sessions)
                .values("session_id")
                .distinct()
                .count()
            )
            dsr_submission_rate = _percent(dsr_submitted_count, total_sessions)
        except Exception:  # pragma: no cover - defensive against a model still taking shape
            dsr_submission_rate = None
            dsr_submitted_count = None

    # -- Assignments: the marking workload on this trainer's batches.
    submissions = AssignmentSubmission.objects.filter(enrollment__batch_id__in=batch_ids)
    total_submissions = submissions.count()
    graded_submissions = (
        submissions.filter(status=SubmissionStatus.GRADED).count() if total_submissions else 0
    )
    assignment_completion_percent = _percent(graded_submissions, total_submissions)
    pending_assignments = (
        submissions.filter(status=SubmissionStatus.SUBMITTED).count() if total_submissions else 0
    )

    # -- Projects: required work, and what is still waiting on a review.
    required_projects = StudentProject.objects.filter(
        enrollment__batch_id__in=batch_ids, project__is_required=True
    )
    total_required_projects = required_projects.count()
    finished_required_projects = (
        required_projects.filter(status__in=list(FINISHED_STATUSES)).count()
        if total_required_projects
        else 0
    )
    project_completion_percent = _percent(finished_required_projects, total_required_projects)
    pending_projects = StudentProject.objects.filter(
        enrollment__batch_id__in=batch_ids,
        status__in=(WorkStatus.SUBMITTED, WorkStatus.UNDER_REVIEW),
    ).count()

    # -- Assessments: expected results, per test, against what has been entered.
    assessments = list(
        Assessment.objects.student_visible()
        .filter(batch_id__in=batch_ids)
        .values("id", "batch_id", "closes_at")
    )
    enrollment_counts = dict(
        Enrollment.objects.filter(batch_id__in=batch_ids, status__in=counted_statuses)
        .values_list("batch_id")
        .annotate(total=Count("id"))
    )
    total_expected_results = 0
    total_recorded_results = 0
    pending_assessments = 0
    overdue_assessments = 0
    if assessments:
        recorded_by_assessment = dict(
            AssessmentResult.objects.filter(assessment_id__in=[row["id"] for row in assessments])
            .values_list("assessment_id")
            .annotate(total=Count("id"))
        )
        now = timezone.now()
        for row in assessments:
            expected = enrollment_counts.get(row["batch_id"], 0)
            recorded = min(recorded_by_assessment.get(row["id"], 0), expected)
            total_expected_results += expected
            total_recorded_results += recorded
            shortfall = expected - recorded
            pending_assessments += shortfall
            if row["closes_at"] and row["closes_at"] < now:
                overdue_assessments += shortfall
    assessment_completion_percent = _percent(total_recorded_results, total_expected_results)

    # -- Everything the cohort's own performance numbers already carry: their
    # average score, and how many assignments they have let go overdue.
    bulk = student_performance_bulk(enrollment_rows)
    scores = [row["overall_score"] for row in bulk.values() if row["overall_score"] is not None]
    student_average_score = round(sum(scores) / len(scores), 1) if scores else None
    missed_assignments_total = sum(row["assignments"]["missed"] for row in bulk.values())

    # Required projects still open on a batch whose run has already ended:
    # there is no more class time left for them to be finished in.
    today = timezone.localdate()
    projects_overdue = sum(
        max(
            bulk[enrollment.pk]["projects"]["required"]
            - bulk[enrollment.pk]["projects"]["finished"],
            0,
        )
        for enrollment in enrollment_rows
        if enrollment.batch.end_date < today
    )

    pending_work = {
        "assignments": pending_assignments,
        "projects": pending_projects,
        "assessments": pending_assessments,
    }
    pending_work["total"] = sum(pending_work.values())

    overdue_work = {
        "assignments": missed_assignments_total,
        "projects": projects_overdue,
        "assessments": overdue_assessments,
    }
    overdue_work["total"] = sum(overdue_work.values())

    return {
        "trainer_id": str(trainer.pk),
        "batches_handled": batches_handled,
        "students_handled": students_handled,
        "attendance_submission_rate": attendance_submission_rate,
        "dsr_submission_rate": dsr_submission_rate,
        "dsr_submitted_count": dsr_submitted_count,
        "assignment_completion_percent": assignment_completion_percent,
        "assessment_completion_percent": assessment_completion_percent,
        "project_completion_percent": project_completion_percent,
        "student_average_score": student_average_score,
        "pending_work": pending_work,
        "overdue_work": overdue_work,
        "counts": {
            "batches": batches_handled,
            "students": students_handled,
            "sessions_taken": total_sessions,
        },
    }
