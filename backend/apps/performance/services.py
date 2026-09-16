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
from django.db.models import Case, Count, IntegerField, When
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError

from . import access, engine
from .models import (
    Feedback,
    PerformanceReview,
    PerformanceSubjectType,
    ReviewType,
    RiskLevel,
    RiskState,
)

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
    review_type: str = ReviewType.AD_HOC,
    score=None,
    summary: str = "",
    strengths: str = "",
    concerns: str = "",
    actions: str = "",
    recommendations: str = "",
    next_review_at=None,
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
        review_type=review_type,
        score=score,
        summary=summary,
        strengths=strengths,
        concerns=concerns,
        actions=actions,
        recommendations=recommendations,
        next_review_at=next_review_at,
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
    {
        "review_type",
        "period_start",
        "period_end",
        "rating",
        "score",
        "summary",
        "strengths",
        "concerns",
        "actions",
        "recommendations",
        "next_review_at",
        "status",
    }
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


# ---------------------------------------------------------------------------
# Risk (ERP Phase 13, ADR-11)
# ---------------------------------------------------------------------------


def _notify_risk_changed(*, enrollment, level: str, previous_level: str | None) -> None:
    """Tell the person best placed to act — the batch's own trainer, if it
    has one. Nobody else is an obvious single recipient yet (a manager's
    caseload view is `/risk/summary/`, not a push notification per student),
    and Phase 14's automation engine is exactly where a richer routing rule
    ("notify the counsellor too", "escalate critical to a manager") belongs
    once it exists — this is deliberately the simplest thing that is still
    useful today, not a final routing policy."""
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    if not enrollment.batch_id or not enrollment.batch.trainer_id:
        return
    trainer_user = enrollment.batch.trainer.user
    student_name = enrollment.student.user.get_full_name()
    was = previous_level or RiskLevel.NONE
    notify(
        recipient=trainer_user,
        kind=NotificationKind.RISK_LEVEL_CHANGED,
        title=f"{student_name}'s risk level is now {level}",
        body=f"Changed from {was} to {level} on {enrollment.batch.code}.",
        link_path=f"/students/{enrollment.student_id}",
        resource_type="performance.riskstate",
        resource_id=enrollment.pk,
    )


@transaction.atomic
def recompute_risk(*, enrollment) -> RiskState:
    """The one place a `RiskState` is computed and written (ADR-11).

    Called from `apps.performance.tasks.recompute_risk` (Celery, debounced)
    and from `apps.students.student_360.risk_state_for` (a synchronous
    fallback for an enrolment's very first read, so a screen never has to
    wait on the async task) — the same function either way, so a verdict
    never differs by which caller asked for it first.

    "Changed" is judged against a *baseline* of `NONE`/`[]` when there is no
    previous verdict yet, not against the stored `previous_level` (which is
    genuinely `""` on a first computation, per the model's own docstring).
    A brand-new enrolment's first-ever verdict landing on `none` — the
    overwhelmingly common case, since there is rarely much to measure yet —
    is correctly "no change, no noise"; one that lands on `warning` or
    `critical` on its very first computation is still real news nobody has
    been told before, and treating that as silence would be the actual bug.
    """
    from .engine import student_performance

    performance = student_performance(enrollment)
    risk_result = performance["risk"]
    new_level = risk_result["level"]
    new_triggered = risk_result["triggered"]
    numbers = {outcome["key"]: outcome["numbers"] for outcome in risk_result["outcomes"]}
    now = timezone.now()

    existing = RiskState.objects.select_for_update().filter(enrollment=enrollment).first()
    previous_level = existing.level if existing else None
    previous_triggered = existing.triggered if existing else None
    baseline_level = previous_level or RiskLevel.NONE
    baseline_triggered = previous_triggered or []
    changed = new_level != baseline_level or set(new_triggered) != set(baseline_triggered)

    if existing is None:
        # `previous_level=""` (the field's own default — DJ001 rules out
        # `null=True` on a `CharField`) and `previous_triggered=None` (a
        # `JSONField`, where `null` is the idiomatic "nothing yet") are both
        # the "no previous verdict at all" the model's own docstring
        # promises — set explicitly rather than left to field defaults, so
        # this reads the same whichever one changes later.
        state = RiskState.objects.create(
            enrollment=enrollment,
            level=new_level,
            triggered=new_triggered,
            numbers=numbers,
            computed_at=now,
            previous_level="",
            previous_triggered=None,
        )
    else:
        existing.previous_level = existing.level
        existing.previous_triggered = existing.triggered
        existing.level = new_level
        existing.triggered = new_triggered
        existing.numbers = numbers
        existing.computed_at = now
        existing.save(
            update_fields=[
                "previous_level",
                "previous_triggered",
                "level",
                "triggered",
                "numbers",
                "computed_at",
                "updated_at",
            ]
        )
        state = existing

    record(
        action=AuditAction.RISK_RECOMPUTED,
        actor=None,
        resource_type="performance.riskstate",
        resource_id=state.pk,
        context={
            "enrollment": str(enrollment.pk),
            "level": new_level,
            "triggered": new_triggered,
            "previous_level": previous_level,
            "changed": changed,
        },
        durable=False,
    )

    if changed:
        from .signals import RISK_CHANGED

        RISK_CHANGED.send(
            sender=RiskState,
            risk_state=state,
            enrollment=enrollment,
            level=new_level,
            previous_level=previous_level,
            triggered=new_triggered,
            previous_triggered=previous_triggered,
        )
        _notify_risk_changed(enrollment=enrollment, level=new_level, previous_level=previous_level)

    return state


def risk_state_for(enrollment) -> RiskState:
    """The stored verdict for `enrollment` — computed and stored now, on the
    caller's own request, if none exists yet. Student 360's first-ever read
    of a brand-new enrolment must not show a placeholder just because the
    debounced task has not run — see `recompute_risk`'s docstring."""
    existing = RiskState.objects.filter(enrollment=enrollment).first()
    if existing is not None:
        return existing
    return recompute_risk(enrollment=enrollment)


def risk_summary(user) -> dict[str, Any]:
    """`GET /risk/summary/`'s body: counts by level within the caller's own
    authority, and the 20 most severe currently-flagged enrolments
    (`API_CONTRACTS.md`).

    Scoped by `access.visible_enrollments_for_performance` — the exact
    queryset every other performance read in this app already answers "may
    this caller see this enrolment's performance" through — never a new,
    parallel scoping rule for risk alone.

    Three queries, fixed regardless of roster size: the scoped count, one
    aggregate for the warning/critical counts, and one bounded `[:20]`
    select for the list. `none` is derived (`total - warning - critical`)
    rather than a fourth query, and correctly includes every enrolment that
    has never been computed at all — an enrolment with no `RiskState` row
    has, by definition, never triggered anything.
    """
    enrollments = access.visible_enrollments_for_performance(user)
    total = enrollments.count()

    severity_counts = dict(
        RiskState.objects.filter(enrollment__in=enrollments)
        .exclude(level=RiskLevel.NONE)
        .values_list("level")
        .annotate(count=Count("id"))
    )
    warning = severity_counts.get(RiskLevel.WARNING, 0)
    critical = severity_counts.get(RiskLevel.CRITICAL, 0)
    counts = {
        RiskLevel.NONE: max(total - warning - critical, 0),
        RiskLevel.WARNING: warning,
        RiskLevel.CRITICAL: critical,
    }

    top_states = (
        RiskState.objects.filter(enrollment__in=enrollments)
        .exclude(level=RiskLevel.NONE)
        .select_related(
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
            "enrollment__course",
        )
        .annotate(
            _rank=Case(
                When(level=RiskLevel.CRITICAL, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("_rank", "-computed_at")[:20]
    )

    return {
        "counts": counts,
        "top": [
            {
                "enrollment_id": str(state.enrollment_id),
                "student_id": str(state.enrollment.student_id),
                "student_code": state.enrollment.student.student_id,
                "student_name": state.enrollment.student.user.get_full_name(),
                "batch_code": state.enrollment.batch.code,
                "course_title": state.enrollment.course.title,
                "level": state.level,
                "triggered": state.triggered,
                "computed_at": state.computed_at.isoformat(),
                "href": f"/students/{state.enrollment.student_id}",
            }
            for state in top_states
        ],
    }
