"""`GET /students/{id}/360/` (ERP Phase 11, ADR-09/10/11).

Three things this suite exists to prove, in order of how easy they are to get
wrong by accident:

1. Permission is exactly `StudentActivityListView`'s/`StudentTimelineView`'s
   rule, reused rather than reinvented — a cross-branch id 404s, a
   same-branch classmate a student may not read 403s.
2. The response cost does not grow with how much the student has going on —
   `API_CONTRACTS.md`'s "query count asserted flat".
3. The 1-minute cache is keyed on `(student, viewer scope)`, not just the
   student — the one genuinely security-relevant piece of an otherwise
   ordinary GET. A caller with a *narrower* view of the same student must
   never be served a *broader* caller's cached response, or vice versa.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _url(student) -> str:
    return f"/api/v1/students/{student.pk}/360/"


def _make_activity_type(**overrides):
    from apps.work.models import ActivityType

    defaults = {
        "slug": f"s360-{ActivityType.objects.count()}",
        "name": "360 Test Activity",
        "category": "mentoring",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer", "counsellor"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _add_activities(*, actor, student, enrollment, activity_type, count: int) -> None:
    from apps.work import services as work_services

    for _ in range(count):
        work_services.create_activity(
            actor=actor, student=student, activity_type=activity_type, enrollment=enrollment
        )


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_student_360_shape(api_client_no_csrf, admin_user, student_profile, enrollment, batch):
    response = _client(admin_user).get(_url(student_profile))
    assert response.status_code == 200
    body = response.json()

    assert body["profile"]["id"] == str(student_profile.pk)
    assert body["enrollment"]["id"] == str(enrollment.pk)
    assert body["batch"] == {
        "id": str(batch.pk),
        "code": batch.code,
        "name": batch.name,
        "status": batch.status,
    }
    assert body["trainer"]["name"]
    # `enrol_student` in the fixture is called with `actor=admin_user`; the
    # counsellor stand-in (see `student_360`'s module docstring) is the
    # enrolment's `created_by`.
    assert body["counsellor"]["id"] == str(admin_user.pk)
    # `published_course` (the `batch` fixture's course) ships two published
    # lessons; `course_progress` counts published lessons only (`services.py`),
    # so a fresh enrolment with none completed is 2 total / 0 done, not 0/0.
    assert body["progress"]["total_lessons"] == 2
    assert body["progress"]["completed_lessons"] == 0
    # No attendance has been marked yet on this fresh enrolment: a real,
    # unremarkable zero state, not `null`/`NaN`/a crash.
    assert body["attendance_summary"] == {
        "percent": None,
        "attended": 0,
        "total_sessions": 0,
        "has_records": False,
    }
    # Real ADR-10 performance data (Phase 12) — a fresh enrolment has touched
    # nothing but its two published lessons (0% done), so `progress` is the
    # only measured component and `overall_score` is exactly its value.
    performance = body["performance"]
    assert performance["overall_score"] == 0.0
    components_by_key = {c["key"]: c for c in performance["components"]}
    assert set(components_by_key) == {
        "attendance",
        "assessment",
        "assignments",
        "projects",
        "progress",
        "activity",
    }
    assert components_by_key["progress"]["value"] == 0
    assert components_by_key["progress"]["weight"] == 1.0
    assert components_by_key["progress"]["contribution"] == 0.0
    for key in ("attendance", "assessment", "assignments", "projects", "activity"):
        assert components_by_key[key]["value"] is None
        assert components_by_key[key]["contribution"] is None
        assert components_by_key[key]["sources"] == []
    # Still placeholders Phases 13/14 fill in — the correct *shape*, neutral data.
    assert body["risk"] == {"level": "none", "triggered": []}
    assert body["next_actions"] == []
    assert body["fee_status"] == student_profile.fee_status
    assert body["counts"] == {
        "activities_open": 0,
        "activities_overdue": 0,
        "assessments": 0,
        "assignments": 0,
        "projects": 0,
    }
    assert body["recent_activities"] == []


def test_student_360_reflects_completed_scored_activities_in_performance(
    api_client_no_csrf, admin_user, student_profile, enrollment, trainer_profile
):
    """ERP Phase 12: the real performance engine, not the placeholder, once
    the student has something scored on this enrolment."""
    from decimal import Decimal

    from django.utils import timezone

    from apps.work.models import Activity, ActivityStatus, ActivityType

    activity_type = ActivityType.objects.create(
        slug="s360-scored",
        name="Scored Mock Interview",
        category="interview",
        allowed_creator_roles=["admin", "superadmin", "manager", "trainer"],
        allowed_assignee_roles=["trainer"],
        performance_weight=Decimal("1.00"),
    )
    Activity.objects.create(
        student=student_profile,
        enrollment=enrollment,
        batch=enrollment.batch,
        branch=enrollment.batch.branch,
        activity_type=activity_type,
        title="Scored Mock Interview",
        status=ActivityStatus.COMPLETED,
        created_by=admin_user,
        performed_by=trainer_profile.user,
        score=Decimal("72"),
        max_score=Decimal("90"),
        completed_at=timezone.now(),
    )

    response = _client(admin_user).get(_url(student_profile))
    assert response.status_code == 200
    body = response.json()

    performance = body["performance"]
    # progress (0%, untouched lessons) and activity (72/90*100 = 80%),
    # equal default weights: (0 + 80) / 2 = 40.0 — no longer the placeholder.
    assert performance["overall_score"] == 40.0
    components_by_key = {c["key"]: c for c in performance["components"]}
    activity_component = components_by_key["activity"]
    assert activity_component["value"] == 80.0
    assert len(activity_component["sources"]) == 1
    source = activity_component["sources"][0]
    assert source["type"] == "Scored Mock Interview"
    assert source["score"] == 80.0
    assert source["trainer"] == trainer_profile.user.full_name


def test_student_360_without_an_enrollment_degrades_to_neutral_values(
    api_client_no_csrf, admin_user, student_profile
):
    """A student who has never been enrolled anywhere is a real state, not a
    crash — every enrolment-derived field is `null`/`0`, never `undefined`,
    `NaN` or a 500."""
    response = _client(admin_user).get(_url(student_profile))
    assert response.status_code == 200
    body = response.json()
    assert body["enrollment"] is None
    assert body["batch"] is None
    assert body["trainer"] is None
    assert body["counsellor"] is None
    assert body["progress"] is None
    assert body["attendance_summary"]["has_records"] is False
    # No enrolment to compute a performance picture from: the inert
    # placeholder shape, not an error.
    assert body["performance"] == {"components": [], "overall_score": None}
    assert body["counts"] == {
        "activities_open": 0,
        "activities_overdue": 0,
        "assessments": 0,
        "assignments": 0,
        "projects": 0,
    }


# ---------------------------------------------------------------------------
# Permission — exactly the sibling endpoints' rule, reused
# ---------------------------------------------------------------------------


def test_a_caller_who_cannot_see_the_student_at_all_gets_a_404(
    admin_user, student_profile, other_branch_student
):
    response = _client(student_profile.user).get(_url(other_branch_student))
    assert response.status_code == 404


def test_a_student_cannot_read_a_same_branch_classmates_360(student_profile, other_student_profile):
    response = _client(student_profile.user).get(_url(other_student_profile))
    assert response.status_code == 403


def test_a_student_reads_their_own_360(student_profile):
    response = _client(student_profile.user).get(_url(student_profile))
    assert response.status_code == 200


def test_a_manager_reads_a_same_branch_student(manager_user, student_profile):
    response = _client(manager_user).get(_url(student_profile))
    assert response.status_code == 200


def test_a_manager_cannot_reach_another_branchs_student(manager_user, other_branch_student):
    response = _client(manager_user).get(_url(other_branch_student))
    assert response.status_code == 404


def test_a_trainer_who_does_not_teach_the_students_batch_gets_a_403(
    trainer_profile_two, student_profile, enrollment
):
    """`trainer_profile_two` teaches nothing this student is enrolled on, but
    shares the student's branch (both created via `admin_user`), so
    `reachable_students` (branch only) still resolves the record — the
    refusal is `can_view_student`'s audience question, same as
    `test_timeline.py::test_a_caller_in_the_same_branch_without_audience_gets_a_403`
    for the sibling endpoint: a same-branch caller without audience gets a
    403, not a 404 that would only apply to a different branch entirely."""
    response = _client(trainer_profile_two.user).get(_url(student_profile))
    assert response.status_code == 403


def test_the_trainer_teaching_the_batch_reads_the_student(
    trainer_profile, student_profile, enrollment
):
    response = _client(trainer_profile.user).get(_url(student_profile))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Query count asserted flat
# ---------------------------------------------------------------------------


def test_student_360_flat(api_client_no_csrf, admin_user, student_profile, enrollment, batch):
    """Same endpoint, many times the related data, same query cost."""
    activity_type = _make_activity_type()
    client = _client(admin_user)
    url = _url(student_profile)

    # `risk` (ERP Phase 13) computes and stores a `RiskState` on this
    # enrolment's very first read (`apps.performance.services.risk_state_for`)
    # — a one-time cost, not a per-request one. Warmed here, before either
    # measurement, so both `measure()` calls below hit the cheap
    # "already computed" path and this test keeps proving what it says: cost
    # does not grow with data volume, not "a cold cache is as cheap as a warm
    # one".
    cache.clear()
    client.get(url)

    def measure() -> int:
        cache.clear()
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url)
        assert response.status_code == 200
        return len(captured.captured_queries)

    _add_activities(
        actor=admin_user,
        student=student_profile,
        enrollment=enrollment,
        activity_type=activity_type,
        count=2,
    )
    small = measure()

    _add_activities(
        actor=admin_user,
        student=student_profile,
        enrollment=enrollment,
        activity_type=activity_type,
        count=25,
    )
    large = measure()

    assert large == small, f"{small} queries for a few activities, {large} for many"


# ---------------------------------------------------------------------------
# Cache: keyed on (student, viewer scope) — never just the student
# ---------------------------------------------------------------------------


def test_viewer_scope_key_distinguishes_every_tier_but_not_identical_peers(
    admin_user, manager_user, trainer_profile, student_profile, branch, other_branch_manager
):
    from apps.accounts.models import User, UserRole
    from apps.students.student_360 import viewer_scope_key

    admin_key = viewer_scope_key(admin_user)
    manager_key = viewer_scope_key(manager_user)
    trainer_key = viewer_scope_key(trainer_profile.user)
    student_key = viewer_scope_key(student_profile.user)
    other_branch_key = viewer_scope_key(other_branch_manager)

    # Four different scope tiers (and a manager in a different branch) never
    # collide with one another.
    assert len({admin_key, manager_key, trainer_key, student_key, other_branch_key}) == 5

    # A second manager in the *same* branch is the same effective view, so it
    # is allowed (not required elsewhere, but allowed here) to share a key.
    second_manager = User.objects.create_user(
        email="second-manager@example.test",
        password="Str0ng-Passphrase!42",
        first_name="Second",
        last_name="Manager",
        role=UserRole.MANAGER,
        branch=branch,
    )
    assert viewer_scope_key(second_manager) == manager_key

    # Two different trainers never share a key even if, coincidentally, they
    # taught the same branch — their reach is their own taught batches.
    from apps.trainers.services import create_trainer

    other_trainer = create_trainer(
        email="second-trainer@example.test",
        first_name="Second",
        last_name="Trainer",
        actor=admin_user,
        password="Str0ng-Passphrase!42",
        send_invitation=False,
    )
    assert viewer_scope_key(other_trainer.user) != trainer_key


def test_a_lower_privilege_cached_view_is_never_served_to_a_higher_privilege_caller(
    manager_user, trainer_profile, student_profile, batch, enrollment
):
    """`notes` is administrator-only (`AdminStudentProfileSerializer` only).
    A trainer holds no `student.view_any` at all, so their profile serializer
    omits the field entirely — a real, observable difference in shape driven
    by scope tier, not just by value. Warming the cache with the *narrower*
    view first and asking the *broader* one must not serve the narrow one's
    cached (notes-less) response.
    """
    student_profile.notes = "Confidential counsellor note."
    student_profile.save(update_fields=["notes"])
    cache.clear()
    url = _url(student_profile)

    trainer_first = _client(trainer_profile.user).get(url)
    assert trainer_first.status_code == 200
    assert "notes" not in trainer_first.json()["profile"]

    manager_second = _client(manager_user).get(url)
    assert manager_second.status_code == 200
    assert manager_second.json()["profile"]["notes"] == "Confidential counsellor note."


def test_a_higher_privilege_cached_view_is_never_served_to_a_lower_privilege_caller(
    manager_user, trainer_profile, student_profile, batch, enrollment
):
    """The same proof, warmed in the opposite order."""
    student_profile.notes = "Confidential counsellor note."
    student_profile.save(update_fields=["notes"])
    cache.clear()
    url = _url(student_profile)

    manager_first = _client(manager_user).get(url)
    assert manager_first.status_code == 200
    assert manager_first.json()["profile"]["notes"] == "Confidential counsellor note."

    trainer_second = _client(trainer_profile.user).get(url)
    assert trainer_second.status_code == 200
    assert "notes" not in trainer_second.json()["profile"]
