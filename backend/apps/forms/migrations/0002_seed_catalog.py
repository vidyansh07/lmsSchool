"""Seed the catalog forms (`docs/erp/FORM_CATALOG.md`), each straight to
PUBLISHED version 1, so later phases can render them immediately.

A `RunPython` data migration, not a management command, so the seed
replays identically in CI and on staging and is idempotent — running it
twice (a re-applied migration, a fresh database rebuilt from a dump that
already has the rows) must not duplicate or error.

Uses historical models throughout (``apps.get_model``), never the real
`apps.forms.models` classes, so this migration keeps working even after a
future migration changes the schema those classes describe.
"""

from __future__ import annotations

import hashlib
import json

from django.db import migrations
from django.utils import timezone

# ---------------------------------------------------------------------------
# Field catalog, transcribed verbatim from FORM_CATALOG.md.
# ---------------------------------------------------------------------------

SCORE_RANGE = {"min": 0, "max": 10}


def _field(
    key,
    label,
    type_,
    *,
    required=False,
    validation=None,
    options=None,
    student=False,
    performance_key="",
    group="",
    help_="",
):
    return {
        "key": key,
        "label": label,
        "help": help_,
        "type": type_,
        "required": required,
        "group": group,
        "options": options or [],
        "validation": validation or {},
        "visible_to_student": student,
        "performance_key": performance_key,
    }


def _score(label="Overall (0-10)", key="score", student=True):
    return _field(key, label, "decimal", required=True, validation=SCORE_RANGE, student=student, performance_key="score")


def _select(key, label, choices, *, required=True, student=False):
    return _field(
        key,
        label,
        "select",
        required=required,
        options=[{"value": value, "label": text} for value, text in choices],
        student=student,
    )


FORMS = [
    {
        "slug": "mock-interview",
        "name": "Mock interview",
        "entity": "activity",
        "fields": [
            _field("technical", "Technical (0-10)", "decimal", required=True, validation=SCORE_RANGE, student=True),
            _field(
                "communication",
                "Communication (0-10)",
                "decimal",
                required=True,
                validation=SCORE_RANGE,
                student=True,
                help_="Feeds the next-action condition form.communication.",
            ),
            _field("confidence", "Confidence (0-10)", "decimal", required=True, validation=SCORE_RANGE, student=True),
            _score(),
            _select(
                "outcome",
                "Outcome",
                [("ready", "Ready"), ("needs_practice", "Needs practice"), ("not_ready", "Not ready")],
                student=True,
            ),
            _field("strengths", "Strengths", "textarea", validation={"max_length": 2000}, student=True),
            _field(
                "improvements", "Improve", "textarea", required=True, validation={"max_length": 2000}, student=True
            ),
            _field("notes", "Private notes", "textarea", validation={"max_length": 4000}),
        ],
    },
    {
        "slug": "technical-interview",
        "name": "Technical interview",
        "entity": "activity",
        "fields": [
            _field("technical", "Technical (0-10)", "decimal", required=True, validation=SCORE_RANGE, student=True),
            _field(
                "problem_solving",
                "Problem solving (0-10)",
                "decimal",
                required=True,
                validation=SCORE_RANGE,
                student=True,
            ),
            _score(),
            _select("outcome", "Outcome", [("ready", "Ready"), ("needs_practice", "Needs practice"), ("not_ready", "Not ready")], student=True),
            _field(
                "topics_covered",
                "Topics covered",
                "multiselect",
                options={"model": "module"},
                student=True,
                help_="Relation to the course's modules.",
            ),
            _field("improvements", "Improve", "textarea", student=True),
            _field("notes", "Private notes", "textarea"),
        ],
    },
    {
        "slug": "hr-interview",
        "name": "HR interview",
        "entity": "activity",
        "fields": [
            _field("communication", "Communication (0-10)", "decimal", required=True, validation=SCORE_RANGE, student=True),
            _field("attitude", "Attitude (0-10)", "decimal", required=True, validation=SCORE_RANGE, student=True),
            _score(),
            _select("outcome", "Outcome", [("ready", "Ready"), ("needs_practice", "Needs practice"), ("not_ready", "Not ready")], student=True),
            _field("notes", "Private notes", "textarea"),
        ],
    },
    {
        "slug": "mentoring-note",
        "name": "Mentoring note",
        "entity": "activity",
        "fields": [
            _field("topic", "Topic", "text", required=True, validation={"max_length": 160}, student=True),
            _field("summary", "Summary", "textarea", required=True, validation={"max_length": 4000}, student=True),
            _field("action_items", "Action items", "textarea", student=True),
            _field("follow_up_on", "Follow up on", "date", validation={"not_past": True}),
        ],
    },
    {
        "slug": "counselling-note",
        "name": "Counselling note",
        "entity": "activity",
        "fields": [
            _select(
                "reason",
                "Reason",
                [
                    ("attendance", "Attendance"),
                    ("fees", "Fees"),
                    ("academic", "Academic"),
                    ("personal", "Personal"),
                    ("placement", "Placement"),
                    ("other", "Other"),
                ],
            ),
            _field("summary", "Summary", "textarea", required=True, validation={"max_length": 4000}),
            _field("commitments", "Commitments", "textarea"),
            _field("next_follow_up", "Next follow-up", "date", validation={"not_past": True}),
            _field("guardian_informed", "Guardian informed", "boolean"),
        ],
    },
    {
        "slug": "doubt-session",
        "name": "Doubt session",
        "entity": "activity",
        "fields": [
            _field("topic", "Topic", "text", required=True, student=True),
            _field(
                "lesson",
                "Lesson",
                "relation",
                options={"model": "lesson"},
                student=True,
                help_="Within the batch's course.",
            ),
            _field("resolved", "Resolved", "boolean", required=True, student=True),
            _field("notes", "Notes", "textarea", student=True),
        ],
    },
    {
        "slug": "code-review",
        "name": "Code review",
        "entity": "activity",
        "fields": [
            _field("repository_url", "Repository URL", "url", validation={"https_only": True}, student=True),
            _score(),
            _field("readability", "Readability (0-10)", "decimal", validation=SCORE_RANGE, student=True),
            _field("correctness", "Correctness (0-10)", "decimal", validation=SCORE_RANGE, student=True),
            _field("structure", "Structure (0-10)", "decimal", validation=SCORE_RANGE, student=True),
            _field(
                "comments", "Comments", "richtext", required=True, validation={"max_length": 8000}, student=True
            ),
        ],
    },
    {
        "slug": "resume-review",
        "name": "Resume review",
        "entity": "activity",
        "fields": [
            _field(
                "resume",
                "Resume",
                "file",
                required=True,
                validation={"accept": [".pdf", ".docx"], "max_mb": 5},
                student=True,
            ),
            _score(),
            _select("outcome", "Outcome", [("ready", "Ready"), ("revise", "Revise")], student=True),
            _field("suggestions", "Suggestions", "textarea", required=True, student=True),
        ],
    },
    {
        "slug": "project-review",
        "name": "Project review",
        "entity": "activity",
        "fields": [
            _field(
                "project",
                "Project",
                "relation",
                required=True,
                options={"model": "studentproject"},
                student=True,
                help_="The student's own project.",
            ),
            _score(),
            _select(
                "outcome",
                "Outcome",
                [("approved", "Approved"), ("revise", "Revise"), ("rejected", "Rejected")],
                student=True,
            ),
            _field("feedback", "Feedback", "richtext", required=True, student=True),
        ],
    },
    {
        "slug": "placement-call",
        "name": "Placement call",
        "entity": "activity",
        "fields": [
            _field("company", "Company", "text"),
            _select("outcome", "Outcome", [("ready", "Ready"), ("not_ready", "Not ready"), ("placed", "Placed"), ("declined", "Declined")]),
            _field("package", "Package", "decimal", validation={"min": 0}),
            _field("notes", "Notes", "textarea"),
        ],
    },
    {
        "slug": "feedback-note",
        "name": "Feedback note",
        "entity": "activity",
        "fields": [
            _field("body", "Body", "textarea", required=True, validation={"max_length": 5000}, student=True),
            _field("visible_to_student", "Visible to student", "boolean", required=True),
        ],
    },
    {
        "slug": "parent-meeting",
        "name": "Parent meeting",
        "entity": "activity",
        "fields": [
            _field("attendee", "Attendee", "text", required=True),
            _select("mode", "Mode", [("in_person", "In person"), ("phone", "Phone"), ("video", "Video")]),
            _field("summary", "Summary", "textarea", required=True),
            _field("commitments", "Commitments", "textarea"),
        ],
    },
    {
        "slug": "warning-note",
        "name": "Warning note",
        "entity": "activity",
        "fields": [
            _select(
                "reason",
                "Reason",
                [
                    ("attendance", "Attendance"),
                    ("conduct", "Conduct"),
                    ("academic", "Academic"),
                    ("fees", "Fees"),
                ],
                student=True,
            ),
            _field("details", "Details", "textarea", required=True, student=True),
            _field("acknowledged_by_student", "Acknowledged by student", "boolean", student=True),
        ],
    },
    {
        "slug": "follow-up-note",
        "name": "Follow-up note",
        "entity": "activity",
        "fields": [
            _select("channel", "Channel", [("phone", "Phone"), ("whatsapp", "WhatsApp"), ("email", "Email"), ("in_person", "In person")]),
            _select("outcome", "Outcome", [("reached", "Reached"), ("no_answer", "No answer"), ("callback", "Callback"), ("closed", "Closed")]),
            _field("summary", "Summary", "textarea"),
            _field("next_follow_up", "Next follow-up", "datetime", validation={"not_past": True}),
        ],
    },
    {
        "slug": "communication-practice",
        "name": "Communication practice",
        "entity": "activity",
        "fields": [
            _field("topic", "Topic", "text", required=True, student=True),
            _score(),
            _field("notes", "Notes", "textarea", student=True),
        ],
    },
    {
        "slug": "student-custom",
        "name": "Student custom fields",
        "entity": "student",
        "fields": [],
    },
    {
        "slug": "registration-extra",
        "name": "Registration extra fields",
        "entity": "registration",
        "fields": [],
    },
]


def _schema_hash(fields: list[dict]) -> str:
    ordered = [
        (f["key"], f["type"], f["required"], f["options"], f["validation"])
        for f in sorted(fields, key=lambda f: (0, f["key"]))
    ]
    payload = json.dumps(ordered, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seed_forms(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormVersion = apps.get_model("forms", "FormVersion")
    FormField = apps.get_model("forms", "FormField")

    for spec in FORMS:
        definition, _created = FormDefinition.objects.get_or_create(
            slug=spec["slug"],
            defaults={"name": spec["name"], "entity": spec["entity"]},
        )
        version = FormVersion.objects.filter(definition=definition, number=1).first()
        if version is not None:
            # Already seeded (idempotent replay): leave it exactly as it was.
            continue

        version = FormVersion.objects.create(
            definition=definition,
            number=1,
            status="published",
            schema_hash=_schema_hash(spec["fields"]),
            published_at=timezone.now(),
        )

        FormField.objects.bulk_create(
            [
                FormField(
                    version=version,
                    key=field["key"],
                    label=field["label"],
                    help=field["help"],
                    type=field["type"],
                    required=field["required"],
                    order=index,
                    group=field["group"],
                    options=field["options"],
                    validation=field["validation"],
                    visible_to_student=field["visible_to_student"],
                    performance_key=field["performance_key"],
                )
                for index, field in enumerate(spec["fields"])
            ]
        )


def unseed_forms(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormDefinition.objects.filter(slug__in=[spec["slug"] for spec in FORMS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("forms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_forms, unseed_forms),
    ]
