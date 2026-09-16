"""Resolving policy values (ERP Phase 3, ADR-04).

Everything that needs to know a policy asks :func:`policy`. Nothing reads
the `Policy` table directly, so the inheritance order — branch override,
then global, then the schema default — exists in exactly one place, the same
shape `apps.academics.policies.policy_for` uses for academic rules.

Memoised twice, for two different reasons (ADR-14):

* :func:`apps.common.request_context.scoped` — at most one lookup per
  request for a given `(category, key, branch)`, so serialising a page of
  rows does not ask the same question once per row.
* :func:`apps.common.caching.remember` — at most one database read per
  cache TTL across every request, invalidated by :func:`forget_policies`
  the moment a write happens (`services.py` calls it inline and again
  `on_commit`).
"""

from __future__ import annotations

from typing import Any

from apps.common.caching import MINUTE, forget, remember
from apps.common.request_context import clear_scope, scoped

from .schemas import schema_for

PREFIX = "policy"
TTL = 10 * MINUTE


def policy(category: str, key: str, branch: Any = None) -> Any:
    """The value in force for `category.key`, at `branch` or institution-wide.

    `branch` accepts a `Branch` instance, an id, or `None`. Raises
    `KeyError` for a category/key the schema does not declare — a
    programming error, not a request the caller made, so it is not wrapped
    as an `ApplicationError`.
    """
    if schema_for(category, key) is None:
        raise KeyError(f"Unknown policy: {category}.{key}")
    branch_id = getattr(branch, "pk", branch)
    memo_key = f"policy:{category}:{key}:{branch_id or 'global'}"
    return scoped(memo_key, lambda: _cached(category, key, branch_id))


def _cached(category: str, key: str, branch_id: Any) -> Any:
    return remember(
        PREFIX, (category, key, branch_id or "global"), TTL, lambda: _load(category, key, branch_id)
    )


def _load(category: str, key: str, branch_id: Any) -> Any:
    from .models import Policy, PolicyScope

    schema = schema_for(category, key)
    if branch_id is not None:
        row = Policy.objects.filter(category=category, key=key, branch_id=branch_id).first()
        if row is not None:
            return _reconcile(schema, row.value)
    row = Policy.objects.filter(
        category=category, key=key, scope=PolicyScope.GLOBAL, branch__isnull=True
    ).first()
    if row is not None:
        return _reconcile(schema, row.value)
    return schema["default"]


def _reconcile(schema: dict[str, Any], value: Any) -> Any:
    """Fill in a persisted "weights" value's missing keys from the schema's
    current default, rather than trusting a `Policy` row saved by an older
    schema to already carry every key the schema declares today.

    `performance.weights` is a fixed key set validated at write time
    (:func:`apps.policies.schemas.validate_value`), but that validation runs
    only when a value is *written*. A row saved before `PERFORMANCE_COMPONENTS`
    grew a new entry (as it did for `activity` in ERP Phase 12) predates that
    key entirely, and the engine's `weights.get(key, 0)` would otherwise treat
    the missing component as permanently weight-0 forever — silently, with no
    migration or admin-visible warning. Reconciling here, at read time, means
    every caller sees a complete weight set regardless of when its row was
    last saved, the same way the schema default already would for a category
    with no row at all.
    """
    if schema.get("type") != "weights" or not isinstance(value, dict):
        return value
    default = schema["default"]
    if set(value) == set(default):
        return value
    return {**default, **{key: weight for key, weight in value.items() if key in default}}


def forget_policies() -> None:
    """Drop both memos: the cross-request cache, and this request's own —
    the latter is what makes a read right after a write, in the same
    request, see the new value rather than the one this request already
    asked for (the same reason `apps.academics.policies` clears its scope
    on every write)."""
    forget(PREFIX)
    clear_scope()


__all__ = ["forget_policies", "policy"]
