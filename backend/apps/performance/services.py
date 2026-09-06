"""Writing a review, a piece of feedback, or the risk thresholds.

Business rules live here, not in the views, for the usual reason: the admin
site, a management command and a future bulk-import path all have to refuse a
self-review the same way the API does, and that only holds if there is exactly
one place the rule is written.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError

from . import access, engine
from .models import Feedback, PerformanceReview, PerformanceSubjectType

#: The only fields `update_risk_thresholds` may touch. Kept as its own list
#: rather than reusing `apps.academics.models.POLICY_FIELDS` — that list is
#: every configurable rule on `AcademicPolicy`, and this endpoint is scoped to
#: the four this app owns.
RISK_THRESHOLD_FIELDS: tuple[str, ...] = (
    "risk_attendance_percent",
    "risk_assessment_average_percent",
    "risk_missed_assignments",
    "risk_progress_variance_percent",
)


def _subject(*, student=None, trainer=None) -> str:
    if student is not None and trainer is not None:
        raise ApplicationError({"subject": ["This is about a student or a trainer, not both."]})
    if student is None and trainer is None:
        raise ApplicationError({"subject": ["Choose a student or a trainer."]})
    return PerformanceSubjectType.STUDENT if student is not None else PerformanceSubjectType.TRAINER


def _refuse_self(actor: User, *, student=None, trainer=None) -> None:
    """Nobody reviews themselves. Not a manager, not a superadmin.

    A rating a person gave themselves is not a review — the record's whole
    purpose is that somebody else looked — so this is checked before anything
    else, and there is no capability that overrides it.
    """
    if access.is_self_review(actor, student=student, trainer=trainer):
        raise AuthorityError({"subject": ["You may not review or leave feedback about yourself."]})


def _snapshot_for(*, student=None, trainer=None) -> dict[str, Any]:
    """The engine's output, right now, frozen into the review at creation time."""
    if trainer is not None:
        return {"subject_type": "trainer", "trainer": engine.trainer_performance(trainer)}

    from apps.enrollments.models import Enrollment

    enrollments = Enrollment.objects.with_related().filter(student=student)
    performance = engine.student_performance_bulk(enrollments)
    return {"subject_type": "student", "enrollments": list(performance.values())}


@transaction.atomic
def create_review(
    *,
    actor: User,
    student=None,
    trainer=None,
    period_start,
    period_end,
    rating: int,
    summary: str = "",
    strengths: str = "",
    concerns: str = "",
    actions: str = "",
) -> PerformanceReview:
    subject_type = _subject(student=student, trainer=trainer)
    _refuse_self(actor, student=student, trainer=trainer)

    review = PerformanceReview(
        subject_type=subject_type,
        student=student,
        trainer=trainer,
        period_start=period_start,
        period_end=period_end,
        rating=rating,
        summary=summary,
        strengths=strengths,
        concerns=concerns,
        actions=actions,
        snapshot=_snapshot_for(student=student, trainer=trainer),
        reviewer=actor if getattr(actor, "pk", None) else None,
    )
    try:
        review.full_clean()
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    review.save()

    record(
        action=AuditAction.REVIEW_RECORDED,
        actor=actor,
        resource_type="performance.performancereview",
        resource_id=review.pk,
        context={
            "subject_type": subject_type,
            "subject_id": str(student.pk if student else trainer.pk),
            "rating": rating,
        },
        durable=False,
    )
    return review


#: Fields a review may still change after it is written. The subject, the
#: reviewer and the snapshot are fixed at creation — see `PerformanceReview`'s
#: docstring on why the snapshot in particular is never touched again.
REVIEW_EDITABLE_FIELDS = frozenset(
    {"period_start", "period_end", "rating", "summary", "strengths", "concerns", "actions"}
)


@transaction.atomic
def update_review(*, review: PerformanceReview, actor: User, **fields: Any) -> PerformanceReview:
    unknown = sorted(set(fields) - REVIEW_EDITABLE_FIELDS)
    if unknown:
        raise ApplicationError({field: ["This field cannot be edited."] for field in unknown})

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(review, field) != value:
            setattr(review, field, value)
            changed.append(field)

    if not changed:
        return review

    try:
        review.full_clean()
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    review.save()

    record(
        action=AuditAction.REVIEW_UPDATED,
        actor=actor,
        resource_type="performance.performancereview",
        resource_id=review.pk,
        context={"fields": sorted(changed)},
        durable=False,
    )
    return review


@transaction.atomic
def create_feedback(
    *,
    actor: User,
    student=None,
    trainer=None,
    batch=None,
    body: str,
    visible_to_subject: bool = True,
) -> Feedback:
    subject_type = _subject(student=student, trainer=trainer)
    _refuse_self(actor, student=student, trainer=trainer)

    feedback = Feedback(
        subject_type=subject_type,
        student=student,
        trainer=trainer,
        batch=batch,
        body=body,
        visible_to_subject=visible_to_subject,
        author=actor if getattr(actor, "pk", None) else None,
    )
    try:
        feedback.full_clean()
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    feedback.save()

    record(
        action=AuditAction.FEEDBACK_RECORDED,
        actor=actor,
        resource_type="performance.feedback",
        resource_id=feedback.pk,
        context={
            "subject_type": subject_type,
            "subject_id": str(student.pk if student else trainer.pk),
        },
        durable=False,
    )
    return feedback


@transaction.atomic
def update_risk_thresholds(*, actor: User, **fields: Any):
    """Change the four numbers `apps.performance.risk` reads, institution-wide.

    Lives here rather than in `apps.academics.services.update_policy` — which
    already covers every field on `AcademicPolicy`, including these — because
    a change to a risk threshold is audited as its own event
    (`AuditAction.RISK_THRESHOLDS_UPDATED`), not folded into the generic
    `ACADEMIC_POLICY_UPDATED` a manager scanning for "who changed how risk gets
    flagged" would otherwise have to pick out from every other rule change.
    """
    from apps.academics.policies import forget_resolved_policies
    from apps.academics.services import get_or_create_policy

    unknown = sorted(set(fields) - set(RISK_THRESHOLD_FIELDS))
    if unknown:
        raise ApplicationError({field: ["This is not a risk threshold."] for field in unknown})

    policy = get_or_create_policy()
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, value in fields.items():
        current = getattr(policy, field)
        if current != value:
            before[field] = None if current is None else str(current)
            after[field] = None if value is None else str(value)
            setattr(policy, field, value)

    if not after:
        return policy

    policy.updated_by = actor if getattr(actor, "pk", None) else None
    try:
        policy.full_clean(exclude=["course"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    policy.save()

    forget_resolved_policies()

    record(
        action=AuditAction.RISK_THRESHOLDS_UPDATED,
        actor=actor,
        resource_type="academic_policy",
        resource_id=policy.pk,
        context={"from": before, "to": after},
        durable=False,
    )
    return policy
