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
    return queue


def reset() -> None:
    _request_id.set("-")
    _request_meta.set(None)
    _deferred_audits.set(None)
