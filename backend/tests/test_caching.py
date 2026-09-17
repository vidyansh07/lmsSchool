"""Application caching (20a): dashboards and overviews for a minute per person,
branding and public settings until changed. Never across people, never past a
write that would make the value a lie.

Performance sweep (Phases 1-19): `auth:matrix`/`auth:permissions` caching,
`template:published`, the `dashboard:student`/`dashboard:trainer` prefixes and
`student:360`'s invalidation. The gate that matters most among these is
`test_revoking_a_permission_is_never_served_stale_to_the_holder` below: a
capability check is never allowed to answer from a version of the cache that
predates the write revoking it.

Phase 21 (TOCTOU hardening): `_forget_published`, `forget_360` and
`on_activity_changed` are all called from *inside* the writer's own
`@transaction.atomic` block, so each now bumps its cache version twice —
immediately, and again via `transaction.on_commit` — the identical double
bump `apps.authorization.services._forget` already used for `auth:roles`.
`TestDoubleBumpClosesTheCommitRace` below proves the second bump is actually
registered and that firing it invalidates whatever a concurrent reader
poisoned during the writer's still-open transaction; the sections after it
close the plain "does this write path invalidate at all" gaps the phase's
own docstring claimed but never tested: every `forget_360` call site, both
`template:published` transitions, and `dashboard:student`/`dashboard:trainer`
per-caller keying.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase as DjangoTestCase

from apps.common import caching


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def test_remember_computes_once_and_forget_moves_on():
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    assert caching.remember("t", ("a",), 60, compute) == {"n": 1}
    assert caching.remember("t", ("a",), 60, compute) == {"n": 1}
    assert caching.remember("t", ("b",), 60, compute) == {"n": 2}
    caching.forget("t")
    assert caching.remember("t", ("a",), 60, compute) == {"n": 3}


@pytest.mark.django_db
def test_the_admin_dashboard_is_held_for_a_minute_per_person(
    api_client_no_csrf, admin_user, unbounded_superadmin, batch
):
    api_client_no_csrf.force_login(admin_user)
    first = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    from apps.batches.models import BatchStatus
    from apps.batches.services import set_batch_status

    set_batch_status(batch=batch, target=BatchStatus.CANCELLED, actor=admin_user)
    again = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    assert again["active_batches"] == first["active_batches"]
    # A different person is never served this person's figures.
    api_client_no_csrf.force_login(unbounded_superadmin)
    theirs = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    assert theirs["active_batches"] == first["active_batches"] - 1


@pytest.mark.django_db
def test_the_fees_overview_forgets_on_every_ledger_write(
    api_client_no_csrf, counsellor_user, enrollment
):
    from apps.fees import services as fees

    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get("/api/v1/fees/overview/").json()["outstanding_total"] == "0.00"
    fees.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="5000")
    assert api_client_no_csrf.get("/api/v1/fees/overview/").json()["outstanding_total"] == "5000.00"


@pytest.mark.django_db
def test_revoking_a_permission_is_never_served_stale_to_the_holder(
    api_client_no_csrf, admin_user, manager_user
):
    """The security-critical gate this phase adds: revoking a role's
    permission through the real write path (`PATCH /api/v1/roles/manager/`,
    never a raw model `.save()`) must be visible to a caller who already
    holds that role on their VERY NEXT request — never served stale from
    `auth:roles`/`auth:matrix`/`auth:permissions` caching for up to their
    TTL, and never merely because `cache.clear()` or a TTL wait happened to
    run first.

    Edits the seeded `manager` SYSTEM role (`manager_user` holds it by kind
    fallback, `custom_role_id` is `None`) rather than building a custom one:
    `update_role` also revokes the session of every holder of the role it
    just edited (`role.users`, the reverse FK from `User.custom_role`), so a
    custom-role holder's very next request would be refused by a dead
    session regardless of whether the capability cache itself was correctly
    invalidated — which would make the assertion below pass even if
    `forget_roles()` had a real bug. `role.users` is empty for the system
    row (nobody's `custom_role` FK points at it), so `manager_user`'s
    session survives this write untouched, and the 403 below is decided by
    caching alone.
    """
    from rest_framework.test import APIClient

    from apps.accounts.roles import ROLE_CAPABILITIES, UserRole

    assert manager_user.custom_role_id is None

    manager_client = APIClient()
    manager_client.force_login(manager_user)
    manager_session_key = manager_client.session.session_key
    assert manager_client.get("/api/v1/dsr/").status_code == 200

    # Warm `auth:matrix`/`auth:permissions` too (this phase's own additions),
    # not only `auth:roles`, so the test would fail if any of the three
    # served a stale answer after the write below.
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get("/api/v1/roles/matrix/").status_code == 200
    assert api_client_no_csrf.get("/api/v1/permissions/").status_code == 200

    granted = sorted(ROLE_CAPABILITIES[UserRole.MANAGER])
    assert "dsr.view_any" in granted
    revoked = api_client_no_csrf.patch(
        "/api/v1/roles/manager/",
        {"permissions": [{"code": code} for code in granted if code != "dsr.view_any"]},
        format="json",
    )
    assert revoked.status_code == 200, revoked.json()

    from django.contrib.sessions.models import Session

    # manager_client's own session, specifically, was not revoked — this
    # write's `revoke_sessions` fan-out found no `custom_role` holders.
    assert Session.objects.filter(session_key=manager_session_key).exists()

    # The SAME already-open session, on its very next request: refused.
    assert manager_client.get("/api/v1/dsr/").status_code == 403


@pytest.mark.django_db
def test_branding_and_public_settings_are_held_until_changed(
    api_client_no_csrf, unbounded_superadmin, admin_user
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    before = api_client_no_csrf.get("/api/v1/branding/").json()
    api_client_no_csrf.patch("/api/v1/branding/", {"brand_color": "#123456"}, format="json")
    after = api_client_no_csrf.get("/api/v1/branding/").json()
    assert after != before

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.get("/api/v1/settings/public/")
    changed = api_client_no_csrf.patch(
        "/api/v1/settings/", {"institution_name": "Grras Pune"}, format="json"
    )
    assert changed.status_code == 200, changed.data
    assert (
        api_client_no_csrf.get("/api/v1/settings/public/").json()["institution_name"]
        == "Grras Pune"
    )


# ---------------------------------------------------------------------------
# Phase 21: the double bump closes the writer-transaction / reader race
# ---------------------------------------------------------------------------
#
# Each test below reproduces the exact race the finding named: a concurrent
# `remember()` call lands *between* the writer's immediate `forget()` and
# that writer's transaction actually committing, so it recomputes from
# not-yet-committed state and caches that stale answer under the
# already-bumped version. A single immediate `forget()` has nothing left to
# invalidate that stale entry once the transaction finishes. Proving the fix
# means proving two things, not one: that a second bump is genuinely
# *registered* via `transaction.on_commit` (not just that the function
# returns without error), and that firing it actually clears the entry the
# race poisoned.


@pytest.mark.django_db
def test_forget_360_closes_the_commit_race():
    from apps.students.student_360 import PREFIX, forget_360

    key = f"{PREFIX}:11111111-1111-1111-1111-111111111111"

    with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with transaction.atomic():
            forget_360("11111111-1111-1111-1111-111111111111")
            # The concurrent reader: recomputes and caches under the version
            # `forget_360`'s immediate call just bumped to, before this
            # transaction (the write forget_360 was called from) commits.
            caching.remember(key, (), 3600, lambda: "stale-mid-transaction")

    assert callbacks, "forget_360 must register a second bump via transaction.on_commit"
    assert (
        caching.remember(key, (), 3600, lambda: "poisoned-still-there") == "stale-mid-transaction"
    )

    for callback in callbacks:
        callback()

    assert caching.remember(key, (), 3600, lambda: "fresh-after-commit") == "fresh-after-commit"


@pytest.mark.django_db
def test_forget_published_closes_the_commit_race():
    from apps.communication.services import _forget_published, _published_cache_key

    key = _published_cache_key("some.template", "email")

    with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with transaction.atomic():
            _forget_published("some.template", "email")
            caching.remember(key, (), 3600, lambda: "stale-mid-transaction")

    assert callbacks, "_forget_published must register a second bump via transaction.on_commit"
    assert (
        caching.remember(key, (), 3600, lambda: "poisoned-still-there") == "stale-mid-transaction"
    )

    for callback in callbacks:
        callback()

    assert caching.remember(key, (), 3600, lambda: "fresh-after-commit") == "fresh-after-commit"


@pytest.mark.django_db
def test_dashboard_activity_completed_forget_closes_the_commit_race():
    from apps.dashboards.receivers import on_activity_changed

    manager_key = caching.key_for("dashboard:manager")
    trainer_key = caching.key_for("dashboard:trainer")

    with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with transaction.atomic():
            on_activity_changed(sender=None, activity=None, event="completed")
            # A concurrent reader of either dashboard, mid-transaction.
            cache.set(manager_key, "stale-manager", 3600)
            cache.set(trainer_key, "stale-trainer", 3600)

    assert callbacks, "on_activity_changed must register a second bump via transaction.on_commit"
    assert cache.get(manager_key) == "stale-manager"
    assert cache.get(trainer_key) == "stale-trainer"

    for callback in callbacks:
        callback()

    # The version moved again, so the *old* keys are simply orphaned (never
    # looked up again) rather than deleted — `key_for` under the new version
    # resolves to a fresh, unset key.
    assert cache.get(caching.key_for("dashboard:manager")) is None
    assert cache.get(caching.key_for("dashboard:trainer")) is None


@pytest.mark.django_db
def test_dashboard_activity_changed_ignores_events_other_than_completed():
    """The guard the fix must not disturb: only `"completed"` bumps anything,
    still true now that the function also touches `transaction.on_commit`."""
    from apps.dashboards.receivers import on_activity_changed

    with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with transaction.atomic():
            on_activity_changed(sender=None, activity=None, event="created")

    assert callbacks == []


# ---------------------------------------------------------------------------
# Phase 21: dashboard:student / dashboard:trainer are keyed per caller
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_student_dashboard_is_never_shared_between_two_students(
    api_client_no_csrf, student_profile, other_student_profile, enrollment
):
    """`enrollment` enrols `student_profile` only; `other_student_profile`
    has none. If `dashboard:student` were ever keyed without the caller's
    own id, the second student's request would come back with the first
    student's (non-empty) course list instead of their own (empty) one."""
    api_client_no_csrf.force_login(student_profile.user)
    mine = api_client_no_csrf.get("/api/v1/dashboard/student/").json()
    assert mine["is_student"] is True
    assert len(mine["courses"]) == 1

    api_client_no_csrf.force_login(other_student_profile.user)
    theirs = api_client_no_csrf.get("/api/v1/dashboard/student/").json()
    assert theirs["courses"] == []


@pytest.mark.django_db
def test_the_trainer_dashboard_is_never_shared_between_two_trainers(
    api_client_no_csrf, trainer_profile, trainer_profile_two, batch, upcoming_batch
):
    """`trainer_profile` teaches `batch`; `trainer_profile_two` teaches the
    separate `upcoming_batch`. A shared `dashboard:trainer` key would leak
    whichever trainer asked first into the second trainer's response."""
    api_client_no_csrf.force_login(trainer_profile.user)
    mine = api_client_no_csrf.get("/api/v1/dashboard/trainer/").json()
    assert {b["id"] for b in mine["batches"]} == {str(batch.pk)}

    api_client_no_csrf.force_login(trainer_profile_two.user)
    theirs = api_client_no_csrf.get("/api/v1/dashboard/trainer/").json()
    assert {b["id"] for b in theirs["batches"]} == {str(upcoming_batch.pk)}


@pytest.mark.django_db
def test_completing_an_activity_forgets_the_trainers_dashboard(
    api_client_no_csrf, admin_user, trainer_profile, student_profile, enrollment
):
    """`apps.dashboards.receivers.on_activity_changed` is the one write path
    this phase actually wired for `dashboard:trainer` — untested until now.
    An activity assigned to this trainer counts toward `work.pending`;
    completing it must be visible on the trainer's very next dashboard read,
    with no `cache.clear()` in between."""
    from apps.work.models import Activity, ActivityStatus, ActivityType
    from apps.work.services import complete_activity

    activity_type = ActivityType.objects.create(
        slug="caching-completable",
        name="Caching completable",
        category="mentoring",
        allowed_creator_roles=["admin", "trainer"],
        allowed_assignee_roles=["trainer"],
        visible_to_student=True,
    )
    activity = Activity.objects.create(
        student=student_profile,
        enrollment=enrollment,
        batch=enrollment.batch,
        branch=enrollment.batch.branch,
        activity_type=activity_type,
        title="Caching completable",
        status=ActivityStatus.ASSIGNED,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    before = api_client_no_csrf.get("/api/v1/dashboard/trainer/").json()
    assert before["work"]["pending"] == 1

    complete_activity(actor=trainer_profile.user, activity=activity)

    after = api_client_no_csrf.get("/api/v1/dashboard/trainer/").json()
    assert after["work"]["pending"] == 0


# ---------------------------------------------------------------------------
# Phase 21: every forget_360() call site actually invalidates student:360
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_marking_attendance_invalidates_the_students_360(
    api_client_no_csrf, admin_user, trainer_profile, student_profile, enrollment, batch
):
    """`apps.attendance.services.mark_attendance` -> `forget_360`. Warms the
    360 cache with "no attendance yet", marks the student present, and reads
    again with no `cache.clear()` — the stale, pre-write percentage must not
    survive the write."""
    from datetime import time, timedelta

    from django.utils import timezone

    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Caching test session",
    )

    url = f"/api/v1/students/{student_profile.pk}/360/"
    api_client_no_csrf.force_login(admin_user)
    before = api_client_no_csrf.get(url).json()
    assert before["attendance_summary"]["has_records"] is False

    register_url = f"/api/v1/sessions/{session.id}/register/"
    marked = api_client_no_csrf.post(
        register_url,
        {"entries": [{"enrollment_id": str(enrollment.id), "status": "present"}]},
        format="json",
    )
    assert marked.status_code == 200, marked.json()

    after = api_client_no_csrf.get(url).json()
    assert after["attendance_summary"]["has_records"] is True
    assert after["attendance_summary"]["attended"] == 1


@pytest.mark.django_db
def test_recording_an_assessment_result_invalidates_the_students_360(
    api_client_no_csrf, admin_user, student_profile, enrollment, batch
):
    """`apps.assessments.services.record_result` -> `forget_360`. Warms the
    real, view-level 360 cache first (the same key `Student360View` reads
    under), then proves the write's `forget_360` call — not a `cache.clear()`
    — is what makes the next read current."""
    from decimal import Decimal

    from django.utils import timezone

    from apps.assessments.models import AssessmentCategory, AssessmentDelivery, AssessmentStatus
    from apps.assessments.services import create_assessment, record_result, set_assessment_status

    assessment = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Caching weekly test",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.EXTERNAL_LINK,
        external_url="https://docs.google.com/forms/d/e/abc/viewform",
        external_provider="Google Forms",
        scheduled_for=timezone.now(),
        duration_minutes=30,
        max_marks=Decimal("20.00"),
        passing_marks=Decimal("8.00"),
    )
    assessment = set_assessment_status(
        assessment=assessment, actor=admin_user, status=AssessmentStatus.PUBLISHED
    )

    url = f"/api/v1/students/{student_profile.pk}/360/"
    api_client_no_csrf.force_login(admin_user)
    before = api_client_no_csrf.get(url).json()
    before_component = {c["key"]: c for c in before["performance"]["components"]}["assessment"]
    assert before_component["value"] is None

    record_result(
        assessment=assessment, enrollment=enrollment, actor=admin_user, marks=Decimal("15")
    )

    after = api_client_no_csrf.get(url).json()
    after_component = {c["key"]: c for c in after["performance"]["components"]}["assessment"]
    assert after_component["value"] == 75.0


@pytest.mark.django_db
def test_grading_an_assignment_submission_invalidates_the_students_360(
    admin_user, student_profile, enrollment, published_course
):
    """`apps.assignments.services.grade_submission` -> `forget_360`.

    Grading does not, by itself, change any of `student_360.build`'s own
    numbers (the `assignments` performance component reads the *submission*
    rate, not the mark — `apps.progress.reports.assignment_progress`), so
    this proves the invalidation directly the same way the mechanism tests
    above do: plant a value under the real `student:360` cache key, call the
    write, and show a stale `remember()` can no longer win.
    """
    from datetime import timedelta
    from decimal import Decimal

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.utils import timezone

    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )
    from apps.students.student_360 import PREFIX

    assignment = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Caching assignment",
        instructions="Do the thing.",
        max_marks=Decimal("50.00"),
        passing_marks=Decimal("25.00"),
        due_at=timezone.now() + timedelta(days=3),
    )
    assignment = set_assignment_status(
        assignment=assignment, actor=admin_user, status=AssignmentStatus.PUBLISHED
    )
    submission = submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("solution.py", b"print('hi')\n", content_type="text/x-python")],
    )

    key = f"{PREFIX}:{student_profile.pk}"
    assert caching.remember(key, (), 3600, lambda: "planted-before-grading") == (
        "planted-before-grading"
    )

    grade_submission(submission=submission, actor=admin_user, marks=Decimal("40"))

    assert caching.remember(key, (), 3600, lambda: "recomputed-after-grading") == (
        "recomputed-after-grading"
    )


# ---------------------------------------------------------------------------
# Phase 21: template:published invalidates on both publish and unpublish
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publishing_a_template_invalidates_resolve_published_template(admin_user):
    from apps.communication import services
    from apps.communication.models import MessageChannel

    template = services.create_template(
        actor=admin_user,
        key="caching.publish.test",
        name="Caching publish test",
        channel=MessageChannel.EMAIL,
        kind="activity.assigned",
    )
    assert (
        services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL) is None
    )

    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Hi {{recipient.name}}",
        body_html="<p>Hi</p>",
        body_text="Hi",
        variables=["recipient.name"],
    )
    version = services.approve_version(actor=admin_user, version=version)
    services.publish_version(actor=admin_user, version=version)

    # No cache.clear() between the write and this read: the 1-hour TTL cache
    # must not still be answering with the pre-publish `None`.
    resolved = services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL)
    assert resolved is not None
    assert resolved.pk == version.pk


@pytest.mark.django_db
def test_opening_a_new_draft_unpublishes_and_invalidates_resolve_published_template(admin_user):
    from apps.communication import services
    from apps.communication.models import MessageChannel

    template = services.create_template(
        actor=admin_user,
        key="caching.unpublish.test",
        name="Caching unpublish test",
        channel=MessageChannel.EMAIL,
        kind="activity.assigned",
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Hi {{recipient.name}}",
        body_html="<p>Hi</p>",
        body_text="Hi",
        variables=["recipient.name"],
    )
    version = services.approve_version(actor=admin_user, version=version)
    services.publish_version(actor=admin_user, version=version)
    template.refresh_from_db()

    # Warm the cache with the published version, exactly as a real send would.
    warm = services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL)
    assert warm is not None

    services.create_draft_version(actor=admin_user, template=template)

    # No cache.clear(): the template is a draft again, and a send must not
    # keep resolving the version that create_draft_version just superseded.
    resolved = services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL)
    assert resolved is None
