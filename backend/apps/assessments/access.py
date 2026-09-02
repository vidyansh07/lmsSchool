"""Assessment and result access control.

Same shape as assignments, one level simpler: an assessment always belongs to a
single batch, so "whose batch is this?" answers the whole question.

* Administrators and managers hold the global capabilities.
* A trainer reaches the assessments on the batches they teach, or on a course
  they author.
* A student reaches published and closed assessments for the batch they are
  enrolled on, and their own result rows and nobody else's.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Assessment, AssessmentResult


def _live_enrollments(user):
    student = batch_access.student_profile(user)
    if student is None:
        return []

    from apps.enrollments.models import Enrollment

    rows = Enrollment.objects.granting_access().filter(student=student).select_related("batch")
    return [row for row in rows if row.grants_access()]


def _trainer_scope(user, trainer) -> Q:
    from apps.courses.access import assigned_course_ids

    scope = Q(batch__trainer=trainer)
    authored = assigned_course_ids(user)
    if authored:
        scope |= Q(course_id__in=authored)
    return scope


def visible_assessments(user) -> QuerySet[Assessment]:
    base = Assessment.objects.with_related()

    if has_capability(user, Capability.ASSESSMENT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(_trainer_scope(user, trainer)).distinct()

    enrollments = _live_enrollments(user)
    if not enrollments:
        return base.none()
    return base.student_visible().filter(batch_id__in=[row.batch_id for row in enrollments])


def manageable_assessments(user) -> QuerySet[Assessment]:
    base = Assessment.objects.with_related()

    if has_capability(user, Capability.ASSESSMENT_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()
    return base.filter(_trainer_scope(user, trainer)).distinct()


def can_manage_assessment(user, assessment: Assessment) -> bool:
    if has_capability(user, Capability.ASSESSMENT_MANAGE_ANY):
        return True
    return manageable_assessments(user).filter(pk=assessment.pk).exists()


def can_set_assessments_on(user, batch) -> bool:
    """May the caller set a test on this batch? Asked before a record exists."""
    if has_capability(user, Capability.ASSESSMENT_MANAGE_ANY):
        return True

    from apps.courses.access import can_manage_course

    if can_manage_course(user, batch.course):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


def can_record_results(user, assessment: Assessment) -> bool:
    """Enter or import marks.

    Separate from managing the assessment so an examinations office could hold
    marking rights without the right to change the paper.
    """
    if has_capability(user, Capability.RESULT_MANAGE_ANY):
        return True
    return can_manage_assessment(user, assessment)


def visible_results(user) -> QuerySet[AssessmentResult]:
    base = AssessmentResult.objects.with_related()

    if has_capability(user, Capability.ASSESSMENT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    student = batch_access.student_profile(user)
    if student is not None:
        # A student sees their own marks, and only for assessments that are
        # visible to them — a mark on a draft test is not a mark yet.
        return base.filter(enrollment__student=student, assessment__in=visible_assessments(user))

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(assessment__in=manageable_assessments(user))

    return base.none()
