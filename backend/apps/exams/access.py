"""Examination access control.

An exam belongs to a batch, so "whose batch is this?" answers most of it. The
one thing worth stating: an attempt is **the candidate's**, and the only people
who reach it are that candidate and the staff who may mark it. A student
holding another student's attempt id gets a 404, because the lookup runs inside
:func:`visible_attempts`.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Exam, ExamAttempt


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


def visible_exams(user) -> QuerySet[Exam]:
    base = Exam.objects.with_related()

    if has_capability(user, Capability.EXAM_VIEW_ANY):
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


def manageable_exams(user) -> QuerySet[Exam]:
    base = Exam.objects.with_related()

    if has_capability(user, Capability.EXAM_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()
    return base.filter(_trainer_scope(user, trainer)).distinct()


def can_manage_exam(user, exam: Exam) -> bool:
    if has_capability(user, Capability.EXAM_MANAGE_ANY):
        return True
    return manageable_exams(user).filter(pk=exam.pk).exists()


def can_set_exams_on(user, batch) -> bool:
    if has_capability(user, Capability.EXAM_MANAGE_ANY):
        return True

    from apps.courses.access import can_manage_course

    if can_manage_course(user, batch.course):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


def can_grade(user, exam: Exam) -> bool:
    """Mark the written answers, and publish results."""
    if has_capability(user, Capability.EXAM_GRADE_ANY):
        return True
    return can_manage_exam(user, exam)


def visible_attempts(user) -> QuerySet[ExamAttempt]:
    base = ExamAttempt.objects.with_related()

    if has_capability(user, Capability.EXAM_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(enrollment__student=student)

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(exam__in=manageable_exams(user))

    return base.none()
