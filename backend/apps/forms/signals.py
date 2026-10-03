"""Extension point for whoever needs to know a form was answered.

``form_submitted`` is sent by ``services.submit_assignment`` inside its
transaction, after the response is stored, with ``assignment`` (a
`FormAssignment`, now `submitted`) and ``actor``. A receiver that does
anything slow or external owns its own ``transaction.on_commit`` and its own
``try/except`` — the same contract ``apps.work.signals.activity_changed``
sets. ``apps.automation`` connects to it from its ``ready()``; this app
imports nothing from there.
"""

from __future__ import annotations

from django.dispatch import Signal

form_submitted = Signal()
