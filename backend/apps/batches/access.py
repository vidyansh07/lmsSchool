"""Batch and enrolment access control.

Same shape as ``apps.courses.access``: views ask, they never decide, and the
object being authorised is always the one fetched from the database — never an
identifier the client supplied.

Three audiences, three answers:

* **Administrators** hold the global capabilities and see everything.
* **Trainers** see the batches they are assigned to teach. That comes from
  ``Batch.trainer``, resolved per record — there is no global trainer batch
  capability, so a trainer cannot reach a batch by guessing its id.
* **Students** see the batches they are enrolled on, and only their own
  enrolment rows.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability

from .models import Batch


def _profile_of(user, attribute: str):
    """The caller's student or trainer profile, or None."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    return getattr(user, attribute, None)


def trainer_profile(user):
    return _profile_of(user, "trainer_profile")


def student_profile(user):
    return _profile_of(user, "student_profile")


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------


def visible_batches(user) -> QuerySet[Batch]:
    """Every batch the caller may see, as a queryset.

    Returned as a queryset rather than filtered in Python so the database
    applies the rule — a caller cannot page, sort or filter past their own
    visibility.
    """
    base = Batch.objects.with_related()

    if has_capability(user, Capability.BATCH_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = trainer_profile(user)
    if trainer is not None:
        return base.filter(trainer=trainer)

    student = student_profile(user)
    if student is not None:
        # Only batches this student actually holds a place on — including
        # cancelled and completed ones, so their history stays visible.
        return base.filter(enrollments__student=student).distinct()

    return base.none()


def can_manage_batch(user, batch: Batch) -> bool:
    """Edit the batch, its schedule and its roster.

    ``batch`` is unused today — batch management is a global capability —
    but the signature matches every other check so a per-batch rule can be
    added later without changing a single call site.
    """
    return has_capability(user, Capability.BATCH_UPDATE_ANY)


def can_view_batch(user, batch: Batch) -> bool:
    if has_capability(user, Capability.BATCH_VIEW_ANY):
        return True

    trainer = trainer_profile(user)
    if trainer is not None and batch.trainer_id == trainer.pk:
        return True

    student = student_profile(user)
    if student is not None:
        return batch.enrollments.filter(student=student).exists()

    return False


def can_view_roster(user, batch: Batch) -> bool:
    """Who may see the list of students on a batch.

    Administrators and the batch's own trainer. Deliberately *not* the other
    students: a classmate list is other people's personal data, and nothing in
    this phase needs it.
    """
    if has_capability(user, Capability.ENROLMENT_VIEW_ANY):
        return True
    trainer = trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


def can_manage_schedule(user, batch: Batch) -> bool:
    """See :func:`can_manage_batch` on the unused ``batch`` argument."""
    return has_capability(user, Capability.BATCH_MANAGE_SCHEDULE)


# ---------------------------------------------------------------------------
# Enrolments
# ---------------------------------------------------------------------------


def visible_enrollments(user):
    """Every enrolment row the caller may see."""
    from apps.enrollments.models import Enrollment

    base = Enrollment.objects.with_related()

    if has_capability(user, Capability.ENROLMENT_VIEW_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = trainer_profile(user)
    if trainer is not None:
        # A trainer sees the enrolments on their own batches, and no others.
        return base.filter(batch__trainer=trainer)

    student = student_profile(user)
    if student is not None:
        return base.filter(student=student)

    return base.none()


def can_view_enrollment(user, enrollment) -> bool:
    if has_capability(user, Capability.ENROLMENT_VIEW_ANY):
        return True

    student = student_profile(user)
    if student is not None and enrollment.student_id == student.pk:
        return True

    trainer = trainer_profile(user)
    return trainer is not None and enrollment.batch.trainer_id == trainer.pk


def can_manage_enrollment(user, enrollment) -> bool:
    """Change an enrolment's status.

    Administrators only. A trainer may see their students but not suspend or
    cancel them, and a student may not change their own status — both of those
    are institutional decisions.
    """
    return has_capability(user, Capability.ENROLMENT_UPDATE_ANY)
