"""How far a capability reaches for one person (ADR-02).

The role kind is the floor: superadmin and admin see every centre, manager
and counsellor their own, a trainer what they are assigned, a student their
own records. A grant on the role may *narrow* that, never widen it. The
answer is cached with the role (same prefix as the resolver, forgotten by
the same writes) and applied by `apps.organisation.scoping`.
"""

from __future__ import annotations

from apps.accounts.roles import UserRole
from apps.common.caching import remember
from apps.common.request_context import scoped

from .resolver import PREFIX, TTL

ALL, BRANCH, ASSIGNED, OWN = "all", "branch", "assigned", "own"
ORDER = [ALL, BRANCH, ASSIGNED, OWN]

SCOPE_FLOOR = {
    UserRole.SUPERADMIN: ALL,
    UserRole.ADMIN: ALL,
    UserRole.MANAGER: BRANCH,
    UserRole.COUNSELLOR: BRANCH,
    UserRole.TRAINER: ASSIGNED,
    UserRole.STUDENT: OWN,
}


def narrowest(*scopes: str) -> str:
    return max(scopes, key=ORDER.index)


def _configured_scopes(kind: str, custom_role_id) -> dict[str, str]:
    from .models import Role, RolePermission, RoleStatus

    role = None
    if custom_role_id is not None:
        role = Role.objects.filter(pk=custom_role_id, status=RoleStatus.ACTIVE, kind=kind).first()
    if role is None:
        role = Role.objects.filter(slug=kind, is_system=True).first()
    if role is None:
        return {}
    return dict(
        RolePermission.objects.filter(role=role)
        .exclude(scope="")
        .values_list("permission__code", "scope")
    )


def configured_scopes(user) -> dict[str, str]:
    kind = user.role
    custom_role_id = getattr(user, "custom_role_id", None)
    parts = (
        ("scopes", "custom", str(custom_role_id)) if custom_role_id else ("scopes", "kind", kind)
    )
    return remember(PREFIX, parts, TTL, lambda: _configured_scopes(kind, custom_role_id))


def effective_scope(user, capability: str) -> str:
    """The narrowest of the kind's floor and the configured scope."""
    if getattr(user, "is_superuser", False) or user.role == UserRole.SUPERADMIN:
        return ALL
    floor = SCOPE_FLOOR.get(user.role, OWN)
    configured = configured_scopes(user).get(capability)
    return narrowest(floor, configured) if configured else floor


def assigned_batch_ids(user) -> list:
    """Batches this person teaches or was granted, plus every batch of a
    granted course. Memoised per request: one list, however many querysets
    ask."""

    def produce():
        from apps.batches.models import Batch

        from .models import ScopeGrant

        ids: set = set()
        trainer_id = getattr(getattr(user, "trainer_profile", None), "pk", None)
        if trainer_id is not None:
            ids.update(Batch.objects.filter(trainer_id=trainer_id).values_list("pk", flat=True))
        grants = ScopeGrant.objects.filter(user=user)
        ids.update(grants.exclude(batch__isnull=True).values_list("batch_id", flat=True))
        course_ids = list(grants.exclude(course__isnull=True).values_list("course_id", flat=True))
        if course_ids:
            ids.update(Batch.objects.filter(course_id__in=course_ids).values_list("pk", flat=True))
        return list(ids)

    return scoped(f"assigned_batches:{user.pk}", produce)
