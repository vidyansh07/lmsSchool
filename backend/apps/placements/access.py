"""Who may see and record a placement.

Three audiences, and the first two are the point of the app being separate:

* **A placement officer, manager, counsellor or administrator** holds
  `placement.view_any`, bounded to their own centre
  (`scope_to_branch`) — so Himmat Nagar's offers are not Jaipur corporate's
  to read, and the other way round.
* **A trainer** holds nothing here by default, not even for a student on a
  batch they teach. Their reach over a student's *learning* is per record
  (`apps.batches.access`); an offer and its package are not learning, and a
  trainer who should see them — the one doing the interview preparation — is
  given `placement.view_any` through a custom role (ADR-02) by somebody who
  decided they should have it.
* **A student** reaches their own offers and nobody else's.

`placement.manage` is checked separately from reading: a role may be able to
see every offer at its centre and record none of them.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.organisation.scoping import scope_to_branch

from .models import Placement


def visible_placements(user) -> QuerySet[Placement]:
    """Every placement the caller may see, as a queryset."""
    base = Placement.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    if has_capability(user, Capability.PLACEMENT_VIEW_ANY):
        return scope_to_branch(base, user, path="branch", capability=Capability.PLACEMENT_VIEW_ANY)

    student = batch_access.student_profile(user)
    if student is not None:
        return base.filter(student=student)

    return base.none()


def can_manage_placements(user) -> bool:
    """Whether this caller may record or change an offer at all. *Which*
    student they may record one for is a separate question, answered by
    resolving the student out of `students.access.visible_students` — a write
    is a read as well."""
    return has_capability(user, Capability.PLACEMENT_MANAGE)
