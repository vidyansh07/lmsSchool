"""Assignment access control.

Three audiences, and the interesting one is the trainer.

A trainer holds no global assignment capability. Their authority comes from one
of two relationships, both resolved per record:

* they teach a batch the assignment applies to, or
* they author the course it belongs to (``courses.CourseAssignment``).

Either is enough to set and mark work; neither is enough to touch somebody
else's course. An assignment id from another trainer's course resolves to
nothing, because the record is fetched from a queryset the caller is already
entitled to rather than fetched first and checked afterwards.

A student sees published and closed assignments for the courses they are
actually enrolled on — matched **per enrolment**, so a student on batch 1 never
sees work set specifically for batch 2 of the same course.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Assignment, AssignmentSubmission


def _live_enrollments(user):
    """The caller's enrolments that currently open a course.

    Evaluated through :meth:`Enrollment.grants_access` rather than in SQL so the
    date window and batch status are weighed by the one function that owns that
    rule.
    """
    student = batch_access.student_profile(user)
    if student is None:
        return []

    from apps.enrollments.models import Enrollment

    rows = Enrollment.objects.granting_access().filter(student=student).select_related("batch")
    return [row for row in rows if row.grants_access()]


def visible_assignments(user) -> QuerySet[Assignment]:
    """Every assignment the caller may see, as a queryset."""
    base = Assignment.objects.with_related()

    if has_capability(user, Capability.ASSIGNMENT_VIEW_ANY):
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
        # Course-wide work, or work set for this student's own batch. Written
        # per enrolment rather than as two `__in` lists, which would let a
        # student on two courses see batch-specific work from the wrong pairing.
        scope |= Q(course_id=enrollment.course_id) & (
            Q(batch__isnull=True) | Q(batch_id=enrollment.batch_id)
        )
    return base.student_visible().filter(scope).distinct()


def _trainer_scope(user, trainer) -> Q:
    """Assignments a trainer may act on: their batches, or their courses."""
    from apps.courses.access import assigned_course_ids

    scope = Q(batch__trainer=trainer) | Q(batch__isnull=True, course__batches__trainer=trainer)
    authored = assigned_course_ids(user)
    if authored:
        scope |= Q(course_id__in=authored)
    return scope


def manageable_assignments(user) -> QuerySet[Assignment]:
    """Assignments the caller may create against, edit, publish or grade."""
    base = Assignment.objects.with_related()

    if has_capability(user, Capability.ASSIGNMENT_MANAGE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()
    return base.filter(_trainer_scope(user, trainer)).distinct()


def can_manage_assignment(user, assignment: Assignment) -> bool:
    """Edit the brief, publish it, close it, delete it."""
    if has_capability(user, Capability.ASSIGNMENT_MANAGE_ANY):
        return True
    return manageable_assignments(user).filter(pk=assignment.pk).exists()


def can_set_assignments_on(user, course, batch=None) -> bool:
    """May the caller create work on this course, optionally scoped to a batch?

    Checked before the assignment exists, so it asks about the *course* rather
    than about a record: an administrator always may; a trainer may when they
    author the course or teach the batch the work is for.
    """
    if has_capability(user, Capability.ASSIGNMENT_MANAGE_ANY):
        return True

    from apps.courses.access import can_manage_course

    if can_manage_course(user, course):
        return True

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False
    if batch is not None:
        return batch.trainer_id == trainer.pk
    # Course-wide work requires teaching at least one batch of that course.
    return course.batches.filter(trainer=trainer).exists()


def can_grade(user, assignment: Assignment) -> bool:
    """Award marks on this assignment's submissions.

    Separate from managing it so grading can be widened or narrowed later
    without touching who may edit a brief.
    """
    if has_capability(user, Capability.ASSIGNMENT_GRADE_ANY):
        return True
    return can_manage_assignment(user, assignment)


def visible_submissions(user) -> QuerySet[AssignmentSubmission]:
    """Every submission row the caller may see.

    A student sees their own attempts and nobody else's — the isolation rule
    §4.8 asks to be tested. A trainer sees the attempts on the assignments they
    manage, which is derived from the same scope, not a second copy of it.
    """
    base = AssignmentSubmission.objects.with_related()

    if has_capability(user, Capability.ASSIGNMENT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(enrollment__student=student)

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(assignment__in=manageable_assignments(user))

    return base.none()


def can_download_submission_file(user, submission: AssignmentSubmission) -> bool:
    """Who may read the bytes a student handed in.

    The student who submitted it, the staff who may grade it, and nobody else —
    a classmate holding a file id gets a 404, because the lookup runs inside
    :func:`visible_submissions`.
    """
    return visible_submissions(user).filter(pk=submission.pk).exists()
