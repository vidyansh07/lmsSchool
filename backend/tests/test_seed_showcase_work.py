"""Stage 8 of the showcase: activities in every status, reviews, risk, the
reporting side-rooms and the recycle bin — and a second run that creates
nothing.

Runs the command up to and including ``work`` on the empty test database,
twice, inside ``django_capture_on_commit_callbacks`` so the automation
dispatches, the risk notifications and the stage's own overdue/missed sweep
all fire the way they do after a real commit. There are no SITP rows here,
so the twenty SITP specs are proved to be a clean skip.

One test runs the command twice and checks everything, rather than one test
per promise: the four stages in front build a hundred accounts, a catalogue
and fourteen batches, and a run per test would put the file well over its
time budget.
"""

from __future__ import annotations

import os
import re
from io import StringIO
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.authorization.models import Role
from apps.automation.models import AutomationRun
from apps.batches.models import Batch
from apps.common.showcase.context import MARKER, batch_key
from apps.common.showcase.stages.s04_batches import SPECS
from apps.common.showcase.stages.s08_work import (
    ACTIVITIES,
    BINNED_ACTIVITY,
    CAPSTONE_EVALUATION,
    EXPORTS,
    FEEDBACK,
    IMPORT_FIXTURE_PATH,
    LIBRARY_INDUCTION,
    PLACEMENT_DRIVE,
    RESTORED_ACTIVITY,
    REVIEWS,
    SAVED_FILTERS,
)
from apps.enrollments.models import Enrollment
from apps.forms.models import FormVersionStatus
from apps.notifications.models import Notification
from apps.performance.models import (
    Feedback,
    PerformanceReview,
    ReviewStatus,
    RiskLevel,
    RiskState,
)
from apps.reporting.models import BulkImport, ExportJob, ExportStatus, SavedFilter
from apps.requirements.models import TrainerRequirement
from apps.students.models import StudentProfile
from apps.work.access import student_visible_activities
from apps.work.models import (
    Activity,
    ActivityPriority,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
)

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches,work"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = (
    "activity",
    "activity_type",
    "form_definition",
    "form_version",
    "performance_review",
    "feedback",
    "risk_state",
    "saved_filter",
    "export_job",
    "import_fixture",
    "bulk_import",
    "requirement",
    "soft_delete",
    "restore",
)

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)

#: The eighteen catalog slugs (``apps/work/migrations/0002_seed_catalog.py``).
CATALOG = (
    "mock-interview",
    "technical-interview",
    "hr-interview",
    "mentoring",
    "counselling",
    "career-guidance",
    "doubt-session",
    "code-review",
    "resume-review",
    "project-review",
    "placement-call",
    "feedback",
    "parent-meeting",
    "warning",
    "performance-review",
    "follow-up",
    "communication-practice",
    "attendance-counselling",
)


def run(django_capture_on_commit_callbacks) -> str:
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def mine() -> list[Activity]:
    """Every activity this stage logged itself (not the automation's)."""
    return list(Activity.all_objects.filter(client_key__startswith=f"{MARKER}[act/"))


def counts() -> dict[str, int]:
    return {
        "activities": Activity.all_objects.count(),
        "activities_deleted": Activity.all_objects.filter(deleted_at__isnull=False).count(),
        **{
            f"activities_{status}": Activity.objects.filter(status=status).count()
            for status in ActivityStatus.values
        },
        "activity_types": ActivityType.all_objects.count(),
        "automation_runs": AutomationRun.objects.count(),
        "reviews": PerformanceReview.all_objects.count(),
        "feedback": Feedback.all_objects.count(),
        "risk_states": RiskState.objects.count(),
        "saved_filters": SavedFilter.objects.count(),
        "export_jobs": ExportJob.all_objects.count(),
        "bulk_imports": BulkImport.objects.count(),
        "requirements": TrainerRequirement.all_objects.count(),
        "roles_deleted": Role.all_objects.filter(deleted_at__isnull=False).count(),
        "notifications": Notification.objects.count(),
        "users": User.objects.count(),
        "batches": Batch.all_objects.count(),
        "enrolments": Enrollment.all_objects.count(),
        "restores": AuditLog.objects.filter(action=AuditAction.RECORD_RESTORED).count(),
    }


# Deliberately NOT ``transaction=True``. The stage's fan-out — the automation
# dispatches, the risk notifications, its own overdue/missed sweep — all hangs
# off ``transaction.on_commit``, and ``django_capture_on_commit_callbacks``
# runs those callbacks inside an ordinary rolled-back test, which is what that
# fixture is for. A transactional test would buy nothing and cost correctness:
# its teardown truncates every table, and the rows the *migrations* seed (the
# permission catalog, the eighteen activity types, the published forms, the
# automation rules, the message templates, the MAIN branch) come from
# ``RunPython``, not from a ``post_migrate`` receiver, so nothing puts them
# back. The next transactional test to need them then fails with "Unknown
# permission" — passing alone and failing in the suite, which is the worst way
# for a test to be wrong. (``serialized_rollback`` is not the way out either:
# restoring the snapshot collides with the content types the post-flush
# ``post_migrate`` has already recreated.)
@pytest.mark.django_db
def test_work_stage_builds_every_state_and_a_second_run_creates_nothing(
    django_capture_on_commit_callbacks,
):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    table = rows(first)

    # --- The specs that reach this database: no SITP, and no batch stage 4
    # leaves out here (the demo trainer's, which needs the demo roster) -----
    names = {batch_key(spec.name): spec.key for spec in SPECS}
    present = {names[batch_key(b.name)] for b in Batch.objects.all() if batch_key(b.name) in names}
    assert "a2" in present and "c1" in present and "pa1" in present
    reachable = [spec for spec in ACTIVITIES if spec.batch in present]
    assert len(reachable) >= 85
    assert table["activity"] == (len(reachable), 0)
    assert "specs skipped (batch or roster not on this database)" in first
    logged = mine()
    assert len(logged) == len(reachable)
    by_key = {a.client_key.split("[act/", 1)[1].rstrip("]"): a for a in logged}
    assert set(by_key) == {spec.key for spec in reachable}

    # --- All twelve statuses, every priority, every catalog type ------------
    live = [a for a in logged if a.deleted_at is None]
    statuses = {a.status for a in live}
    assert statuses == set(ActivityStatus.values), sorted(set(ActivityStatus.values) - statuses)
    assert {a.priority for a in live} == set(ActivityPriority.values)
    used = set(Activity.all_objects.values_list("activity_type__slug", flat=True))
    assert set(CATALOG) <= used, sorted(set(CATALOG) - used)
    # The spec's target status is where each one landed — the sweep included.
    for spec in reachable:
        assert by_key[spec.key].status == spec.status, (spec.key, by_key[spec.key].status)

    # --- Custom types: active, disabled, requires-review with a pinned form -
    placement = ActivityType.objects.get(slug=PLACEMENT_DRIVE)
    assert placement.status == ActivityTypeStatus.ACTIVE and placement.is_system is False
    induction = ActivityType.objects.get(slug=LIBRARY_INDUCTION)
    assert induction.status == ActivityTypeStatus.DISABLED
    assert Activity.objects.filter(
        activity_type=induction, status=ActivityStatus.COMPLETED
    ).exists()
    capstone = ActivityType.objects.get(slug=CAPSTONE_EVALUATION)
    assert capstone.requires_review is True
    assert capstone.form is not None and capstone.form.slug == CAPSTONE_EVALUATION
    assert capstone.form.versions.filter(status=FormVersionStatus.PUBLISHED).count() == 1
    for activity in Activity.objects.filter(activity_type=capstone).exclude(
        status__in=(ActivityStatus.PLANNED, ActivityStatus.ASSIGNED)
    ):
        assert activity.form_version_id is not None
        assert activity.form_response is not None
        assert activity.score is not None and activity.max_score == 10

    # --- Forms: every completed form-backed activity has a valid response ----
    for activity in live:
        if activity.completed_at is not None and activity.form_version_id:
            assert activity.form_response is not None, activity.title
            assert activity.form_response.values, activity.title
        if activity.form_version_id is None:
            assert activity.form_response_id is None

    # --- The counsellor KPIs: due later today, and already overdue ----------
    today = timezone.localdate()
    due_today = [
        a
        for a in live
        if a.status in (ActivityStatus.ASSIGNED, ActivityStatus.IN_PROGRESS)
        and a.due_at is not None
        and timezone.localtime(a.due_at).date() == today
    ]
    assert len(due_today) >= 6
    assert Activity.objects.filter(status=ActivityStatus.OVERDUE).count() >= 8
    assert Activity.objects.filter(status=ActivityStatus.MISSED).count() >= 3
    # Overdue and missed are the system's: no actor on those history rows.
    for activity in Activity.objects.filter(
        status__in=(ActivityStatus.OVERDUE, ActivityStatus.MISSED)
    ):
        entry = activity.history.order_by("-created_at").first()
        assert entry.actor_id is None and entry.to_status == activity.status

    # --- My work and the student's own view ---------------------------------
    trainer = User.objects.get(email="trainer@grras.com")
    assert Activity.objects.filter(assigned_to=trainer).count() >= 15
    headline = StudentProfile.objects.get(user__email="student@grras.com")
    assert student_visible_activities(headline).count() >= 10
    assert (
        not student_visible_activities(headline)
        .filter(activity_type__visible_to_student=False)
        .exists()
    )

    # --- The automation the weak scores were meant to trigger ----------------
    automated = Activity.objects.filter(automation_run__isnull=False)
    assert automated.filter(activity_type__slug="communication-practice").count() >= 2
    assert automated.filter(activity_type__slug="doubt-session").count() >= 2
    assert automated.filter(activity_type__slug="mock-interview").count() >= 1
    ran = set(AutomationRun.objects.filter(status="ran").values_list("rule__name", flat=True))
    assert "Communication practice after a weak mock" in ran
    assert "Doubt session after a weak technical interview" in ran
    assert "Not ready for placement" in ran
    # An activity a completion spawned points back at it; the ones the risk
    # and attendance triggers spawn have no parent activity to point at.
    spawned = automated.filter(automation_run__trigger="ACTIVITY_COMPLETED")
    assert spawned.count() >= 5
    for activity in spawned:
        assert activity.parent_id is not None

    # --- Performance: reviews, feedback, never a self-review ----------------
    reviews = PerformanceReview.all_objects.filter(summary__startswith=f"{MARKER}[review/")
    assert reviews.count() == len([r for r in REVIEWS if "sitp" not in r.subject[1]])
    assert {r.status for r in reviews} == set(ReviewStatus.values)
    assert reviews.filter(subject_type="trainer").count() == 6
    assert (
        reviews.filter(
            next_review_at__lte=today, status__in=(ReviewStatus.DRAFT, ReviewStatus.SHARED)
        ).count()
        >= 4
    )
    assert reviews.filter(status=ReviewStatus.DRAFT, next_review_at__isnull=True).exists()
    for review in reviews.select_related("student", "trainer", "reviewer"):
        subject = review.student or review.trainer
        assert review.reviewer_id != subject.user_id
        assert review.reviewer.role in ("manager", "admin", "superadmin")
        assert review.snapshot
    feedback = Feedback.all_objects.filter(body__startswith=f"{MARKER}[feedback/")
    assert feedback.count() == len(FEEDBACK)
    assert feedback.filter(subject_type="trainer").count() == 4
    for row in feedback.select_related("student", "trainer"):
        assert row.author_id != (row.student or row.trainer).user_id

    # --- Risk: a verdict for every live enrolment on the showcase batches ----
    showcase = Batch.objects.filter(description__startswith=MARKER).exclude(status="completed")
    live_enrolments = Enrollment.objects.live().filter(batch__in=showcase)
    assert live_enrolments.exists()
    assert (
        RiskState.objects.filter(enrollment__in=live_enrolments).count() == live_enrolments.count()
    )
    levels = set(RiskState.objects.values_list("level", flat=True))
    assert RiskLevel.NONE in levels and len(levels) >= 2, levels

    # --- Reporting: presets, export jobs in every state, the import fixture -
    assert SavedFilter.objects.filter(screen="activities").count() == len(SAVED_FILTERS)
    counsellor = User.objects.get(email="counsellor@grras.com")
    assert SavedFilter.objects.filter(user=counsellor).count() == 2
    jobs = ExportJob.all_objects.filter(filters__note__startswith=f"{MARKER}[export/")
    assert {j.status for j in jobs} == {spec.status for spec in EXPORTS}
    completed = jobs.get(status=ExportStatus.COMPLETED)
    assert completed.file and default_storage.exists(completed.file.name)
    assert completed.size_bytes > 0 and completed.row_count > 0 and completed.checksum
    assert completed.expires_at is not None
    failed = jobs.get(status=ExportStatus.FAILED)
    assert "no longer visible" in failed.error
    assert jobs.get(status=ExportStatus.PROCESSING).started_at is not None
    assert jobs.get(status=ExportStatus.CANCELLED).finished_at is not None
    assert default_storage.exists(IMPORT_FIXTURE_PATH)
    preview = BulkImport.objects.get(kind="students")
    assert (preview.valid_count, preview.error_count, preview.status) == (4, 5, "preview")
    problems = {row["problem"] for row in preview.report["errors"]}
    # The refusal names the cell and the character it starts with, rather than
    # saying only that something somewhere looked like a formula — a message
    # that, on a two-hundred-row file, says neither which cell nor why. The
    # fixture's bad row puts an `=` in the first name.
    assert any("reads as the start of a formula" in problem for problem in problems), problems
    assert "An account with this address already exists." in problems

    # --- Recycle bin --------------------------------------------------------
    binned = by_key[BINNED_ACTIVITY]
    assert binned.deleted_at is not None and binned.delete_reason.startswith(MARKER)
    restored = by_key[RESTORED_ACTIVITY]
    assert restored.deleted_at is None
    assert AuditLog.objects.filter(
        action=AuditAction.RECORD_RESTORED, resource_id=str(restored.pk)
    ).exists()
    role = Role.all_objects.get(slug="guest-lecturer")
    assert role.deleted_at is not None and role.delete_reason.startswith(MARKER)
    requirement = TrainerRequirement.all_objects.get(details__startswith=f"{MARKER}[req/bin-hdmi]")
    assert requirement.deleted_at is not None
    assert "announcement: skipped (stage 9 has not run yet" in first
    assert table["soft_delete"] == (4, 0) and table["restore"] == (1, 0)

    # --- Nothing outside the contract moved ---------------------------------
    assert after_first["users"] == User.objects.count()
    assert SEED_PASSWORD not in first

    # --- The second run: creates nothing, changes no counts -----------------
    second = run(django_capture_on_commit_callbacks)
    table2 = rows(second)
    for label in LABELS:
        created, found = table2[label]
        assert created == 0, (label, table2[label])
        assert found > 0, (label, table2[label])
    assert counts() == after_first
    assert "re-anchored" not in second
    for spec in reachable:
        assert (
            Activity.all_objects.get(client_key=by_key[spec.key].client_key).status == spec.status
        )
    assert SEED_PASSWORD not in second
