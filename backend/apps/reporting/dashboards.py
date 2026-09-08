"""Dashboard figures — §8.4.

The admin dashboard is the new one; the trainer and student dashboards already
existed and are extended rather than replaced.

Every figure here is either a count over a scoped queryset or a call into
:mod:`apps.reporting.metrics`, which means the number on the dashboard and the
number in the report are the same number. A dashboard that computes its own
totals is a dashboard that eventually disagrees with the report beneath it.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q
from django.utils import timezone


def admin_dashboard(user) -> dict[str, Any]:
    """What an administrator needs on opening the product."""
    from apps.batches.models import Batch, BatchStatus
    from apps.certificates.models import Certificate, CertificateStatus
    from apps.courses.models import Course, PublishStatus
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.progress.models import CompletionStatus, CourseCompletion
    from apps.trainers.models import TrainerProfile

    from . import access, metrics

    scope = access.scope_for(user)

    return {
        "active_students": Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE)
        .values("student_id")
        .distinct()
        .count(),
        "active_trainers": TrainerProfile.objects.filter(
            user__is_active=True, batches__status=BatchStatus.ACTIVE
        )
        .distinct()
        .count(),
        "published_courses": Course.objects.filter(status=PublishStatus.PUBLISHED).count(),
        "active_batches": Batch.objects.filter(status=BatchStatus.ACTIVE).count(),
        "awaiting_completion_approval": CourseCompletion.objects.filter(
            status=CompletionStatus.ELIGIBLE
        ).count(),
        "certificates_issued": Certificate.objects.filter(status=CertificateStatus.ISSUED).count(),
        "metrics": metrics.compute(
            scope,
            [
                metrics.ATTENDANCE_RATE.key,
                metrics.COMPLETION_RATE.key,
                metrics.ASSIGNMENT_COMPLETION_RATE.key,
                metrics.PENDING_MARKING.key,
                metrics.ACTIVE_LEARNERS.key,
            ],
        ),
    }


def trainer_workload(user) -> dict[str, Any]:
    """What a trainer still has to do — §8.4's trainer dashboard additions."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.assessments.models import Assessment, AssessmentStatus
    from apps.assignments.models import AssignmentSubmission, SubmissionStatus
    from apps.batches import access as batch_access
    from apps.exams.models import AttemptAnswer, Exam, ExamStatus
    from apps.projects.models import StudentProject, WorkStatus
    from apps.sessions.models import ClassSession, SessionStatus

    batches = batch_access.visible_batches(user)
    today = timezone.localdate()
    horizon = today + timedelta(days=14)

    return {
        "batches": batches.count(),
        "sessions_today": ClassSession.objects.filter(
            batch__in=batches, session_date=today
        ).count(),
        "registers_outstanding": ClassSession.objects.filter(
            batch__in=batches,
            session_date__lt=today,
            status=SessionStatus.SCHEDULED,
            attendance__isnull=True,
        )
        .distinct()
        .count(),
        "submissions_to_mark": AssignmentSubmission.objects.filter(
            enrollment__batch__in=batches, status=SubmissionStatus.SUBMITTED
        ).count(),
        "exam_answers_to_mark": AttemptAnswer.objects.filter(
            attempt_question__attempt__enrollment__batch__in=batches,
            needs_manual_marking=True,
            awarded__isnull=True,
        ).count(),
        "projects_to_review": StudentProject.objects.filter(
            enrollment__batch__in=batches,
            status__in=(WorkStatus.SUBMITTED, WorkStatus.UNDER_REVIEW),
        ).count(),
        "upcoming_tests": Assessment.objects.filter(
            batch__in=batches,
            status=AssessmentStatus.PUBLISHED,
            scheduled_for__date__gte=today,
            scheduled_for__date__lte=horizon,
        ).count(),
        "upcoming_exams": Exam.objects.filter(
            batch__in=batches,
            status=ExamStatus.PUBLISHED,
            opens_at__date__gte=today,
            opens_at__date__lte=horizon,
        ).count(),
    }


def batch_summaries(user, limit: int = 20) -> list[dict[str, Any]]:
    """A trainer's batches with their headline numbers.

    Three queries, deliberately, instead of one clever one. Annotating the
    student count and the attendance counts onto the same queryset joins
    enrolments against sessions against attendance records, and the database
    counts rows in that product: a batch with thirty students and forty classes
    made PostgreSQL walk thirty-six thousand rows to produce two numbers, and
    the endpoint took four seconds.

    Splitting them costs two extra round trips and makes each one a plain
    grouped count over an indexed column.
    """

    from apps.attendance.models import COUNTS_AS_PRESENT, EXCLUDED_FROM_PERCENTAGE, AttendanceRecord
    from apps.batches import access as batch_access
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    batches = list(
        batch_access.visible_batches(user).select_related("course").order_by("code")[:limit]
    )
    if not batches:
        return []

    ids = [batch.pk for batch in batches]
    students = dict(
        Enrollment.objects.filter(batch_id__in=ids, status=EnrollmentStatus.ACTIVE)
        .values_list("batch_id")
        .annotate(total=Count("id"))
    )
    attendance = {
        row["session__batch_id"]: row
        for row in AttendanceRecord.objects.filter(session__batch_id__in=ids)
        .values("session__batch_id")
        .annotate(
            counted=Count("id", filter=~Q(status__in=list(EXCLUDED_FROM_PERCENTAGE))),
            attended=Count("id", filter=Q(status__in=list(COUNTS_AS_PRESENT))),
        )
    }

    summaries = []
    for batch in batches:
        counts = attendance.get(batch.pk, {})
        counted = counts.get("counted", 0)
        summaries.append(
            {
                "id": str(batch.pk),
                "code": batch.code,
                "name": batch.name,
                "course_title": batch.course.title,
                "status": batch.status,
                "students": students.get(batch.pk, 0),
                "attendance_percent": (
                    round(counts.get("attended", 0) * 100 / counted, 2) if counted else None
                ),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# The manager hubs.
#
#     "What a manager here wants is two pages that drill all the way down:
#     Batches ... Trainers."
#
# Everything below serves that: a landing summary (`manager_dashboard`), a
# batch's full picture in one request (`batch_overview`), its roster at a
# flat query cost (`batch_roster_rows`), and a trainer's full picture
# (`trainer_overview`). None of it computes an attendance percentage, a risk
# verdict or a completion rate a second time — each figure is either read
# straight off `apps.performance.engine`, `apps.progress.reports` or
# `apps.reporting.metrics`, or is a grouped query beside one of them, kept in
# the open the same way `metrics.by_batch` sits beside the scalar metrics it
# must never disagree with.
# ---------------------------------------------------------------------------


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _severity(count: int) -> str:
    """A rough sort key for the attention queue, not a second scoring system.

    Deliberately coarse, in the same spirit as `apps.performance.risk`'s own
    severity split: one outstanding item is worth a manager's attention but
    is not a crisis; a handful is worth flagging harder; a real backlog is
    `high` regardless of which of the four queues it sits in.
    """
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _risk_rollup(active_enrollments) -> dict[str, int]:
    """One `student_performance_bulk` gather, every risk-derived count in it.

    "How many students are at risk" and "how many batches have an at-risk
    student on them" are two readings of the same computation. Deriving both
    from the one bulk gather — instead of one risk pass for the dashboard and
    a second, slightly different one for the batch screen — is what keeps
    them from ever disagreeing with each other or with a student's own risk
    flags.

    Takes an already-scoped, already-active queryset: the whole institution
    for the manager dashboard, one batch for a batch overview, one trainer's
    batches for a trainer overview. What counts as "active" is the caller's
    decision; this only ever reads what it is handed.
    """
    from apps.performance.engine import student_performance_bulk

    rows = list(active_enrollments.select_related("course", "batch"))
    bulk = student_performance_bulk(rows)
    at_risk_student_ids = {row.student_id for row in rows if bulk[row.pk]["risk"]["at_risk"]}
    at_risk_batch_ids = {row.batch_id for row in rows if bulk[row.pk]["risk"]["at_risk"]}
    return {
        "active_students": len({row.student_id for row in rows}),
        "at_risk_students": len(at_risk_student_ids),
        "at_risk_batches": len(at_risk_batch_ids),
    }


# ---------------------------------------------------------------------------
# The attention predicates, as sets of ids
# ---------------------------------------------------------------------------
#
# The attention strip says "3 batches running behind schedule" and links to a
# list. The list has to be *those three*, by the same test that counted them —
# so the list filters below reuse these, rather than defining "behind" or "at
# risk" a second time somewhere else.


def behind_schedule_batch_ids() -> set:
    """Active batches whose teaching has fallen behind their own dates."""
    from apps.batches.models import Batch, BatchStatus

    return _behind_schedule_batch_ids(Batch.objects.filter(status=BatchStatus.ACTIVE))


def at_risk_batch_ids() -> set:
    """Batches with at least one active student the risk engine has flagged."""
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.performance.engine import student_performance_bulk

    rows = list(
        Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE).select_related("course", "batch")
    )
    bulk = student_performance_bulk(rows)
    return {row.batch_id for row in rows if bulk[row.pk]["risk"]["at_risk"]}


def trainers_without_review_ids():
    """Trainers with no performance review on file — as a queryset of ids, so
    a filter can use it in one `NOT IN` rather than materialising the set."""
    from apps.performance.models import PerformanceReview, PerformanceSubjectType
    from apps.trainers.models import TrainerProfile

    reviewed = PerformanceReview.objects.filter(subject_type=PerformanceSubjectType.TRAINER).values(
        "trainer_id"
    )
    return TrainerProfile.objects.exclude(pk__in=reviewed).values("pk")


def _dsr_rollup(sessions) -> dict[str, int]:
    """Expected, submitted, approved, pending-review and overdue daily reports.

    Takes whatever set of classes the caller hands in — one batch's, or one
    trainer's.

    A daily status report is one-to-one with the class it is about (`DSR.session`
    is a `OneToOneField`), so "expected" is simply how many of the given
    classes have actually finished — one report each, once the class is
    over; a class still in progress is not yet late for one. "Submitted"
    counts a report the moment it first leaves `DRAFT`, including one sent
    back for revision — it *was* submitted, even if it was handed back.
    "Overdue" is what that leaves: a finished class with no report at all, or
    one still sitting in `DRAFT`.

    Two queries regardless of how many classes are in scope: one for which of
    them are `COMPLETED`, one grouped count over the reports on those.
    """
    from apps.dsr.models import DSR, DSRStatus
    from apps.sessions.models import SessionStatus

    completed_ids = list(
        sessions.filter(status=SessionStatus.COMPLETED).values_list("id", flat=True)
    )
    expected = len(completed_ids)
    if not expected:
        return {"expected": 0, "submitted": 0, "approved": 0, "pending_review": 0, "overdue": 0}

    counts = DSR.objects.filter(session_id__in=completed_ids).aggregate(
        submitted=Count("id", filter=~Q(status=DSRStatus.DRAFT)),
        approved=Count("id", filter=Q(status=DSRStatus.APPROVED)),
        pending_review=Count(
            "id", filter=Q(status__in=(DSRStatus.SUBMITTED, DSRStatus.UNDER_REVIEW))
        ),
    )
    return {
        "expected": expected,
        "submitted": counts["submitted"],
        "approved": counts["approved"],
        "pending_review": counts["pending_review"],
        "overdue": expected - counts["submitted"],
    }


def _behind_schedule_batch_ids(batches) -> set:
    """Which of these batches' own teaching has fallen behind their own dates.

    The identical test `apps.progress.reports.timeline_progress` runs for one
    batch — published lessons covered against published lessons total,
    elapsed time against the batch's own start and end dates, judged against
    `TIMELINE_BEHIND_THRESHOLD_PERCENT` — run here as two grouped queries
    instead of two queries *per batch*. An institution with two hundred
    active batches would otherwise cost this one dashboard figure four
    hundred round trips. `test_manager_hubs.py` asserts this agrees with
    `timeline_progress` batch by batch, the same discipline
    `test_reporting.py` already holds `metrics.by_batch` to.
    """
    from django.contrib.postgres.aggregates import ArrayAgg

    from apps.courses.models import Lesson, PublishStatus
    from apps.progress.reports import TIMELINE_BEHIND_THRESHOLD_PERCENT
    from apps.sessions.models import ClassSession, SessionStatus, TopicStatus

    rows = list(batches.only("id", "course_id", "start_date", "end_date"))
    if not rows:
        return set()

    lesson_totals = dict(
        Lesson.objects.filter(
            module__course_id__in={row.course_id for row in rows},
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        )
        .values_list("module__course_id")
        .annotate(total=Count("id"))
    )
    stats = {
        row["batch_id"]: row
        for row in ClassSession.objects.filter(batch_id__in=[row.pk for row in rows])
        .exclude(status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED))
        .values("batch_id")
        .annotate(
            sessions_total=Count("id"),
            covered_lesson_ids=ArrayAgg(
                "actual_lesson_id",
                filter=Q(topic_status=TopicStatus.COMPLETED, actual_lesson_id__isnull=False),
                distinct=True,
            ),
        )
    }

    today = timezone.localdate()
    behind: set = set()
    for batch in rows:
        lessons_total = lesson_totals.get(batch.course_id, 0)
        row = stats.get(batch.pk)
        if not lessons_total or not row or not row["sessions_total"] or today < batch.start_date:
            continue
        covered = len(row["covered_lesson_ids"] or [])
        percent_complete = round(covered * 100 / lessons_total)
        total_days = max((batch.end_date - batch.start_date).days, 1)
        elapsed_days = min(max((today - batch.start_date).days, 0), total_days)
        percent_expected = round(elapsed_days * 100 / total_days)
        if (percent_complete - percent_expected) < TIMELINE_BEHIND_THRESHOLD_PERCENT:
            behind.add(batch.pk)
    return behind


def _overdue_dsr_trainer_count() -> int:
    """How many trainers currently have a finished class with no submitted report.

    Grouped by the trainer frozen onto each session — the one who actually
    took the class, which may not be the batch's *current* trainer after a
    reassignment — rather than walked one trainer at a time.
    """
    from apps.dsr.models import DSR, DSRStatus
    from apps.sessions.models import ClassSession, SessionStatus

    reported_session_ids = DSR.objects.exclude(status=DSRStatus.DRAFT).values_list(
        "session_id", flat=True
    )
    return (
        ClassSession.objects.filter(status=SessionStatus.COMPLETED, trainer__isnull=False)
        .exclude(id__in=reported_session_ids)
        .values_list("trainer_id", flat=True)
        .distinct()
        .count()
    )


def manager_dashboard(user) -> dict[str, Any]:
    """The landing summary behind both manager hubs.

        "A KPI strip may sit at the top of each hub, but as a summary of the
        page below it. Nobody navigates to a number."

    So every figure here is either a plain count over a scoped queryset, or
    read from the same bulk risk and timeline computations the batch and
    trainer hubs themselves use — nothing here is a second definition of "at
    risk" or "behind schedule" that could one day disagree with the screen
    it is meant to summarise.

    `attention` is the manager's queue, and an empty list is a real, good
    answer: nothing here needs a manager's attention right now. Each entry
    only appears when its count is positive, and only when the caller holds
    the capability that actually owns that figure — `dsr.view_any` for the
    daily-report queue, `performance.view_any` for the review queue — so a
    role that can read this dashboard but not, say, daily status reports,
    sees a shorter queue rather than a number it has no way to act on.
    """
    from apps.accounts.roles import Capability, has_capability
    from apps.batches.models import Batch, BatchStatus
    from apps.dsr.models import DSR, DSRStatus
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.performance.models import PerformanceReview, PerformanceSubjectType
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile

    today = timezone.localdate()

    active_batches = Batch.objects.filter(status=BatchStatus.ACTIVE)
    behind_ids = _behind_schedule_batch_ids(active_batches)
    risk = _risk_rollup(Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE))

    attention: list[dict[str, Any]] = []

    if has_capability(user, Capability.DSR_VIEW_ANY):
        pending_dsr = DSR.objects.filter(
            status__in=(DSRStatus.SUBMITTED, DSRStatus.UNDER_REVIEW)
        ).count()
        if pending_dsr:
            attention.append(
                {
                    "kind": "dsr_pending_review",
                    "label": (
                        f"{pending_dsr} {_plural(pending_dsr, 'daily status report')} "
                        "awaiting review"
                    ),
                    "count": pending_dsr,
                    "href": "/dsr?status=pending_review",
                    "severity": _severity(pending_dsr),
                }
            )

    # Every href here is a *frontend* route with the filter the page reads —
    # `/manage/batches?attention=…` — not an API path. These used to point at
    # `/batches?status=behind_schedule`, a page that does not exist, so the
    # attention strip's most useful links were 404s.
    if behind_ids:
        behind_count = len(behind_ids)
        attention.append(
            {
                "kind": "batches_behind_schedule",
                "label": (
                    f"{behind_count} {_plural(behind_count, 'batch', 'batches')} "
                    "running behind schedule"
                ),
                "count": behind_count,
                "href": "/manage/batches?attention=behind_schedule",
                "severity": _severity(behind_count),
            }
        )

    if risk["at_risk_students"]:
        at_risk = risk["at_risk_students"]
        attention.append(
            {
                "kind": "students_at_risk",
                "label": f"{at_risk} {_plural(at_risk, 'student')} flagged at risk",
                "count": at_risk,
                "href": "/manage/batches?attention=at_risk",
                "severity": _severity(at_risk),
            }
        )

    if has_capability(user, Capability.PERFORMANCE_VIEW_ANY):
        reviewed_trainer_ids = PerformanceReview.objects.filter(
            subject_type=PerformanceSubjectType.TRAINER
        ).values("trainer_id")
        missing_reviews = TrainerProfile.objects.exclude(pk__in=reviewed_trainer_ids).count()
        if missing_reviews:
            attention.append(
                {
                    "kind": "trainer_reviews_outstanding",
                    "label": (
                        f"{missing_reviews} {_plural(missing_reviews, 'trainer')} with no "
                        "performance review on file"
                    ),
                    "count": missing_reviews,
                    "href": "/manage/trainers?attention=review_missing",
                    "severity": _severity(missing_reviews),
                }
            )

    return {
        "batches": {
            "total": Batch.objects.count(),
            "active": active_batches.count(),
            "behind_schedule": len(behind_ids),
            "at_risk": risk["at_risk_batches"],
        },
        "students": {
            "total": StudentProfile.objects.count(),
            "active": risk["active_students"],
            "at_risk": risk["at_risk_students"],
        },
        "trainers": {
            "total": TrainerProfile.objects.count(),
            "with_overdue_dsr": _overdue_dsr_trainer_count(),
        },
        "attention": attention,
        "as_of": today.isoformat(),
    }


def batch_overview(batch) -> dict[str, Any]:
    """Everything about one batch, in the one request the client asked for.

        "Open one and see everything: current attendance, the students on
        it, progress against the plan, how many assessments have run, how
        many projects are in, how many DSRs were written and approved, and
        which trainer did the work."

    Every section is either a call straight into the engine that owns it
    (`timeline_progress`, `student_performance_bulk`, `metrics.test_average`,
    `metrics.assignment_completion_rate`) or a single grouped query beside
    one, never a second copy of an already-answered question. A batch with no
    sessions, no trainer or no students yet is not a special case: every
    count below is honestly zero, and every percentage with nothing to divide
    by is `None` rather than a lying `0`.
    """
    from apps.assessments.models import Assessment
    from apps.assignments.models import Assignment, AssignmentSubmission, SubmissionStatus
    from apps.attendance.models import (
        COUNTS_AS_PRESENT,
        EXCLUDED_FROM_PERCENTAGE,
        AttendanceRecord,
        AttendanceStatus,
    )
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.progress.reports import timeline_progress
    from apps.projects.models import StudentProject
    from apps.sessions.models import ClassSession, SessionStatus

    from . import metrics

    today = timezone.localdate()
    seats_taken = batch.seats_taken()

    attendance_counts = AttendanceRecord.objects.filter(session__batch=batch).aggregate(
        counted=Count("id", filter=~Q(status__in=list(EXCLUDED_FROM_PERCENTAGE))),
        attended=Count("id", filter=Q(status__in=list(COUNTS_AS_PRESENT))),
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
    )

    session_counts = ClassSession.objects.filter(batch=batch).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=SessionStatus.COMPLETED)),
        cancelled=Count("id", filter=Q(status=SessionStatus.CANCELLED)),
        upcoming=Count("id", filter=Q(status=SessionStatus.SCHEDULED, session_date__gte=today)),
    )

    dsr = _dsr_rollup(ClassSession.objects.filter(batch=batch))

    assessment_counts = (
        Assessment.objects.student_visible()
        .filter(batch=batch)
        .aggregate(
            total=Count("id", distinct=True),
            completed=Count("id", filter=Q(results__isnull=False), distinct=True),
        )
    )
    assessment_average = metrics.test_average({"batch": batch.pk})["value"]

    # The same assignment set `assignment_completion_rate` scores against, so
    # "graded" can never count a pair "total"/"submitted" does not know about.
    applicable_assignments = [
        assignment
        for assignment in Assignment.objects.student_visible().filter(course=batch.course)
        if assignment.applies_to_batch(batch.pk)
    ]
    assignment_metric = metrics.assignment_completion_rate({"batch": batch.pk})
    graded_pairs = (
        AssignmentSubmission.objects.filter(
            assignment_id__in=[assignment.pk for assignment in applicable_assignments],
            enrollment__batch=batch,
            status=SubmissionStatus.GRADED,
        )
        .values("enrollment_id", "assignment_id")
        .distinct()
        .count()
        if applicable_assignments
        else 0
    )

    project_counts = StudentProject.objects.filter(
        enrollment__batch=batch,
        enrollment__status__in=(
            EnrollmentStatus.ACTIVE,
            EnrollmentStatus.COMPLETED,
            EnrollmentStatus.SUSPENDED,
        ),
    ).aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(submitted_at__isnull=False)),
        reviewed=Count("id", filter=Q(reviewed_at__isnull=False)),
    )

    risk = _risk_rollup(Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.ACTIVE))

    return {
        "batch": {
            "id": str(batch.pk),
            "code": batch.code,
            "name": batch.name,
            "kind": batch.kind,
            "status": batch.status,
            "delivery_mode": batch.delivery_mode,
            "start_date": batch.start_date,
            "end_date": batch.end_date,
            "capacity": batch.capacity,
            "seats_taken": seats_taken,
        },
        "course": {
            "id": str(batch.course_id),
            "title": batch.course.title,
            "code": batch.course.code,
        },
        "trainer": (
            {
                "id": str(batch.trainer_id),
                "name": batch.trainer.user.get_full_name(),
                "trainer_id": batch.trainer.trainer_id,
            }
            if batch.trainer_id
            else None
        ),
        "attendance": {
            "percentage": (
                round(attendance_counts["attended"] * 100 / attendance_counts["counted"])
                if attendance_counts["counted"]
                else None
            ),
            "present": attendance_counts["present"],
            "absent": attendance_counts["absent"],
            "total_sessions": attendance_counts["counted"],
        },
        "timeline": timeline_progress(batch),
        "sessions": {
            "total": session_counts["total"],
            "completed": session_counts["completed"],
            "cancelled": session_counts["cancelled"],
            "upcoming": session_counts["upcoming"],
        },
        "dsr": dsr,
        "assessments": {
            "total": assessment_counts["total"],
            "completed": assessment_counts["completed"],
            "average_percent": assessment_average,
        },
        "assignments": {
            "total": assignment_metric["denominator"],
            "submitted": assignment_metric["numerator"],
            "graded": graded_pairs,
        },
        "projects": {
            "total": project_counts["total"],
            "submitted": project_counts["submitted"],
            "reviewed": project_counts["reviewed"],
        },
        "students": {
            "total": seats_taken,
            "active": risk["active_students"],
            "at_risk": risk["at_risk_students"],
        },
        "as_of": today.isoformat(),
    }


def roster_queryset(batch):
    """The base queryset a batch's roster is built from.

    Scoped to whoever still counts as "on" this batch — the same
    `SEAT_HOLDING_STATUSES` `Batch.seats_taken` reads — so the roster's row
    count and `batch_overview`'s `students.total` can never disagree. A
    transferred-out row belongs to the batch the student left, not a roster
    anyone reads today; `transferred_to` and `transferred_from` are fetched
    here, with everything else a roster row needs, so
    `Enrollment.transfer_chain` costs no query at all once the page is built
    — see `batch_roster_rows` and `_transfer_aware_attendance`.
    """
    from apps.enrollments.models import SEAT_HOLDING_STATUSES, Enrollment

    return Enrollment.objects.filter(batch=batch, status__in=SEAT_HOLDING_STATUSES).select_related(
        "student", "student__user", "course", "batch", "transferred_to", "transferred_from"
    )


def _transfer_aware_attendance(enrollments: list) -> dict[Any, dict[str, Any]]:
    """Attendance per enrolment, honest across a batch transfer — for a whole page at once.

        "A student who moved batches must not look new; use
        transfer_attendance_summary rather than reading the current row
        alone."

    `apps.enrollments.services.transfer_attendance_summary` answers exactly
    this for one enrolment — walking `Enrollment.transfer_chain` and calling
    `attendance_summaries` itself. Exactly right for a student's own screen,
    and exactly wrong for a roster page: called once per row it turns twenty-
    five students into twenty-five extra round trips, on top of the one the
    page already needs. `transfer_chain` costs no query at all here, because
    `roster_queryset` fetches `transferred_to` and `transferred_from` with
    the page; only the summed attendance is read from the database, and only
    once, for every enrolment id every chain on the page touches.

    Mirrors `transfer_attendance_summary`'s arithmetic exactly; a chain that
    reaches beyond the one hop fetched with the page costs an extra query for
    that row alone, which is the accepted cost of a transfer of more than one
    hop being rare rather than the common case this function is sized for.
    See `test_manager_hubs.py` for the test that keeps the two functions
    honest with each other.
    """
    from apps.attendance.models import attendance_summaries

    chains = {enrollment.pk: enrollment.transfer_chain() for enrollment in enrollments}
    all_ids = {row.pk for chain in chains.values() for row in chain}
    summaries = attendance_summaries(all_ids)

    result = {}
    for enrollment_id, chain in chains.items():
        attended = sum(summaries[row.pk]["attended"] or 0 for row in chain)
        total = sum(summaries[row.pk]["total_sessions"] or 0 for row in chain)
        result[enrollment_id] = {
            "attended": attended,
            "total_sessions": total,
            "percentage": round(attended * 100 / total) if total else None,
        }
    return result


def batch_roster_rows(enrollments: list) -> list[dict[str, Any]]:
    """One roster page, per-student rollups included, at a fixed query cost.

    `enrollments` is expected to already be the page — filtered, ordered and
    sliced by the view, through `roster_queryset` and DRF's own pagination.
    Everything from here on is one bulk gather per figure, never one query
    per row: `student_performance_bulk` supplies the assessment, assignment
    and progress numbers and the risk flags in a single pass;
    `_transfer_aware_attendance` supplies attendance across a transfer; the
    project counts are one grouped query beside them, the same "three
    queries, deliberately" reasoning `batch_summaries` above already
    documents.
    """
    from apps.performance.engine import student_performance_bulk
    from apps.projects.models import StudentProject

    if not enrollments:
        return []

    performance = student_performance_bulk(enrollments)
    attendance = _transfer_aware_attendance(enrollments)
    project_counts = {
        row["enrollment_id"]: row
        for row in StudentProject.objects.filter(enrollment__in=enrollments)
        .values("enrollment_id")
        .annotate(total=Count("id"), submitted=Count("id", filter=Q(submitted_at__isnull=False)))
    }

    rows = []
    for enrollment in enrollments:
        result = performance[enrollment.pk]
        projects = project_counts.get(enrollment.pk, {"total": 0, "submitted": 0})
        rows.append(
            {
                "enrollment_id": str(enrollment.pk),
                "student_id": enrollment.student.student_id,
                "name": enrollment.student.user.get_full_name(),
                "status": enrollment.status,
                "attendance_percent": attendance[enrollment.pk]["percentage"],
                "assessment_average": result["assessment"]["average_percent"],
                "assignments_submitted": result["assignments"]["submitted"],
                "assignments_total": result["assignments"]["total"],
                "projects_submitted": projects["submitted"],
                "projects_total": projects["total"],
                "progress_percent": result["progress"]["percent"],
                "risk_flags": result["risk"]["triggered"],
                # A reverse `OneToOneField` accessor raises
                # `RelatedObjectDoesNotExist` rather than returning `None` when
                # nothing points at this row — unlike the forward `transferred_to`,
                # which is a plain nullable column. `getattr` with a default is
                # the documented way around it (the exception multiply-inherits
                # `AttributeError` for exactly this reason).
                "transferred_in": getattr(enrollment, "transferred_from", None) is not None,
            }
        )
    return rows


def trainer_overview(trainer, viewer) -> dict[str, Any]:
    """Everything about one trainer: their load, their record, what is waiting on them.

        "Trainers — every trainer listed, with their performance, the
        reviews written about them, and the feedback their students gave."

    The workload and rate figures are `apps.performance.engine.trainer_performance`,
    verbatim — nothing here recomputes a rate that engine already owns.
    Reviews and feedback are read through `apps.performance.access`, exactly
    as the performance app itself reads them, so a manager sees everything
    and the trainer sees only what a review or a piece of feedback says they
    may — the same rule holds whether the screen is this one or theirs.
    `student_feedback` is filtered to feedback an actual student wrote, per
    the client's own words: "the reviews of trainer that student gave them."
    """
    from apps.accounts.roles import UserRole
    from apps.batches.models import Batch, BatchStatus
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.performance import access as performance_access
    from apps.performance.engine import trainer_performance
    from apps.performance.models import PerformanceSubjectType
    from apps.sessions.models import ClassSession

    from . import metrics

    today = timezone.localdate()
    performance = trainer_performance(trainer)

    batch_ids = list(Batch.objects.filter(trainer=trainer).values_list("id", flat=True))
    active_batches = Batch.objects.filter(trainer=trainer, status=BatchStatus.ACTIVE).count()

    risk = _risk_rollup(
        Enrollment.objects.filter(batch__trainer=trainer, status=EnrollmentStatus.ACTIVE)
    )
    dsr = _dsr_rollup(ClassSession.objects.filter(trainer=trainer))
    dsr_approval_rate = (
        round(dsr["approved"] * 100 / dsr["submitted"], 2) if dsr["submitted"] else None
    )
    student_attendance = metrics.attendance_rate({"restrict_to_batches": batch_ids})["value"]

    reviews = list(
        performance_access.visible_reviews(viewer)
        .filter(subject_type=PerformanceSubjectType.TRAINER, trainer=trainer)
        .order_by("-period_end")[:20]
    )
    feedback = list(
        performance_access.visible_feedback(viewer)
        .filter(
            subject_type=PerformanceSubjectType.TRAINER,
            trainer=trainer,
            author__role=UserRole.STUDENT,
        )
        .order_by("-created_at")[:20]
    )

    return {
        "trainer": {
            "id": str(trainer.pk),
            "name": trainer.user.get_full_name(),
            "trainer_id": trainer.trainer_id,
            "email": trainer.user.email,
        },
        "batches": {
            "total": performance["batches_handled"],
            "active": active_batches,
        },
        "students": {
            "total": performance["students_handled"],
            "at_risk": risk["at_risk_students"],
        },
        "submission": {
            "attendance_rate": performance["attendance_submission_rate"],
            "dsr_rate": performance["dsr_submission_rate"],
            "dsr_approval_rate": dsr_approval_rate,
        },
        "completion": {
            "assessments": performance["assessment_completion_percent"],
            "assignments": performance["assignment_completion_percent"],
            "projects": performance["project_completion_percent"],
        },
        "outcomes": {
            "student_average_score": performance["student_average_score"],
            "student_attendance_percent": (
                round(student_attendance) if student_attendance is not None else None
            ),
        },
        "pending": {
            "dsr_to_submit": dsr["overdue"],
            "assignments_to_grade": performance["pending_work"]["assignments"],
            "projects_to_review": performance["pending_work"]["projects"],
            "overdue": performance["overdue_work"]["total"],
        },
        "reviews": [
            {
                "id": str(review.pk),
                "period_start": review.period_start,
                "period_end": review.period_end,
                "rating": review.rating,
                "summary": review.summary,
                "reviewer": review.reviewer.get_full_name() if review.reviewer_id else None,
                "created_at": review.created_at,
            }
            for review in reviews
        ],
        "student_feedback": [
            {
                "id": str(item.pk),
                "body": item.body,
                "created_at": item.created_at,
                "batch_code": item.batch.code if item.batch_id else None,
            }
            for item in feedback
        ],
        "as_of": today.isoformat(),
    }
