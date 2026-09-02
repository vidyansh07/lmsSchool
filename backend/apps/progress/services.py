"""Progress and completion services — §6.6.

The workflow §6.6 describes, in order:

    activities complete → the system evaluates the rules → the student becomes
    completion-eligible → an administrator reviews → approves → completion is
    recorded

Eligibility is **derived**, so it is recomputed every time anybody looks, and a
rule change moves it immediately. Approval is **decided**, so it is stored with
who decided it and what the rules said at the time. Confusing the two is how a
system ends up unable to explain a certificate it issued.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.academics.policies import policy_for
from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.enrollments.models import Enrollment, EnrollmentStatus

from .models import CompletionStatus, CourseCompletion
from .reports import progress_report
from .rules import evaluate


def evaluate_enrollment(enrollment: Enrollment) -> dict[str, Any]:
    """Progress, the rules in force, and the verdict — without writing anything.

    Safe to call on every read, which is the point: nothing about eligibility is
    cached, so an administrator who lowers the attendance requirement sees the
    effect on the next request rather than after a nightly job.
    """
    report = progress_report(enrollment)
    policy = policy_for(enrollment.course_id)
    outcome = evaluate(report, policy)
    return {"progress": report, **outcome}


@transaction.atomic
def refresh_completion(*, enrollment: Enrollment, actor: User | None = None) -> CourseCompletion:
    """Recompute eligibility and record it, leaving decisions alone.

    A completion an administrator has already approved or rejected is not
    touched: a student who dips below the attendance line the week after
    graduating has not un-graduated.
    """
    completion, _created = CourseCompletion.objects.get_or_create(enrollment=enrollment)
    if completion.is_decided:
        return completion

    result = evaluate_enrollment(enrollment)
    target = CompletionStatus.ELIGIBLE if result["eligible"] else CompletionStatus.IN_PROGRESS

    if target == completion.status:
        return completion

    completion.status = target
    if target == CompletionStatus.ELIGIBLE:
        completion.became_eligible_at = timezone.now()
    else:
        completion.became_eligible_at = None
    completion.save(update_fields=["status", "became_eligible_at", "updated_at"])

    if target == CompletionStatus.ELIGIBLE:
        record(
            action=AuditAction.COMPLETION_ELIGIBLE,
            actor=actor,
            resource_type="course_completion",
            resource_id=completion.pk,
            context={
                "enrollment": str(enrollment.pk),
                "course": enrollment.course.title,
                "required_rules": result["required_count"],
            },
            durable=False,
        )
    return completion


@transaction.atomic
def approve_completion(
    *,
    enrollment: Enrollment,
    actor: User,
    completed_on=None,
    note: str = "",
    override: bool = False,
) -> CourseCompletion:
    """Record that a student has finished the course.

    Refuses a student who does not meet the rules unless ``override`` is set —
    and an override is stored in the snapshot, so the decision is explainable
    later rather than indistinguishable from an ordinary approval.
    """
    completion = refresh_completion(enrollment=enrollment, actor=actor)
    if completion.status == CompletionStatus.APPROVED:
        raise ConflictError({"completion": ["This course is already recorded as complete."]})

    result = evaluate_enrollment(enrollment)
    if not result["eligible"] and not override:
        raise ApplicationError(
            {
                "completion": [
                    "This student does not meet the completion rules: "
                    + ", ".join(result["unmet"])
                    + "."
                ]
            }
        )

    completion.status = CompletionStatus.APPROVED
    completion.completed_on = completed_on or timezone.localdate()
    completion.decided_by = actor if getattr(actor, "pk", None) else None
    completion.decided_at = timezone.now()
    completion.decision_note = note[:500]
    completion.rule_snapshot = {
        "evaluated_at": timezone.now().isoformat(),
        "eligible": result["eligible"],
        "overridden": bool(override and not result["eligible"]),
        "rules": result["rules"],
    }
    completion.save()

    # The enrolment follows the decision: a completed course is a completed
    # enrolment, and nothing else should have to remember to do this.
    if enrollment.status == EnrollmentStatus.ACTIVE:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = timezone.now()
        enrollment.save(update_fields=["status", "completed_at", "updated_at"])

    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=enrollment.student.user,
        kind=NotificationKind.COMPLETION_APPROVED,
        title=f"You have completed {enrollment.course.title}",
        body="Your certificate will follow once it has been issued.",
        link_path="/my-progress",
        resource_type="course",
        resource_id=enrollment.course_id,
    )

    record(
        action=AuditAction.COMPLETION_APPROVED,
        actor=actor,
        resource_type="course_completion",
        resource_id=completion.pk,
        context={
            "enrollment": str(enrollment.pk),
            "course": enrollment.course.title,
            "completed_on": completion.completed_on.isoformat(),
            "overridden": completion.rule_snapshot["overridden"],
        },
        durable=False,
    )
    return completion


@transaction.atomic
def reject_completion(*, enrollment: Enrollment, actor: User, note: str) -> CourseCompletion:
    """Decline a completion, with a reason.

    A reason is required: "not approved" with no explanation is not a decision a
    student can act on.
    """
    if not note.strip():
        raise ApplicationError({"note": ["Say why the completion was not approved."]})

    completion, _created = CourseCompletion.objects.get_or_create(enrollment=enrollment)
    if completion.status == CompletionStatus.APPROVED:
        raise ConflictError(
            {"completion": ["This course is already approved. Revoke the certificate instead."]}
        )

    result = evaluate_enrollment(enrollment)
    completion.status = CompletionStatus.REJECTED
    completion.decided_by = actor if getattr(actor, "pk", None) else None
    completion.decided_at = timezone.now()
    completion.decision_note = note[:500]
    completion.rule_snapshot = {
        "evaluated_at": timezone.now().isoformat(),
        "eligible": result["eligible"],
        "overridden": False,
        "rules": result["rules"],
    }
    completion.save()

    record(
        action=AuditAction.COMPLETION_REJECTED,
        actor=actor,
        resource_type="course_completion",
        resource_id=completion.pk,
        context={"enrollment": str(enrollment.pk), "note": completion.decision_note},
        durable=False,
    )
    return completion


@transaction.atomic
def reopen_completion(*, enrollment: Enrollment, actor: User, note: str) -> CourseCompletion:
    """Undo a decision, putting the enrolment back under evaluation.

    Deliberately available: decisions are made by people, and people correct
    them. What is not available is silently erasing the previous decision — the
    audit trail keeps both.
    """
    completion, _created = CourseCompletion.objects.get_or_create(enrollment=enrollment)
    if not completion.is_decided:
        return completion
    if completion.certificates.live().exists():
        raise ConflictError(
            {"completion": ["Revoke the certificate before reopening this completion."]}
        )

    completion.status = CompletionStatus.IN_PROGRESS
    completion.completed_on = None
    completion.decided_by = actor if getattr(actor, "pk", None) else None
    completion.decided_at = timezone.now()
    completion.decision_note = note[:500]
    completion.save()

    record(
        action=AuditAction.COMPLETION_REOPENED,
        actor=actor,
        resource_type="course_completion",
        resource_id=completion.pk,
        context={"enrollment": str(enrollment.pk), "note": completion.decision_note},
        durable=False,
    )
    return refresh_completion(enrollment=enrollment, actor=actor)
