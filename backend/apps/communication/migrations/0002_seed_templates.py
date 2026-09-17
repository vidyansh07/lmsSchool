# ERP Phase 19 (ADR-12): a starter set of published, email-channel templates
# for the `NotificationKind`s this codebase already sends today through the
# plain `apps.notifications.services.notify()` path — the same kinds
# Phase 14's seeded automation rules (`apps.automation.migrations
# .0002_seed_rules`) already name in their `send_notification` actions.
#
# None of those nine seeded rules actually uses a `send_email`/
# `send_whatsapp` action (they all use `send_notification`, which needs no
# template), so this migration is forward-looking rather than fixing a rule
# that would otherwise be broken today: an administrator who edits one of
# those rules — or writes a new one — to send a real email instead of (or
# alongside) the in-app notification for one of these events now has a real,
# published template to point `send_email`'s `template` param at immediately,
# rather than every such rule always falling back to `skipped` until someone
# first visits the template builder.
#
# Frozen exactly the same way `0002_seed_rules.py` freezes its own seed data
# (a migration must never import live app code that can change out from
# under a historical migration) — this never imports
# `apps.communication.services`/`.rendering`.
from django.db import migrations
from django.utils import timezone

_TEMPLATES = [
    {
        "key": "email.activity_assigned",
        "name": "Activity assigned",
        "kind": "activity.assigned",
        "subject": "A new activity has been assigned to you",
        "body_text": (
            "Hello {{recipient.name}},\n\n"
            "A new activity has been assigned to you. Please check your "
            "dashboard for the details.\n"
        ),
    },
    {
        "key": "email.activity_completed",
        "name": "Activity completed",
        "kind": "activity.completed",
        "subject": "An activity was completed",
        "body_text": (
            "Hello {{recipient.name}},\n\nAn activity you are following has "
            "just been completed.\n"
        ),
    },
    {
        "key": "email.attendance_warning",
        "name": "Attendance warning",
        "kind": "attendance.warning",
        "subject": "Your attendance needs attention",
        "body_text": (
            "Hello {{recipient.name}},\n\nYour attendance has fallen below "
            "the expected level. Please speak with your trainer or "
            "counsellor if you have questions.\n"
        ),
    },
    {
        "key": "email.result_published",
        "name": "Result published",
        "kind": "result.published",
        "subject": "A result has been published",
        "body_text": (
            "Hello {{recipient.name}},\n\nA new assessment result is "
            "available on your dashboard.\n"
        ),
    },
    {
        "key": "email.activity_overdue",
        "name": "Activity overdue",
        "kind": "activity.overdue",
        "subject": "An activity is overdue",
        "body_text": (
            "Hello {{recipient.name}},\n\nAn activity assigned to you is "
            "now overdue. Please complete it as soon as you can.\n"
        ),
    },
    {
        "key": "email.risk_level_changed",
        "name": "Student risk level changed",
        "kind": "risk.level_changed",
        "subject": "A student's risk level has changed",
        "body_text": (
            "Hello {{recipient.name}},\n\nA student's risk level has "
            "changed. Please review their record.\n"
        ),
    },
    {
        "key": "email.project_overdue",
        "name": "Project overdue",
        "kind": "project.overdue",
        "subject": "A project is overdue",
        "body_text": (
            "Hello {{recipient.name}},\n\nA project is now overdue. Please "
            "check the schedule and follow up.\n"
        ),
    },
]

_VARIABLES = ["recipient.name"]


def seed_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("communication", "MessageTemplate")
    TemplateVersion = apps.get_model("communication", "TemplateVersion")

    now = timezone.now()
    for spec in _TEMPLATES:
        if MessageTemplate.objects.filter(key=spec["key"]).exists():
            continue
        template = MessageTemplate.objects.create(
            key=spec["key"],
            name=spec["name"],
            channel="email",
            kind=spec["kind"],
            language="en",
            status="published",
        )
        version = TemplateVersion.objects.create(
            template=template,
            number=1,
            subject=spec["subject"],
            body_text=spec["body_text"],
            body_html="<p>" + spec["body_text"].replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>",
            variables=_VARIABLES,
            approved_at=now,
            published_at=now,
        )
        template.current_version = version
        template.save(update_fields=["current_version"])


def unseed_templates(apps, schema_editor):
    MessageTemplate = apps.get_model("communication", "MessageTemplate")
    MessageTemplate.objects.filter(key__in=[spec["key"] for spec in _TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [("communication", "0001_initial")]

    operations = [migrations.RunPython(seed_templates, unseed_templates)]
