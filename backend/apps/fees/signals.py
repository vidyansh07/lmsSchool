"""Extension points for whoever needs to know about money moving.

``payment_recorded`` is sent inside the transaction that recorded the
payment, with ``payment`` and ``actor``. ``instalment_due`` and
``instalment_overdue`` are sent by the morning sweep (`tasks.sweep_instalments`)
with ``installment`` and ``days`` (days until it is due, or days since).
`apps.automation` connects to all three from its own ``ready()``; a receiver
that does anything slow owns its own ``transaction.on_commit``.

None of them is sent while ledgers are being seeded or imported
(`apps.fees.mail.suppressed()`): a rule written for today's payments has no
business running against a payment made months ago in another system.
"""

from __future__ import annotations

from django.dispatch import Signal

payment_recorded = Signal()
instalment_due = Signal()
instalment_overdue = Signal()
