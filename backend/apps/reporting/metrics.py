"""LMS metrics — §8.6, and the definitions §8.6 requires.

    "Every metric must have a documented definition."

So each metric is a :class:`Metric` carrying its own definition text, and the
API returns that definition alongside the number. A figure on a dashboard with
no stated definition is a figure two people will read differently and act on
differently, and the disagreement surfaces months later in a meeting.

The definitions are deliberately specific about the awkward cases — what counts
as "enrolled", whether an absence counts as a sitting, which attempt of several
is measured — because those are exactly the choices that make two
implementations of "completion rate" disagree by ten points.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q


@dataclass(frozen=True)
class Metric:
    """One number, and what it means."""

    key: str
    label: str
    definition: str
    unit: str = "percent"

    def as_dict(self, value, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "definition": self.definition,
            "unit": self.unit,
            "value": value,
            **(extra or {}),
        }


def _percent(part: int, whole: int) -> float | None:
    """A percentage, or ``None`` when there is nothing to divide by.

    Zero would be a lie: "0% of nothing completed" reads as a failure when it
    means there was nothing to complete.
    """
    return round(part * 100 / whole, 2) if whole else None


# ---------------------------------------------------------------------------
# The definitions
# ---------------------------------------------------------------------------

COMPLETION_RATE = Metric(
    key="course_completion_rate",
    label="Course completion rate",
    definition=(
        "Enrolments whose completion has been approved, as a percentage of all "
        "enrolments that are active, completed or suspended. Cancelled enrolments "
        "are excluded entirely — a student who withdrew is not a failure to "
        "complete. Counted per enrolment, so a student taking two courses counts "
        "twice."
    ),
)

ATTENDANCE_RATE = Metric(
    key="attendance_rate",
    label="Attendance rate",
    definition=(
        "Attendance records marked present or late, as a percentage of all records "
        "except those marked excused. Excused absences leave the denominator, so a "
        "student excused for half a term is not penalised. Classes with no register "
        "taken are not counted at all."
    ),
)

ASSIGNMENT_COMPLETION_RATE = Metric(
    key="assignment_completion_rate",
    label="Assignment completion rate",
    definition=(
        "Distinct (student, assignment) pairs with at least one submission, as a "
        "percentage of every pair that should exist — each published assignment "
        "multiplied by the students it applies to. Several attempts at one "
        "assignment count once."
    ),
)

TEST_AVERAGE = Metric(
    key="test_average",
    label="Weekly test average",
    definition=(
        "Marks obtained divided by marks available, across every recorded weekly-test "
        "result. A student marked absent contributes neither a mark nor a maximum, so "
        "absences do not drag the average down; they show in the sitting rate instead."
    ),
)

EXAM_PASS_RATE = Metric(
    key="exam_pass_rate",
    label="Examination pass rate",
    definition=(
        "Candidates whose best graded attempt reached the pass mark, as a percentage "
        "of candidates with at least one graded attempt. Judged on the best attempt "
        "where several are allowed. Attempts still awaiting marking are excluded, not "
        "counted as failures."
    ),
)

PROJECT_COMPLETION_RATE = Metric(
    key="project_completion_rate",
    label="Project completion rate",
    definition=(
        "Required projects approved or completed, as a percentage of required "
        "projects assigned. Optional projects are excluded, because they cannot be "
        "outstanding."
    ),
)

AVERAGE_PROGRESS = Metric(
    key="average_course_progress",
    label="Average course progress",
    definition=(
        "The mean of each enrolment's published-lesson completion percentage. "
        "Enrolments on courses with no published lessons are excluded rather than "
        "counted as zero."
    ),
)

ACTIVE_LEARNERS = Metric(
    key="active_learners",
    label="Active learners",
    definition=(
        "Students who opened at least one lesson in the last 14 days. An activity "
        "indicator, not attendance: it says who is using the system, which is a "
        "different question from who is turning up."
    ),
    unit="count",
)

PENDING_MARKING = Metric(
    key="pending_marking",
    label="Work awaiting marking",
    definition=(
        "Assignment submissions not yet graded, plus examination answers flagged for "
        "manual marking. A workload figure, counted per item rather than per student."
    ),
    unit="count",
)


ALL_METRICS = (
    COMPLETION_RATE,
    ATTENDANCE_RATE,
    ASSIGNMENT_COMPLETION_RATE,
    TEST_AVERAGE,
    EXAM_PASS_RATE,
    PROJECT_COMPLETION_RATE,
    AVERAGE_PROGRESS,
    ACTIVE_LEARNERS,
    PENDING_MARKING,
)


# ---------------------------------------------------------------------------
# The calculations
# ---------------------------------------------------------------------------


def _enrollments(scope, *, statuses=None):
    """The enrolments a caller may count, narrowed to their own scope.

    ``statuses`` defaults to the three that mean "this enrolment is real" --
    the set every ratio metric has always used. A caller that genuinely needs
    the cancelled ones, such as the enrolment trend, passes its own set; it
    must never widen the default, because every existing metric reads it.
    """
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    if statuses is None:
        statuses = (
            EnrollmentStatus.ACTIVE,
            EnrollmentStatus.COMPLETED,
            EnrollmentStatus.SUSPENDED,
        )
    rows = Enrollment.objects.filter(status__in=tuple(statuses))
    if scope.get("batch"):
        rows = rows.filter(batch_id=scope["batch"])
    if scope.get("course"):
        rows = rows.filter(course_id=scope["course"])
    # A caller without the global capability carries the batches they may see.
    # Applied here rather than at the call sites so no metric can forget it.
    if "restrict_to_batches" in scope:
        rows = rows.filter(batch_id__in=scope["restrict_to_batches"])
    return rows


def _sessions(scope):
    """The class sessions a caller may count.

    A second choke point, for the same reason ``_enrollments`` is one. A
    session carries no per-row permission check of its own, so an aggregate
    that filtered ``ClassSession`` inline would hand a trainer every batch in
    the institution and nothing in the test suite would notice.

    ``ClassSession`` has no ``course`` FK; a batch's course is the only path.
    """
    from apps.sessions.models import ClassSession

    rows = ClassSession.objects.all()
    if scope.get("batch"):
        rows = rows.filter(batch_id=scope["batch"])
    if scope.get("course"):
        rows = rows.filter(batch__course_id=scope["course"])
    if "restrict_to_batches" in scope:
        rows = rows.filter(batch_id__in=scope["restrict_to_batches"])
    return rows


def _dsr(scope):
    """The daily status reports a caller may count.

    Through the default manager, so a soft-deleted report stays out of every
    aggregate built on it.
    """
    from apps.dsr.models import DSR

    rows = DSR.objects.all()
    if scope.get("batch"):
        rows = rows.filter(batch_id=scope["batch"])
    if scope.get("course"):
        rows = rows.filter(batch__course_id=scope["course"])
    if "restrict_to_batches" in scope:
        rows = rows.filter(batch_id__in=scope["restrict_to_batches"])
    return rows


def completion_rate(scope: dict) -> dict[str, Any]:
    from apps.progress.models import CompletionStatus, CourseCompletion

    enrollments = _enrollments(scope)
    total = enrollments.count()
    approved = CourseCompletion.objects.filter(
        enrollment__in=enrollments, status=CompletionStatus.APPROVED
    ).count()
    return COMPLETION_RATE.as_dict(
        _percent(approved, total), {"numerator": approved, "denominator": total}
    )


def attendance_rate(scope: dict) -> dict[str, Any]:
    from apps.attendance.models import COUNTS_AS_PRESENT, EXCLUDED_FROM_PERCENTAGE, AttendanceRecord

    rows = AttendanceRecord.objects.filter(enrollment__in=_enrollments(scope)).exclude(
        status__in=EXCLUDED_FROM_PERCENTAGE
    )
    counted = rows.count()
    attended = rows.filter(status__in=COUNTS_AS_PRESENT).count()
    return ATTENDANCE_RATE.as_dict(
        _percent(attended, counted), {"numerator": attended, "denominator": counted}
    )


def assignment_completion_rate(scope: dict) -> dict[str, Any]:
    from apps.assignments.models import Assignment, AssignmentSubmission

    enrollments = list(_enrollments(scope).select_related("batch"))
    if not enrollments:
        return ASSIGNMENT_COMPLETION_RATE.as_dict(None, {"numerator": 0, "denominator": 0})

    assignments = list(
        Assignment.objects.student_visible().filter(
            course_id__in={row.course_id for row in enrollments}
        )
    )
    expected = sum(
        1
        for row in enrollments
        for assignment in assignments
        if assignment.course_id == row.course_id and assignment.applies_to_batch(row.batch_id)
    )
    submitted = (
        AssignmentSubmission.objects.filter(enrollment__in=enrollments, assignment__in=assignments)
        .values("enrollment_id", "assignment_id")
        .distinct()
        .count()
    )
    return ASSIGNMENT_COMPLETION_RATE.as_dict(
        _percent(submitted, expected), {"numerator": submitted, "denominator": expected}
    )


def test_average(scope: dict) -> dict[str, Any]:
    from apps.assessments.models import AssessmentResult

    rows = AssessmentResult.objects.filter(
        enrollment__in=_enrollments(scope), marks_obtained__isnull=False
    ).select_related("assessment")

    obtained = Decimal("0")
    available = Decimal("0")
    for row in rows:
        obtained += row.marks_obtained
        available += row.assessment.max_marks

    value = round(float(obtained) / float(available) * 100, 2) if available else None
    return TEST_AVERAGE.as_dict(value, {"numerator": str(obtained), "denominator": str(available)})


def exam_pass_rate(scope: dict) -> dict[str, Any]:
    from apps.exams.models import AttemptStatus, ExamAttempt

    attempts = ExamAttempt.objects.filter(
        enrollment__in=_enrollments(scope),
        status=AttemptStatus.GRADED,
        total_score__isnull=False,
    ).select_related("exam", "enrollment")

    best: dict = {}
    for attempt in attempts:
        key = (attempt.enrollment_id, attempt.exam_id)
        current = best.get(key)
        if current is None or (attempt.percentage or 0) > (current.percentage or 0):
            best[key] = attempt

    total = len(best)
    passed = sum(1 for attempt in best.values() if attempt.is_passing)
    return EXAM_PASS_RATE.as_dict(
        _percent(passed, total), {"numerator": passed, "denominator": total}
    )


def project_completion_rate(scope: dict) -> dict[str, Any]:
    from apps.projects.models import FINISHED_STATUSES, StudentProject

    rows = StudentProject.objects.filter(
        enrollment__in=_enrollments(scope), project__is_required=True
    )
    total = rows.count()
    finished = rows.filter(status__in=list(FINISHED_STATUSES)).count()
    return PROJECT_COMPLETION_RATE.as_dict(
        _percent(finished, total), {"numerator": finished, "denominator": total}
    )


def average_progress(scope: dict) -> dict[str, Any]:
    """Averaged over enrolments, in SQL rather than one report per student."""
    from apps.courses.models import Lesson, PublishStatus
    from apps.enrollments.models import LessonProgressStatus

    enrollments = list(_enrollments(scope).select_related("course"))
    if not enrollments:
        return AVERAGE_PROGRESS.as_dict(None, {"denominator": 0})

    totals = dict(
        Lesson.objects.filter(
            module__course_id__in={row.course_id for row in enrollments},
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        )
        .values_list("module__course_id")
        .annotate(count=Count("id"))
    )
    from apps.enrollments.models import LessonProgress

    done = dict(
        LessonProgress.objects.filter(
            enrollment__in=enrollments,
            status=LessonProgressStatus.COMPLETED,
            lesson__status=PublishStatus.PUBLISHED,
            lesson__module__status=PublishStatus.PUBLISHED,
        )
        .values_list("enrollment_id")
        .annotate(count=Count("id"))
    )

    percentages = [
        done.get(row.pk, 0) * 100 / totals[row.course_id]
        for row in enrollments
        if totals.get(row.course_id)
    ]
    value = round(sum(percentages) / len(percentages), 2) if percentages else None
    return AVERAGE_PROGRESS.as_dict(value, {"denominator": len(percentages)})


def active_learners(scope: dict, *, days: int = 14) -> dict[str, Any]:
    from datetime import timedelta

    from django.utils import timezone

    from apps.enrollments.models import LessonProgress

    since = timezone.now() - timedelta(days=days)
    count = (
        LessonProgress.objects.filter(
            enrollment__in=_enrollments(scope), last_accessed_at__gte=since
        )
        .values("enrollment__student_id")
        .distinct()
        .count()
    )
    return ACTIVE_LEARNERS.as_dict(count, {"window_days": days})


def pending_marking(scope: dict) -> dict[str, Any]:
    from apps.assignments.models import AssignmentSubmission, SubmissionStatus
    from apps.exams.models import AttemptAnswer

    submissions = AssignmentSubmission.objects.filter(
        enrollment__in=_enrollments(scope), status=SubmissionStatus.SUBMITTED
    ).count()
    answers = AttemptAnswer.objects.filter(
        attempt_question__attempt__enrollment__in=_enrollments(scope),
        needs_manual_marking=True,
        awarded__isnull=True,
    ).count()
    return PENDING_MARKING.as_dict(
        submissions + answers, {"submissions": submissions, "exam_answers": answers}
    )


def by_batch(batch_ids: list, *, scope: dict | None = None) -> dict[Any, dict[str, Any]]:
    """Three of the metrics above, for many batches, in four queries.

    The batch-performance report needs completion, attendance and pending
    marking per batch. Calling the scalar functions once per batch cost seven
    queries each — a hundred batches was seven hundred round trips to render a
    page.

    This lives here, next to the definitions, rather than in the report. The
    filters below are the same constants and the same statuses the scalar
    functions use, and `tests/test_reporting.py` asserts the two agree for every
    batch; putting the grouped version anywhere else is how a report comes to
    show a number the metric page contradicts.
    """
    from django.db.models import Count, Q

    from apps.assignments.models import AssignmentSubmission, SubmissionStatus
    from apps.attendance.models import COUNTS_AS_PRESENT, EXCLUDED_FROM_PERCENTAGE
    from apps.exams.models import AttemptAnswer
    from apps.progress.models import CompletionStatus, CourseCompletion

    ids = list(batch_ids)
    if not ids:
        return {}

    base = _enrollments({**(scope or {}), "batch": None})
    enrollments = base.filter(batch_id__in=ids)

    totals = enrollments.values("batch_id").annotate(
        students=Count("id", distinct=True),
        counted=Count("attendance", filter=~Q(attendance__status__in=EXCLUDED_FROM_PERCENTAGE)),
        attended=Count("attendance", filter=Q(attendance__status__in=COUNTS_AS_PRESENT)),
    )
    approved = dict(
        CourseCompletion.objects.filter(
            enrollment__in=enrollments, status=CompletionStatus.APPROVED
        )
        .values_list("enrollment__batch_id")
        .annotate(total=Count("id"))
    )
    submissions = dict(
        AssignmentSubmission.objects.filter(
            enrollment__in=enrollments, status=SubmissionStatus.SUBMITTED
        )
        .values_list("enrollment__batch_id")
        .annotate(total=Count("id"))
    )
    answers = dict(
        AttemptAnswer.objects.filter(
            attempt_question__attempt__enrollment__in=enrollments,
            needs_manual_marking=True,
            awarded__isnull=True,
        )
        .values_list("attempt_question__attempt__enrollment__batch_id")
        .annotate(total=Count("id"))
    )

    result: dict[Any, dict[str, Any]] = {
        key: {
            "students": 0,
            "completion_percent": None,
            "attendance_percent": None,
            "pending_marking": 0,
        }
        for key in ids
    }
    for row in totals:
        batch_id = row["batch_id"]
        result[batch_id] = {
            "students": row["students"],
            "completion_percent": _percent(approved.get(batch_id, 0), row["students"]),
            "attendance_percent": _percent(row["attended"], row["counted"]),
            "pending_marking": submissions.get(batch_id, 0) + answers.get(batch_id, 0),
        }
    return result


#: metric key → calculation. The API iterates this, so adding a metric means
#: writing a `Metric` with its definition and one function.
CALCULATIONS: dict[str, Callable[[dict], dict[str, Any]]] = {
    COMPLETION_RATE.key: completion_rate,
    ATTENDANCE_RATE.key: attendance_rate,
    ASSIGNMENT_COMPLETION_RATE.key: assignment_completion_rate,
    TEST_AVERAGE.key: test_average,
    EXAM_PASS_RATE.key: exam_pass_rate,
    PROJECT_COMPLETION_RATE.key: project_completion_rate,
    AVERAGE_PROGRESS.key: average_progress,
    ACTIVE_LEARNERS.key: active_learners,
    PENDING_MARKING.key: pending_marking,
}


def compute(scope: dict, keys: list[str] | None = None) -> list[dict[str, Any]]:
    """Every metric, or the ones asked for, with their definitions attached."""
    wanted = keys or list(CALCULATIONS)
    return [CALCULATIONS[key](scope) for key in wanted if key in CALCULATIONS]


def attendance_trend(scope: dict, *, weeks: int = 12) -> list[dict[str, Any]]:
    """Attendance rate per week — §8.6's "attendance trends".

    Grouped in the database rather than by looping over weeks in Python, because
    a year of history is 52 queries the naive way.
    """
    from datetime import timedelta

    from django.db.models.functions import TruncWeek
    from django.utils import timezone

    from apps.attendance.models import COUNTS_AS_PRESENT, EXCLUDED_FROM_PERCENTAGE, AttendanceRecord

    since = timezone.localdate() - timedelta(weeks=weeks)
    rows = (
        AttendanceRecord.objects.filter(
            enrollment__in=_enrollments(scope), session__session_date__gte=since
        )
        .exclude(status__in=EXCLUDED_FROM_PERCENTAGE)
        .annotate(week=TruncWeek("session__session_date"))
        .values("week")
        .annotate(
            counted=Count("id"),
            attended=Count("id", filter=Q(status__in=list(COUNTS_AS_PRESENT))),
        )
        .order_by("week")
    )
    return [
        {
            "week": row["week"],
            "counted": row["counted"],
            "attended": row["attended"],
            "percent": _percent(row["attended"], row["counted"]),
        }
        for row in rows
    ]


def enrolment_trend(scope: dict, *, weeks: int = 12) -> list[dict[str, Any]]:
    """Enrolments started per week, and where they ended up.

    Grouped in the database, like every other trend here. Two details that
    are not cosmetic:

    ``enrolled_at`` is a ``DateTimeField``, unlike the ``DateField`` every
    other trend in this module buckets on, so ``TruncWeek`` would hand back a
    datetime and the serializer's ``DateField`` would shift the week boundary
    by the active timezone's offset. ``output_field`` pins it to a date.

    The status set is the full one, deliberately widened past
    ``_enrollments``' default: a trend that silently dropped cancellations
    would show a pipeline with no leaks in it.
    """
    from datetime import timedelta

    from django.db.models import DateField
    from django.db.models.functions import TruncWeek
    from django.utils import timezone

    from apps.enrollments.models import EnrollmentStatus

    since = timezone.localdate() - timedelta(weeks=weeks)
    rows = (
        _enrollments(scope, statuses=EnrollmentStatus.values)
        .filter(enrolled_at__date__gte=since)
        .annotate(week=TruncWeek("enrolled_at", output_field=DateField()))
        .values("week")
        .annotate(
            started=Count("id"),
            active=Count("id", filter=Q(status=EnrollmentStatus.ACTIVE)),
            completed=Count("id", filter=Q(status=EnrollmentStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status=EnrollmentStatus.CANCELLED)),
        )
        .order_by("week")
    )
    return [
        {
            "week": row["week"],
            "started": row["started"],
            "active": row["active"],
            "completed": row["completed"],
            "cancelled": row["cancelled"],
        }
        for row in rows
    ]


def delivery_trend(scope: dict, *, weeks: int = 12) -> list[dict[str, Any]]:
    """Classes scheduled, held and cancelled per week, and registers still owed.

    ``registers_outstanding`` counts only sessions that have already happened
    and are marked completed: a class later today with no register yet is not
    outstanding, it is pending, and counting it would make every Monday
    morning look like a compliance failure.
    """
    from datetime import timedelta

    from django.db.models.functions import TruncWeek
    from django.utils import timezone

    from apps.sessions.models import SessionStatus

    today = timezone.localdate()
    rows = (
        _sessions(scope)
        # Bounded at both ends. Without the upper bound a "last 12 weeks"
        # chart runs its axis out to whenever the furthest class is
        # scheduled -- batches are created months ahead, so the window would
        # be mostly empty future and the shape of the recent past would be
        # squeezed into the left margin.
        .filter(session_date__gte=today - timedelta(weeks=weeks), session_date__lte=today)
        .annotate(week=TruncWeek("session_date"))
        .values("week")
        .annotate(
            scheduled=Count("id"),
            held=Count("id", filter=Q(status=SessionStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status=SessionStatus.CANCELLED)),
            registers_outstanding=Count(
                "id",
                filter=Q(
                    attendance_taken_at__isnull=True,
                    status=SessionStatus.COMPLETED,
                    session_date__lt=today,
                ),
            ),
        )
        .order_by("week")
    )
    return [
        {
            "week": row["week"],
            "scheduled": row["scheduled"],
            "held": row["held"],
            "cancelled": row["cancelled"],
            "registers_outstanding": row["registers_outstanding"],
        }
        for row in rows
    ]


def dsr_compliance_trend(scope: dict, *, weeks: int = 12) -> list[dict[str, Any]]:
    """Daily status reports per week, by where each one got to.

    This measures *report submission*, and nothing else. The DSR model also
    stores ``present_count``/``absent_count``, which are prefilled from the
    register and then editable by the trainer -- so an attendance figure
    derived from them would disagree with the register-derived
    ``attendance_rate`` metric, and §8.6's rule that every metric carries one
    definition would become two contradictory definitions on one screen. If
    the online/offline split is ever wanted it belongs on its own card,
    labelled "as reported by the trainer".
    """
    from datetime import timedelta

    from django.db.models.functions import TruncWeek
    from django.utils import timezone

    from apps.dsr.models import DSRStatus

    since = timezone.localdate() - timedelta(weeks=weeks)
    rows = (
        _dsr(scope)
        .filter(report_date__gte=since)
        .annotate(week=TruncWeek("report_date"))
        .values("week")
        .annotate(
            draft=Count("id", filter=Q(status=DSRStatus.DRAFT)),
            submitted=Count("id", filter=Q(status=DSRStatus.SUBMITTED)),
            approved=Count("id", filter=Q(status=DSRStatus.APPROVED)),
            rejected=Count("id", filter=Q(status=DSRStatus.REJECTED)),
        )
        .order_by("week")
    )
    return [
        {
            "week": row["week"],
            "draft": row["draft"],
            "submitted": row["submitted"],
            "approved": row["approved"],
            "rejected": row["rejected"],
        }
        for row in rows
    ]
