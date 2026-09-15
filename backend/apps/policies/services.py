"""Writing and reading policies (ERP Phase 3, ADR-04).

Every rule about a policy write lives here: validate against the schema,
require an explicit `confirm` for a critical key, write the `PolicyVersion`
history row, forget the cache, audit. Views resolve *which* branch a caller
may name (a scope question, `views._resolve_branch`); this module never asks
who the caller is beyond stamping `updated_by`/`changed_by`.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.audit.services import AuditAction, record
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError

from .models import Policy, PolicyScope, PolicyVersion
from .resolver import forget_policies
from .schemas import categories as schema_categories
from .schemas import iter_schema, schema_for, validate_value

CONFIRM_REQUIRED = "This is a critical setting. Confirm by repeating its key exactly."


def _forget() -> None:
    forget_policies()
    transaction.on_commit(forget_policies)


def _branch_id(branch: Any) -> Any:
    return getattr(branch, "pk", branch)


def _require_schema(category: str, key: str) -> dict[str, Any]:
    schema = schema_for(category, key)
    if schema is None:
        raise ApplicationError({"key": [f"Unknown policy: {category}.{key}."]})
    return schema


def _entry(
    category: str, key: str, schema: dict[str, Any], row: Policy | None, branch_id: Any
) -> dict[str, Any]:
    value = row.value if row is not None else schema["default"]
    return {
        "category": category,
        "key": key,
        "value": value,
        "default": schema["default"],
        "is_default": row is None,
        "scope": row.scope
        if row is not None
        else (PolicyScope.BRANCH if branch_id else PolicyScope.GLOBAL),
        "branch": row.branch_id if row is not None else branch_id,
        "version": row.version if row is not None else 0,
        "critical": bool(schema.get("critical")),
        "description": schema.get("description", ""),
        "updated_at": row.updated_at if row is not None else None,
        "updated_by_name": (
            row.updated_by.get_full_name() if row is not None and row.updated_by_id else None
        ),
    }


def get_policy(*, category: str, key: str, branch: Any = None) -> dict[str, Any]:
    """One key's full picture: the value in force, its default, and the row
    behind it, if any — resolved branch override, then global (ADR-04)."""
    schema = _require_schema(category, key)
    branch_id = _branch_id(branch)
    row = None
    if branch_id is not None:
        row = (
            Policy.objects.filter(category=category, key=key, branch_id=branch_id)
            .select_related("updated_by")
            .first()
        )
    if row is None:
        row = (
            Policy.objects.filter(
                category=category, key=key, scope=PolicyScope.GLOBAL, branch__isnull=True
            )
            .select_related("updated_by")
            .first()
        )
    return _entry(category, key, schema, row, branch_id)


def list_policies(*, category: str | None = None, branch: Any = None) -> list[dict[str, Any]]:
    """Every schema key (optionally narrowed to one category), resolved for
    `branch`. Two queries regardless of how many keys the schema holds."""
    if category is not None and category not in schema_categories():
        raise ApplicationError({"category": [f"Unknown policy category: {category}."]})
    branch_id = _branch_id(branch)
    items = [
        (cat, key, schema)
        for cat, key, schema in iter_schema()
        if category is None or cat == category
    ]
    global_rows = {
        (row.category, row.key): row
        for row in Policy.objects.filter(
            scope=PolicyScope.GLOBAL, branch__isnull=True
        ).select_related("updated_by")
    }
    branch_rows: dict[tuple[str, str], Policy] = {}
    if branch_id is not None:
        branch_rows = {
            (row.category, row.key): row
            for row in Policy.objects.filter(branch_id=branch_id).select_related("updated_by")
        }
    return [
        _entry(
            cat, key, schema, branch_rows.get((cat, key)) or global_rows.get((cat, key)), branch_id
        )
        for cat, key, schema in items
    ]


@transaction.atomic
def update_policy(
    *,
    actor,
    category: str,
    key: str,
    value: Any,
    branch: Any = None,
    reason: str,
    confirm: str | None = None,
) -> Policy:
    """Set `category.key` to `value`, at `branch` or institution-wide.

    Validates against the schema, requires `reason`, requires `confirm ==
    key` on a critical key (ADR-04), writes the `PolicyVersion` row, forgets
    the cache, and audits `policy.updated` with the from/to value.
    """
    schema = _require_schema(category, key)
    if not reason or not reason.strip():
        raise ApplicationError({"reason": ["A reason is required."]})
    if schema.get("critical") and confirm != key:
        raise ApplicationError({"confirm": [CONFIRM_REQUIRED]})

    normalised = validate_value(category, key, value)
    branch_id = _branch_id(branch)
    scope = PolicyScope.BRANCH if branch_id else PolicyScope.GLOBAL
    actor_ref = actor if getattr(actor, "pk", None) else None
    reason = reason.strip()

    row = Policy.objects.filter(category=category, key=key, branch_id=branch_id).first()
    previous_value = row.value if row is not None else schema["default"]
    if row is not None and row.value == normalised:
        return row  # no-op: nothing changed, nothing to write or audit

    if row is None:
        row = Policy.objects.create(
            category=category,
            key=key,
            scope=scope,
            branch_id=branch_id,
            value=normalised,
            version=1,
            updated_by=actor_ref,
        )
    else:
        row.value = normalised
        row.version += 1
        row.updated_by = actor_ref
        row.save(update_fields=["value", "version", "updated_by", "updated_at"])

    PolicyVersion.objects.create(
        policy=row, version=row.version, value=normalised, changed_by=actor_ref, reason=reason
    )
    _forget()
    record(
        action=AuditAction.POLICY_UPDATED,
        actor=actor,
        resource_type="policy",
        resource_id=row.pk,
        context={
            "category": category,
            "key": key,
            "branch": str(branch_id) if branch_id else None,
            "from": previous_value,
            "to": normalised,
            "reason": reason,
        },
        durable=False,
    )
    return row


@transaction.atomic
def reset_policy(*, actor, category: str, key: str, branch: Any = None) -> None:
    """Return `category.key` to its schema default by soft-deleting the row.

    A no-op — not an error — when nothing was ever configured: resetting
    something already at its default changes nothing to record.
    """
    schema = _require_schema(category, key)
    branch_id = _branch_id(branch)
    row = Policy.objects.filter(category=category, key=key, branch_id=branch_id).first()
    if row is None:
        return
    previous_value = row.value
    soft_delete(
        instance=row, actor=actor, reason=f"Reset to the schema default ({schema['default']!r})."
    )
    _forget()
    record(
        action=AuditAction.POLICY_RESET,
        actor=actor,
        resource_type="policy",
        resource_id=row.pk,
        context={
            "category": category,
            "key": key,
            "branch": str(branch_id) if branch_id else None,
            "from": previous_value,
        },
        durable=False,
    )


def policy_history_queryset(*, category: str, key: str, branch: Any = None):
    """Every `PolicyVersion` ever written for `category.key` at `branch`,
    newest first — across a reset and a reconfigure, because history is
    never lost (D-019 extended to configuration history)."""
    _require_schema(category, key)
    branch_id = _branch_id(branch)
    policy_ids = Policy.all_objects.filter(
        category=category, key=key, branch_id=branch_id
    ).values_list("pk", flat=True)
    return (
        PolicyVersion.objects.filter(policy_id__in=policy_ids)
        .select_related("changed_by")
        .order_by("-version", "-created_at")
    )


__all__ = [
    "get_policy",
    "list_policies",
    "policy_history_queryset",
    "reset_policy",
    "update_policy",
]
