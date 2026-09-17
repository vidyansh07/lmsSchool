"""The Celery-facing edge of the automation engine (ERP Phase 14, ADR-13).

Every task here is a thin wrapper: resolve the real objects a trigger needs
from the primitive (JSON-serializable) ids Celery can actually carry, then
call `services.dispatch` — the one place evaluation, idempotency, guards and
actions live. A signal receiver (`receivers.py`) or a beat task
(`apps.work.services.mark_overdue_and_missed`, `apps.assessments.services.
record_result`, `apps.performance.services.recompute_risk`) enqueues one of
these; none of them calls `services.dispatch` synchronously in its own
request/signal-handling path (ADR-17: background jobs are idempotent and
bounded; ADR-13: "Executed by Celery").

A missing object (deleted between the enqueue and the worker picking it up)
is not an error — the occurrence this dispatch was for no longer exists, so
there is nothing to evaluate a rule against; the task simply returns.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="automation.dispatch_activity_completed", ignore_result=True)
def dispatch_activity_completed(activity_id: str) -> None:
    from apps.work.models import Activity

    from .models import AutomationTrigger
    from .services import dispatch

    activity = (
        Activity.objects.filter(pk=activity_id)
        .select_related(
            "activity_type",
            "student",
            "student__user",
            "enrollment",
            "enrollment__batch",
            "assigned_to",
            "performed_by",
            "form_version",
            "form_response",
            "branch",
        )
        .first()
    )
    if activity is None:
        return
    dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity, depth=0)


@shared_task(name="automation.dispatch_activity_overdue", ignore_result=True)
def dispatch_activity_overdue(activity_id: str, days_overdue: int) -> None:
    from apps.work.models import Activity

    from .models import AutomationTrigger
    from .services import dispatch

    activity = (
        Activity.objects.filter(pk=activity_id)
        .select_related(
            "activity_type",
            "student",
            "student__user",
            "enrollment",
            "enrollment__batch",
            "assigned_to",
            "branch",
        )
        .first()
    )
    if activity is None:
        return
    dispatch(AutomationTrigger.ACTIVITY_OVERDUE, activity, depth=0, days_overdue=days_overdue)


@shared_task(name="automation.dispatch_assessment_failed", ignore_result=True)
def dispatch_assessment_failed(result_id: str, percent: float, attempt_number: int) -> None:
    from apps.assessments.models import AssessmentResult

    from .models import AutomationTrigger
    from .services import dispatch

    result = (
        AssessmentResult.objects.filter(pk=result_id)
        .select_related(
            "assessment",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
        )
        .first()
    )
    if result is None:
        return
    dispatch(
        AutomationTrigger.ASSESSMENT_FAILED,
        result,
        depth=0,
        percent=percent,
        attempt_number=attempt_number,
    )


@shared_task(name="automation.dispatch_attendance_threshold", ignore_result=True)
def dispatch_attendance_threshold(enrollment_id: str, percent: float, absent_streak: int) -> None:
    from apps.enrollments.models import Enrollment

    from .models import AutomationTrigger
    from .services import dispatch

    enrollment = (
        Enrollment.objects.filter(pk=enrollment_id)
        .select_related("student", "student__user", "batch")
        .first()
    )
    if enrollment is None:
        return
    dispatch(
        AutomationTrigger.ATTENDANCE_THRESHOLD,
        enrollment,
        depth=0,
        percent=percent,
        absent_streak=absent_streak,
    )


@shared_task(name="automation.dispatch_project_overdue", ignore_result=True)
def dispatch_project_overdue(student_project_id: str, days_overdue: int) -> None:
    from apps.projects.models import StudentProject

    from .models import AutomationTrigger
    from .services import dispatch

    student_project = (
        StudentProject.objects.filter(pk=student_project_id)
        .select_related(
            "project",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
        )
        .first()
    )
    if student_project is None:
        return
    dispatch(AutomationTrigger.PROJECT_OVERDUE, student_project, depth=0, days_overdue=days_overdue)


@shared_task(name="automation.dispatch_assignment_overdue", ignore_result=True)
def dispatch_assignment_overdue(assignment_id: str, enrollment_id: str, days_overdue: int) -> None:
    from apps.assignments.models import Assignment
    from apps.enrollments.models import Enrollment

    from .models import AutomationTrigger
    from .services import dispatch

    assignment = Assignment.objects.filter(pk=assignment_id).first()
    enrollment = (
        Enrollment.objects.filter(pk=enrollment_id)
        .select_related("student", "student__user", "batch")
        .first()
    )
    if assignment is None or enrollment is None:
        return
    dispatch(
        AutomationTrigger.ASSIGNMENT_OVERDUE,
        assignment,
        depth=0,
        enrollment=enrollment,
        assignment_id=str(assignment.pk),
        days_overdue=days_overdue,
    )


@shared_task(name="automation.dispatch_risk_changed", ignore_result=True)
def dispatch_risk_changed(
    risk_state_id: str,
    enrollment_id: str,
    level: str,
    previous_level: str,
    triggered: list,
    previous_triggered: list,
) -> None:
    from apps.enrollments.models import Enrollment
    from apps.performance.models import RiskState

    from .models import AutomationTrigger
    from .services import dispatch

    risk_state = RiskState.objects.filter(pk=risk_state_id).first()
    enrollment = (
        Enrollment.objects.filter(pk=enrollment_id)
        .select_related("student", "student__user", "batch")
        .first()
    )
    if risk_state is None or enrollment is None:
        return
    dispatch(
        AutomationTrigger.RISK_CHANGED,
        risk_state,
        depth=0,
        enrollment=enrollment,
        level=level,
        previous_level=previous_level or None,
        triggered=triggered,
        previous_triggered=previous_triggered,
    )


@shared_task(name="automation.sync_rule_authors", ignore_result=True)
def sync_rule_authors() -> int:
    from .services import sync_rule_authors as _sync

    return _sync()
