"""Creating and changing roles. Every rule about who may hand out what lives
here, not in the views, so the admin site and a management command obey it
too.

The ladder invariant (D-033, D-095) is kept over *effective* sets: nobody
may build, assign or widen a role beyond what they themselves hold.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import UserRole, effective_capabilities
from apps.audit.services import AuditAction, record
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError

from .models import Permission, PermissionScope, Role, RolePermission, RoleStatus
from .resolver import forget_roles
from .sync import SUPERADMIN_ONLY

#: The widest reach each kind may be configured to. A grant may narrow below
#: the floor; it may never widen above it (ADR-02).
SCOPE_FLOOR = {
    UserRole.SUPERADMIN: PermissionScope.ALL,
    UserRole.ADMIN: PermissionScope.ALL,
    UserRole.MANAGER: PermissionScope.BRANCH,
    UserRole.COUNSELLOR: PermissionScope.BRANCH,
    UserRole.TRAINER: PermissionScope.ASSIGNED,
    UserRole.STUDENT: PermissionScope.OWN,
}
SCOPE_ORDER = [
    PermissionScope.ALL,
    PermissionScope.BRANCH,
    PermissionScope.ASSIGNED,
    PermissionScope.OWN,
]


def _forget() -> None:
    forget_roles()
    transaction.on_commit(forget_roles)


def _is_superadmin(actor) -> bool:
    return bool(getattr(actor, "is_superuser", False)) or actor.role == UserRole.SUPERADMIN


def _check_grants(*, actor: User, kind: str, grants: list[dict[str, Any]]) -> dict[str, Permission]:
    """Validate a permission list against the catalog, the kind and the ladder.

    Returns the permissions keyed by code. Refuses: an unknown code, a
    superadmin-only code on any other kind, a scope wider than the kind's
    floor, and — with a 403, not a 400 (D-097) — any code the actor does not
    hold themselves.
    """
    codes = [grant["code"] for grant in grants]
    if len(set(codes)) != len(codes):
        raise ApplicationError({"permissions": ["A permission is listed twice."]})
    found = {row.code: row for row in Permission.objects.filter(code__in=codes, is_active=True)}
    unknown = sorted(set(codes) - set(found))
    if unknown:
        raise ApplicationError({"permissions": [f"Unknown permission: {', '.join(unknown)}."]})
    if kind != UserRole.SUPERADMIN:
        reserved = sorted(set(codes) & SUPERADMIN_ONLY)
        if reserved:
            raise ApplicationError(
                {"permissions": [f"Only the superadmin role may hold {', '.join(reserved)}."]}
            )
    floor = SCOPE_ORDER.index(SCOPE_FLOOR[kind])
    for grant in grants:
        scope = grant.get("scope") or ""
        if scope and SCOPE_ORDER.index(scope) < floor:
            widest = SCOPE_FLOOR[kind].label.lower()
            raise ApplicationError(
                {"permissions": [f"{grant['code']}: a {kind} role cannot see wider than {widest}."]}
            )
    if not _is_superadmin(actor):
        held = effective_capabilities(actor)
        beyond = sorted(set(codes) - held)
        if beyond:
            raise AuthorityError(f"You cannot grant what you do not hold: {', '.join(beyond)}.")
    return found


def _replace_grants(
    *, role: Role, grants: list[dict[str, Any]], permissions: dict[str, Permission], actor: User
) -> dict[str, list[str]]:
    """Make the role's grants equal to `grants`. Returns what changed."""
    current = {grant.permission.code: grant for grant in role.grants.select_related("permission")}
    wanted = {grant["code"]: grant for grant in grants}
    added, removed, rescoped = [], [], []
    for code, grant in current.items():
        if code not in wanted:
            if grant.is_locked and not _is_superadmin(actor):
                raise AuthorityError(f"{code} is locked on this role.")
            grant.delete()
            removed.append(code)
    for code, grant in wanted.items():
        scope = grant.get("scope") or ""
        existing = current.get(code)
        if existing is None:
            RolePermission.objects.create(
                role=role, permission=permissions[code], scope=scope, granted_by=actor
            )
            added.append(code)
        elif existing.scope != scope:
            if existing.is_locked and not _is_superadmin(actor):
                raise AuthorityError(f"{code} is locked on this role.")
            existing.scope = scope
            existing.save(update_fields=["scope", "updated_at"])
            rescoped.append(code)
    return {"added": sorted(added), "removed": sorted(removed), "rescoped": sorted(rescoped)}


@transaction.atomic
def create_role(
    *,
    actor: User,
    slug: str,
    name: str,
    kind: str,
    description: str = "",
    permissions: list[dict[str, Any]] | None = None,
) -> Role:
    if kind not in UserRole.values:
        raise ApplicationError({"kind": ["Choose one of the system roles to build from."]})
    if kind == UserRole.SUPERADMIN:
        raise ApplicationError({"kind": ["A custom role cannot be built from superadmin."]})
    if Role.objects.filter(slug=slug).exists():
        raise ConflictError({"slug": ["A role with this name already exists."]})
    grants = permissions if permissions is not None else []
    found = _check_grants(actor=actor, kind=kind, grants=grants)
    role = Role.objects.create(
        slug=slug,
        name=name.strip(),
        kind=kind,
        description=description.strip(),
        created_by=actor,
        updated_by=actor,
    )
    _replace_grants(role=role, grants=grants, permissions=found, actor=actor)
    _forget()
    record(
        action=AuditAction.ROLE_CREATED,
        actor=actor,
        resource_type="role",
        resource_id=role.pk,
        context={"slug": slug, "kind": kind, "permissions": sorted(found)},
    )
    return role


@transaction.atomic
def update_role(
    *,
    actor: User,
    role: Role,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    permissions: list[dict[str, Any]] | None = None,
) -> Role:
    if role.is_locked and not _is_superadmin(actor):
        raise AuthorityError("This role is locked.")
    changes: dict[str, Any] = {}
    if role.is_system:
        if name is not None and name.strip() != role.name:
            raise ApplicationError({"name": ["A system role keeps its name."]})
        if status is not None and status != role.status:
            raise ApplicationError({"status": ["A system role cannot be disabled."]})
    if name is not None and name.strip() != role.name:
        changes["name"] = {"from": role.name, "to": name.strip()}
        role.name = name.strip()
    if description is not None and description.strip() != role.description:
        changes["description"] = {"from": role.description, "to": description.strip()}
        role.description = description.strip()
    if status is not None and status != role.status:
        if status not in RoleStatus.values:
            raise ApplicationError({"status": ["Unknown status."]})
        changes["status"] = {"from": role.status, "to": status}
        role.status = status
    if permissions is not None:
        found = _check_grants(actor=actor, kind=role.kind, grants=permissions)
        diff = _replace_grants(role=role, grants=permissions, permissions=found, actor=actor)
        if any(diff.values()):
            changes["permissions"] = diff
    if not changes:
        return role
    role.updated_by = actor
    role.save(
        update_fields=[*(k for k in changes if k != "permissions"), "updated_by", "updated_at"]
    )
    _forget()
    record(
        action=AuditAction.ROLE_UPDATED,
        actor=actor,
        resource_type="role",
        resource_id=role.pk,
        context={"slug": role.slug, "changes": changes},
    )
    if "permissions" in changes or "status" in changes:
        # A person holding this role is working under a set that just changed;
        # their next request re-resolves, and a live session under the old set
        # is ended the way a role change ends one.
        from apps.accounts.services import revoke_sessions

        for user in role.users.filter(is_active=True):
            revoke_sessions(user=user, actor=actor, reason="role_permissions_changed")
    return role


@transaction.atomic
def delete_role(*, actor: User, role: Role, reason: str) -> None:
    if role.is_system:
        raise ApplicationError({"role": ["A system role cannot be removed."]})
    if role.is_locked and not _is_superadmin(actor):
        raise AuthorityError("This role is locked.")
    holders = role.users.count()
    if holders:
        raise ConflictError(
            {"role": [f"{holders} account(s) still hold this role. Move them first."]}
        )
    soft_delete(instance=role, actor=actor, reason=reason)
    _forget()
    record(
        action=AuditAction.ROLE_DELETED,
        actor=actor,
        resource_type="role",
        resource_id=role.pk,
        context={"slug": role.slug, "reason": reason},
    )


def check_custom_role_assignment(
    *, actor: User, target: User, role: Role | None, kind: str
) -> None:
    """Rules for putting a custom role on an account (called by
    `accounts.services.update_user`): same kind, active, and no wider than
    the actor's own reach."""
    if role is None:
        return
    if role.kind != kind:
        raise ApplicationError(
            {"custom_role": [f"{role.name} is built from {role.kind}, not {kind}."]}
        )
    if role.status != RoleStatus.ACTIVE:
        raise ApplicationError({"custom_role": ["That role is disabled."]})
    if not _is_superadmin(actor):
        beyond = sorted(role.codes - effective_capabilities(actor))
        if beyond:
            raise AuthorityError("You cannot assign a role that holds more than your own.")


def matrix() -> dict[str, Any]:
    """Every role by every permission, as the five states the screen renders."""
    permissions = list(Permission.objects.filter(is_active=True).order_by("category", "code"))
    roles = list(Role.objects.with_related().order_by("-is_system", "kind", "name"))
    from apps.accounts.roles import ROLE_CAPABILITIES

    cells: dict[str, dict[str, str]] = {}
    for role in roles:
        grants = {grant.permission.code: grant for grant in role.grants.all()}
        seeded = set(ROLE_CAPABILITIES.get(role.kind, frozenset()))
        row: dict[str, str] = {}
        for permission in permissions:
            grant = grants.get(permission.code)
            if role.is_system and role.kind == UserRole.SUPERADMIN:
                row[permission.code] = "system"
            elif grant is None:
                row[permission.code] = "denied"
            elif grant.is_locked:
                row[permission.code] = "locked"
            elif permission.code in seeded:
                row[permission.code] = "inherited"
            else:
                row[permission.code] = "explicit"
        cells[role.slug] = row
    return {"roles": roles, "permissions": permissions, "cells": cells}


__all__ = [
    "SCOPE_FLOOR",
    "check_custom_role_assignment",
    "create_role",
    "delete_role",
    "matrix",
    "update_role",
]
