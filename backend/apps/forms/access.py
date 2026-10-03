"""Who may see and act on a form assignment.

The person a form was sent to, and the person who sent it, always see it.
Beyond that, a holder of `form.view` sees the assignments at their own
centre (`apps.organisation.scoping.scope_to_branch`) — the same reach they
have over the people involved. Cancelling needs `form.assign` on top of
that reach, or being the sender.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.organisation.scoping import scope_to_branch

from .models import FormAssignment


def visible_assignments(user) -> QuerySet[FormAssignment]:
    base = FormAssignment.objects.with_related()
    mine = Q(assigned_to=user) | Q(requested_by=user)
    if has_capability(user, Capability.FORM_VIEW):
        centre = scope_to_branch(FormAssignment.objects.all(), user, path="branch")
        return base.filter(mine | Q(pk__in=centre.values("pk")))
    return base.filter(mine)


def can_view_assignment(user, assignment: FormAssignment) -> bool:
    return visible_assignments(user).filter(pk=assignment.pk).exists()


def can_cancel_assignment(user, assignment: FormAssignment) -> bool:
    if assignment.requested_by_id and assignment.requested_by_id == getattr(user, "pk", None):
        return True
    if not has_capability(user, Capability.FORM_ASSIGN):
        return False
    return scope_to_branch(
        FormAssignment.objects.filter(pk=assignment.pk), user, path="branch"
    ).exists()
