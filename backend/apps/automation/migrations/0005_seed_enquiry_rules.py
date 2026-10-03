"""Seed example rules for the enquiry pipeline, as drafts.

They show one flow end to end, Meritto style — an enquiry event, conditions
on the enquiry, and an activity created with its content filled in — but are
left in draft, so nothing starts happening on an upgrade until an
administrator reads them and activates them in the builder.
"""

from __future__ import annotations

from django.db import migrations

RULES = [
    {
        "name": "Call a new enquiry within 2 hours",
        "description": (
            "When an enquiry is created, give it to the counsellor with the least open "
            "work if nobody owns it yet, and create a counselling call due in 2 hours."
        ),
        "trigger": "ENQUIRY_CREATED",
        "conditions": [],
        "actions": [
            {
                "type": "update_enquiry",
                "params": {"owner": "least_busy_counsellor", "only_if_unowned": True},
            },
            {
                "type": "create_activity",
                "params": {
                    "type": "enquiry-call",
                    "assign_to": "enquiry_owner",
                    "due_in_hours": 2,
                    "priority": "high",
                    "title": "Call {{enquiry.full_name}}",
                    "summary": (
                        "New enquiry for {{enquiry.course}} from {{enquiry.source}}. "
                        "Mobile {{enquiry.mobile}}, {{enquiry.city}}."
                    ),
                    "form_prefill": {"call_status": "connected"},
                },
            },
        ],
    },
    {
        "name": "Book a demo class for an interested enquiry",
        "description": "When an enquiry becomes interested, plan a demo class for the next day.",
        "trigger": "ENQUIRY_STAGE_CHANGED",
        "conditions": [{"path": "enquiry.stage", "op": "eq", "value": "interested"}],
        "actions": [
            {
                "type": "create_activity",
                "params": {
                    "type": "demo-class",
                    "assign_to": "enquiry_owner",
                    "planned_in_hours": 24,
                    "due_in_days": 3,
                    "title": "Demo class: {{enquiry.full_name}} ({{enquiry.course}})",
                    "summary": "Interested in {{enquiry.course}} {{enquiry.track}}.",
                },
            }
        ],
    },
    {
        "name": "Follow up an unanswered call next day",
        "description": "When a counselling call is completed but the enquiry was not reached, call again tomorrow.",
        "trigger": "ACTIVITY_COMPLETED",
        "conditions": [
            {"path": "activity.type", "op": "eq", "value": "enquiry-call"},
            {
                "path": "form.call_status",
                "op": "in",
                "value": ["not_answered", "busy", "switched_off"],
            },
        ],
        "actions": [
            {
                "type": "create_activity",
                "params": {
                    "type": "enquiry-call",
                    "assign_to": "same_assignee",
                    "due_in_days": 1,
                    "title": "Call again: {{enquiry.full_name}}",
                    "summary": "Last call: {{form.call_status}}.",
                },
            }
        ],
    },
    {
        "name": "Tell the manager about a lost enquiry",
        "description": "When an enquiry is marked not interested, notify the centre manager.",
        "trigger": "ENQUIRY_STAGE_CHANGED",
        "conditions": [{"path": "enquiry.stage", "op": "eq", "value": "not_interested"}],
        "actions": [
            {
                "type": "send_notification",
                "params": {
                    "to": "manager",
                    "kind": "form.submitted",
                    "title": "Enquiry lost: {{enquiry.full_name}}",
                    "body": "Reason: {{enquiry.lost_reason}}. Course: {{enquiry.course}}.",
                },
            }
        ],
    },
]


def seed_rules(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    for spec in RULES:
        if AutomationRule.objects.filter(name=spec["name"]).exists():
            continue
        AutomationRule.objects.create(
            name=spec["name"],
            description=spec["description"],
            trigger=spec["trigger"],
            conditions=spec["conditions"],
            actions=spec["actions"],
            status="draft",
            version=1,
            is_system=False,
        )


def unseed_rules(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    AutomationRun = apps.get_model("automation", "AutomationRun")
    for spec in RULES:
        for rule in AutomationRule.objects.filter(name=spec["name"], is_system=False):
            if not AutomationRun.objects.filter(rule=rule).exists():
                rule.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("automation", "0004_form_and_enquiry_triggers"),
        ("work", "0007_seed_enquiry_activity_types"),
        ("forms", "0005_formassignment_enquiry"),
    ]

    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
