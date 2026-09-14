"""The reports §8.3 asks for.

Each report is a function returning ``(columns, rows)`` — a list of column
definitions and an iterable of dictionaries. That shape is what lets the same
report be rendered as JSON for a screen and streamed as CSV for a download
without writing it twice, and it is why :mod:`apps.reporting.exports` needs no
knowledge of any individual report.

Rows are produced from a **scoped queryset** passed in by the caller, so a
report cannot widen its own access. Every one of them is also written to avoid
loading a whole institution into memory: they iterate, and the export streams.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Column:
    key: str
    label: str


@dataclass(frozen=True)
class Report:
    key: str
    label: str
    description: str
    columns: tuple[Column, ...]

    def column_dicts(self) -> list[dict[str, str]]:
        return [{"key": column.key, "label": column.label} for column in self.columns]


def _grade(policy, percent) -> str:
    return policy.grade_for(percent) if percent is not None else ""


# ---------------------------------------------------------------------------
# Student progress
# ---------------------------------------------------------------------------

STUDENT_PROGRESS = Report(
    key="student_progress",
    label="Student progress",
    description="Where every student stands on every activity, from the one progress calculation.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("course_title", "Course"),
        Column("lessons_percent", "Lessons %"),
        Column("attendance_percent", "Attendance %"),
        Column("assignments_submitted", "Assignments in"),
        Column("assignments_total", "Assignments set"),
        Column("tests_recorded", "Tests sat"),
        Column("test_average", "Test average %"),
        Column("projects_finished", "Projects done"),
        Column("projects_required", "Projects required"),
        Column("completion_status", "Completion"),
    ),
)


#: How many enrolments one gathered batch covers. The point of the bulk path is
#: a query count that does not grow with the cohort; the point of chunking it is
#: that the gathered inputs for a whole institution would not fit in memory.
CHUNK = 200


def _chunks(queryset, size: int = CHUNK) -> Iterator[list]:
    """Walk a queryset in fixed-size lists, holding one chunk at a time."""
    chunk: list = []
    for row in queryset.iterator(chunk_size=size):
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def student_progress(enrollments) -> Iterator[dict[str, Any]]:
    """Every student's standing, from the one progress calculation.

    Reads the bulk inputs rather than calling the single-student report per row:
    that cost seventeen queries a student, so a page of five hundred was eight
    thousand round trips. The arithmetic is the same function either way.
    """
    from apps.progress.bulk import ProgressInputs
    from apps.progress.reports import progress_report

    base = enrollments.select_related("student", "student__user", "batch", "course")
    for chunk in _chunks(base):
        data = ProgressInputs(chunk)
        decided = {key: row.status for key, row in data.completions.items()}
        for enrollment in chunk:
            report = progress_report(enrollment, data)
            yield {
                "student_code": enrollment.student.student_id,
                "student_name": enrollment.student.user.get_full_name(),
                "batch_code": enrollment.batch.code,
                "course_title": enrollment.course.title,
                "lessons_percent": report["lessons"]["percent"],
                "attendance_percent": report["attendance"]["percent"],
                "assignments_submitted": report["assignments"]["submitted"],
                "assignments_total": report["assignments"]["total"],
                "tests_recorded": report["tests"]["recorded"],
                "test_average": report["tests"]["average_percent"],
                "projects_finished": report["projects"]["finished"],
                "projects_required": report["projects"]["required"],
                "completion_status": decided.get(enrollment.pk, "in_progress"),
            }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

ATTENDANCE = Report(
    key="attendance",
    label="Attendance",
    description="Per student: classes counted, attended, and the percentage against the rule.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("total_sessions", "Counted"),
        Column("present", "Present"),
        Column("late", "Late"),
        Column("absent", "Absent"),
        Column("excused", "Excused"),
        Column("percent", "Attendance %"),
        Column("required_percent", "Required %"),
        Column("meets_requirement", "Meets it"),
    ),
)


def attendance(enrollments) -> Iterator[dict[str, Any]]:
    """Per student, against the attendance rule in force for their course.

    The counts come from one grouped query per chunk instead of five per
    student; the rule is still applied by `attendance_requirement`, so the
    threshold and the verdict keep one owner.
    """
    from apps.academics.policies import attendance_requirement
    from apps.attendance.models import attendance_summaries

    base = enrollments.select_related("student", "student__user", "batch", "course")
    for chunk in _chunks(base):
        summaries = attendance_summaries([enrollment.pk for enrollment in chunk])
        for enrollment in chunk:
            verdict = attendance_requirement(enrollment, summary=summaries[enrollment.pk])
            yield {
                "student_code": enrollment.student.student_id,
                "student_name": enrollment.student.user.get_full_name(),
                "batch_code": enrollment.batch.code,
                "total_sessions": verdict["total_sessions"],
                "present": verdict["present"],
                "late": verdict["late"],
                "absent": verdict["absent"],
                "excused": verdict["excused"],
                "percent": verdict["percentage"],
                "required_percent": str(verdict["minimum_percent"]),
                "meets_requirement": verdict["met"],
            }


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

ASSIGNMENTS = Report(
    key="assignments",
    label="Assignment completion",
    description="Every published assignment against every student it applies to.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("assignment_code", "Assignment"),
        Column("assignment_title", "Title"),
        Column("status", "Status"),
        Column("attempt", "Attempt"),
        Column("is_late", "Late"),
        Column("marks_awarded", "Marks"),
        Column("max_marks", "Out of"),
        Column("grade", "Grade"),
    ),
)


def assignments(enrollments) -> Iterator[dict[str, Any]]:
    from apps.academics.policies import policy_for
    from apps.assignments.models import Assignment, AssignmentSubmission

    rows = list(enrollments.select_related("student", "student__user", "batch", "course"))
    if not rows:
        return

    published = list(
        Assignment.objects.student_visible().filter(course_id__in={row.course_id for row in rows})
    )
    submissions: dict = {}
    for submission in AssignmentSubmission.objects.filter(
        enrollment__in=rows, assignment__in=published
    ).select_related("assignment"):
        key = (submission.enrollment_id, submission.assignment_id)
        current = submissions.get(key)
        if current is None or submission.attempt > current.attempt:
            submissions[key] = submission

    for enrollment in rows:
        policy = policy_for(enrollment.course_id)
        for assignment in published:
            if assignment.course_id != enrollment.course_id:
                continue
            if not assignment.applies_to_batch(enrollment.batch_id):
                continue
            submission = submissions.get((enrollment.pk, assignment.pk))
            percent = (
                float(submission.marks_awarded) / float(assignment.max_marks) * 100
                if submission and submission.marks_awarded is not None
                else None
            )
            yield {
                "student_code": enrollment.student.student_id,
                "student_name": enrollment.student.user.get_full_name(),
                "batch_code": enrollment.batch.code,
                "assignment_code": assignment.code,
                "assignment_title": assignment.title,
                "status": submission.status if submission else "not_submitted",
                "attempt": submission.attempt if submission else 0,
                "is_late": submission.is_late if submission else None,
                "marks_awarded": str(submission.marks_awarded)
                if submission and submission.marks_awarded is not None
                else "",
                "max_marks": str(assignment.max_marks),
                "grade": _grade(policy, percent),
            }


# ---------------------------------------------------------------------------
# Weekly tests, projects, exams
# ---------------------------------------------------------------------------

TEST_RESULTS = Report(
    key="test_results",
    label="Weekly test results",
    description="Every recorded weekly-test result, with the grade band applied.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("assessment_code", "Test"),
        Column("assessment_title", "Title"),
        Column("marks_obtained", "Marks"),
        Column("max_marks", "Out of"),
        Column("percent", "%"),
        Column("grade", "Grade"),
        Column("is_absent", "Absent"),
        Column("source", "Source"),
    ),
)


def test_results(enrollments) -> Iterator[dict[str, Any]]:
    from apps.academics.policies import policy_for
    from apps.assessments.models import AssessmentResult

    rows = AssessmentResult.objects.filter(enrollment__in=enrollments).select_related(
        "assessment",
        "enrollment",
        "enrollment__student",
        "enrollment__student__user",
        "enrollment__batch",
    )
    for result in rows.iterator(chunk_size=200):
        policy = policy_for(result.assessment.course_id)
        yield {
            "student_code": result.enrollment.student.student_id,
            "student_name": result.enrollment.student.user.get_full_name(),
            "batch_code": result.enrollment.batch.code,
            "assessment_code": result.assessment.code,
            "assessment_title": result.assessment.title,
            "marks_obtained": str(result.marks_obtained) if result.marks_obtained else "",
            "max_marks": str(result.assessment.max_marks),
            "percent": result.percentage,
            "grade": _grade(policy, result.percentage),
            "is_absent": result.is_absent,
            "source": result.source,
        }


PROJECT_RESULTS = Report(
    key="project_results",
    label="Project results",
    description="Every project handed out, where it stands and what it scored.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("project_code", "Project"),
        Column("project_title", "Title"),
        Column("is_required", "Required"),
        Column("status", "Status"),
        Column("submitted_at", "Handed in"),
        Column("marks_awarded", "Marks"),
        Column("max_marks", "Out of"),
    ),
)


def project_results(enrollments) -> Iterator[dict[str, Any]]:
    from apps.projects.models import StudentProject

    rows = StudentProject.objects.filter(enrollment__in=enrollments).select_related(
        "project",
        "enrollment",
        "enrollment__student",
        "enrollment__student__user",
        "enrollment__batch",
    )
    for work in rows.iterator(chunk_size=200):
        yield {
            "student_code": work.enrollment.student.student_id,
            "student_name": work.enrollment.student.user.get_full_name(),
            "batch_code": work.enrollment.batch.code,
            "project_code": work.project.code,
            "project_title": work.project.title,
            "is_required": work.project.is_required,
            "status": work.status,
            "submitted_at": work.submitted_at,
            "marks_awarded": str(work.marks_awarded) if work.marks_awarded is not None else "",
            "max_marks": str(work.project.max_marks),
        }


EXAM_RESULTS = Report(
    key="exam_results",
    label="Examination results",
    description="Every sitting, its score and whether it reached the pass mark.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("exam_code", "Examination"),
        Column("exam_title", "Title"),
        Column("attempt_number", "Attempt"),
        Column("status", "Status"),
        Column("total_score", "Score"),
        Column("max_score", "Out of"),
        Column("percent", "%"),
        Column("grade", "Grade"),
        Column("is_passing", "Passed"),
    ),
)


def exam_results(enrollments) -> Iterator[dict[str, Any]]:
    from apps.academics.policies import policy_for
    from apps.exams.models import ExamAttempt

    rows = ExamAttempt.objects.filter(enrollment__in=enrollments).select_related(
        "exam",
        "enrollment",
        "enrollment__student",
        "enrollment__student__user",
        "enrollment__batch",
    )
    for attempt in rows.iterator(chunk_size=200):
        policy = policy_for(attempt.exam.course_id)
        yield {
            "student_code": attempt.enrollment.student.student_id,
            "student_name": attempt.enrollment.student.user.get_full_name(),
            "batch_code": attempt.enrollment.batch.code,
            "exam_code": attempt.exam.code,
            "exam_title": attempt.exam.title,
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
            "total_score": str(attempt.total_score) if attempt.total_score is not None else "",
            "max_score": str(attempt.max_score),
            "percent": attempt.percentage,
            "grade": _grade(policy, attempt.percentage),
            "is_passing": attempt.is_passing,
        }


# ---------------------------------------------------------------------------
# Completion, batches, trainers, certificates
# ---------------------------------------------------------------------------

COMPLETION = Report(
    key="completion",
    label="Course completion",
    description="Where each enrolment stands against the completion rules, and what was decided.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("batch_code", "Batch"),
        Column("course_title", "Course"),
        Column("status", "Status"),
        Column("became_eligible_at", "Became eligible"),
        Column("completed_on", "Completed"),
        Column("decided_by", "Decided by"),
    ),
)


def completion(enrollments) -> Iterator[dict[str, Any]]:
    from apps.progress.models import CourseCompletion

    rows = CourseCompletion.objects.filter(enrollment__in=enrollments).with_related()
    for row in rows.iterator(chunk_size=200):
        yield {
            "student_code": row.enrollment.student.student_id,
            "student_name": row.enrollment.student.user.get_full_name(),
            "batch_code": row.enrollment.batch.code,
            "course_title": row.enrollment.course.title,
            "status": row.status,
            "became_eligible_at": row.became_eligible_at,
            "completed_on": row.completed_on,
            "decided_by": row.decided_by.get_full_name() if row.decided_by else "",
        }


BATCH_PERFORMANCE = Report(
    key="batch_performance",
    label="Batch performance",
    description="One row per batch: size, attendance, completion and pending work.",
    columns=(
        Column("batch_code", "Batch"),
        Column("batch_name", "Name"),
        Column("course_title", "Course"),
        Column("trainer_name", "Trainer"),
        Column("status", "Status"),
        Column("students", "Students"),
        Column("attendance_percent", "Attendance %"),
        Column("completion_percent", "Completed %"),
        Column("pending_marking", "Awaiting marking"),
    ),
)


def batch_performance(batches) -> Iterator[dict[str, Any]]:
    """One row per batch, with its headline numbers.

    The numbers come from `metrics.by_batch`, which computes them for a whole
    chunk at once and — because it sits beside the metric definitions — cannot
    drift from what the metrics page reports.
    """
    from . import metrics

    base = batches.select_related("course", "trainer", "trainer__user")
    for chunk in _chunks(base, 50):
        computed = metrics.by_batch([batch.pk for batch in chunk])
        for batch in chunk:
            numbers = computed[batch.pk]
            yield {
                "batch_code": batch.code,
                "batch_name": batch.name,
                "course_title": batch.course.title,
                "trainer_name": batch.trainer.user.get_full_name() if batch.trainer else "",
                "status": batch.status,
                "students": numbers["students"],
                "attendance_percent": numbers["attendance_percent"],
                "completion_percent": numbers["completion_percent"],
                "pending_marking": numbers["pending_marking"],
            }


TRAINER_ACTIVITY = Report(
    key="trainer_activity",
    label="Trainer activity",
    description=(
        "What each trainer has done inside the LMS: batches taught, registers taken, "
        "work marked. Deliberately not a productivity score — it counts actions, and "
        "an action is not an outcome."
    ),
    columns=(
        Column("trainer_code", "Trainer"),
        Column("trainer_name", "Name"),
        Column("batches", "Batches"),
        Column("sessions_marked", "Registers taken"),
        Column("assignments_graded", "Assignments marked"),
        Column("projects_reviewed", "Projects reviewed"),
    ),
)


def trainer_activity(trainers) -> Iterator[dict[str, Any]]:
    """What each trainer has done, counted for the whole chunk in four queries.

    Not four per trainer: the previous shape asked the database once per trainer
    per column, which is a page of thirty trainers costing a hundred and twenty
    round trips to render six numbers each.
    """
    from django.db.models import Count

    from apps.assignments.models import AssignmentSubmission
    from apps.attendance.models import AttendanceRecord
    from apps.batches.models import Batch
    from apps.projects.models import StudentProject

    for chunk in _chunks(trainers.select_related("user"), 50):
        trainer_ids = [trainer.pk for trainer in chunk]
        user_ids = [trainer.user_id for trainer in chunk]

        batches = dict(
            Batch.objects.filter(trainer_id__in=trainer_ids)
            .values_list("trainer_id")
            .annotate(total=Count("id"))
        )
        registers = dict(
            AttendanceRecord.objects.filter(marked_by_id__in=user_ids)
            .values_list("marked_by_id")
            .annotate(total=Count("session_id", distinct=True))
        )
        graded = dict(
            AssignmentSubmission.objects.filter(graded_by_id__in=user_ids)
            .values_list("graded_by_id")
            .annotate(total=Count("id"))
        )
        reviewed = dict(
            StudentProject.objects.filter(reviewer_id__in=trainer_ids)
            .values_list("reviewer_id")
            .annotate(total=Count("id"))
        )

        for trainer in chunk:
            yield {
                "trainer_code": trainer.trainer_id,
                "trainer_name": trainer.user.get_full_name(),
                "batches": batches.get(trainer.pk, 0),
                "sessions_marked": registers.get(trainer.user_id, 0),
                "assignments_graded": graded.get(trainer.user_id, 0),
                "projects_reviewed": reviewed.get(trainer.pk, 0),
            }


CERTIFICATES = Report(
    key="certificates",
    label="Certificates",
    description="Every certificate issued, and its current standing.",
    columns=(
        Column("number", "Certificate"),
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("course_title", "Course"),
        Column("batch_code", "Batch"),
        Column("completion_date", "Completed"),
        Column("issued_at", "Issued"),
        Column("status", "Status"),
    ),
)


def certificates(enrollments) -> Iterator[dict[str, Any]]:
    from apps.certificates.models import Certificate

    rows = Certificate.objects.filter(completion__enrollment__in=enrollments).select_related(
        "completion"
    )
    for certificate in rows.iterator(chunk_size=200):
        yield {
            "number": certificate.number,
            "student_code": certificate.student_code,
            "student_name": certificate.student_name,
            "course_title": certificate.course_title,
            "batch_code": certificate.batch_code,
            "completion_date": certificate.completion_date,
            "issued_at": certificate.issued_at,
            "status": certificate.status,
        }


#: Report key → (definition, row producer, what the producer takes).
#:
#: The third element says which scoped queryset the producer expects, so the
#: view can build the right one without a branch per report.
REPORTS: dict[str, tuple[Report, Any, str]] = {
    STUDENT_PROGRESS.key: (STUDENT_PROGRESS, student_progress, "enrollments"),
    ATTENDANCE.key: (ATTENDANCE, attendance, "enrollments"),
    ASSIGNMENTS.key: (ASSIGNMENTS, assignments, "enrollments"),
    TEST_RESULTS.key: (TEST_RESULTS, test_results, "enrollments"),
    PROJECT_RESULTS.key: (PROJECT_RESULTS, project_results, "enrollments"),
    EXAM_RESULTS.key: (EXAM_RESULTS, exam_results, "enrollments"),
    COMPLETION.key: (COMPLETION, completion, "enrollments"),
    BATCH_PERFORMANCE.key: (BATCH_PERFORMANCE, batch_performance, "batches"),
    TRAINER_ACTIVITY.key: (TRAINER_ACTIVITY, trainer_activity, "trainers"),
    CERTIFICATES.key: (CERTIFICATES, certificates, "enrollments"),
}


def catalogue() -> list[dict[str, Any]]:
    """Every report, with its columns. What a reports screen renders from."""
    return [
        {
            "key": report.key,
            "label": report.label,
            "description": report.description,
            "columns": report.column_dicts(),
            "source": source,
        }
        for report, _producer, source in REPORTS.values()
    ]


def run(key: str, queryset) -> tuple[Report, Iterable[dict[str, Any]]]:
    report, producer, _source = REPORTS[key]
    return report, producer(queryset)


# ---------------------------------------------------------------------------
# The list screens as reports (14 September 2026: "everything exportable")
# ---------------------------------------------------------------------------
#
# Each of these mirrors a screen an administrator, manager or counsellor reads
# every day — students, enrolments, the fee ledger, daily reports, batches, the
# activity record — so that "export what I am looking at" is the same rows the
# screen showed, through the same scoped queryset, in CSV, Excel or PDF.


def _fmt_money(value) -> str:
    if value is None:
        return ""
    try:
        return f"{value:,.2f}"
    except (TypeError, ValueError):
        return str(value)


STUDENTS = Report(
    key="students",
    label="Students",
    description="Every student record with contact, background and what the fee ledger says.",
    columns=(
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("email", "Email"),
        Column("phone", "Phone"),
        Column("city", "City"),
        Column("centre", "Centre"),
        Column("institution", "College / employer"),
        Column("qualification", "Qualification"),
        Column("fee_status", "Fee status"),
        Column("fee_payable", "Fee agreed"),
        Column("fee_paid", "Paid"),
        Column("fee_balance", "Balance"),
        Column("fee_next_due_on", "Next expected"),
        Column("registered_on", "Registered"),
    ),
)


def students(profiles) -> Iterator[dict[str, Any]]:
    from apps.fees.queries import annotate_student_fee_totals

    rows = annotate_student_fee_totals(
        profiles.select_related("user", "branch").order_by("student_id")
    )
    for profile in rows.iterator(chunk_size=CHUNK):
        yield {
            "student_code": profile.student_id,
            "student_name": profile.user.get_full_name(),
            "email": profile.user.email,
            "phone": profile.user.phone,
            "city": profile.city,
            "centre": profile.branch.name if profile.branch_id else "",
            "institution": profile.institution,
            "qualification": profile.get_qualification_display() if profile.qualification else "",
            "fee_status": profile.get_fee_status_display(),
            "fee_payable": _fmt_money(profile.fee_payable),
            "fee_paid": _fmt_money(profile.fee_paid),
            "fee_balance": _fmt_money(profile.fee_balance),
            "fee_next_due_on": profile.fee_next_due_on,
            "registered_on": profile.created_at.date(),
        }


ENROLLMENTS = Report(
    key="enrollments",
    label="Enrolments",
    description="Every enrolment: who is on which batch, its status, and the fee against it.",
    columns=(
        Column("enrollment_code", "Enrolment"),
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("course_title", "Course"),
        Column("batch_code", "Batch"),
        Column("trainer_name", "Trainer"),
        Column("status", "Status"),
        Column("enrolled_on", "Enrolled"),
        Column("fee_payable", "Fee agreed"),
        Column("fee_paid", "Paid"),
        Column("fee_balance", "Balance"),
        Column("fee_next_due_on", "Next expected"),
    ),
)


def enrollments(rows) -> Iterator[dict[str, Any]]:
    from apps.fees.queries import annotate_enrollment_fee

    base = annotate_enrollment_fee(
        rows.select_related("student__user", "course", "batch__trainer__user").order_by(
            "-enrolled_at"
        )
    )
    for enrollment in base.iterator(chunk_size=CHUNK):
        trainer = enrollment.batch.trainer
        yield {
            "enrollment_code": enrollment.code,
            "student_code": enrollment.student.student_id,
            "student_name": enrollment.student.user.get_full_name(),
            "course_title": enrollment.course.title,
            "batch_code": enrollment.batch.code,
            "trainer_name": trainer.user.get_full_name() if trainer else "",
            "status": enrollment.get_status_display(),
            "enrolled_on": enrollment.enrolled_at.date(),
            "fee_payable": _fmt_money(enrollment.fee_payable),
            "fee_paid": _fmt_money(enrollment.fee_paid),
            "fee_balance": _fmt_money(enrollment.fee_balance),
            "fee_next_due_on": enrollment.fee_next_due_on,
        }


FEE_PAYMENTS = Report(
    key="fee_payments",
    label="Fee payments",
    description="The ledger, one line per payment, voided ones marked rather than hidden.",
    columns=(
        Column("receipt_number", "Receipt"),
        Column("paid_on", "Paid on"),
        Column("student_code", "Student"),
        Column("student_name", "Name"),
        Column("course_title", "Course"),
        Column("batch_code", "Batch"),
        Column("amount", "Amount"),
        Column("method", "Method"),
        Column("reference", "Reference"),
        Column("recorded_by", "Recorded by"),
        Column("voided", "Voided"),
        Column("void_reason", "Void reason"),
    ),
)


def fee_payments(payments) -> Iterator[dict[str, Any]]:
    base = payments.select_related(
        "plan__enrollment__student__user",
        "plan__enrollment__course",
        "plan__enrollment__batch",
        "recorded_by",
    ).order_by("-paid_on", "-created_at")
    for payment in base.iterator(chunk_size=CHUNK):
        enrollment = payment.plan.enrollment
        yield {
            "receipt_number": payment.receipt_number,
            "paid_on": payment.paid_on,
            "student_code": enrollment.student.student_id,
            "student_name": enrollment.student.user.get_full_name(),
            "course_title": enrollment.course.title,
            "batch_code": enrollment.batch.code,
            "amount": _fmt_money(payment.amount),
            "method": payment.get_method_display(),
            "reference": payment.reference,
            "recorded_by": payment.recorded_by.get_full_name() if payment.recorded_by else "",
            "voided": "yes" if payment.is_voided else "",
            "void_reason": payment.void_reason,
        }


DAILY_REPORTS = Report(
    key="daily_reports",
    label="Daily reports",
    description="Every daily status report: the class, the trainer, the counts and its review.",
    columns=(
        Column("report_date", "Date"),
        Column("batch_code", "Batch"),
        Column("trainer_name", "Trainer"),
        Column("status", "Status"),
        Column("planned_topic", "Planned"),
        Column("actual_topic", "Taught"),
        Column("student_count", "Roster"),
        Column("present_count", "Present"),
        Column("absent_count", "Absent"),
        Column("issues", "Issues"),
        Column("reviewed_by", "Reviewed by"),
        Column("reviewed_at", "Reviewed at"),
    ),
)


def daily_reports(reports_qs) -> Iterator[dict[str, Any]]:
    base = reports_qs.select_related("batch", "trainer__user", "reviewed_by").order_by(
        "-report_date"
    )
    for dsr in base.iterator(chunk_size=CHUNK):
        yield {
            "report_date": dsr.report_date,
            "batch_code": dsr.batch.code,
            "trainer_name": dsr.trainer.user.get_full_name() if dsr.trainer_id else "",
            "status": dsr.get_status_display(),
            "planned_topic": dsr.planned_topic,
            "actual_topic": dsr.actual_topic,
            "student_count": dsr.student_count,
            "present_count": dsr.present_count,
            "absent_count": dsr.absent_count,
            "issues": dsr.issues,
            "reviewed_by": dsr.reviewed_by.get_full_name() if dsr.reviewed_by_id else "",
            "reviewed_at": dsr.reviewed_at,
        }


BATCHES = Report(
    key="batches",
    label="Batches",
    description="Every batch: course, centre, trainer, dates, capacity and seats taken.",
    columns=(
        Column("batch_code", "Batch"),
        Column("batch_name", "Name"),
        Column("course_title", "Course"),
        Column("centre", "Centre"),
        Column("trainer_name", "Trainer"),
        Column("status", "Status"),
        Column("start_date", "Starts"),
        Column("end_date", "Ends"),
        Column("capacity", "Capacity"),
        Column("enrolled", "Enrolled"),
        Column("seats_left", "Seats left"),
    ),
)


def batches(rows) -> Iterator[dict[str, Any]]:
    from django.db.models import Count, Q

    from apps.enrollments.models import LIVE_STATUSES

    base = (
        rows.select_related("course", "branch", "trainer__user")
        .annotate(live=Count("enrollments", filter=Q(enrollments__status__in=LIVE_STATUSES)))
        .order_by("-start_date")
    )
    for batch in base.iterator(chunk_size=CHUNK):
        yield {
            "batch_code": batch.code,
            "batch_name": batch.name,
            "course_title": batch.course.title,
            "centre": batch.branch.name if batch.branch_id else "",
            "trainer_name": batch.trainer.user.get_full_name() if batch.trainer_id else "",
            "status": batch.get_status_display(),
            "start_date": batch.start_date,
            "end_date": batch.end_date,
            "capacity": batch.capacity,
            "enrolled": batch.live,
            "seats_left": max(batch.capacity - batch.live, 0),
        }


ACTIVITY = Report(
    key="activity",
    label="Activity record",
    description=(
        "Who did what, when — the audit log without the noise, as the activity review shows it."
    ),
    columns=(
        Column("when", "When"),
        Column("actor", "Who"),
        Column("role", "Role"),
        Column("centre", "Centre"),
        Column("action", "Action"),
        Column("kind", "Kind"),
        Column("summary", "What"),
        Column("resource_type", "Record"),
        Column("resource_id", "Record id"),
    ),
)


def activity(entries) -> Iterator[dict[str, Any]]:
    from apps.activity import services as activity_services

    for entry in entries.iterator(chunk_size=CHUNK):
        actor = entry.actor
        yield {
            "when": entry.created_at,
            "actor": entry.actor_label or (actor.email if actor else "system"),
            "role": actor.role if actor else "",
            "centre": actor.branch.name if actor and actor.branch_id else "",
            "action": entry.get_action_display(),
            "kind": activity_services.kind_of(entry.action),
            "summary": activity_services.describe(entry),
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
        }


REPORTS.update(
    {
        STUDENTS.key: (STUDENTS, students, "students"),
        ENROLLMENTS.key: (ENROLLMENTS, enrollments, "enrollments"),
        FEE_PAYMENTS.key: (FEE_PAYMENTS, fee_payments, "fee_payments"),
        DAILY_REPORTS.key: (DAILY_REPORTS, daily_reports, "dsrs"),
        BATCHES.key: (BATCHES, batches, "batches"),
        ACTIVITY.key: (ACTIVITY, activity, "activity"),
    }
)
