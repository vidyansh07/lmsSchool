"""Seed an example class-report rule, as a draft.

A trainer marking a student "needs attention" in a class report books a
counselling session with that student's counsellor. Left in draft, like the
other examples, until an administrator activates it.
"""

from __future__ import annotations

from django.db import migrations

RULE = {
    "name": "Counselling for a student flagged in class",
    "description": (
        "When a trainer marks a student as needing attention in a class report, "
        "book a counselling session with the student's counsellor within 2 days."
    ),
    "trigger": "DSR_STUDENT_FLAGGED",
    "conditions": [{"path": "note.flag", "op": "eq", "value": "needs_attention"}],
    "actions": [
        {
            "type": "create_activity",
            "params": {
                "type": "counselling",
                "assign_to": "counsellor",
                "due_in_days": 2,
                "title": "Check in with {{student.name}}",
                "summary": "Flagged in {{dsr.batch_code}}'s class report: {{note.text}}",
            },
        }
    ],
}


def seed(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    if AutomationRule.objects.filter(name=RULE["name"]).exists():
        return
    AutomationRule.objects.create(status="draft", version=1, is_system=False, **RULE)


def unseed(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    AutomationRun = apps.get_model("automation", "AutomationRun")
    for rule in AutomationRule.objects.filter(name=RULE["name"], is_system=False):
        if not AutomationRun.objects.filter(rule=rule).exists():
            rule.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0006_class_report_triggers"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
