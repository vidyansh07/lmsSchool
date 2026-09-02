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
