"""Seed the activity types a counsellor works an enquiry with.

Meritto's standard lead activities, as activity types whose subject is an
enquiry: a counselling call (answered with the enquiry follow-up form, so
completing the call moves the enquiry's stage) and a demo class. Both are
ordinary types an administrator can edit or disable.
"""

from __future__ import annotations

from django.db import migrations

TYPES = [
    {
        "slug": "enquiry-call",
        "name": "Counselling call",
        "category": "counselling",
        "form_slug": "enquiry-follow-up",
        "creators": ["counsellor", "manager", "automation"],
        "assignees": ["counsellor", "manager"],
        "duration": 15,
        "description": "A call to an enquiry. Its form records the outcome and moves the enquiry's stage.",
    },
    {
        "slug": "demo-class",
        "name": "Demo class",
        "category": "other",
        "form_slug": None,
        "creators": ["counsellor", "manager", "automation"],
        "assignees": ["counsellor", "manager", "trainer"],
        "duration": 60,
        "description": "A trial class booked for an interested enquiry.",
    },
]


def seed_types(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    FormDefinition = apps.get_model("forms", "FormDefinition")
    for spec in TYPES:
        if ActivityType.objects.filter(slug=spec["slug"]).exists():
            continue
        form = (
            FormDefinition.objects.filter(slug=spec["form_slug"]).first()
            if spec["form_slug"]
            else None
        )
        ActivityType.objects.create(
            slug=spec["slug"],
            name=spec["name"],
            description=spec["description"],
            category=spec["category"],
            subject="enquiry",
            form=form,
            allowed_creator_roles=spec["creators"],
            allowed_assignee_roles=spec["assignees"],
            visible_to_student=False,
            default_duration_minutes=spec["duration"],
            requires_review=False,
            performance_weight=0,
            risk_effect="none",
            next_action=None,
            is_system=True,
            status="active",
        )


def unseed_types(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    Activity = apps.get_model("work", "Activity")
    for spec in TYPES:
        for activity_type in ActivityType.objects.filter(slug=spec["slug"], is_system=True):
            if not Activity.objects.filter(activity_type=activity_type).exists():
                activity_type.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("work", "0006_enquiry_activities"),
        ("forms", "0004_seed_enquiry_forms"),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
