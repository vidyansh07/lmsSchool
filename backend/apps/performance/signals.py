"""`RISK_CHANGED` — the extension point ADR-11 promises Phase 14.

Mirrors `apps.work.signals.activity_changed`'s exact pattern: a bare
`django.dispatch.Signal()`, sent from `apps.performance.services.recompute_risk`
whenever a recompute actually moves the verdict (level or triggered-rule-set
changed from the previous one — never on every recompute, most of which
confirm nothing changed). Nothing in this app connects a receiver to it —
Phase 14's automation engine attaches its own when it exists, the same
"never depend on a phase that has not shipped" discipline `apps.work.signals`
documents for itself.

Signature: ``RISK_CHANGED.send(sender=RiskState, risk_state=risk_state,
enrollment=enrollment, level=level, previous_level=previous_level,
triggered=triggered, previous_triggered=previous_triggered)``.
"""

from __future__ import annotations

import django.dispatch

RISK_CHANGED = django.dispatch.Signal()
