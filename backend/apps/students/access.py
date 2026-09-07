"""Student record access control.

Written when branches arrived, because until then the answer was a capability
and nothing else — `_base_queryset()` in `views.py` takes no user, so there was
nowhere to put a rule that depends on who is asking. Now there is one.

Three audiences:

* **Administrators, managers and counsellors** hold `student.view_any`, bounded
  to the centre they belong to. A student id from another city resolves to
  nothing, rather than to a 403 that would confirm the person exists.
* **Trainers** hold no global student right at all. They reach the students on
  the batches they teach, derived from `apps.batches.access.visible_enrollments`
  so there is one definition of "my students" rather than two.
* **Students** reach themselves.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.organisation.scoping import scope_to_branch

from .models import StudentProfile


def _base() -> QuerySet[StudentProfile]:
    return StudentProfile.objects.select_related("user", "fee_status_updated_by", "branch")


def visible_students(user) -> QuerySet[StudentProfile]:
    """Every student record the caller may see, as a queryset."""
    base = _base()

    if has_capability(user, Capability.STUDENT_VIEW_ANY):
        return scope_to_branch(base, user, path="branch")
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(enrollments__batch__trainer=trainer).distinct()

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(pk=student.pk)

    return base.none()


def reachable_students(user) -> QuerySet[StudentProfile]:
    """Every student record whose *centre* the caller is in — audience aside.

    The detail route resolves through this rather than through
    :func:`visible_students`, because the two questions that route answers have
    two different right answers. "Is this record in your world at all?" is the
    branch, and no to that is a 404: another city's student id must not be
    confirmable. "May you, a student, read a classmate?" is the audience, and no
    to that has always been a 403 — asserted five times under the IDOR banner in
    ``tests/test_security_access_control.py``, where the point is that guessing
    an id gets you a refusal rather than somebody else's data.

    Answering the second question with a 404 as well would be a product change,
    and a silent one made by swapping a queryset. So this narrows the branch and
    nothing else; :class:`~apps.common.permissions.IsOwnerOrHasCapability` keeps
    the audience.
    """
    return scope_to_branch(_base(), user, path="branch")


def can_view_student(user, profile: StudentProfile) -> bool:
    """Implemented through the queryset, so the two cannot drift apart."""
    return visible_students(user).filter(pk=profile.pk).exists()
