"""Extension point for whoever needs to know an enquiry changed.

``enquiry_changed`` is sent inside the transaction that changed it, with
``enquiry``, ``event`` (``"created"`` / ``"updated"``), ``changed`` (the
field names that changed), ``previous_stage`` (the stage before, when the
stage changed) and ``actor``. `apps.automation` connects to it from its own
``ready()``; a receiver that does anything slow owns its own
``transaction.on_commit``.

Automation's own `update_enquiry` action does not send this signal — it
dispatches the follow-on event itself, one depth deeper, so a rule that
changes an enquiry cannot re-trigger itself forever.
"""

from __future__ import annotations

from django.dispatch import Signal

enquiry_changed = Signal()
