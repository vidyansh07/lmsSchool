"""The one place the capability check reads the rows.

`apps.accounts.roles.capabilities_for` calls `resolved_capabilities`; nothing
else should. Cached under a versioned prefix (ADR-14) that every write in
`services.py` forgets — immediately and again on commit, so a test that
rolls back and a request that commits both see the truth next time.
"""

from __future__ import annotations

from django.conf import settings

from apps.common.caching import MINUTE, forget, remember

PREFIX = "auth:roles"
TTL = 10 * MINUTE

#: `views.RoleMatrixView`/`views.PermissionListView`'s own cache prefixes
#: (PERFORMANCE_PLAN.md's caching table: 10 min / 1 h, no scope key — neither
#: response varies by caller). Forgotten from the exact same call sites as
#: `PREFIX` above, by `forget_roles()` below, so there is one invalidation
#: path for every auth-shaped cache, never a second one that could drift.
MATRIX_PREFIX = "auth:matrix"
MATRIX_TTL = 10 * MINUTE
PERMISSIONS_PREFIX = "auth:permissions"
PERMISSIONS_TTL = 60 * MINUTE


def _codes_for(role) -> frozenset[str]:
    from .models import RolePermission

    return frozenset(
        RolePermission.objects.filter(role=role, permission__is_active=True).values_list(
            "permission__code", flat=True
        )
    )


def _compute(kind: str, custom_role_id) -> frozenset[str] | None:
    from .models import Role, RoleStatus

    if custom_role_id is not None:
        custom = Role.objects.filter(pk=custom_role_id, status=RoleStatus.ACTIVE, kind=kind).first()
        if custom is not None:
            return _codes_for(custom)
        # A disabled, deleted or mismatched custom role falls back to the kind:
        # the person keeps working with the system role rather than nothing.
    system = Role.objects.filter(slug=kind, is_system=True).first()
    if system is None:
        return None  # the table is not seeded — the caller uses the code matrix
    return _codes_for(system)


def resolved_capabilities(kind: str, custom_role_id=None) -> frozenset[str] | None:
    """The configured set for this kind (or custom role), or None when the
    table holds nothing yet or dynamic roles are switched off."""
    if not getattr(settings, "DYNAMIC_ROLES_ENABLED", True):
        return None
    parts = ("custom", str(custom_role_id)) if custom_role_id is not None else ("kind", kind)
    return remember(PREFIX, parts, TTL, lambda: _compute(kind, custom_role_id))


def forget_roles() -> None:
    forget(PREFIX)
    forget(MATRIX_PREFIX)
    forget(PERMISSIONS_PREFIX)
