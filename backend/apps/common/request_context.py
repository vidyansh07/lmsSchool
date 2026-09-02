"""Per-request context propagated without threading it through call signatures.

Used by logging (to stamp every line with a request id) and by the audit log
(to record request metadata from deep inside service code). Implemented with
``contextvars`` so it is correct under threads and async alike.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
# A mutable default would be shared across every context, so the default is
# None and readers substitute a fresh empty mapping.
_request_meta: ContextVar[dict[str, Any] | None] = ContextVar("request_meta", default=None)

#: Audit entries that must outlive a rolled-back request. See `defer_audit`.
_deferred_audits: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "deferred_audits", default=None
)

#: Whether this request has already recorded an authorization refusal.
_denial_recorded: ContextVar[bool] = ContextVar("denial_recorded", default=False)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


def set_request_meta(meta: dict[str, Any]) -> None:
    _request_meta.set(meta)


def get_request_meta() -> dict[str, Any]:
    return _request_meta.get() or {}


def mark_denial_recorded() -> None:
    """Note that this request already has an authorization refusal on record."""
    _denial_recorded.set(True)


def denial_already_recorded() -> bool:
    return _denial_recorded.get()


def defer_audit(payload: dict[str, Any]) -> None:
    """Queue an audit entry to be written after the request transaction ends.

    ``ATOMIC_REQUESTS`` wraps each request in a transaction, and DRF marks that
    transaction for rollback whenever it converts an exception into an error
    response. A failure audit written inline would therefore be discarded by the
    very failure it records. Queueing it here lets middleware — which runs
    outside the request transaction — write it in its own transaction.
    """
    queue = _deferred_audits.get()
    if queue is None:
        queue = []
        _deferred_audits.set(queue)
    queue.append(payload)


def take_deferred_audits() -> list[dict[str, Any]]:
    """Return and clear the queued audit entries."""
    queue = _deferred_audits.get() or []
    _deferred_audits.set(None)
    _denial_recorded.set(False)
    return queue


#: A scratch space that lives exactly as long as one request.
#:
#: Used for values that are expensive to resolve, identical for every row in a
#: response, and must not be stale across requests — the academic policy is the
#: motivating case: without it, serialising a page of twenty submissions asks
#: the database for the same rules twenty times, and with a shared cache a rule
#: change would not take effect until it expired.
_request_scope: ContextVar[dict[str, Any] | None] = ContextVar("request_scope", default=None)


def scoped(key: str, produce):
    """Return ``produce()``, computed at most once per request for this key."""
    store = _request_scope.get()
    if store is None:
        store = {}
        _request_scope.set(store)
    if key not in store:
        store[key] = produce()
    return store[key]


def clear_scope(key: str | None = None) -> None:
    """Drop one memoised value, or all of them.

    Called after a write that would make a memoised value wrong within the same
    request.
    """
    store = _request_scope.get()
    if store is None:
        return
    if key is None:
        store.clear()
    else:
        store.pop(key, None)


def reset() -> None:
    _request_id.set("-")
    _request_meta.set(None)
    _deferred_audits.set(None)
    _denial_recorded.set(False)
    _request_scope.set(None)
