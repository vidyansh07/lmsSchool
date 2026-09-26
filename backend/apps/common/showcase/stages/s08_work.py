"""Stage 8 — the work around students: activities, reviews, risk, housekeeping.

Creates, through the services and idempotently:

* **Activity types** (``apps.work.services``): three custom rows next to the
  eighteen catalog ones — *Placement drive* (active, no form), *Library
  induction* (created active, one activity logged on it, then **disabled**
  through ``update_activity_type`` so the catalog shows a retired type with
  history) and *Capstone evaluation* (``requires_review`` with its own form,
  built and published through ``apps.forms.services``). Idempotent by slug
  through ``ActivityType.all_objects``.

* **Activities** — :data:`ACTIVITIES`, about a hundred and ten across both
  centres, every catalog type, every priority and all twelve statuses, walked
  through ``create_activity`` → ``transition_activity`` → ``complete_activity``
  → ``review_activity`` exactly as ``work/transitions.py`` allows. Twenty are
  on the imported SITP students of the four live SITP batches (through
  ``ctx.live_enrolments``; a clean no-op where nothing imported exists),
  eight are due later today and ten already past due (the counsellor KPIs),
  twenty-odd are assigned to the headline trainer (*My work*) and eleven are
  visible to the headline student. Form-backed types are completed with
  values valid against the pinned published version; two mock interviews are
  completed with communication below six and two technical interviews with a
  score below sixty on purpose, so the seeded automation rules fire and
  leave their own activities, notifications and ``AutomationRun`` rows.
  *Overdue* and *missed* are the system's verdict, never written by hand:
  the rows are set up (assigned, past due; assigned, planned an hour or more
  ago, never started) and ``mark_overdue_and_missed`` runs once, **on
  commit** — it enqueues automation dispatches with ``.delay()`` directly,
  which under eager Celery must not run inside the stage's transaction.

  The idempotency key is the service's own: ``client_key`` carries
  ``[showcase][act/<key>]`` and the row is found through
  ``Activity.all_objects`` (the bin included, since this stage bins two).
  A found open row whose planned/due time has slipped into the past since
  the run that made it is re-anchored to the intended relative time, so
  *assigned* and *due today* stay true on any day — see :func:`_keep_live`.

* **Performance** (``apps.performance.services``): reviews for ten students
  and six trainers in draft/shared/acknowledged — five with ``next_review_at``
  already past (*Reviews due*), drafts with no date — and feedback on both,
  always by a manager, never by the subject. Idempotent by subject plus the
  ``[showcase][review/…]`` tag in the summary (or feedback body): a period
  is a calendar month and would move on a re-run next month, the tag does
  not. Then ``recompute_risk(enrollment=)`` for every live enrolment on the
  showcase batches and the four live SITP batches, so ``RiskState`` is
  materialised and the caseload screens have a none/warning/critical mix to
  draw (stage 6's attendance is what drives it).

* **Reporting**: four ``SavedFilter`` presets on the activities screen (two
  for the counsellor, two for the manager, through ``save_filter``); export
  jobs in every state — *queued*, *processing*, *completed* by running
  ``reporting.tasks.run_export`` for real (a small CSV in private storage),
  *failed* by asking for a batch the requester cannot see (the task writes
  the refusal into ``error``), *cancelled* the way the cancel endpoint does
  it; a bulk-import fixture with valid and invalid rows under
  ``showcase/students-import.csv`` in ``default_storage``, previewed once
  through ``preview_students`` so ``/admin/imports`` has a row.

* **Recycle bin** (``apps.common.deletion``): two activities binned through
  ``delete_activity`` with reasons, one of them **restored** (the audit row
  is what says it happened, so the second run leaves it alone); stage 2's
  disabled *Guest lecturer* role through ``delete_role``; one trainer
  requirement raised here and binned through ``delete_requirement`` — not
  one of stage 6's, because stage 6 finds its rows through ``objects`` and
  would make a binned one again on the next full run; stage 9's cancelled
  guest-lecture notice through ``delete_announcement`` when stage 9 has
  already run, skipped and said so otherwise.

Leaves in ``ctx``: ``activity_types`` with the three added slugs.

What is deliberately not here
-----------------------------
Resume reviews and project reviews are never *completed*: their forms need a
file upload and a ``studentproject`` relation, which the form validator
cannot resolve yet (``apps.forms.validation`` documents both gaps), so those
two types appear as planned/assigned work only. Automation rules are stage
9's, so none is binned here.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.announcements.models import Announcement
from apps.announcements.services import delete_announcement
from apps.audit.models import AuditAction, AuditLog
from apps.authorization.models import Role
from apps.authorization.services import delete_role
from apps.batches.models import Batch, BatchStatus
from apps.common.deletion import restore
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.forms.models import FormDefinition, FormEntity, FormVersion, FormVersionStatus
from apps.forms.services import create_definition, create_draft_version, publish_version, set_fields
from apps.performance.models import (
    Feedback,
    PerformanceReview,
    ReviewStatus,
    ReviewType,
    RiskState,
)
from apps.performance.services import create_feedback, create_review, recompute_risk, update_review
from apps.reporting.importers import preview_students
from apps.reporting.models import (
    BulkImport,
    ExportFormat,
    ExportJob,
    ExportStatus,
    ImportKind,
    SavedFilter,
)
from apps.reporting.saved_filters import save_filter
from apps.reporting.tasks import run_export
from apps.requirements.models import TrainerRequirement
from apps.requirements.services import delete_requirement, raise_requirement
from apps.students.models import StudentProfile
from apps.trainers.models import TrainerProfile
from apps.work.models import (
    Activity,
    ActivityCategory,
    ActivityHistory,
    ActivityPriority,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
    RiskEffect,
)
from apps.work.services import (
    MISSED_GRACE_MINUTES,
    complete_activity,
    create_activity,
    create_activity_type,
    delete_activity,
    mark_overdue_and_missed,
    review_activity,
    transition_activity,
    update_activity_type,
)

from ..context import MARKER, Context, batch_key
from ..roster import MAIN
from .s04_batches import SPECS

DRAFT = ActivityStatus.DRAFT
PLANNED = ActivityStatus.PLANNED
ASSIGNED = ActivityStatus.ASSIGNED
IN_PROGRESS = ActivityStatus.IN_PROGRESS
COMPLETED = ActivityStatus.COMPLETED
MISSED = ActivityStatus.MISSED
OVERDUE = ActivityStatus.OVERDUE
CANCELLED = ActivityStatus.CANCELLED
REOPENED = ActivityStatus.REOPENED
UNDER_REVIEW = ActivityStatus.UNDER_REVIEW
APPROVED = ActivityStatus.APPROVED
REQUIRES_ACTION = ActivityStatus.REQUIRES_ACTION

LOW = ActivityPriority.LOW
NORMAL = ActivityPriority.NORMAL
HIGH = ActivityPriority.HIGH
URGENT = ActivityPriority.URGENT

#: The headline student, wherever a spec names a student by position.
HEADLINE = "headline"

#: Batch keys for the four live SITP batches, in code order. On a database
#: with no import (the test database) none of these resolves and every spec
#: on them is skipped.
SITP_KEYS = ("sitp1", "sitp2", "sitp3", "sitp4")

#: The screen the activities page files its presets under
#: (``frontend/app/activities/page.tsx``, ``SAVED_FILTER_SCREEN``).
ACTIVITIES_SCREEN = "activities"

IMPORT_FIXTURE_PATH = "showcase/students-import.csv"


# ---------------------------------------------------------------------------
# Custom activity types
# ---------------------------------------------------------------------------

PLACEMENT_DRIVE = "placement-drive"
LIBRARY_INDUCTION = "library-induction"
CAPSTONE_EVALUATION = "capstone-evaluation"

#: The form behind the capstone type: every value below is what
#: ``apps.forms.validation`` accepts for its type, and ``mentor_rating`` is
#: the performance field the engine reads (``performance_key="score"``).
CAPSTONE_FORM_FIELDS: list[dict[str, Any]] = [
    {
        "key": "project_title",
        "label": "Project",
        "type": "text",
        "required": True,
        "validation": {"max_length": 160},
        "visible_to_student": True,
    },
    {
        "key": "mentor_rating",
        "label": "Mentor rating (0-10)",
        "type": "decimal",
        "required": True,
        "validation": {"min": 0, "max": 10},
        "visible_to_student": True,
        "performance_key": "score",
    },
    {
        "key": "outcome",
        "label": "Outcome",
        "type": "select",
        "required": True,
        "options": [
            {"value": "approved", "label": "Approved"},
            {"value": "revise", "label": "Revise"},
        ],
        "visible_to_student": True,
    },
    {
        "key": "remarks",
        "label": "Remarks",
        "type": "textarea",
        "required": True,
        "validation": {"max_length": 4000},
        "visible_to_student": True,
    },
]

CUSTOM_TYPES: list[dict[str, Any]] = [
    {
        "slug": PLACEMENT_DRIVE,
        "name": "Placement drive",
        "description": "A student's slot in a campus placement drive: who, which company, outcome.",
        "category": ActivityCategory.PLACEMENT,
        "allowed_creator_roles": [UserRole.MANAGER, UserRole.COUNSELLOR],
        "allowed_assignee_roles": [UserRole.COUNSELLOR, UserRole.MANAGER],
        "visible_to_student": True,
        "default_duration_minutes": 60,
        "requires_review": False,
        "performance_weight": "0.00",
        "risk_effect": RiskEffect.NONE,
        "disabled": False,
        "form_slug": None,
    },
    {
        "slug": LIBRARY_INDUCTION,
        "name": "Library induction",
        "description": "The old first-week library walkthrough; retired when the library moved.",
        "category": ActivityCategory.OTHER,
        "allowed_creator_roles": [UserRole.MANAGER, UserRole.COUNSELLOR],
        "allowed_assignee_roles": [UserRole.COUNSELLOR],
        "visible_to_student": False,
        "default_duration_minutes": 20,
        "requires_review": False,
        "performance_weight": "0.00",
        "risk_effect": RiskEffect.NONE,
        "disabled": True,
        "form_slug": None,
    },
    {
        "slug": CAPSTONE_EVALUATION,
        "name": "Capstone evaluation",
        "description": "The trainer's evaluation of a student's capstone; a manager signs it off.",
        "category": ActivityCategory.REVIEW,
        "allowed_creator_roles": [UserRole.MANAGER, UserRole.TRAINER],
        "allowed_assignee_roles": [UserRole.TRAINER],
        "visible_to_student": True,
        "default_duration_minutes": 45,
        "requires_review": True,
        "performance_weight": "1.00",
        "risk_effect": RiskEffect.SCORE_BELOW_THRESHOLD,
        "disabled": False,
        "form_slug": CAPSTONE_EVALUATION,
    },
]


# ---------------------------------------------------------------------------
# The activities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Act:
    """One activity, as the staff would have logged it.

    ``batch`` is a stage-4 spec key (``a2``) or one of :data:`SITP_KEYS`;
    ``student`` a position on that batch's roster (the headline student is
    kept out of the roster and named :data:`HEADLINE`). ``creator``,
    ``assignee`` and ``reviewer`` are actor references resolved per batch by
    :func:`_actor`: a roster local part (``neha.saxena``), or ``admin`` /
    ``manager`` / ``counsellor`` for the centre's own. ``planned`` and
    ``due`` are ``(days from today, hour)``; ``completed`` is days ago.
    ``status`` is where the activity ends up — for *overdue* and *missed* it
    is where the sweep will put it.
    """

    key: str
    batch: str
    type: str
    status: str
    creator: str
    assignee: str | None
    student: int | str
    title: str
    priority: str = NORMAL
    planned: tuple[int, int] | None = None
    due: tuple[int, int] | None = None
    completed: int | None = None
    form: dict[str, Any] | None = None
    summary: str = ""
    note: str = ""
    reviewer: str = "admin"
    reopen_from: str = CANCELLED
    started: bool = False


def _acts() -> tuple[Act, ...]:
    """Every activity. A function rather than a module constant only so the
    long list reads top to bottom without a hundred ``Act(`` prefixes."""
    A = Act  # a local alias keeps the table narrow
    # fmt: off
    rows: list[Act] = [
        # --- Jaipur: DevOps Engineering Morning (the headline batch, Vikram) ---
        A("a2-mock-01", "a2", "mock-interview", COMPLETED, "manager", "trainer", HEADLINE,
          "Mock interview — Docker and Linux fundamentals", planned=(-12, 11), completed=12,
          form={"communication": 8, "technical": 8, "confidence": 7, "score": 8, "outcome": "ready",
                "improvements": "More depth on storage drivers."},
          summary="Confident on containers; a little more depth on storage drivers wanted."),
        A("a2-mock-02", "a2", "mock-interview", COMPLETED, "manager", "trainer", 3,
          "Mock interview — Kubernetes basics", priority=HIGH, planned=(-9, 11), completed=9,
          # Communication below six on purpose: the seeded rule schedules a
          # communication-practice session and tells the manager.
          form={"communication": 4, "technical": 6, "confidence": 4, "score": 5,
                "outcome": "needs_practice", "improvements": "Explain what you know out loud."},
          summary="Knows the material; struggles to explain it. Practice sessions booked."),
        A("a2-mock-03", "a2", "mock-interview", ASSIGNED, "manager", "trainer", 5,
          "Mock interview — CI/CD pipelines", priority=HIGH, planned=(2, 11), due=(2, 18)),
        A("a2-mock-04", "a2", "mock-interview", OVERDUE, "manager", "trainer", 7,
          "Mock interview — Ansible playbooks", priority=HIGH, planned=(-4, 11), due=(-3, 18)),
        A("a2-mock-05", "a2", "mock-interview", REOPENED, "manager", "trainer", 26,
          "Mock interview — cloud fundamentals", planned=(1, 15),
          note="Student was unwell; reopened now that they are back in class."),
        A("a2-tech-01", "a2", "technical-interview", COMPLETED, "trainer", "trainer", HEADLINE,
          "Technical interview — containers, round 1", planned=(-6, 14), completed=6,
          form={"technical": 8, "problem_solving": 8, "score": 8, "outcome": "ready"},
          summary="Solid. Explained image layering and networking without prompting."),
        A("a2-tech-02", "a2", "technical-interview", COMPLETED, "trainer", "trainer", 9,
          "Technical interview — Linux administration", planned=(-5, 14), completed=5,
          # Score five of ten — 50 % — on purpose: the seeded rule books a
          # doubt session with the batch trainer.
          form={"technical": 5, "problem_solving": 5, "score": 5, "outcome": "needs_practice",
                "improvements": "Permissions and process management."},
          summary="Gaps in permissions and process management; a doubt session follows."),
        A("a2-tech-03", "a2", "technical-interview", IN_PROGRESS, "trainer", "trainer", 11,
          "Technical interview — Kubernetes workloads", planned=(0, 10), due=(1, 18),
          started=True),
        A("a2-tech-04", "a2", "technical-interview", CANCELLED, "manager", "trainer", 25,
          "Technical interview — infrastructure as code", planned=(1, 14),
          note="Student is on leave this week; to be rescheduled next month."),
        A("a2-ment-01", "a2", "mentoring", COMPLETED, "trainer", "trainer", HEADLINE,
          "Mentoring — a career path into DevOps", planned=(-20, 16), completed=20,
          form={"topic": "Career path into DevOps",
                "summary": "Talked through the RHCSA → CKA → cloud route and which projects to "
                           "show on GitHub first.",
                "action_items": "Finish the CI pipeline project; start the CKA syllabus."},
          summary="Clear about the goal; needs a public project portfolio."),
        A("a2-ment-02", "a2", "mentoring", ASSIGNED, "trainer", "trainer", 13,
          "Mentoring — study plan for the CKA", planned=(1, 16), due=(1, 18)),
        A("a2-ment-03", "a2", "mentoring", MISSED, "trainer", "trainer", 15,
          "Mentoring — catching up after the break", planned=(-2, 15)),
        A("a2-ment-04", "a2", "mentoring", IN_PROGRESS, "trainer", "trainer", 23,
          "Mentoring — project scoping", planned=(-1, 16), due=(2, 18), started=True),
        A("a2-doubt-01", "a2", "doubt-session", COMPLETED, "trainer", "trainer", HEADLINE,
          "Doubt session — Kubernetes networking", priority=LOW, planned=(-3, 12), completed=3,
          form={"topic": "Services, ingress and network policies", "resolved": True,
                "notes": "Drew the traffic path from ingress to pod; resolved."},
          summary="Resolved in twenty minutes."),
        A("a2-doubt-02", "a2", "doubt-session", ASSIGNED, "trainer", "trainer", 17,
          "Doubt session — Helm charts", planned=(0, 22), due=(0, 23)),
        A("a2-doubt-03", "a2", "doubt-session", DRAFT, "trainer", None, 1,
          "Doubt session — Ansible vault"),
        A("a2-code-01", "a2", "code-review", COMPLETED, "trainer", "trainer", HEADLINE,
          "Code review — CI pipeline repository", planned=(-8, 17), completed=8,
          form={"repository_url": "https://github.com/grras-students/ci-pipeline-aarav",
                "score": 7, "readability": 7, "correctness": 8, "structure": 6,
                "comments": "<p>Good stage separation. Pin the base image versions and add a "
                            "lint stage before build.</p>"},
          summary="Pass. Pin image versions; add a lint stage."),
        A("a2-code-02", "a2", "code-review", OVERDUE, "trainer", "trainer", 19,
          "Code review — monitoring stack", priority=URGENT, planned=(-6, 17), due=(-2, 18)),
        A("a2-code-03", "a2", "code-review", REOPENED, "trainer", "trainer", 21,
          "Code review — Terraform modules", planned=(-10, 17), completed=10,
          form={"repository_url": "https://github.com/grras-students/terraform-modules",
                "score": 6, "readability": 6, "correctness": 6, "structure": 5,
                "comments": "<p>Modules work but repeat themselves; extract the VPC module.</p>"},
          reopen_from=COMPLETED,
          note="Repository was re-submitted after the review; look at it again."),
        A("a2-cap-01", "a2", CAPSTONE_EVALUATION, UNDER_REVIEW, "manager", "trainer", 2,
          "Capstone evaluation — monitoring stack", planned=(-1, 15), completed=1,
          form={"project_title": "Prometheus and Grafana monitoring stack", "mentor_rating": 7,
                "outcome": "approved", "remarks": "Alerting rules are thoughtful; dashboards "
                                                   "need labels."},
          summary="Recommended for approval."),
        A("a2-cap-02", "a2", CAPSTONE_EVALUATION, APPROVED, "manager", "trainer", HEADLINE,
          "Capstone evaluation — GitOps deployment", planned=(-7, 15), completed=7,
          form={"project_title": "GitOps deployment with Argo CD", "mentor_rating": 9,
                "outcome": "approved", "remarks": "Production-shaped: secrets handled, "
                                                   "rollbacks demonstrated."},
          summary="Recommended for approval.", reviewer="manager",
          note="Well documented and demonstrated end to end; approved."),
        A("a2-cap-03", "a2", CAPSTONE_EVALUATION, REQUIRES_ACTION, "manager", "trainer", 4,
          "Capstone evaluation — autoscaling lab", planned=(-3, 15), completed=3,
          form={"project_title": "Horizontal pod autoscaling lab", "mentor_rating": 5,
                "outcome": "revise", "remarks": "Works, but no load test to show the scaling."},
          summary="Revise before sign-off.", reviewer="manager",
          note="Add the load-test results before this is signed off."),
        A("a2-warn-01", "a2", "warning", APPROVED, "manager", "admin", 6,
          "Attendance warning — three consecutive absences", priority=HIGH,
          planned=(-4, 10), completed=4,
          form={"reason": "attendance", "acknowledged_by_student": True,
                "details": "Absent on three consecutive lab days without notice."},
          summary="Warning issued and acknowledged.", reviewer="manager",
          note="Issued correctly; keep an eye on the next fortnight."),
        A("a2-warn-02", "a2", "warning", UNDER_REVIEW, "manager", "admin", 8,
          "Conduct warning — lab equipment", planned=(-1, 10), completed=1,
          form={"reason": "conduct", "acknowledged_by_student": False,
                "details": "Left the lab machines logged in and unlocked twice this week."},
          summary="Awaiting the manager's sign-off.", reviewer="manager"),
        A("a2-perf-01", "a2", "performance-review", COMPLETED, "manager", "manager", HEADLINE,
          "Monthly performance review — August", planned=(-15, 12), completed=15,
          summary="On track across attendance, tests and labs."),
        A("a2-perf-02", "a2", "performance-review", PLANNED, "manager", "manager", 10,
          "Monthly performance review — September", planned=(5, 12)),
        A("a2-fu-01", "a2", "follow-up", COMPLETED, "counsellor", "counsellor", 12,
          "Follow-up — fee instalment reminder", priority=LOW, planned=(-2, 10), completed=2,
          form={"channel": "phone", "outcome": "reached",
                "summary": "Will pay the second instalment on Friday."},
          summary="Reached; payment promised for Friday."),
        A("a2-fu-02", "a2", "follow-up", ASSIGNED, "counsellor", "counsellor", 14,
          "Follow-up — missing ID proof", planned=(0, 21), due=(0, 22)),
        A("a2-fu-03", "a2", "follow-up", OVERDUE, "counsellor", "counsellor", 16,
          "Follow-up — hostel address confirmation", planned=(-5, 10), due=(-4, 18)),
        A("a2-fu-04", "a2", "follow-up", CANCELLED, "counsellor", "counsellor", 18,
          "Follow-up — timetable query", priority=LOW, planned=(1, 10),
          note="Student called back first; nothing pending."),
        A("a2-couns-01", "a2", "counselling", COMPLETED, "counsellor", "counsellor", 20,
          "Counselling — falling behind on labs", planned=(-6, 15), completed=6,
          form={"reason": "academic", "summary": "Behind on the Ansible labs after a week off; "
                                                  "agreed a catch-up plan with the trainer.",
                "commitments": "Two extra lab hours on Saturdays.", "guardian_informed": False},
          summary="Catch-up plan agreed."),
        A("a2-cg-01", "a2", "career-guidance", COMPLETED, "counsellor", "counsellor", HEADLINE,
          "Career guidance — DevOps roles and certifications", planned=(-18, 15), completed=18,
          form={"reason": "placement", "summary": "Mapped the roles open to a fresher and which "
                                                   "certifications the hiring partners ask for.",
                "commitments": "Sit the RHCSA before the placement drive.",
                "guardian_informed": False},
          summary="RHCSA before the drive."),
        A("a2-fb-01", "a2", "feedback", COMPLETED, "trainer", "admin", HEADLINE,
          "Feedback — lab discipline", priority=LOW, planned=(-1, 18), completed=1,
          form={"body": "Consistently the first to have the lab environment ready and the "
                        "last to leave it tidy. Keep it up.", "visible_to_student": True},
          summary="Positive."),
        A("a2-fb-02", "a2", "feedback", DRAFT, "trainer", None, 22,
          "Feedback — presentation skills", priority=LOW),
        A("a2-cp-01", "a2", "communication-practice", ASSIGNED, "trainer", "trainer", 3,
          "Communication practice — explaining a deployment", planned=(3, 16), due=(3, 18)),
        A("a2-hr-01", "a2", "hr-interview", COMPLETED, "manager", "manager", HEADLINE,
          "HR interview — round 1", planned=(-2, 12), completed=2,
          form={"communication": 8, "attitude": 9, "score": 8, "outcome": "ready"},
          summary="Ready for the drive."),
        A("a2-res-01", "a2", "resume-review", PLANNED, "counsellor", "trainer", HEADLINE,
          "Resume review — before the October drive", planned=(2, 15)),
        A("a2-proj-01", "a2", "project-review", ASSIGNED, "trainer", "trainer", 24,
          "Project review — three-tier deployment", planned=(4, 15), due=(4, 18)),
        A("a2-pd-01", "a2", PLACEMENT_DRIVE, ASSIGNED, "manager", "counsellor", 2,
          "Placement drive — Infosys campus round", priority=HIGH, planned=(6, 9), due=(6, 18)),
        A("a2-pc-01", "a2", "placement-call", COMPLETED, "counsellor", "counsellor", 26,
          "Placement call — Wipro screening", planned=(-1, 11), completed=1,
          # "Not ready" on purpose: the seeded rule books a mock interview
          # with the batch trainer and tells the manager.
          form={"company": "Wipro", "outcome": "not_ready",
                "notes": "Needs another mock before the screening round."},
          summary="Not ready yet; mock interview to follow."),
        A("a2-lib-01", "a2", LIBRARY_INDUCTION, COMPLETED, "manager", "counsellor", 0,
          "Library induction — first week", priority=LOW, planned=(-40, 10), completed=40,
          summary="Done in the first week, before the type was retired."),
        # --- Jaipur: AWS Solutions Architect Evening (Rohit) ------------------
        A("a1-mock-01", "a1", "mock-interview", COMPLETED, "manager", "rohit.kumawat", 0,
          "Mock interview — AWS core services", planned=(-7, 19), completed=7,
          form={"communication": 7, "technical": 7, "confidence": 6, "score": 7,
                "outcome": "ready", "improvements": "Revise IAM policies."},
          summary="Good on compute and storage; revise IAM policies."),
        A("a1-tech-01", "a1", "technical-interview", OVERDUE, "manager", "rohit.kumawat", 2,
          "Technical interview — VPC design", priority=HIGH, planned=(-3, 19), due=(-2, 21)),
        A("a1-ment-01", "a1", "mentoring", COMPLETED, "rohit.kumawat", "rohit.kumawat", 4,
          "Mentoring — balancing work and the evening batch", planned=(-11, 20), completed=11,
          form={"topic": "Balancing a day job with the evening batch",
                "summary": "Agreed a lighter lab schedule during the month-end close at work.",
                "action_items": "Recorded sessions for the two classes missed."},
          summary="Plan agreed."),
        A("a1-doubt-01", "a1", "doubt-session", ASSIGNED, "rohit.kumawat", "rohit.kumawat", 6,
          "Doubt session — IAM policy evaluation", planned=(2, 20), due=(2, 21)),
        A("a1-fu-01", "a1", "follow-up", ASSIGNED, "counsellor2", "counsellor2", 8,
          "Follow-up — instalment overdue by a week", priority=HIGH, planned=(0, 21), due=(0, 22)),
        A("a1-couns-01", "a1", "counselling", COMPLETED, "counsellor2", "counsellor2", 10,
          "Counselling — fee schedule", planned=(-4, 18), completed=4,
          form={"reason": "fees", "summary": "Reworked the instalment plan around the student's "
                                              "salary date.", "commitments": "Pay on the 5th.",
                "guardian_informed": True},
          summary="Instalments moved to the 5th."),
        A("a1-pc-01", "a1", "placement-call", COMPLETED, "counsellor", "counsellor", 12,
          "Placement call — TCS offer", planned=(-13, 11), completed=13,
          form={"company": "TCS", "outcome": "placed", "package": 4.5,
                "notes": "Offer accepted; joins in January."},
          summary="Placed at TCS, 4.5 LPA."),
        A("a1-code-01", "a1", "code-review", MISSED, "rohit.kumawat", "rohit.kumawat", 14,
          "Code review — Terraform VPC module", planned=(-3, 19)),
        A("a1-cg-01", "a1", "career-guidance", PLANNED, "counsellor", None, 16,
          "Career guidance — cloud roles for a career changer", planned=(3, 18)),
        # --- Jaipur: Python Full Stack Weekend (Neha) --------------------------
        A("a3-mock-01", "a3", "mock-interview", COMPLETED, "manager", "neha.saxena", 0,
          "Mock interview — Django and REST", planned=(-14, 10), completed=14,
          form={"communication": 7, "technical": 8, "confidence": 7, "score": 7,
                "outcome": "ready", "improvements": "Polish the project walkthrough."},
          summary="Ready; polish the project walkthrough."),
        A("a3-tech-01", "a3", "technical-interview", COMPLETED, "neha.saxena", "neha.saxena", 2,
          "Technical interview — Python data structures", planned=(-9, 10), completed=9,
          form={"technical": 9, "problem_solving": 9, "score": 9, "outcome": "ready"},
          summary="Excellent."),
        A("a3-code-01", "a3", "code-review", COMPLETED, "neha.saxena", "neha.saxena", 4,
          "Code review — blog application", priority=LOW, planned=(-3, 11), completed=3,
          form={"repository_url": "https://github.com/grras-students/django-blog",
                "score": 8, "readability": 8, "correctness": 8, "structure": 7,
                "comments": "<p>Clean views; move the query logic into managers.</p>"},
          summary="Pass."),
        A("a3-cap-01", "a3", CAPSTONE_EVALUATION, UNDER_REVIEW, "manager", "neha.saxena", 6,
          "Capstone evaluation — inventory system", planned=(-2, 11), completed=2,
          form={"project_title": "Inventory management system", "mentor_rating": 8,
                "outcome": "approved", "remarks": "Complete feature set; tests could be broader."},
          summary="Recommended for approval."),
        A("a3-fu-01", "a3", "follow-up", OVERDUE, "counsellor", "counsellor", 8,
          "Follow-up — certificate name correction", planned=(-8, 10), due=(-6, 18)),
        A("a3-pm-01", "a3", "parent-meeting", COMPLETED, "counsellor", "counsellor", 10,
          "Parent meeting — attendance on Sundays", planned=(-5, 16), completed=5,
          form={"attendee": "Father", "mode": "phone",
                "summary": "Sunday absences are down to a family business; agreed the student "
                           "watches the recordings and attends the Saturday lab in full.",
                "commitments": "Saturday attendance in full."},
          summary="Agreed with the father."),
        A("a3-doubt-01", "a3", "doubt-session", ASSIGNED, "neha.saxena", "neha.saxena", 12,
          "Doubt session — Django ORM joins", planned=(1, 12), due=(1, 13)),
        A("a3-fu-02", "a3", "follow-up", ASSIGNED, "counsellor", "counsellor", 14,
          "Follow-up — weekend lab access card", planned=(0, 21), due=(0, 22)),
        # --- Jaipur: Data Science Internship (Priya) ---------------------------
        A("a4-cap-01", "a4", CAPSTONE_EVALUATION, APPROVED, "manager", "priya.malhotra", 0,
          "Capstone evaluation — churn prediction", planned=(-12, 14), completed=12,
          form={"project_title": "Customer churn prediction", "mentor_rating": 8,
                "outcome": "approved", "remarks": "Sound feature engineering; honest about "
                                                   "the model's limits."},
          summary="Recommended for approval.", reviewer="manager",
          note="Approved; a strong internship report."),
        A("a4-cap-02", "a4", CAPSTONE_EVALUATION, REQUIRES_ACTION, "manager", "priya.malhotra", 2,
          "Capstone evaluation — sales dashboard", planned=(-4, 14), completed=4,
          form={"project_title": "Sales dashboard", "mentor_rating": 5, "outcome": "revise",
                "remarks": "The dashboard reads well but the data pipeline is manual."},
          summary="Revise.", reviewer="manager",
          note="Automate the refresh before this can be signed off."),
        A("a4-ment-01", "a4", "mentoring", COMPLETED, "priya.malhotra", "priya.malhotra", 4,
          "Mentoring — choosing an internship project", planned=(-6, 15), completed=6,
          form={"topic": "Choosing an internship project",
                "summary": "Narrowed three ideas to one with a public dataset and a clear "
                           "business question.", "action_items": "Write the one-page proposal."},
          summary="Proposal due next week."),
        A("a4-mock-01", "a4", "mock-interview", ASSIGNED, "manager", "priya.malhotra", 6,
          "Mock interview — data science fundamentals", planned=(4, 14), due=(4, 17)),
        A("a4-pc-01", "a4", "placement-call", COMPLETED, "counsellor2", "counsellor2", 8,
          "Placement call — Deloitte analytics", planned=(-3, 11), completed=3,
          form={"company": "Deloitte", "outcome": "ready", "notes": "Shortlisted for round 2."},
          summary="Shortlisted."),
        A("a4-fu-01", "a4", "follow-up", ASSIGNED, "counsellor2", "counsellor2", 10,
          "Follow-up — stipend bank details", planned=(0, 21), due=(0, 22)),
        A("a4-hr-01", "a4", "hr-interview", COMPLETED, "manager", "manager", 12,
          "HR interview — internship conversion", planned=(-8, 12), completed=8,
          form={"communication": 6, "attitude": 8, "score": 7, "outcome": "ready"},
          summary="Ready."),
        A("a4-doubt-01", "a4", "doubt-session", OVERDUE, "priya.malhotra", "priya.malhotra", 1,
          "Doubt session — feature scaling", planned=(-2, 15), due=(-1, 17)),
        # --- Jaipur: RHCSA Evening, completed (history for the headline student) -
        A("c1-pc-01", "c1", "placement-call", COMPLETED, "counsellor", "counsellor", HEADLINE,
          "Placement call — Wipro", planned=(-70, 11), completed=70,
          form={"company": "Wipro", "outcome": "placed", "package": 3.8,
                "notes": "Offer letter received."},
          summary="Placed at Wipro, 3.8 LPA."),
        A("c1-hr-01", "c1", "hr-interview", COMPLETED, "manager", "manager", HEADLINE,
          "HR interview — Wipro preparation", planned=(-80, 12), completed=80,
          form={"communication": 7, "attitude": 8, "score": 7, "outcome": "ready"},
          summary="Ready."),
        A("c1-mock-01", "c1", "mock-interview", COMPLETED, "manager", "trainer", 1,
          "Mock interview — RHCSA objectives", planned=(-90, 18), completed=90,
          form={"communication": 7, "technical": 8, "confidence": 7, "score": 7,
                "outcome": "ready", "improvements": "Time management in the lab."},
          summary="Ready for the exam."),
        A("c1-cg-01", "c1", "career-guidance", COMPLETED, "counsellor", "counsellor", 2,
          "Career guidance — after the RHCSA", planned=(-75, 15), completed=75,
          form={"reason": "placement", "summary": "Discussed support roles versus a DevOps "
                                                   "track.", "guardian_informed": False},
          summary="Support role first."),
        # --- Jaipur: Ansible Automation Weekend (demo trainer) -----------------
        A("d1-couns-01", "d1", "counselling", COMPLETED, "counsellor", "counsellor", 0,
          "Counselling — weekend travel time", planned=(-2, 13), completed=2,
          form={"reason": "personal", "summary": "Two hours each way on Saturdays; agreed the "
                                                  "Sunday session can be attended online.",
                "guardian_informed": False},
          summary="Sunday online."),
        A("d1-fu-01", "d1", "follow-up", OVERDUE, "counsellor", "counsellor", 2,
          "Follow-up — pending photograph for the ID card", priority=LOW,
          planned=(-3, 10), due=(-2, 18)),
        A("d1-pd-01", "d1", PLACEMENT_DRIVE, PLANNED, "manager", None, 4,
          "Placement drive — HCL walk-in", planned=(8, 9)),
        # --- Jaipur: RHCSA Morning, upcoming (Vikram) --------------------------
        A("u1-couns-01", "u1", "counselling", COMPLETED, "counsellor", "counsellor", 0,
          "Counselling — pre-course orientation", planned=(-1, 11), completed=1,
          form={"reason": "other", "guardian_informed": True,
                "summary": "Walked through the timetable, the lab rules and the exam booking "
                           "process."},
          summary="Oriented."),
        A("u1-fu-01", "u1", "follow-up", ASSIGNED, "counsellor", "counsellor", 1,
          "Follow-up — pending admission documents", planned=(1, 10), due=(1, 18)),
        # --- Pune: MERN Full Stack Morning (Ankit) -----------------------------
        A("pa1-mock-01", "pa1", "mock-interview", COMPLETED, "manager", "ankit.kulkarni", 0,
          "Mock interview — React and state", planned=(-5, 10), completed=5,
          form={"communication": 7, "technical": 8, "confidence": 7, "score": 8,
                "outcome": "ready", "improvements": "Talk through trade-offs."},
          summary="Ready."),
        A("pa1-mock-02", "pa1", "mock-interview", COMPLETED, "manager", "ankit.kulkarni", 2,
          "Mock interview — Node and Express", planned=(-2, 10), completed=2,
          # Communication three of ten on purpose: the seeded rule fires here too.
          form={"communication": 3, "technical": 6, "confidence": 3, "score": 4,
                "outcome": "not_ready", "improvements": "Practise explaining the request cycle."},
          summary="Freezes when asked to explain; practice sessions booked."),
        A("pa1-tech-01", "pa1", "technical-interview", OVERDUE, "ankit.kulkarni", "ankit.kulkarni",
          4, "Technical interview — MongoDB schema design", priority=HIGH,
          planned=(-4, 10), due=(-3, 13)),
        A("pa1-code-01", "pa1", "code-review", COMPLETED, "ankit.kulkarni", "ankit.kulkarni", 6,
          "Code review — task manager app", planned=(-7, 11), completed=7,
          form={"repository_url": "https://github.com/grras-students/mern-task-manager",
                "score": 7, "readability": 7, "correctness": 7, "structure": 7,
                "comments": "<p>Good component boundaries; validate on the server too.</p>"},
          summary="Pass."),
        A("pa1-cap-01", "pa1", CAPSTONE_EVALUATION, UNDER_REVIEW, "manager", "ankit.kulkarni", 8,
          "Capstone evaluation — e-commerce storefront", planned=(-1, 11), completed=1,
          form={"project_title": "E-commerce storefront", "mentor_rating": 7,
                "outcome": "approved", "remarks": "Checkout flow complete; add order history."},
          summary="Recommended for approval."),
        A("pa1-fu-01", "pa1", "follow-up", ASSIGNED, "counsellor", "counsellor", 10,
          "Follow-up — laptop loan agreement", planned=(0, 21), due=(0, 22)),
        A("pa1-warn-01", "pa1", "warning", APPROVED, "manager", "admin", 12,
          "Attendance warning — Friday project sessions", priority=HIGH,
          planned=(-6, 9), completed=6,
          form={"reason": "attendance", "details": "Missed four Friday project sessions in a "
                                                    "row.", "acknowledged_by_student": True},
          summary="Issued and acknowledged.", reviewer="manager",
          note="Issued correctly."),
        A("pa1-doubt-01", "pa1", "doubt-session", ASSIGNED, "ankit.kulkarni", "ankit.kulkarni", 14,
          "Doubt session — JWT refresh tokens", planned=(2, 12), due=(2, 13)),
        A("pa1-fb-01", "pa1", "feedback", COMPLETED, "ankit.kulkarni", "admin", 1,
          "Feedback — helping classmates", priority=LOW, planned=(-3, 13), completed=3,
          form={"body": "Spent the project Friday unblocking two classmates on deployment; "
                        "exactly the attitude the hiring partners look for.",
                "visible_to_student": True},
          summary="Positive."),
        # --- Pune: Data Analytics Evening (Tushar) -----------------------------
        A("pa2-ment-01", "pa2", "mentoring", COMPLETED, "tushar.patel", "tushar.patel", 0,
          "Mentoring — moving from Excel to SQL", planned=(-9, 19), completed=9,
          form={"topic": "From Excel to SQL",
                "summary": "Rebuilt one of the student's Excel reports as a SQL query and a "
                           "Power BI page.", "action_items": "Rebuild two more reports."},
          summary="Two more reports to rebuild."),
        A("pa2-tech-01", "pa2", "technical-interview", COMPLETED, "tushar.patel", "tushar.patel", 2,
          "Technical interview — SQL joins and window functions", planned=(-3, 19), completed=3,
          # Score four of ten — 40 % — on purpose: the seeded rule books a doubt session.
          form={"technical": 4, "problem_solving": 5, "score": 4, "outcome": "needs_practice",
                "improvements": "Window functions."},
          summary="Window functions are not there yet; doubt session follows."),
        A("pa2-fu-01", "pa2", "follow-up", OVERDUE, "counsellor", "counsellor", 4,
          "Follow-up — pending fee receipt", planned=(-6, 18), due=(-5, 20)),
        A("pa2-couns-01", "pa2", "counselling", COMPLETED, "counsellor", "counsellor", 6,
          "Counselling — evening commute", planned=(-1, 18), completed=1,
          form={"reason": "personal", "summary": "Late arrivals are the 17:40 bus; agreed a "
                                                  "ten-minute grace on Tuesdays.",
                "guardian_informed": False},
          summary="Grace agreed."),
        A("pa2-mock-01", "pa2", "mock-interview", MISSED, "manager", "tushar.patel", 8,
          "Mock interview — analytics case study", planned=(-1, 19)),
        A("pa2-pc-01", "pa2", "placement-call", ASSIGNED, "counsellor", "counsellor", 10,
          "Placement call — Capgemini analytics", priority=HIGH, planned=(0, 21), due=(0, 22)),
        A("pa2-hr-01", "pa2", "hr-interview", CANCELLED, "manager", "manager", 12,
          "HR interview — round 1", planned=(2, 18),
          note="Company withdrew the requisition; no interview this month."),
        # --- Pune: DevOps Engineering Weekend, upcoming (Shivani) --------------
        A("pu1-fu-01", "pu1", "follow-up", ASSIGNED, "counsellor", "counsellor", 0,
          "Follow-up — orientation invite", priority=LOW, planned=(2, 10), due=(2, 18)),
    ]
    # fmt: on

    # --- The imported SITP students: five per live SITP batch ----------------
    # Counsellor and manager work only: the imported placeholder trainer is
    # not somebody this stage assigns work to.
    for index, key in enumerate(SITP_KEYS, start=1):
        due_today = index <= 2
        open_ac = bool(index % 2)
        rows += [
            A(
                f"{key}-couns-01",
                key,
                "counselling",
                COMPLETED,
                "counsellor",
                "counsellor",
                0,
                "Counselling — placement readiness",
                planned=(-3 - index, 15),
                completed=3 + index,
                form={
                    "reason": "placement",
                    "summary": "Reviewed the placement timeline and what "
                    "the college expects before the drive.",
                    "commitments": "Resume draft by next week.",
                    "guardian_informed": False,
                },
                summary="Resume draft by next week.",
            ),
            A(
                f"{key}-fu-01",
                key,
                "follow-up",
                ASSIGNED if due_today else OVERDUE,
                "counsellor2",
                "counsellor2",
                1,
                "Follow-up — college NOC for the internship",
                priority=HIGH if due_today else NORMAL,
                planned=(0, 21) if due_today else (-4 - index, 10),
                due=(0, 22) if due_today else (-2 - index, 18),
            ),
            A(
                f"{key}-pc-01",
                key,
                "placement-call",
                COMPLETED,
                "placement",
                "placement",
                2,
                "Placement call — campus drive shortlist",
                planned=(-6 - index, 11),
                completed=6 + index,
                form={
                    "company": "Infosys",
                    "outcome": "ready" if index % 2 else "placed",
                    "notes": "Shortlisted for the campus drive.",
                },
                summary="Shortlisted.",
            ),
            A(
                f"{key}-cg-01",
                key,
                "career-guidance",
                COMPLETED,
                "manager",
                "counsellor",
                3,
                "Career guidance — roles after the programme",
                planned=(-9 - index, 15),
                completed=9 + index,
                form={
                    "reason": "placement",
                    "summary": "Mapped the programme's modules to the "
                    "roles the hiring partners are filling.",
                    "guardian_informed": False,
                },
                summary="Mapped.",
            ),
            A(
                f"{key}-ac-01",
                key,
                "attendance-counselling",
                ASSIGNED if open_ac else COMPLETED,
                "counsellor",
                "counsellor",
                4,
                "Attendance counselling — below 75 %",
                priority=HIGH,
                planned=(2, 15) if open_ac else (-2, 15),
                due=(2, 17) if open_ac else None,
                completed=None if open_ac else 2,
                form=None
                if open_ac
                else {
                    "reason": "attendance",
                    "summary": "Attendance slipped under the threshold "
                    "during the college exam fortnight.",
                    "commitments": "Full attendance this month.",
                    "guardian_informed": True,
                },
                summary="" if open_ac else "Commitment recorded.",
            ),
        ]
    return tuple(rows)


ACTIVITIES: tuple[Act, ...] = _acts()

#: The activities this stage bins, with reasons. The second is restored.
BINNED_ACTIVITY = "a2-fu-04"
RESTORED_ACTIVITY = "a2-doubt-03"


# ---------------------------------------------------------------------------
# Performance reviews and feedback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewSpec:
    """``subject`` is ``("student", batch key, position)`` or ``("trainer",
    local part)``; ``next_review`` is days from today, ``None`` for no date."""

    key: str
    subject: tuple[str, ...]
    status: str
    rating: int
    review_type: str
    next_review: int | None
    summary: str
    strengths: str = ""
    concerns: str = ""
    actions: str = ""


REVIEWS: tuple[ReviewSpec, ...] = (
    ReviewSpec(
        "s-headline",
        ("student", "a2", HEADLINE),
        ReviewStatus.SHARED,
        4,
        ReviewType.MONTHLY,
        -3,
        "Strong month: labs on time, tests above the batch average.",
        strengths="Lab discipline; explains concepts to classmates.",
        actions="Sit the RHCSA before the placement drive.",
    ),
    ReviewSpec(
        "s-a2-3",
        ("student", "a2", 3),
        ReviewStatus.DRAFT,
        2,
        ReviewType.MONTHLY,
        -1,
        "Attendance fine; communication is the gap the mock interview showed.",
        concerns="Cannot yet explain what he can do.",
        actions="Communication practice.",
    ),
    ReviewSpec(
        "s-a2-9",
        ("student", "a2", 9),
        ReviewStatus.SHARED,
        3,
        ReviewType.AD_HOC,
        -6,
        "Ad-hoc review after the weak technical interview.",
        actions="Doubt session on permissions and processes; re-test in two weeks.",
    ),
    ReviewSpec(
        "s-a1-0",
        ("student", "a1", 0),
        ReviewStatus.ACKNOWLEDGED,
        4,
        ReviewType.MONTHLY,
        -10,
        "On track for the evening cohort; IAM to revise.",
        strengths="Consistent.",
    ),
    ReviewSpec(
        "s-a3-2",
        ("student", "a3", 2),
        ReviewStatus.DRAFT,
        5,
        ReviewType.PLACEMENT,
        None,
        "Placement review draft: top of the weekend batch.",
        strengths="Everything.",
    ),
    ReviewSpec(
        "s-a4-0",
        ("student", "a4", 0),
        ReviewStatus.SHARED,
        4,
        ReviewType.QUARTERLY,
        30,
        "Quarter one of the internship: capstone approved.",
        strengths="Rigour.",
    ),
    ReviewSpec(
        "s-pa1-2",
        ("student", "pa1", 2),
        ReviewStatus.DRAFT,
        2,
        ReviewType.AD_HOC,
        None,
        "Draft after the weak mock interview; to discuss with the trainer first.",
        concerns="Freezes under questioning.",
    ),
    ReviewSpec(
        "s-pa2-2",
        ("student", "pa2", 2),
        ReviewStatus.ACKNOWLEDGED,
        3,
        ReviewType.MONTHLY,
        -2,
        "SQL fundamentals fine; window functions and DAX to come.",
        actions="Doubt session booked.",
    ),
    ReviewSpec(
        "s-sitp1-0",
        ("student", "sitp1", 0),
        ReviewStatus.SHARED,
        3,
        ReviewType.MONTHLY,
        20,
        "Steady through the college exam fortnight.",
        strengths="Turns up.",
    ),
    ReviewSpec(
        "s-sitp2-0",
        ("student", "sitp2", 0),
        ReviewStatus.DRAFT,
        3,
        ReviewType.MONTHLY,
        None,
        "Draft for the programme lead.",
        concerns="Attendance dipped in August.",
    ),
    ReviewSpec(
        "t-trainer",
        ("trainer", "trainer"),
        ReviewStatus.ACKNOWLEDGED,
        5,
        ReviewType.QUARTERLY,
        -5,
        "Runs the flagship batch and the RHCSA track; DSRs always in on time.",
        strengths="Preparation; student outcomes.",
        actions="Take on the Udaipur college drive.",
    ),
    ReviewSpec(
        "t-neha.saxena",
        ("trainer", "neha.saxena"),
        ReviewStatus.SHARED,
        4,
        ReviewType.QUARTERLY,
        40,
        "Weekend batch is nearly full on word of mouth.",
        strengths="Project mentoring.",
    ),
    ReviewSpec(
        "t-rohit.kumawat",
        ("trainer", "rohit.kumawat"),
        ReviewStatus.DRAFT,
        3,
        ReviewType.QUARTERLY,
        None,
        "Draft: evening cohort attendance needs watching.",
        concerns="Two registers a week late.",
    ),
    ReviewSpec(
        "t-priya.malhotra",
        ("trainer", "priya.malhotra"),
        ReviewStatus.SHARED,
        4,
        ReviewType.QUARTERLY,
        -12,
        "Internship track producing approved capstones.",
        strengths="Industry contacts.",
    ),
    ReviewSpec(
        "t-ankit.kulkarni",
        ("trainer", "ankit.kulkarni"),
        ReviewStatus.ACKNOWLEDGED,
        4,
        ReviewType.QUARTERLY,
        25,
        "Pune's MERN batch is the centre's best attended.",
        strengths="Friday project sessions.",
    ),
    ReviewSpec(
        "t-shivani.nair",
        ("trainer", "shivani.nair"),
        ReviewStatus.DRAFT,
        3,
        ReviewType.PROBATION,
        None,
        "Probation draft: first fast track completed on time.",
        concerns="Weekend batch timetable still unpublished.",
    ),
)

#: ``(key, subject, batch key or None, body, visible to the subject)``.
FEEDBACK: tuple[tuple[str, tuple[str, ...], str | None, str, bool], ...] = (
    (
        "s-headline",
        ("student", "a2", HEADLINE),
        "a2",
        "Your CI pipeline write-up is the one we now show new students. Thank you.",
        True,
    ),
    (
        "s-a2-3",
        ("student", "a2", 3),
        "a2",
        "The practice sessions are for you, not a punishment — use them.",
        True,
    ),
    (
        "s-a1-0",
        ("student", "a1", 0),
        "a1",
        "Balancing the job and the evening batch well; keep the recordings habit.",
        True,
    ),
    (
        "s-a3-2",
        ("student", "a3", 2),
        "a3",
        "Placement-ready. Trainer to put her forward for the first drive.",
        False,
    ),
    (
        "s-pa1-2",
        ("student", "pa1", 2),
        "pa1",
        "Knows the material; needs to hear himself explain it. Pair him for demos.",
        False,
    ),
    ("s-pa2-2", ("student", "pa2", 2), "pa2", "Good progress from Excel to SQL in a month.", True),
    (
        "t-trainer",
        ("trainer", "trainer"),
        "a2",
        "The Kubernetes lab redesign cut the doubt sessions in half. Well done.",
        True,
    ),
    (
        "t-neha.saxena",
        ("trainer", "neha.saxena"),
        "a3",
        "Weekend batch feedback forms are the best in the centre.",
        True,
    ),
    (
        "t-ankit.kulkarni",
        ("trainer", "ankit.kulkarni"),
        "pa1",
        "Please get the Friday project registers in on the day.",
        True,
    ),
    (
        "t-tushar.patel",
        ("trainer", "tushar.patel"),
        "pa2",
        "The Excel-to-SQL mentoring is exactly what the analytics cohort needed.",
        False,
    ),
)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

#: ``(actor ref, name, filters)`` — the filter vocabulary is the activities
#: page's own (``status``, ``type`` as a slug, ``assignedTo``, ``mine``,
#: ``overdue``); anything else it would drop on load.
SAVED_FILTERS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("counsellor", "Overdue follow-ups", {"status": OVERDUE, "type": "follow-up"}),
    ("counsellor", "My open work", {"mine": True}),
    ("manager", "Awaiting my review", {"status": UNDER_REVIEW}),
    ("manager", "Mock interviews", {"type": "mock-interview"}),
)


@dataclass(frozen=True)
class ExportSpec:
    key: str
    status: str
    requester: str
    report_key: str
    format: str
    #: A stage-4 batch key to scope the job to, if any.
    batch: str | None = None
    #: Days ago it was queued.
    age: int = 0


EXPORTS: tuple[ExportSpec, ...] = (
    ExportSpec("students-csv", ExportStatus.COMPLETED, "manager", "students", ExportFormat.CSV),
    ExportSpec(
        "activities-xlsx", ExportStatus.QUEUED, "counsellor", "work_activities", ExportFormat.XLSX
    ),
    ExportSpec(
        "attendance-pdf",
        ExportStatus.PROCESSING,
        "admin",
        "attendance",
        ExportFormat.PDF,
        batch="a2",
    ),
    # A Pune counsellor asking for a Jaipur batch: the task refuses the scope
    # and writes why into `error`.
    ExportSpec(
        "fees-csv",
        ExportStatus.FAILED,
        "counsellor.pune",
        "fee_payments",
        ExportFormat.CSV,
        batch="a2",
        age=1,
    ),
    ExportSpec(
        "enrolments-xlsx",
        ExportStatus.CANCELLED,
        "manager.pune",
        "enrollments",
        ExportFormat.XLSX,
        age=2,
    ),
)

#: Header spellings the importer accepts, and rows that exercise each of its
#: refusals: no email, a malformed one, a duplicate, an account that already
#: exists, and a cell that looks like a formula. Phones carry no ``+``: the
#: importer reads a leading plus as the start of a formula and refuses the row.
IMPORT_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("Email", "First name", "Last name", "Phone"),
    ("aman.jain@example.com", "Aman", "Jain", "9876501234"),
    ("kirti.rathore@example.com", "Kirti", "Rathore", "9876501235"),
    ("mohit.saini@example.com", "Mohit", "Saini", "9876501236"),
    ("prachi.goyal@example.com", "Prachi", "Goyal", ""),
    ("", "Suraj", "Meena", "9876501237"),
    ("not-an-email", "Tanvi", "Vyas", "9876501238"),
    ("aman.jain@example.com", "Aman", "Jain", "9876501234"),
    ("student@grras.com", "Aarav", "Mehta", "9876501239"),
    ("yash.soni@example.com", "=SUM(A1:A2)", "Soni", "9876501240"),
)


# ---------------------------------------------------------------------------
# Scope: batches, rosters, actors
# ---------------------------------------------------------------------------


@dataclass
class Scope:
    """The batches in play and who is on them, resolved once."""

    batches: dict[str, Batch]
    rosters: dict[str, list[Enrollment]]
    headline: dict[str, Enrollment]
    headline_student: StudentProfile | None


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    if not ctx.showcase_batches:
        raise RuntimeError("No showcase batches yet: run the batches stage first.")

    scope = _timed(ctx, "scope", lambda: _scope(ctx))
    _timed(ctx, "types", lambda: _ensure_types(ctx))
    _timed(ctx, "activities", lambda: _ensure_activities(ctx, scope))
    _timed(ctx, "retire type", lambda: _retire_library_induction(ctx))
    _timed(ctx, "reviews", lambda: _ensure_reviews(ctx, scope))
    _timed(ctx, "feedback", lambda: _ensure_feedback(ctx, scope))
    _timed(ctx, "risk", lambda: _ensure_risk(ctx, scope))
    _timed(ctx, "saved filters", lambda: _ensure_saved_filters(ctx))
    _timed(ctx, "exports", lambda: _ensure_exports(ctx, scope))
    _timed(ctx, "import fixture", lambda: _ensure_import_fixture(ctx))
    _timed(ctx, "recycle bin", lambda: _ensure_recycle_bin(ctx, scope))
    _sweep_on_commit(ctx)


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> Any:
    started = perf_counter()
    result = step()
    ctx.out(f"work/{what}: {perf_counter() - started:.1f}s")
    return result


def _scope(ctx: Context) -> Scope:
    """Showcase batches by stage-4 key, the live SITP batches by code order,
    each with its roster: the active enrolments (the completed cohort ``c1``
    keeps its *completed* ones — its history is the point), the headline
    student's own enrolment set aside so the specs can name him."""
    names = {batch_key(spec.name): spec.key for spec in SPECS}
    batches: dict[str, Batch] = {}
    for key, batch in ctx.showcase_batches.items():
        spec_key = names.get(key)
        if spec_key:
            batches[spec_key] = batch

    live_sitp = sorted(
        (
            batch
            for batch in ctx.imported_batches.values()
            if batch.status == BatchStatus.ACTIVE
            and batch.end_date is not None
            and batch.end_date >= ctx.today
        ),
        key=lambda batch: batch.code,
    )
    for key, batch in zip(SITP_KEYS, live_sitp, strict=False):
        batches[key] = batch

    headline_student = ctx.students[MAIN][0] if ctx.students.get(MAIN) else None
    rosters: dict[str, list[Enrollment]] = {}
    headline: dict[str, Enrollment] = {}
    for key, batch in batches.items():
        if key == "c1":
            rows = list(
                Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.COMPLETED)
                .select_related("student__user", "batch__branch")
                .order_by("pk")
            )
        else:
            rows = [
                row
                for row in ctx.live_enrolments(batch).select_related("batch__branch")
                if row.status == EnrollmentStatus.ACTIVE
            ]
        roster: list[Enrollment] = []
        for row in rows:
            if headline_student is not None and row.student_id == headline_student.pk:
                headline[key] = row
            else:
                roster.append(row)
        rosters[key] = roster

    sitp = "x".join(str(len(rosters[k])) for k in SITP_KEYS if k in rosters) or "none"
    ctx.out(
        f"scope: {len(batches)} batches, "
        f"{sum(len(rows) for rows in rosters.values())} students on the rosters, SITP {sitp}"
    )
    return Scope(
        batches=batches, rosters=rosters, headline=headline, headline_student=headline_student
    )


def _actor(ctx: Context, ref: str, batch: Batch) -> User:
    """Resolve an actor reference for a batch's centre. ``admin``/``manager``/
    ``counsellor`` are the centre's own; anything else is a roster local part.
    A centre without that rung falls back to the superadmin, who may do
    anything the rung could."""
    code = batch.branch.code
    owner: User = ctx.superadmin  # type: ignore[assignment]
    if ref == "owner":
        return owner
    if ref == "admin":
        return ctx.admins.get(code) or owner
    if ref == "manager":
        return ctx.managers.get(code) or ctx.admins.get(code) or owner
    if ref == "counsellor":
        return ctx.counsellors.get(code) or ctx.managers.get(code) or owner
    # The second MAIN counsellor and the placement coordinator are named
    # accounts; Pune has one counsellor, so both fall back to the centre's.
    if ref in ("counsellor2", "placement") and code != MAIN:
        return _actor(ctx, "counsellor", batch)
    user = ctx.users.get(ref)
    if user is None:
        raise RuntimeError(f"Actor {ref!r} is not on this database: run the people stage first.")
    return user


# ---------------------------------------------------------------------------
# Custom types
# ---------------------------------------------------------------------------


def _ensure_types(ctx: Context) -> None:
    owner = ctx.superadmin
    for spec in CUSTOM_TYPES:
        form = _ensure_form(ctx, spec["form_slug"]) if spec["form_slug"] else None
        fields = {k: v for k, v in spec.items() if k not in ("disabled", "form_slug")}
        existing = ActivityType.all_objects.filter(slug=spec["slug"]).first()

        def create(form: FormDefinition | None = form, fields: dict[str, Any] = fields):
            return create_activity_type(actor=owner, form=form, **fields)

        kind = ctx.ensure("activity_type", f"activity type {spec['slug']}", existing, create)
        ctx.activity_types[spec["slug"]] = kind


def _ensure_form(ctx: Context, slug: str) -> FormDefinition:
    """The capstone form: definition, fields, published — or found by slug."""
    owner = ctx.superadmin
    definition = FormDefinition.all_objects.filter(slug=slug).first()
    if definition is None:
        definition = create_definition(
            actor=owner, slug=slug, name="Capstone evaluation", entity=FormEntity.ACTIVITY
        )
        ctx.created("form_definition")
        ctx.out(f"form {slug}: created")
    else:
        ctx.found_existing("form_definition")
        ctx.out(f"form {slug}: found")
    if FormVersion.objects.filter(
        definition=definition, status=FormVersionStatus.PUBLISHED
    ).exists():
        ctx.found_existing("form_version")
    else:
        draft = FormVersion.objects.filter(
            definition=definition, status=FormVersionStatus.DRAFT
        ).first()
        if draft is None:
            draft = create_draft_version(actor=owner, definition=definition)
        set_fields(actor=owner, version=draft, fields=CAPSTONE_FORM_FIELDS)
        publish_version(actor=owner, version=draft)
        ctx.created("form_version")
        ctx.out(f"form {slug}: version {draft.number} published")
    return definition


def _retire_library_induction(ctx: Context) -> None:
    """Disable the induction type *after* its activity exists: the service
    refuses an activity on a disabled type, and a retired type with history
    is the state the catalog screen should show."""
    kind = ctx.activity_types.get(LIBRARY_INDUCTION)
    if kind is None:
        return
    if kind.status == ActivityTypeStatus.DISABLED:
        ctx.out(f"activity type {LIBRARY_INDUCTION}: already disabled")
        return
    update_activity_type(
        actor=ctx.superadmin, activity_type=kind, status=ActivityTypeStatus.DISABLED
    )
    ctx.out(f"activity type {LIBRARY_INDUCTION}: disabled")


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


def _client_key(ctx: Context, key: str) -> str:
    return ctx.tag(f"act/{key}")


def _enrolment_for(scope: Scope, spec: Act) -> Enrollment | None:
    if spec.student == HEADLINE:
        return scope.headline.get(spec.batch)
    roster = scope.rosters.get(spec.batch) or []
    if not roster:
        return None
    return roster[int(spec.student) % len(roster)]


def _moment(ctx: Context, when: tuple[int, int] | None) -> datetime | None:
    if when is None:
        return None
    days, hour = when
    return ctx.at(ctx.days_ahead(days), hour)


def _ensure_activities(ctx: Context, scope: Scope) -> None:
    skipped = 0
    for spec in ACTIVITIES:
        batch = scope.batches.get(spec.batch)
        enrolment = _enrolment_for(scope, spec) if batch is not None else None
        if batch is None or enrolment is None:
            skipped += 1
            continue
        kind = ctx.activity_types.get(spec.type)
        if kind is None:
            raise RuntimeError(f"Activity type {spec.type!r} is missing from the catalog.")

        tag = _client_key(ctx, spec.key)
        existing = Activity.all_objects.filter(client_key=tag).first()
        if existing is not None:
            ctx.found_existing("activity")
            if existing.deleted_at is None:
                _keep_live(ctx, existing, spec)
            continue

        if kind.status != ActivityTypeStatus.ACTIVE:
            # Only the retired induction type can land here, and only when a
            # previous run disabled it after failing to log its activity.
            ctx.out(f"activity {spec.key}: skipped ({spec.type} is disabled)")
            continue

        _create(ctx, spec, kind, batch, enrolment)
        ctx.created("activity")
    if skipped:
        ctx.out(f"activities: {skipped} specs skipped (batch or roster not on this database)")


def _create(
    ctx: Context, spec: Act, kind: ActivityType, batch: Batch, enrolment: Enrollment
) -> None:
    creator = _actor(ctx, spec.creator, batch)
    assignee = _actor(ctx, spec.assignee, batch) if spec.assignee else None
    planned_at = _moment(ctx, spec.planned)
    due_at = _moment(ctx, spec.due)

    activity = create_activity(
        actor=creator,
        student=enrolment.student,
        activity_type=kind,
        enrollment=enrolment,
        title=spec.title,
        assigned_to=assignee,
        planned_at=planned_at,
        due_at=due_at,
        priority=spec.priority,
        client_key=_client_key(ctx, spec.key),
    )
    target = spec.status

    if target == DRAFT:
        _backdate_activity(ctx, activity, spec)
        return

    if target == CANCELLED or (target == REOPENED and spec.reopen_from == CANCELLED):
        if planned_at is not None:
            transition_activity(actor=creator, activity=activity, to_status=PLANNED)
        transition_activity(
            actor=creator, activity=activity, to_status=CANCELLED, note=ctx.note(spec.note)
        )
        if target == REOPENED:
            transition_activity(
                actor=creator, activity=activity, to_status=REOPENED, note=ctx.note(spec.note)
            )
        _backdate_activity(ctx, activity, spec)
        return

    transition_activity(actor=creator, activity=activity, to_status=PLANNED)
    if target == PLANNED:
        _backdate_activity(ctx, activity, spec)
        return

    transition_activity(actor=creator, activity=activity, to_status=ASSIGNED)
    if target in (ASSIGNED, MISSED):
        _backdate_activity(ctx, activity, spec)
        return

    if spec.started or target == IN_PROGRESS:
        transition_activity(actor=assignee, activity=activity, to_status=IN_PROGRESS)
    if target in (IN_PROGRESS, OVERDUE):
        _backdate_activity(ctx, activity, spec)
        return

    # Everything left is completed work: COMPLETED, UNDER_REVIEW, APPROVED,
    # REQUIRES_ACTION, or REOPENED from COMPLETED.
    completer = assignee or creator
    completed_at = ctx.at(ctx.days_ago(spec.completed or 0), (spec.planned or (0, 12))[1], 45)
    complete_activity(
        actor=completer,
        activity=activity,
        form_values=spec.form,
        summary=ctx.note(spec.summary) if spec.summary else None,
        duration_minutes=kind.default_duration_minutes,
        completed_at=completed_at,
    )
    if target in (APPROVED, REQUIRES_ACTION):
        reviewer = _actor(ctx, spec.reviewer, batch)
        review_activity(
            actor=reviewer,
            activity=activity,
            decision="approved" if target == APPROVED else "requires_action",
            note=ctx.note(spec.note),
        )
    elif target == REOPENED:
        transition_activity(
            actor=creator, activity=activity, to_status=REOPENED, note=ctx.note(spec.note)
        )
    _backdate_activity(ctx, activity, spec)


def _backdate_activity(ctx: Context, activity: Activity, spec: Act) -> None:
    """Make a historical activity read as history: created a few days before
    it was planned, reviewed shortly after it was completed, and its trail
    stamped to match. Nothing in the future is touched."""
    anchor = activity.planned_at or activity.completed_at
    if anchor is None or anchor >= ctx.now:
        return
    created_at = anchor - timedelta(days=ctx.rng.randint(1, 4), hours=ctx.rng.randint(0, 6))
    fields: dict[str, Any] = {"created_at": created_at, "updated_at": anchor}
    if activity.completed_at is not None and activity.reviewed_at is not None:
        fields["reviewed_at"] = activity.completed_at + timedelta(hours=ctx.rng.randint(3, 30))
        fields["updated_at"] = fields["reviewed_at"]
    elif activity.completed_at is not None:
        fields["updated_at"] = activity.completed_at
    ctx.backdate(activity, **fields)

    # The trail: creation-time moves at creation time, the completion at its
    # own time, the review after it. History has no service and no
    # `auto_now`, so this is the same queryset update `backdate` is.
    for entry in ActivityHistory.objects.filter(activity=activity).order_by("created_at"):
        if entry.to_status in (COMPLETED, UNDER_REVIEW) and activity.completed_at:
            stamp = activity.completed_at
        elif entry.to_status in (APPROVED, REQUIRES_ACTION) and activity.reviewed_at:
            stamp = activity.reviewed_at
        elif entry.to_status == REOPENED and spec.completed:
            stamp = ctx.at(ctx.days_ago(max(spec.completed - 1, 0)), 10)
        else:
            stamp = created_at
        ActivityHistory.objects.filter(pk=entry.pk).update(created_at=stamp, updated_at=stamp)


def _keep_live(ctx: Context, activity: Activity, spec: Act) -> None:
    """Re-anchor a found open row whose relative dates have gone stale.

    *Assigned*, *planned*, *in progress* and *due today* are statements about
    now. A row made last week with ``due=(0, 22)`` is due last week today,
    and the sweep at the end of this run would (rightly) mark it overdue —
    so the row would drift out of the state the spec promises. When a found
    row is still in its intended open status and its time has passed, the
    time is moved to where the spec says it belongs today. A queryset update,
    like ``backdate``: the service has no verb for it (the API edits these
    two fields with a plain ``PATCH``), and nothing else on the row changes.
    """
    if spec.status not in (PLANNED, ASSIGNED, IN_PROGRESS) or activity.status != spec.status:
        return
    fields: dict[str, Any] = {}
    intended_planned = _moment(ctx, spec.planned)
    intended_due = _moment(ctx, spec.due)
    grace = ctx.now - timedelta(minutes=MISSED_GRACE_MINUTES)
    if (
        spec.status in (PLANNED, ASSIGNED)
        and activity.planned_at is not None
        and activity.planned_at < grace
        and intended_planned is not None
        and intended_planned > activity.planned_at
    ):
        fields["planned_at"] = intended_planned
    if (
        activity.due_at is not None
        and activity.due_at < ctx.now
        and intended_due is not None
        and intended_due > activity.due_at
    ):
        fields["due_at"] = intended_due
    if fields:
        ctx.backdate(activity, **fields)
        ctx.out(f"activity {spec.key}: re-anchored {', '.join(sorted(fields))}")


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def _subject(ctx: Context, scope: Scope, ref: tuple[str, ...]) -> dict[str, Any] | None:
    """``{"student": profile}`` or ``{"trainer": profile}`` for a spec's
    subject, or ``None`` where the roster does not reach (SITP on the test
    database)."""
    if ref[0] == "student":
        _, key, position = ref
        if position == HEADLINE:
            profile = scope.headline_student
        else:
            roster = scope.rosters.get(key) or []
            profile = roster[int(position) % len(roster)].student if roster else None
        return {"student": profile} if profile is not None else None
    user = ctx.users.get(ref[1])
    if user is None:
        return None
    profile = TrainerProfile.objects.filter(user=user).first()
    return {"trainer": profile} if profile is not None else None


def _reviewer_for(ctx: Context, subject: dict[str, Any]) -> User:
    """A manager of the subject's centre, or the admin, or the boss — never
    the subject: ``create_review`` refuses that anyway."""
    profile = subject.get("student") or subject.get("trainer")
    code = profile.branch.code if profile.branch_id else MAIN
    for candidate in (ctx.managers.get(code), ctx.admins.get(code), ctx.superadmin):
        if candidate is not None and candidate.pk != profile.user_id:
            return candidate
    raise RuntimeError("No manager or admin to review with: run the people stage first.")


def _previous_month(today: date) -> tuple[date, date]:
    first_of_this = today.replace(day=1)
    end = first_of_this - timedelta(days=1)
    return end.replace(day=1), end


def _ensure_reviews(ctx: Context, scope: Scope) -> None:
    period_start, period_end = _previous_month(ctx.today)
    skipped = 0
    for spec in REVIEWS:
        subject = _subject(ctx, scope, spec.subject)
        if subject is None:
            skipped += 1
            continue
        tag = ctx.tag(f"review/{spec.key}")
        if PerformanceReview.all_objects.filter(summary__startswith=tag, **subject).exists():
            ctx.found_existing("performance_review")
            continue
        reviewer = _reviewer_for(ctx, subject)
        next_review_at = ctx.days_ahead(spec.next_review) if spec.next_review is not None else None
        review = create_review(
            actor=reviewer,
            period_start=period_start,
            period_end=period_end,
            rating=spec.rating,
            review_type=spec.review_type,
            summary=ctx.tag(f"review/{spec.key}", spec.summary),
            strengths=spec.strengths,
            concerns=spec.concerns,
            actions=spec.actions,
            next_review_at=next_review_at,
            **subject,
        )
        if spec.status != ReviewStatus.DRAFT:
            update_review(review=review, actor=reviewer, status=spec.status)
        # Written in the days after the period closed, not this morning.
        written = ctx.at(period_end + timedelta(days=ctx.rng.randint(2, 9)), 11)
        if written < ctx.now:
            ctx.backdate(review, created_at=written, updated_at=written)
        ctx.created("performance_review")
        ctx.out(f"review {spec.key}: created ({spec.status})")
    if skipped:
        ctx.out(f"reviews: {skipped} specs skipped (subject not on this database)")


def _ensure_feedback(ctx: Context, scope: Scope) -> None:
    for key, ref, batch_ref, body, visible in FEEDBACK:
        subject = _subject(ctx, scope, ref)
        if subject is None:
            continue
        tag = ctx.tag(f"feedback/{key}")
        if Feedback.all_objects.filter(body__startswith=tag, **subject).exists():
            ctx.found_existing("feedback")
            continue
        author = _reviewer_for(ctx, subject)
        row = create_feedback(
            actor=author,
            batch=scope.batches.get(batch_ref) if batch_ref else None,
            body=ctx.tag(f"feedback/{key}", body),
            visible_to_subject=visible,
            **subject,
        )
        written = ctx.at(ctx.days_ago(ctx.rng.randint(1, 20)), ctx.rng.randint(9, 18))
        ctx.backdate(row, created_at=written, updated_at=written)
        ctx.created("feedback")


def _ensure_risk(ctx: Context, scope: Scope) -> None:
    """A verdict for every live enrolment in scope. ``recompute_risk`` is the
    only writer of ``RiskState`` and reads one enrolment at a time, so this
    is one service call per row; the related rows it touches (student,
    batch, trainer) are loaded up front."""
    batch_ids = [batch.pk for batch in scope.batches.values() if batch.status != "completed"]
    enrolments = list(
        Enrollment.objects.live()
        .filter(batch_id__in=batch_ids)
        .select_related("student__user", "batch__trainer__user", "batch__branch", "course")
        .order_by("pk")
    )
    have = set(
        RiskState.objects.filter(enrollment_id__in=[e.pk for e in enrolments]).values_list(
            "enrollment_id", flat=True
        )
    )
    levels: dict[str, int] = {}
    started = perf_counter()
    for index, enrolment in enumerate(enrolments, start=1):
        state = recompute_risk(enrollment=enrolment)
        levels[state.level] = levels.get(state.level, 0) + 1
        if enrolment.pk in have:
            ctx.found_existing("risk_state")
        else:
            ctx.created("risk_state")
        if index % 100 == 0:
            ctx.out(f"risk: {index}/{len(enrolments)} after {perf_counter() - started:.1f}s")
    ctx.out(
        f"risk: {len(enrolments)} enrolments — "
        + ", ".join(f"{level} {count}" for level, count in sorted(levels.items()))
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _ensure_saved_filters(ctx: Context) -> None:
    for ref, name, filters in SAVED_FILTERS:
        user = ctx.users.get(ref)
        if user is None:
            continue
        existing = SavedFilter.objects.filter(
            user=user, screen=ACTIVITIES_SCREEN, name=name
        ).first()

        def create(user: User = user, name: str = name, filters: dict[str, Any] = filters):
            return save_filter(user=user, screen=ACTIVITIES_SCREEN, name=name, filters=filters)

        ctx.ensure("saved_filter", f"saved filter '{name}' for {ref}", existing, create)


def _ensure_exports(ctx: Context, scope: Scope) -> None:
    for spec in EXPORTS:
        tag = ctx.tag(f"export/{spec.key}")
        existing = ExportJob.all_objects.filter(filters__note=tag).first()
        if existing is not None:
            ctx.found_existing("export_job")
            ctx.out(f"export {spec.key}: found ({existing.status})")
            continue
        requester = ctx.users.get(spec.requester)
        if requester is None:
            ctx.out(f"export {spec.key}: skipped ({spec.requester} not on this database)")
            continue
        batch = scope.batches.get(spec.batch) if spec.batch else None
        job = ExportJob.objects.create(
            report_key=spec.report_key,
            format=spec.format,
            filters={
                "batch_id": str(batch.pk) if batch else None,
                "batch_label": batch.code if batch else None,
                "course_id": None,
                "course_label": None,
                "note": tag,
            },
            requested_by=requester,
            status=ExportStatus.QUEUED,
        )
        queued_at = ctx.now - timedelta(days=spec.age, hours=1, minutes=ctx.rng.randint(0, 50))
        if spec.status in (ExportStatus.COMPLETED, ExportStatus.FAILED):
            # The real task, synchronously: it re-derives the requester's
            # scope, writes the file (or the refusal) and tells them.
            run_export(str(job.pk))
            ctx.backdate(job, queued_at=queued_at)
        elif spec.status == ExportStatus.PROCESSING:
            # A worker has picked it up and not finished: the state exists
            # only inside the task, so it is parked here the way stage 9
            # parks a delivery mid-flight.
            ctx.backdate(
                job, status=ExportStatus.PROCESSING, started_at=ctx.now, queued_at=queued_at
            )
        elif spec.status == ExportStatus.CANCELLED:
            # Mirrors `ExportJobCancelView`: no service exists for it.
            ctx.backdate(
                job,
                status=ExportStatus.CANCELLED,
                finished_at=queued_at + timedelta(minutes=3),
                queued_at=queued_at,
            )
        else:
            ctx.backdate(job, queued_at=queued_at)
        job.refresh_from_db()
        if job.status != spec.status:
            raise RuntimeError(
                f"export {spec.key}: expected {spec.status}, got {job.status} ({job.error!r})"
            )
        ctx.created("export_job")
        why = f", {job.error[:60]}" if job.error else ""
        ctx.out(f"export {spec.key}: created ({job.status}{why})")


def _import_fixture_bytes() -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(IMPORT_ROWS)
    return buffer.getvalue().encode("utf-8")


def _ensure_import_fixture(ctx: Context) -> None:
    """The fixture file and its preview row are one thing: the row (found by
    the file's checksum) says the fixture exists, and a file missing from
    storage under a row that exists is put back without being counted — a
    per-process ``MEDIA_ROOT`` (the test settings) or a wiped media volume
    is not a reason to log a second preview."""
    content = _import_fixture_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    previewed = BulkImport.objects.filter(kind=ImportKind.STUDENTS, checksum=checksum).exists()

    if not default_storage.exists(IMPORT_FIXTURE_PATH):
        default_storage.save(IMPORT_FIXTURE_PATH, ContentFile(content))
        ctx.out(f"import fixture {IMPORT_FIXTURE_PATH}: {'restored' if previewed else 'created'}")
    if previewed:
        ctx.found_existing("import_fixture")
        ctx.found_existing("bulk_import")
        return
    ctx.created("import_fixture")

    admin = ctx.admins.get(MAIN) or ctx.superadmin
    run = preview_students(
        actor=admin, uploaded_file=ContentFile(content, name="students-import.csv")
    )
    ctx.created("bulk_import")
    ctx.out(
        f"bulk import preview: {run.valid_count} valid, {run.error_count} with problems "
        f"({run.status})"
    )


# ---------------------------------------------------------------------------
# Recycle bin
# ---------------------------------------------------------------------------


def _ensure_recycle_bin(ctx: Context, scope: Scope) -> None:
    admin: User = ctx.admins.get(MAIN) or ctx.superadmin  # type: ignore[assignment]
    owner: User = ctx.superadmin  # type: ignore[assignment]

    # Two activities: one stays in the bin, the other comes back.
    binned = Activity.all_objects.filter(client_key=_client_key(ctx, BINNED_ACTIVITY)).first()
    if binned is not None:
        if binned.deleted_at is None:
            delete_activity(
                actor=admin,
                activity=binned,
                reason=ctx.note("Logged twice; the other copy is the one being worked."),
            )
            ctx.created("soft_delete")
            ctx.out(f"activity {BINNED_ACTIVITY}: binned")
        else:
            ctx.found_existing("soft_delete")

    restored = Activity.all_objects.filter(client_key=_client_key(ctx, RESTORED_ACTIVITY)).first()
    if restored is not None:
        already = AuditLog.objects.filter(
            action=AuditAction.RECORD_RESTORED, resource_id=str(restored.pk)
        ).exists()
        if restored.deleted_at is not None:
            restore(instance=restored, actor=admin)
            ctx.created("restore")
            ctx.out(f"activity {RESTORED_ACTIVITY}: restored")
        elif already:
            ctx.found_existing("soft_delete")
            ctx.found_existing("restore")
        else:
            delete_activity(
                actor=admin,
                activity=restored,
                reason=ctx.note("Deleted by mistake while tidying drafts."),
            )
            restore(instance=restored, actor=admin)
            ctx.created("soft_delete")
            ctx.created("restore")
            ctx.out(f"activity {RESTORED_ACTIVITY}: binned and restored")

    # Stage 2's disabled custom role, through the role service (refuses a
    # role with holders; this one has none).
    role = Role.all_objects.filter(slug="guest-lecturer").first()
    if role is None:
        ctx.out("role guest-lecturer: skipped (stage 2 has not made it)")
    elif role.deleted_at is not None:
        ctx.found_existing("soft_delete")
    else:
        delete_role(
            actor=owner,
            role=role,
            reason=ctx.note("Guest lecturers are now scheduled through the trainer directory."),
        )
        ctx.roles.pop(role.slug, None)
        ctx.created("soft_delete")
        ctx.out("role guest-lecturer: binned")

    _ensure_binned_requirement(ctx, scope, admin)

    # Stage 9's cancelled guest-lecture notice — only once stage 9 has run.
    notice = Announcement.all_objects.filter(
        title="Guest lecture on Kubernetes security postponed", body__startswith=MARKER
    ).first()
    if notice is None:
        ctx.out("announcement: skipped (stage 9 has not run yet; nothing to bin)")
    elif notice.deleted_at is not None:
        ctx.found_existing("soft_delete")
    else:
        delete_announcement(
            announcement=notice,
            actor=admin,
            reason=ctx.note("Superseded by the rescheduled lecture notice."),
        )
        ctx.created("soft_delete")
        ctx.out("announcement 'Guest lecture…': binned")


def _ensure_binned_requirement(ctx: Context, scope: Scope, admin: User) -> None:
    """A requirement raised here and binned here.

    Not one of stage 6's: that stage finds its rows through
    ``TrainerRequirement.objects``, which hides a binned row, so binning one
    of its four would have stage 6 raise it again on the next full run.
    """
    tag = ctx.tag("req/bin-hdmi")
    requirement = TrainerRequirement.all_objects.filter(details__startswith=tag).first()
    if requirement is None:
        raiser = ctx.users.get("trainer") or ctx.superadmin
        requirement = raise_requirement(
            actor=raiser,
            title="Spare HDMI adapters for Lab 3",
            details=ctx.tag(
                "req/bin-hdmi",
                "Half the students bring laptops without HDMI; four USB-C adapters would "
                "stop the projector queue at the start of every class.",
            ),
            batch=scope.batches.get("a2"),
            needed_by=ctx.days_ahead(7),
        )
        ctx.backdate(requirement, created_at=ctx.at(ctx.days_ago(2), 9, 20))
        ctx.created("requirement")
        ctx.out("requirement 'Spare HDMI adapters': created")
    else:
        ctx.found_existing("requirement")
    if requirement.deleted_at is None:
        delete_requirement(
            requirement=requirement,
            actor=admin,
            reason=ctx.note("Raised twice; the other copy is being tracked."),
        )
        ctx.created("soft_delete")
        ctx.out("requirement 'Spare HDMI adapters': binned")
    else:
        ctx.found_existing("soft_delete")


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


def _sweep_on_commit(ctx: Context) -> None:
    """``mark_overdue_and_missed`` once, after the stage commits.

    It is the beat task's body: it moves every assigned/in-progress activity
    past its due time to *overdue* and every assigned one planned over an
    hour ago and never started to *missed*, as the system actor — the only
    way those two statuses are ever written. It also enqueues the overdue
    automation dispatches with ``.delay()`` directly, which under eager
    Celery would run inside this transaction, so it waits for the commit.
    Registered last: the completions' own automation hooks run first and
    the activities they create (due days from now) are left alone.
    """

    def _sweep() -> None:
        started = perf_counter()
        result = mark_overdue_and_missed()
        ctx.out(
            f"work/sweep: {result['overdue']} overdue, {result['missed']} missed, "
            f"{perf_counter() - started:.1f}s"
        )

    transaction.on_commit(_sweep)


__all__ = [
    "ACTIVITIES",
    "BINNED_ACTIVITY",
    "CAPSTONE_EVALUATION",
    "CUSTOM_TYPES",
    "EXPORTS",
    "FEEDBACK",
    "IMPORT_FIXTURE_PATH",
    "LIBRARY_INDUCTION",
    "PLACEMENT_DRIVE",
    "RESTORED_ACTIVITY",
    "REVIEWS",
    "SAVED_FILTERS",
    "SITP_KEYS",
    "run",
]
