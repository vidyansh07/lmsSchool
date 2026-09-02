"""Announcement access.

Two questions, and they have different answers.

**Who may read one?** Whoever it is addressed to. An announcement to everyone is
readable by everyone signed in; one to a batch by the people on that batch and
the staff who can already see that batch; one to named people by those people.

**Who may write one?** §7.3 says admin, manager or an *authorized* trainer. A
trainer's authority is per batch, as everywhere else: they may address the
batches they teach and the courses they author, and nothing wider. Announcing to
everyone needs the global capability.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Announcement, Audience


def visible_announcements(user) -> QuerySet[Announcement]:
    """The noticeboard, as this person sees it."""
    base = Announcement.objects.with_related()

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return base

    scope = Q(audience=Audience.EVERYONE) | Q(audience=Audience.SELECTED, recipients=user)

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        # A trainer sees what they may write, plus what is addressed to them.
        scope |= Q(batch__trainer=trainer) | Q(created_by=user)
        from apps.courses.access import assigned_course_ids

        authored = assigned_course_ids(user)
        if authored:
            scope |= Q(course_id__in=authored)
        return base.filter(scope).distinct()

    student = batch_access.student_profile(user)
    if student is not None:
        from apps.enrollments.models import Enrollment

        rows = Enrollment.objects.granting_access().filter(student=student)
        live = [row for row in rows if row.grants_access()]
        if live:
            scope |= Q(batch_id__in=[row.batch_id for row in live]) | Q(
                course_id__in=[row.course_id for row in live]
            )
        # A student sees the noticeboard, never a draft.
        return base.live().filter(scope).distinct()

    return base.filter(scope).distinct()


def manageable_announcements(user) -> QuerySet[Announcement]:
    base = Announcement.objects.with_related()

    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()

    from apps.courses.access import assigned_course_ids

    scope = Q(batch__trainer=trainer) | Q(created_by=user)
    authored = assigned_course_ids(user)
    if authored:
        scope |= Q(course_id__in=authored)
    return base.filter(scope).distinct()


def can_publish_to(user, *, audience: str, course=None, batch=None) -> bool:
    """May this person address this audience?"""
    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return True

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False

    if audience == Audience.BATCH and batch is not None:
        return batch.trainer_id == trainer.pk
    if audience == Audience.COURSE and course is not None:
        from apps.courses.access import can_manage_course

        return can_manage_course(user, course) or course.batches.filter(trainer=trainer).exists()
    # Everyone, and naming arbitrary people, stay with the capability holders.
    return False


def can_manage(user, announcement: Announcement) -> bool:
    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return True
    return manageable_announcements(user).filter(pk=announcement.pk).exists()
