"""Seed the message matrix with what the institute already does.

Defaults are *rows*, not an implication in code. A missing row means off, so
without this the product would be silent on the day it is deployed and
somebody would have to tick thirty boxes to get back to where they were.

The seeded set is deliberately narrow and matches the desk's current
practice: the **student** hears about their own money, by SMS and in-app;
cheque clearance and a bounce reach them by email too, because those are the
two a receipt has to follow. Guardians and owners are seeded **off** — texting
somebody's parent is a decision the institute takes on purpose, not a default
it inherits from a migration.

Idempotent: a cell that already exists is left exactly as it is, including a
cell an administrator has deliberately turned off.
"""

from __future__ import annotations

from django.db import migrations

#: (event, recipient, channel) — only the cells that start on.
ENABLED = (
    ("payment.made", "student", "sms"),
    ("payment.made", "student", "push"),
    ("payment.cheque_cleared", "student", "sms"),
    ("payment.cheque_cleared", "student", "email"),
    ("payment.cheque_cleared", "student", "push"),
    ("payment.cheque_bounced", "student", "sms"),
    ("payment.cheque_bounced", "student", "email"),
    ("payment.cheque_bounced", "student", "push"),
    ("payment.refund", "student", "sms"),
    ("payment.refund", "student", "email"),
    ("payment.reminder", "student", "sms"),
    ("admission.added", "student", "push"),
)


def seed(apps, schema_editor):
    MessageRule = apps.get_model("notifications", "MessageRule")
    for event, recipient, channel in ENABLED:
        MessageRule.objects.get_or_create(
            event=event,
            recipient=recipient,
            channel=channel,
            defaults={"is_enabled": True},
        )


def unseed(apps, schema_editor):
    MessageRule = apps.get_model("notifications", "MessageRule")
    for event, recipient, channel in ENABLED:
        MessageRule.objects.filter(
            event=event, recipient=recipient, channel=channel, is_enabled=True
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("notifications", "0014_messagerule")]

    operations = [migrations.RunPython(seed, unseed)]
