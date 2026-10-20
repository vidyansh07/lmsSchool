"""Seed two example fee rules, as drafts.

Three days before an instalment falls due the student is reminded; a week
after it is missed, the counsellor who registered them gets a follow-up to
call. Left in draft, like the other examples, until an administrator
activates them from the rules screen.
"""

from __future__ import annotations

from django.db import migrations

RULES = [
    {
        "name": "Remind the student 3 days before an instalment",
        "description": (
            "Three days before an unpaid instalment falls due, tell the student how much "
            "is due and by when."
        ),
        "trigger": "FEE_INSTALMENT_DUE",
        "conditions": [{"path": "instalment.days_until", "op": "eq", "value": 3}],
        "actions": [
            {
                "type": "send_notification",
                "params": {
                    "to": "student",
                    "kind": "fee.reminder",
                    "title": "Instalment {{instalment.sequence}} is due on {{instalment.due_on}}",
                    "body": (
                        "Rs. {{instalment.balance}} is due for instalment "
                        "{{instalment.sequence}} of {{instalment.count}}."
                    ),
                },
            }
        ],
    },
    {
        "name": "Follow up an instalment a week overdue",
        "description": (
            "When an instalment is seven days late, give the student's counsellor a "
            "follow-up to call them, due the next day."
        ),
        "trigger": "FEE_INSTALMENT_OVERDUE",
        "conditions": [{"path": "instalment.days_overdue", "op": "eq", "value": 7}],
        "actions": [
            {
                "type": "create_activity",
                "params": {
                    "type": "follow-up",
                    "assign_to": "counsellor",
                    "due_in_days": 1,
                    "title": "Fee overdue: call {{student.name}}",
                    "summary": (
                        "Instalment {{instalment.sequence}} (Rs. {{instalment.balance}}) "
                        "was due on {{instalment.due_on}}."
                    ),
                },
            }
        ],
    },
]


def seed(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    for rule in RULES:
        if AutomationRule.objects.filter(name=rule["name"]).exists():
            continue
        AutomationRule.objects.create(status="draft", version=1, is_system=False, **rule)


def unseed(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    AutomationRun = apps.get_model("automation", "AutomationRun")
    names = [rule["name"] for rule in RULES]
    for rule in AutomationRule.objects.filter(name__in=names, is_system=False):
        if not AutomationRun.objects.filter(rule=rule).exists():
            rule.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0008_fee_triggers"),
        ("work", "0002_seed_catalog"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
