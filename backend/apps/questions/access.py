"""Question bank access.

Narrower than the rest of the product on purpose: the bank contains the
answers, so **no student reaches it at all**, by any route. Students meet
questions only through an exam attempt, where the exam engine hands them a
shape with the answers stripped.

Staff reach a question when they hold the capability, or when it belongs to a
course they author.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Question


def _staff_scope(user) -> Q | None:
    """The courses a trainer may draw questions from, or None for nobody."""
    from apps.courses.access import assigned_course_ids

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return None

    scope = Q(course__batches__trainer=trainer)
    authored = assigned_course_ids(user)
    if authored:
        scope |= Q(course_id__in=authored)
    # Shared questions belong to no course, so anybody who may author at all
    # may use them.
    scope |= Q(course__isnull=True)
    return scope


def visible_questions(user) -> QuerySet[Question]:
    base = Question.objects.with_related()

    if has_capability(user, Capability.QUESTION_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    scope = _staff_scope(user)
    if scope is None:
        # A student. The bank holds the answers; there is no read for them.
        return base.none()
    return base.filter(scope).distinct()


def manageable_questions(user) -> QuerySet[Question]:
    base = Question.objects.with_related()

    if has_capability(user, Capability.QUESTION_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    scope = _staff_scope(user)
    if scope is None:
        return base.none()
    # A trainer may edit questions on their own courses, but not the shared
    # bank: a shared question is used by papers they cannot see.
    return base.filter(scope & Q(course__isnull=False)).distinct()


def can_manage_question(user, question: Question) -> bool:
    if has_capability(user, Capability.QUESTION_MANAGE_ANY):
        return True
    return manageable_questions(user).filter(pk=question.pk).exists()


def can_write_questions_for(user, course) -> bool:
    """Asked before a question exists."""
    if has_capability(user, Capability.QUESTION_MANAGE_ANY):
        return True
    if course is None:
        # Only a capability holder writes into the shared bank.
        return False

    from apps.courses.access import can_manage_course

    if can_manage_course(user, course):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and course.batches.filter(trainer=trainer).exists()
