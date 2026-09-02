"""Audit recording API.

One function, ``record``, is the entire public surface. Callers never build
``AuditLog`` instances directly, so redaction, actor resolution and request
metadata capture cannot be forgotten by a future module.

Failures to write an audit row are logged but never propagate: audit is a
safety net, and a broken net must not take the request down with it. The write
failure itself is logged at ERROR so monitoring catches it.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError

from apps.common.logging import scrub
from apps.common.request_context import defer_audit, get_request_id, get_request_meta

from .models import AuditAction, AuditLog, AuditResult

logger = logging.getLogger("grras.audit")

_USER_AGENT_MAX = 512
_LABEL_MAX = 254


def record(
    *,
    action: str,
    actor: Any = None,
    resource_type: str = "",
    resource_id: Any = "",
    result: str = AuditResult.SUCCESS,
    context: dict[str, Any] | None = None,
    actor_label: str = "",
    durable: bool | None = None,
) -> AuditLog | None:
    """Append one audit entry.

    Request metadata (ip, user agent, request id, method, path) is taken from
    the ambient request context, so service-layer callers do not have to pass a
    request object down through their signatures.

    ``durable`` controls *when* the row is written:

    * ``False`` — write inline, inside whatever transaction the caller is in.
      Correct for a successful action: the record and the change it describes
      commit together or not at all.
    * ``True`` — queue the write for after the request transaction ends.
      Necessary for failures, because ``ATOMIC_REQUESTS`` plus DRF's rollback on
      handled exceptions would otherwise discard the entry along with the failed
      operation it was recording.

    The default resolves to ``True`` for any non-success result, which is the
    rule you almost always want.
    """
    if durable is None:
        durable = result != AuditResult.SUCCESS
    meta = get_request_meta()
    actor_obj = (
        actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", False) else None
    )
    label = actor_label or (getattr(actor, "email", "") if actor is not None else "")

    payload = {
        "actor": actor_obj,
        "actor_label": str(label)[:_LABEL_MAX],
        "action": action,
        "resource_type": resource_type[:64],
        "resource_id": str(resource_id or "")[:64],
        "result": result,
        "ip_address": meta.get("ip_address"),
        "user_agent": str(meta.get("user_agent", ""))[:_USER_AGENT_MAX],
        "request_id": get_request_id()[:64],
        "request_method": str(meta.get("method", ""))[:10],
        "request_path": str(meta.get("path", ""))[:255],
        # Redaction happens here, at the single write point, so no caller can
        # accidentally persist a password or token.
        "context": scrub(context or {}),
    }

    logger.info(
        "audit.%s", action, extra={"context": {"result": result, "actor": payload["actor_label"]}}
    )

    if durable:
        # The model instance cannot be built yet — it is written later, outside
        # the current transaction — so the resolved field values are queued.
        deferred = dict(payload)
        deferred["actor_id"] = getattr(actor_obj, "pk", None)
        deferred.pop("actor", None)
        defer_audit(deferred)
        return None

    return _write(payload)


def _write(payload: dict[str, Any]) -> AuditLog | None:
    try:
        return AuditLog.objects.create(**payload)
    except DatabaseError:
        logger.exception(
            "Failed to persist audit entry", extra={"context": {"action": payload.get("action")}}
        )
        return None


def flush_deferred(entries: list[dict[str, Any]]) -> int:
    """Write queued audit entries. Called by middleware after the response.

    Runs in its own transaction, so entries recorded during a failed request are
    preserved even though that request's work was rolled back.
    """
    written = 0
    for entry in entries:
        payload = dict(entry)
        actor_id = payload.pop("actor_id", None)
        payload["actor_id"] = actor_id
        if _write(payload) is not None:
            written += 1
    return written


__all__ = ["AuditAction", "AuditResult", "record"]
