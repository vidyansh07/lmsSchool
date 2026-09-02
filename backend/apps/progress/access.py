"""Progress and completion access.

A student sees their own progress. Staff see the progress of students on the
batches they can already reach — the same scope Phase 3 established, so there is
one answer to "whose student is this?".

Approving a completion is narrower still: it is an institutional decision, so it
needs `COMPLETION_APPROVE`, which sits on the administrator rung.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import CourseCompletion


def visible_enrollments(user):
    """The enrolments whose progress the caller may read.

    Delegates to Phase 3's rule rather than restating it: administrators see
    everything, a trainer sees their batches, a student sees their own.
    """
    return batch_access.visible_enrollments(user)


def visible_completions(user) -> QuerySet[CourseCompletion]:
    base = CourseCompletion.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.filter(enrollment__in=visible_enrollments(user))


def can_decide_completion(user) -> bool:
    """Approve or reject a completion. An institutional act, not a teaching one."""
    return has_capability(user, Capability.COMPLETION_APPROVE)


def can_manage_certificates(user) -> bool:
    return has_capability(user, Capability.CERTIFICATE_MANAGE)
