"""`GET /search/?q=&types=` (ERP Phase 11, `API_CONTRACTS.md` "Search and
productivity").

What this suite exists to prove, same ordering as `apps.search.services`'s
own docstring:

1. `q` shorter than two characters is a 400, not a full-table scan.
2. Every source is scoped through that domain's own `visible_*`/capability
   gate — a record outside the caller's authority never appears as a hit,
   even though its own detail route would separately 403/404 it. Proven per
   domain by creating a record inside and a record outside a scoped caller's
   reach and asserting only the in-scope one comes back.
3. The audit row (`search.performed`) never carries the query text or any
   matched id — counts only.
4. The throttle (`search`) actually throttles.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _search(user, q: str, types: str | None = None):
    url = f"/api/v1/search/?q={q}"
    if types:
        url += f"&types={types}"
    return _client(user).get(url)


def _group(body, type_name: str) -> dict:
    return next(group for group in body["groups"] if group["type"] == type_name)


# ---------------------------------------------------------------------------
# `q` length
# ---------------------------------------------------------------------------


def test_a_query_shorter_than_two_characters_is_rejected(admin_user):
    response = _search(admin_user, "a")
    assert response.status_code == 400


def test_an_empty_query_is_rejected(admin_user):
    response = _search(admin_user, "")
    assert response.status_code == 400


def test_a_two_character_query_is_accepted(admin_user):
    response = _search(admin_user, "en")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Every source is scoped through its own domain's visible_*/capability gate
# ---------------------------------------------------------------------------


def test_students_are_scoped_by_branch(manager_user, student_profile, other_branch_student):
    """`student_profile` ("Enrolled Learner") is in the manager's branch;
    `other_branch_student` ("Pooja Pune") is not — title-matching a record
    outside the caller's branch must not surface it as a hit."""
    response = _search(manager_user, "Enrolled")
    assert response.status_code == 200
    group = _group(response.json(), "students")
    assert group["total"] == 1
    assert group["results"][0]["id"] == str(student_profile.pk)

    response = _search(manager_user, "Pooja")
    group = _group(response.json(), "students")
    assert group["total"] == 0
    assert group["results"] == []


def test_a_student_searching_only_ever_finds_themself(student_profile, other_student_profile):
    """A student holds no `student.view_any`; `visible_students` narrows them
    to their own record even though `other_student_profile` ("Other
    Learner") shares the same branch."""
    response = _search(student_profile.user, "Learner")
    assert response.status_code == 200
    group = _group(response.json(), "students")
    assert group["total"] == 1
    assert group["results"][0]["id"] == str(student_profile.pk)


def test_batches_are_scoped_by_branch(manager_user, batch, other_branch_batch):
    """`batch` ("… Morning") is the manager's own branch; `other_branch_batch`
    ("… Pune") belongs to a different centre."""
    response = _search(manager_user, "Morning")
    group = _group(response.json(), "batches")
    assert group["total"] == 1
    assert group["results"][0]["id"] == str(batch.pk)

    response = _search(manager_user, "Pune")
    group = _group(response.json(), "batches")
    assert group["total"] == 0


def test_staff_directory_requires_the_view_any_capability(
    manager_user, trainer_profile, other_branch_manager
):
    """`users` has no dedicated `visible_users` helper — it reproduces
    `UserListCreateView`'s pair of checks (capability, then branch scope).
    A manager holds `user.view_any`, scoped to their own branch, so a
    same-branch account is a hit and a different branch's is not."""
    response = _search(manager_user, "Manager")
    group = _group(response.json(), "users")
    assert group["total"] >= 1
    assert all(hit["id"] != str(other_branch_manager.pk) for hit in group["results"])

    response = _search(manager_user, "Priya")
    group = _group(response.json(), "users")
    assert group["total"] == 0


def test_a_trainer_without_user_view_any_gets_no_staff_hits(trainer_profile, manager_user):
    """A trainer holds no `user.view_any` at all: title-matching a staff
    member's name must not disclose the staff directory to them, even though
    every other source they *do* hold authority over still returns hits."""
    response = _search(trainer_profile.user, "Manager")
    group = _group(response.json(), "users")
    assert group["total"] == 0
    assert group["results"] == []


def test_a_students_own_activities_do_not_leak_through_global_search(
    admin_user, student_profile, enrollment
):
    """`can_read_staff_activities` is False for a student: their own
    activity view is a different, per-instance-scoped surface
    (`GET /students/{id}/activities/`), not this one."""
    from apps.work import services as work_services
    from apps.work.models import ActivityType

    activity_type = ActivityType.objects.create(
        slug="search-test-activity",
        name="Search Test Activity",
        category="mentoring",
        allowed_creator_roles=["admin", "superadmin", "manager", "trainer", "counsellor"],
        allowed_assignee_roles=["trainer"],
        visible_to_student=True,
    )
    work_services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        title="Unique Mentoring Checkpoint",
    )

    staff_response = _search(admin_user, "Unique Mentoring")
    staff_group = _group(staff_response.json(), "activities")
    assert staff_group["total"] == 1

    student_response = _search(student_profile.user, "Unique Mentoring")
    student_group = _group(student_response.json(), "activities")
    assert student_group["total"] == 0
    assert student_group["results"] == []


def test_a_trainer_who_does_not_teach_the_batch_does_not_see_its_activity(
    admin_user, student_profile, enrollment, trainer_profile_two
):
    """`trainer_profile_two` teaches nothing this student is enrolled on —
    the same scoping `visible_activities` enforces on the list endpoint must
    hold here too."""
    from apps.work import services as work_services
    from apps.work.models import ActivityType

    activity_type = ActivityType.objects.create(
        slug="search-test-activity-2",
        name="Search Test Activity Two",
        category="mentoring",
        allowed_creator_roles=["admin", "superadmin", "manager", "trainer", "counsellor"],
        allowed_assignee_roles=["trainer"],
        visible_to_student=True,
    )
    work_services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        title="Second Unique Checkpoint",
    )

    response = _search(trainer_profile_two.user, "Second Unique")
    group = _group(response.json(), "activities")
    assert group["total"] == 0


# ---------------------------------------------------------------------------
# `types=` expands the per-type cap, never the scoping
# ---------------------------------------------------------------------------


def test_types_expands_the_cap_but_never_the_scoping(manager_user, other_branch_student):
    """Expanding `students` past the default 5-hit cap must still exclude a
    record outside the caller's branch."""
    from apps.students.services import create_student

    for i in range(6):
        create_student(
            email=f"expand-{i}@example.test",
            first_name=f"Expand{i}",
            last_name="Cap",
            actor=manager_user,
            password="Str0ng-Passphrase!42",
            send_invitation=False,
        )

    default_response = _search(manager_user, "Cap")
    default_group = _group(default_response.json(), "students")
    assert len(default_group["results"]) == 5
    assert default_group["total"] == 6

    expanded_response = _search(manager_user, "Cap", types="students")
    expanded_group = _group(expanded_response.json(), "students")
    assert len(expanded_group["results"]) == 6


# ---------------------------------------------------------------------------
# Audit: counts only, never the query text or matched ids
# ---------------------------------------------------------------------------


def test_the_audit_row_never_contains_the_query_text(manager_user, student_profile):
    from apps.audit.models import AuditAction, AuditLog

    _search(manager_user, "Enrolled")

    entry = AuditLog.objects.filter(action=AuditAction.SEARCH_PERFORMED).latest("created_at")
    serialised = str(entry.context)
    assert "Enrolled" not in serialised
    assert str(student_profile.pk) not in serialised
    assert entry.context["query_length"] == len("Enrolled")
    assert "hits_by_type" in entry.context


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


def test_search_is_throttled(admin_user, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "search": "2/min",
        },
    }
    # DRF caches the rate table on the throttle class — reset it, the same
    # pattern `test_certificates.py::test_verification_is_throttled` uses.
    # `conftest.py`'s `_reset_rate_limit_counters` snapshots and restores
    # `SearchThrottle.THROTTLE_RATES` around every test, so the tightened
    # rate set here does not leak into whatever runs next.
    from apps.common.throttling import SearchThrottle

    SearchThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    statuses = [_search(admin_user, "en").status_code for _ in range(5)]
    assert 429 in statuses
