"""Extension points for whoever needs to know about class reports.

``dsr_submitted`` (``dsr``, ``actor``) is sent inside `services.submit_dsr`'s
transaction once the report is handed in; ``dsr_missing`` (``dsr``) by the
after-class sweep when a report goes past its due time. `apps.automation`
connects to both from its own ``ready()`` and owns its own on-commit
dispatch; this app imports nothing from there.
"""

from __future__ import annotations

from django.dispatch import Signal

dsr_submitted = Signal()
dsr_missing = Signal()
