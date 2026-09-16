"""Seed the 18 activity types (`docs/erp/ACTIVITY_CATALOG.md`), `is_system=True`.

A `RunPython` data migration, not a management command, so the seed replays
identically in CI and on staging and is idempotent — running it twice (a
re-applied migration, a fresh database rebuilt from a dump that already has
the rows) must not duplicate or error. Uses historical models throughout
(`apps.get_model`), and resolves each row's `form` by *slug* against
`apps.forms`'s own seed (`apps/forms/migrations/0002_seed_catalog.py`) rather
than importing `apps.forms.models` or hardcoding a `FormDefinition` id — the
standard cross-app migration data pattern this codebase already uses (see
that same file for `FormField`'s `performance_key`/`validation` shapes,
which this migration does not touch).

Three columns needed a documented simplification because the catalog's prose
does not fit the model's deliberately narrow shape:

* `risk_effect` is a two-value enum (`none`/`score_below_threshold`,
  `RiskEffect` in `models.py`). Three rows describe a richer rule in prose —
  `resume-review` and `placement-call` ("placement rule"), `warning` ("yes
  (count)") — that is not "a low score", so those three are seeded `none`
  here; the richer rule stays written down in `ACTIVITY_CATALOG.md` for
  Phase 13 to read when it extends this enum.
* `next_action` follows `DATA_MODEL.md` §5's shape verbatim: `{when,
  threshold, create_type, assign_to, notify}`, one condition. Two rows
  describe something that shape cannot hold: `resume-review`'s "again in 7
  days" (a delay, not just a condition) and `communication-practice`'s two
  branches ("score >= 7 -> none" *and* "score < 5 after 2 sessions -> notify
  manager", the second counting *sessions*, not just today's score). Both
  are seeded with their single most important condition; Phase 14, which
  actually dispatches this field, is where the shape itself should grow to
  fit the rest.
* `allowed_creator_roles` includes the literal string `"automation"` for the
  two rows an automation rule creates (`communication-practice`,
  `attendance-counselling`) and `"student"` for `doubt-session`'s "student
  (request)" — transcribed from the catalog as-is. Neither role passes
  `services.create_activity`'s capability check yet (`activity.create` has
  no `student` tier, and there is no system actor with a `"automation"`
  role); both stay inert until the phase that needs them (14) adds the
  matching authority.
"""

from __future__ import annotations

from django.db import migrations

STAFF = ["superadmin", "admin", "manager", "counsellor", "trainer"]

TYPES = [
    dict(
        slug="mock-interview",
        name="Mock Interview",
        category="interview",
        form_slug="mock-interview",
        creators=["manager", "trainer"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="1.00",
        risk_effect="score_below_threshold",
        next_action={
            "when": "score_below",
            "threshold": 6,
            "create_type": "communication-practice",
            "assign_to": "same_assignee",
            "notify": ["manager"],
        },
    ),
    dict(
        slug="technical-interview",
        name="Technical Interview",
        category="interview",
        form_slug="technical-interview",
        creators=["manager", "trainer"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=45,
        requires_review=False,
        performance_weight="1.00",
        risk_effect="score_below_threshold",
        next_action={
            "when": "score_below",
            "threshold": 6,
            "create_type": "doubt-session",
            "assign_to": "batch_trainer",
            "notify": [],
        },
    ),
    dict(
        slug="hr-interview",
        name="HR Interview",
        category="interview",
        form_slug="hr-interview",
        creators=["manager"],
        assignees=["trainer", "manager"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="0.50",
        risk_effect="score_below_threshold",
        next_action=None,
    ),
    dict(
        slug="mentoring",
        name="Mentoring",
        category="mentoring",
        form_slug="mentoring-note",
        creators=["manager", "trainer"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="counselling",
        name="Counselling",
        category="counselling",
        form_slug="counselling-note",
        creators=["manager", "counsellor"],
        assignees=["counsellor", "manager"],
        visible_to_student=False,
        duration=30,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="career-guidance",
        name="Career Guidance",
        category="counselling",
        form_slug="counselling-note",
        creators=["manager", "counsellor"],
        assignees=["counsellor", "manager"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="doubt-session",
        name="Doubt Session",
        category="mentoring",
        form_slug="doubt-session",
        creators=["trainer", "manager", "student"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="code-review",
        name="Code Review",
        category="review",
        form_slug="code-review",
        creators=["trainer", "manager"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="1.00",
        risk_effect="score_below_threshold",
        next_action=None,
    ),
    dict(
        slug="resume-review",
        name="Resume Review",
        category="placement",
        form_slug="resume-review",
        creators=["manager", "counsellor", "trainer"],
        assignees=["trainer", "manager"],
        visible_to_student=True,
        duration=20,
        requires_review=False,
        performance_weight="0.50",
        risk_effect="none",
        next_action={
            "when": "score_below",
            "threshold": 6,
            "create_type": "resume-review",
            "assign_to": "same_assignee",
            "notify": [],
        },
    ),
    dict(
        slug="project-review",
        name="Project Review",
        category="review",
        form_slug="project-review",
        creators=["trainer", "manager"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=45,
        requires_review=True,
        performance_weight="1.00",
        risk_effect="score_below_threshold",
        next_action=None,
    ),
    dict(
        slug="placement-call",
        name="Placement Call",
        category="placement",
        form_slug="placement-call",
        creators=["manager", "counsellor"],
        assignees=["counsellor", "manager"],
        visible_to_student=False,
        duration=15,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action={
            "when": "outcome_equals",
            "threshold": "not_ready",
            "create_type": "mock-interview",
            "assign_to": "batch_trainer",
            "notify": [],
        },
    ),
    dict(
        slug="feedback",
        name="Feedback",
        category="feedback",
        form_slug="feedback-note",
        creators=STAFF,
        assignees=[],
        visible_to_student=True,
        duration=None,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="parent-meeting",
        name="Parent Meeting",
        category="counselling",
        form_slug="parent-meeting",
        creators=["counsellor", "manager"],
        assignees=["counsellor", "manager"],
        visible_to_student=False,
        duration=30,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="warning",
        name="Warning",
        category="warning",
        form_slug="warning-note",
        creators=["manager"],
        assignees=[],
        visible_to_student=True,
        duration=None,
        requires_review=True,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="performance-review",
        name="Performance Review",
        category="review",
        form_slug=None,
        creators=["manager"],
        assignees=["manager"],
        visible_to_student=True,
        duration=None,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="follow-up",
        name="Follow-up",
        category="follow_up",
        form_slug="follow-up-note",
        creators=["counsellor", "manager", "trainer"],
        assignees=["counsellor", "trainer"],
        visible_to_student=False,
        duration=10,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
    dict(
        slug="communication-practice",
        name="Communication Practice",
        category="mentoring",
        form_slug="communication-practice",
        creators=["trainer", "manager", "automation"],
        assignees=["trainer"],
        visible_to_student=True,
        duration=30,
        requires_review=False,
        performance_weight="0.50",
        risk_effect="score_below_threshold",
        next_action={
            "when": "score_below",
            "threshold": 5,
            "create_type": None,
            "assign_to": None,
            "notify": ["manager"],
        },
    ),
    dict(
        slug="attendance-counselling",
        name="Attendance Counselling",
        category="counselling",
        form_slug="counselling-note",
        creators=["automation", "manager", "counsellor"],
        assignees=["counsellor"],
        visible_to_student=False,
        duration=20,
        requires_review=False,
        performance_weight="0.00",
        risk_effect="none",
        next_action=None,
    ),
]


def seed_types(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    FormDefinition = apps.get_model("forms", "FormDefinition")

    for spec in TYPES:
        if ActivityType.objects.filter(slug=spec["slug"]).exists():
            # Already seeded (idempotent replay): leave it exactly as it was.
            continue
        form = None
        if spec["form_slug"]:
            form = FormDefinition.objects.filter(slug=spec["form_slug"]).first()
        ActivityType.objects.create(
            slug=spec["slug"],
            name=spec["name"],
            category=spec["category"],
            form=form,
            allowed_creator_roles=spec["creators"],
            allowed_assignee_roles=spec["assignees"],
            visible_to_student=spec["visible_to_student"],
            default_duration_minutes=spec["duration"],
            requires_review=spec["requires_review"],
            performance_weight=spec["performance_weight"],
            risk_effect=spec["risk_effect"],
            next_action=spec["next_action"],
            is_system=True,
            status="active",
        )


def unseed_types(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    ActivityType.objects.filter(slug__in=[spec["slug"] for spec in TYPES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("work", "0001_initial"),
        ("forms", "0002_seed_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
