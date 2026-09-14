"""Who sees which requirements.

The same shape as `apps.dsr.access`: the capability holder sees their
centre's, a trainer sees their centre's because they are the people being
asked, and a student has no view at all — a 403, not an empty list (D-121).
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.organisation.scoping import actor_branch_id, scope_to_branch

from .models import TrainerRequirement


def can_read_requirements(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if has_capability(user, Capability.REQUIREMENT_MANAGE):
        return True
    return batch_access.trainer_profile(user) is not None


def visible_requirements(user) -> QuerySet[TrainerRequirement]:
    base = TrainerRequirement.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    if has_capability(user, Capability.REQUIREMENT_MANAGE):
        return scope_to_branch(base, user, path="branch")
    if batch_access.trainer_profile(user) is None:
        return base.none()
    branch_id = actor_branch_id(user)
    if branch_id is None:
        return base.none()
    return base.filter(branch_id=branch_id)


def can_manage_requirements(user) -> bool:
    return has_capability(user, Capability.REQUIREMENT_MANAGE)
