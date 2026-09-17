"""Signal receivers wiring Phase 9/13's extension points into automation
(ERP Phase 14, ADR-13).

Neither ``apps.work`` nor ``apps.performance`` imports this app — these
receivers are connected from ``AutomationConfig.ready()`` only, matching the
"never depend on a phase that has not shipped" discipline both signal
modules document for themselves.

Each receiver only enqueues a Celery task, inside ``transaction.on_commit``,
and never lets a failure to enqueue propagate back into the caller's
request/signal-handling path — this mirrors the "a receiver ... is
responsible for its own transaction.on_commit and its own try/except"
contract ``apps.work.signals.activity_changed``'s own docstring sets for
whoever attaches to it. Dispatch itself (evaluation, idempotency, guards,
actions) always runs inside the Celery worker, never inline here or in the
sender's own request/transaction (ADR-13: "Executed by Celery").
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger("grras.automation")


def on_activity_changed(sender, *, activity, event, actor=None, **kwargs) -> None:
    """Only ``"completed"`` is an ``ACTIVITY_COMPLETED`` occurrence — the
    other four events ``activity_changed`` carries (created, transitioned,
    reviewed, deleted) have no automation trigger of their own."""
    if event != "completed":
        return

    activity_id = str(activity.pk)

    def _enqueue() -> None:
        try:
            from .tasks import dispatch_activity_completed

            dispatch_activity_completed.delay(activity_id)
        except Exception:
            logger.exception(
                "Failed to enqueue ACTIVITY_COMPLETED automation dispatch for activity %s",
                activity_id,
            )

    transaction.on_commit(_enqueue)


def on_risk_changed(
    sender,
    *,
    risk_state,
    enrollment,
    level,
    previous_level,
    triggered,
    previous_triggered,
    **kwargs,
) -> None:
    risk_state_id = str(risk_state.pk)
    enrollment_id = str(enrollment.pk)

    def _enqueue() -> None:
        try:
            from .tasks import dispatch_risk_changed

            dispatch_risk_changed.delay(
                risk_state_id,
                enrollment_id,
                level,
                previous_level or "",
                list(triggered or []),
                list(previous_triggered or []),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue RISK_CHANGED automation dispatch for risk state %s",
                risk_state_id,
            )

    transaction.on_commit(_enqueue)
