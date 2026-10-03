"""Who may see and change an enquiry.

A holder of `enquiry.view_any` sees the enquiries at their own centre
(`scope_to_branch`); everyone sees the enquiries they own or entered.
Changing one needs `enquiry.manage` with the same reach, or owning it.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.organisation.scoping import scope_to_branch

from .models import Enquiry


def visible_enquiries(user) -> QuerySet[Enquiry]:
    base = Enquiry.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    mine = Q(owner=user) | Q(created_by=user)
    if has_capability(user, Capability.ENQUIRY_VIEW_ANY):
        centre = scope_to_branch(
            Enquiry.objects.all(), user, path="branch", capability=Capability.ENQUIRY_VIEW_ANY
        )
        return base.filter(mine | Q(pk__in=centre.values("pk")))
    return base.filter(mine)


def can_manage_enquiry(user, enquiry: Enquiry) -> bool:
    if enquiry.owner_id and enquiry.owner_id == getattr(user, "pk", None):
        return True
    if not has_capability(user, Capability.ENQUIRY_MANAGE):
        return False
    return scope_to_branch(
        Enquiry.objects.filter(pk=enquiry.pk),
        user,
        path="branch",
        capability=Capability.ENQUIRY_MANAGE,
    ).exists()
