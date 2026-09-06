"""Who may see whose performance, and who may write a review or feedback.

Reading follows the same shape as everywhere else in this codebase (see
`apps.batches.access`, `apps.reporting.access`): an administrator or manager
holding `performance.view_any` sees everyone, a trainer sees the students on
the batches they teach and their own trainer figures, and a student sees only
their own. Nobody else sees any of it — a counsellor brings students in and
has no reason to read how they are doing academically, which is exactly why
`Capability.PERFORMANCE_VIEW_ANY` is absent from `_COUNSELLOR_CAPABILITIES`.

Writing is a single, stricter capability: `review.manage_any` covers both a
formal review and a piece of feedback, because both are the same act — putting
a judgement about somebody on their record — at different weights.

Self-review is refused unconditionally, for anyone, including a superadmin. A
person marking their own work is not a review; the whole point of the record is
that somebody else looked.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Feedback, PerformanceReview, PerformanceSubjectType


def can_view_any_performance(user) -> bool:
    return has_capability(user, Capability.PERFORMANCE_VIEW_ANY)


def can_manage_reviews(user) -> bool:
    """Write a review or a piece of feedback, about anyone the caller may reach."""
    return has_capability(user, Capability.REVIEW_MANAGE_ANY)


def is_self_review(actor, *, student=None, trainer=None) -> bool:
    """Whether ``actor`` is the very person a review or feedback is about.

    Compared through the account, not the profile: a student's own account is
    what `request.user` is, and their `StudentProfile` is a different row
    entirely.
    """
    actor_id = getattr(actor, "pk", None)
    if actor_id is None:
        return False
    if student is not None:
        return student.user_id == actor_id
    if trainer is not None:
        return trainer.user_id == actor_id
    return False


def visible_enrollments_for_performance(user) -> QuerySet:
    """Enrolments whose *student* performance this caller may read."""
    from apps.enrollments.models import Enrollment

    base = Enrollment.objects.with_related()

    if can_view_any_performance(user):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(batch__trainer=trainer)

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(student=student)

    return base.none()


def can_view_student_performance(user, enrollment) -> bool:
    if can_view_any_performance(user):
        return True

    student = batch_access.student_profile(user)
    if student is not None and enrollment.student_id == student.pk:
        return True

    trainer = batch_access.trainer_profile(user)
    return trainer is not None and enrollment.batch.trainer_id == trainer.pk


def can_view_batch_performance(user, batch) -> bool:
    """Whether the caller may see the cohort performance view for one batch."""
    if can_view_any_performance(user):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


def can_view_trainer_performance(user, trainer) -> bool:
    if can_view_any_performance(user):
        return True
    own = batch_access.trainer_profile(user)
    return own is not None and own.pk == trainer.pk


def visible_reviews(user) -> QuerySet:
    """Reviews the caller may read: everyone's, or only their own.

    A review is shown to the person it is about — there is little point
    reviewing somebody in a way they can never see — but never to anyone else
    who is not already entitled to read performance generally.
    """
    base = PerformanceReview.objects.with_related()

    if can_manage_reviews(user) or can_view_any_performance(user):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    student = batch_access.student_profile(user)
    trainer = batch_access.trainer_profile(user)
    scope = Q(pk__isnull=True)
    if student is not None:
        scope |= Q(subject_type=PerformanceSubjectType.STUDENT, student=student)
    if trainer is not None:
        scope |= Q(subject_type=PerformanceSubjectType.TRAINER, trainer=trainer)
    return base.filter(scope)


def can_view_review(user, review: PerformanceReview) -> bool:
    if can_manage_reviews(user) or can_view_any_performance(user):
        return True
    student = batch_access.student_profile(user)
    if student is not None and review.student_id == student.pk:
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and review.trainer_id == trainer.pk


def visible_feedback(user) -> QuerySet:
    """Feedback the caller may read.

    A subject only sees feedback marked `visible_to_subject` — a manager's
    private note kept for the next formal review is feedback too, and stays
    private until somebody decides otherwise. The author always sees what they
    wrote, visible or not.
    """
    base = Feedback.objects.with_related()

    if can_manage_reviews(user) or can_view_any_performance(user):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    scope = Q(author=user)
    student = batch_access.student_profile(user)
    if student is not None:
        scope |= Q(
            subject_type=PerformanceSubjectType.STUDENT,
            student=student,
            visible_to_subject=True,
        )
    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        scope |= Q(
            subject_type=PerformanceSubjectType.TRAINER,
            trainer=trainer,
            visible_to_subject=True,
        )
    return base.filter(scope)
