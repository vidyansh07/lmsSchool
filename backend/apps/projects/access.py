"""Project access control.

The same shape as assignments, with one addition: a project has a **reviewer**,
and being named as one is authority in itself. So a trainer reaches a project
three ways — they teach a batch it applies to, they author the course, or they
were named its mentor — and no other way.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Project, StudentProject


def _live_enrollments(user):
    student = batch_access.student_profile(user)
    if student is None:
        return []

    from apps.enrollments.models import Enrollment

    rows = Enrollment.objects.granting_access().filter(student=student).select_related("batch")
    return [row for row in rows if row.grants_access()]


def _trainer_scope(user, trainer) -> Q:
    from apps.courses.access import assigned_course_ids

    scope = (
        Q(batch__trainer=trainer)
        | Q(batch__isnull=True, course__batches__trainer=trainer)
        | Q(reviewer=trainer)
    )
    authored = assigned_course_ids(user)
    if authored:
        scope |= Q(course_id__in=authored)
    return scope


def visible_projects(user) -> QuerySet[Project]:
    base = Project.objects.with_related()

    if has_capability(user, Capability.PROJECT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(_trainer_scope(user, trainer)).distinct()

    enrollments = _live_enrollments(user)
    if not enrollments:
        return base.none()

    scope = Q()
    for enrollment in enrollments:
        scope |= Q(course_id=enrollment.course_id) & (
            Q(batch__isnull=True) | Q(batch_id=enrollment.batch_id)
        )
    return base.student_visible().filter(scope).distinct()


def manageable_projects(user) -> QuerySet[Project]:
    base = Project.objects.with_related()

    if has_capability(user, Capability.PROJECT_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()
    return base.filter(_trainer_scope(user, trainer)).distinct()


def can_manage_project(user, project: Project) -> bool:
    if has_capability(user, Capability.PROJECT_MANAGE_ANY):
        return True
    return manageable_projects(user).filter(pk=project.pk).exists()


def can_set_projects_on(user, course, batch=None) -> bool:
    """Asked before a project exists, so it asks about the course."""
    if has_capability(user, Capability.PROJECT_MANAGE_ANY):
        return True

    from apps.courses.access import can_manage_course

    if can_manage_course(user, course):
        return True
    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False
    if batch is not None:
        return batch.trainer_id == trainer.pk
    return course.batches.filter(trainer=trainer).exists()


def can_review(user, project: Project) -> bool:
    """Review, request rework, and award marks."""
    if has_capability(user, Capability.PROJECT_REVIEW_ANY):
        return True
    return can_manage_project(user, project)


def visible_student_projects(user) -> QuerySet[StudentProject]:
    """A student sees their own work; a mentor sees the work they may review."""
    base = StudentProject.objects.with_related()

    if has_capability(user, Capability.PROJECT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(enrollment__student=student)

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(project__in=manageable_projects(user))

    return base.none()
