"""The one extension point this phase promises later phases.

``activity_changed`` is sent from :mod:`apps.work.services` after every
service-layer event that changes an ``Activity`` — create, transition,
complete, review, delete — carrying the activity instance and the event
name. Phase 13 (risk) needs only the ``"completed"`` event; Phase 14
(automation) needs all of them, including ``"deleted"``, to log an
``AutomationRun`` for a rule keyed on any of these triggers. One signal
rather than one per verb keeps this module's surface small and gives both
future receivers the same shape to filter on, instead of five imports and
five ``connect()`` calls for what is, from the caller's side, one fact:
"this activity just changed, here's how".

Signature: ``activity_changed.send(sender=Activity, activity=activity,
event=event, actor=actor)`` where ``event`` is one of ``"created"``,
``"transitioned"``, ``"completed"``, ``"reviewed"``, ``"deleted"``.

Nothing in this app connects a receiver to this signal — that is
deliberately left to the phase that needs the effect (risk recompute,
automation dispatch), so this app never imports code from apps that do not
exist yet. Sending happens unconditionally and synchronously, inside the
same transaction as the write it describes; a receiver that must not roll
back the caller's transaction on failure is responsible for its own
``transaction.on_commit`` and its own try/except, the same discipline
``apps.notifications.services.notify`` uses for its own callers.
"""

from __future__ import annotations

import django.dispatch

activity_changed = django.dispatch.Signal()
