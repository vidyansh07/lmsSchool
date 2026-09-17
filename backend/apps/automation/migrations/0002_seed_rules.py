# ERP Phase 14 (ADR-13): seed the 9 rules `docs/erp/AUTOMATION_CATALOG.md`'s
# "Seeded rules" table names — `is_system=False`, editable, all `active`,
# per that table's own heading: "none is locked".
#
# Where the catalog's "Actions" column names a `send_notification` call with
# no explicit `kind`, this migration reuses the nearest kind that already
# exists on `NotificationKind` for that event (documented per rule below) —
# every row remains a plain, editable `AutomationRule`, not a fixed
# behaviour, so an administrator can retune any of these from the builder
# without a further migration.
#
# These rows never go through `services.create_rule` — there is no human
# author to run `_require_author_permissions` against (`created_by=None`,
# by design: see `services.sync_rule_authors`'s own docstring on why an
# unauthored rule is never paused for a lapsed permission nobody held in the
# first place) — so `_validate_rule_shape`'s save-time check never runs over
# this data either, and a typo here would otherwise sit undetected forever,
# since nothing revisits an already-saved rule's shape after the fact. What
# follows is a frozen, migration-local echo of that same check (a fixed
# vocabulary, not live app code — a migration must never import
# `apps.automation.services`/`.evaluator`/`.actions`, which can change out
# from under a historical migration; the seed data below is frozen exactly
# the same way the schema it targets already is).
from django.db import migrations

_VALID_TRIGGERS = frozenset(
    {
        "ACTIVITY_COMPLETED",
        "ACTIVITY_OVERDUE",
        "ASSESSMENT_FAILED",
        "ATTENDANCE_THRESHOLD",
        "PROJECT_OVERDUE",
        "ASSIGNMENT_OVERDUE",
        "RISK_CHANGED",
    }
)
_VALID_OPERATORS = frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "contains"})
_VALID_ACTION_TYPES = frozenset(
    {
        "create_activity",
        "send_notification",
        "send_email",
        "send_whatsapp",
        "create_review",
        "flag_risk",
    }
)


def _validate_seed_shape(rules):
    # Explicit raises, not `assert` — this runs unconditionally as part of a
    # migration (never stripped under `-O` the way a bare `assert` would be,
    # and bandit's B101 correctly flags `assert` used outside tests for
    # exactly that reason).
    for spec in rules:
        if spec["trigger"] not in _VALID_TRIGGERS:
            raise ValueError(f"Unknown trigger: {spec['trigger']!r}")
        for condition in spec.get("conditions") or []:
            if "value" not in condition:
                raise ValueError(f"Condition missing 'value': {condition!r}")
            if condition.get("op") not in _VALID_OPERATORS:
                raise ValueError(f"Unknown operator: {condition!r}")
            if not condition.get("path"):
                raise ValueError(f"Condition missing 'path': {condition!r}")
        for action in spec["actions"]:
            if action["type"] not in _VALID_ACTION_TYPES:
                raise ValueError(f"Unknown action type: {action!r}")
            if not isinstance(action.get("params") or {}, dict):
                raise ValueError(f"Bad 'params': {action!r}")


def seed_rules(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")

    rules = [
        {
            "name": "Communication practice after a weak mock",
            "trigger": "ACTIVITY_COMPLETED",
            "conditions": [
                {"path": "activity.type", "op": "eq", "value": "mock-interview"},
                {"path": "form.communication", "op": "lt", "value": 6},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "communication-practice",
                        "assign_to": "same_assignee",
                        "due_in_days": 7,
                    },
                },
                {
                    "type": "send_notification",
                    "params": {
                        "to": "manager",
                        "kind": "activity.assigned",
                        "title": "Follow-up scheduled: {{student.name}}",
                        "body": (
                            "A communication practice session was scheduled for "
                            "{{student.name}} after a weak mock interview score."
                        ),
                    },
                },
            ],
        },
        {
            "name": "Doubt session after a weak technical interview",
            "trigger": "ACTIVITY_COMPLETED",
            "conditions": [
                {"path": "activity.type", "op": "eq", "value": "technical-interview"},
                {"path": "activity.score", "op": "lt", "value": 60},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "doubt-session",
                        "assign_to": "batch_trainer",
                        "due_in_days": 5,
                    },
                },
            ],
        },
        {
            "name": "Resume again if revise",
            "trigger": "ACTIVITY_COMPLETED",
            "conditions": [
                {"path": "activity.type", "op": "eq", "value": "resume-review"},
                {"path": "form.outcome", "op": "eq", "value": "revise"},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "resume-review",
                        "assign_to": "same_assignee",
                        "due_in_days": 7,
                    },
                },
            ],
        },
        {
            "name": "Not ready for placement",
            "trigger": "ACTIVITY_COMPLETED",
            "conditions": [
                {"path": "activity.type", "op": "eq", "value": "placement-call"},
                {"path": "form.outcome", "op": "eq", "value": "not_ready"},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "mock-interview",
                        "assign_to": "batch_trainer",
                        "due_in_days": 7,
                    },
                },
                {
                    "type": "send_notification",
                    # No kind is named in the catalog for this one; the
                    # nearest existing kind is the same one a completed
                    # activity's own review flow already uses.
                    "params": {
                        "to": "manager",
                        "kind": "activity.completed",
                        "title": "Not placement-ready: {{student.name}}",
                        "body": "{{student.name}} was marked not ready on a placement call.",
                    },
                },
            ],
        },
        {
            "name": "Attendance counselling",
            "trigger": "ATTENDANCE_THRESHOLD",
            "conditions": [
                {"path": "attendance.percent", "op": "lt", "value": 75},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "attendance-counselling",
                        "assign_to": "counsellor",
                        "due_in_days": 3,
                    },
                },
                {
                    "type": "send_notification",
                    "params": {
                        "to": "student",
                        "kind": "attendance.warning",
                        "title": "Your attendance needs attention",
                        "body": "Your attendance is at {{attendance.percent}}%.",
                    },
                },
            ],
        },
        {
            "name": "Failed a test twice",
            "trigger": "ASSESSMENT_FAILED",
            "conditions": [
                {"path": "assessment.attempt_number", "op": "gte", "value": 2},
            ],
            "actions": [
                {
                    "type": "create_activity",
                    "params": {
                        "type": "doubt-session",
                        "assign_to": "batch_trainer",
                        "due_in_days": 5,
                    },
                },
                {
                    "type": "send_notification",
                    # No kind is named in the catalog for this one; the
                    # nearest existing kind is a recorded result.
                    "params": {
                        "to": "manager",
                        "kind": "result.published",
                        "title": "Repeated test failure: {{student.name}}",
                        "body": "{{student.name}} has now failed {{assessment.attempt_number}} test(s).",
                    },
                },
            ],
        },
        {
            "name": "Overdue activity nudge",
            "trigger": "ACTIVITY_OVERDUE",
            "conditions": [
                {"path": "activity.days_overdue", "op": "gte", "value": 2},
            ],
            "actions": [
                {
                    "type": "send_notification",
                    "params": {
                        "to": "assignee",
                        "kind": "activity.overdue",
                        "title": "Overdue activity",
                        "body": "An activity assigned to you is {{activity.days_overdue}} day(s) overdue.",
                    },
                },
                {
                    "type": "send_notification",
                    "params": {
                        "to": "manager",
                        "kind": "activity.overdue",
                        "title": "Overdue activity",
                        "body": "An activity for {{student.name}} is {{activity.days_overdue}} day(s) overdue.",
                    },
                },
            ],
        },
        {
            "name": "Risk went critical",
            "trigger": "RISK_CHANGED",
            "conditions": [
                {"path": "risk.level", "op": "eq", "value": "critical"},
                {"path": "risk.previous_level", "op": "ne", "value": "critical"},
            ],
            "actions": [
                {
                    "type": "send_notification",
                    "params": {
                        "to": "manager",
                        "kind": "risk.level_changed",
                        "title": "{{student.name}} is now at critical risk",
                        "body": "Risk level changed from {{risk.previous_level}} to {{risk.level}}.",
                    },
                },
                {
                    "type": "send_notification",
                    "params": {
                        "to": "counsellor",
                        "kind": "risk.level_changed",
                        "title": "{{student.name}} is now at critical risk",
                        "body": "Risk level changed from {{risk.previous_level}} to {{risk.level}}.",
                    },
                },
                {
                    "type": "create_review",
                    "params": {"review_type": "ad_hoc", "reviewer": "manager", "due_in_days": 7},
                },
            ],
        },
        {
            "name": "Project overdue",
            "trigger": "PROJECT_OVERDUE",
            "conditions": [
                {"path": "project.days_overdue", "op": "gte", "value": 3},
            ],
            "actions": [
                {
                    "type": "send_notification",
                    "params": {
                        "to": "student",
                        "kind": "project.overdue",
                        "title": "Your project is overdue",
                        "body": "Your project is {{project.days_overdue}} day(s) overdue.",
                    },
                },
                {
                    "type": "send_notification",
                    "params": {
                        "to": "trainer",
                        "kind": "project.overdue",
                        "title": "Overdue project",
                        "body": "{{student.name}}'s project is {{project.days_overdue}} day(s) overdue.",
                    },
                },
            ],
        },
    ]

    _validate_seed_shape(rules)

    for spec in rules:
        AutomationRule.objects.create(
            name=spec["name"],
            trigger=spec["trigger"],
            conditions=spec["conditions"],
            actions=spec["actions"],
            status="active",
            version=1,
            is_system=False,
        )


def unseed_rules(apps, schema_editor):
    AutomationRule = apps.get_model("automation", "AutomationRule")
    names = [
        "Communication practice after a weak mock",
        "Doubt session after a weak technical interview",
        "Resume again if revise",
        "Not ready for placement",
        "Attendance counselling",
        "Failed a test twice",
        "Overdue activity nudge",
        "Risk went critical",
        "Project overdue",
    ]
    AutomationRule.objects.filter(name__in=names, is_system=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("automation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
