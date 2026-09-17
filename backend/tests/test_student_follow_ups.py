"""`POST /students/{id}/follow-ups/` (ERP Phase 17, `USER_JOURNEYS.md` §4.3)
— "Plan a follow-up" on a student's record.

The one thing worth proving here twice, per the phase brief: this is a new
Activity-creation path, the same risk class Phase 9's review caught two real
bypasses in and Phase 15's re-confirmed clean. It must route through the
real `apps.work.services.create_activity`, never a direct model write — so
an assignee outside the follow-up type's `allowed_assignee_roles` is still
refused *through this endpoint*, exactly as it would be through
`POST /activities/`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.work.models import Activity, ActivityType

FOLLOW_UP_SLUG = "follow-up"


def _follow_up_url(student) -> str:
    return f"/api/v1/students/{student.pk}/follow-ups/"


@pytest.fixture
def follow_up_type(db):
    """The real seeded catalog row (`ACTIVITY_CATALOG.md`), not a stand-in —
    the endpoint hardcodes this slug, so the test should exercise the same
    row production does."""
    return ActivityType.objects.get(slug=FOLLOW_UP_SLUG)


@pytest.mark.django_db
def test_a_counsellor_can_plan_a_follow_up(
    api_client_no_csrf, counsellor_user, student_profile, enrollment, follow_up_type
):
    due_at = timezone.now() + timedelta(days=1)
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        _follow_up_url(student_profile),
        {"due_at": due_at.isoformat(), "priority": "high"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["type"]["slug"] == FOLLOW_UP_SLUG
    assert response.data["priority"] == "high"
    assert response.data["assigned_to"]["id"] == str(counsellor_user.pk)
    assert response.data["student"]["id"] == str(student_profile.pk)

    activity = Activity.objects.get(pk=response.data["id"])
    assert activity.enrollment_id == enrollment.pk
    assert activity.created_by_id == counsellor_user.pk


@pytest.mark.django_db
def test_a_trainer_can_plan_a_follow_up_for_their_own_student(
    api_client_no_csrf, trainer_profile, student_profile, enrollment, follow_up_type
):
    """Follow-up's own creator/assignee lists (`ACTIVITY_CATALOG.md`) both
    include `trainer`."""
    api_client_no_csrf.force_login(trainer_profile.user)

    response = api_client_no_csrf.post(
        _follow_up_url(student_profile),
        {"due_at": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["assigned_to"]["id"] == str(trainer_profile.user.pk)


@pytest.mark.django_db
def test_a_manager_planning_a_follow_up_is_refused_self_assignment(
    api_client_no_csrf, manager_user, student_profile, enrollment, follow_up_type
):
    """A manager may *create* a follow-up (the catalog's creator list), but
    is not one of its assignees. This endpoint always self-assigns, so a
    manager calling it must be refused by the real
    `apps.work.services.validate_assignee` — proof this convenience
    endpoint has not quietly grown its own, laxer assignment rule."""
    assert "manager" not in follow_up_type.allowed_assignee_roles
    assert "manager" in follow_up_type.allowed_creator_roles

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _follow_up_url(student_profile),
        {"due_at": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "assigned_to" in response.data["error"]["details"]
    assert not Activity.objects.filter(
        student=student_profile, activity_type=follow_up_type
    ).exists()


@pytest.mark.django_db
def test_planning_a_follow_up_without_a_due_date_is_refused(
    api_client_no_csrf, counsellor_user, student_profile, follow_up_type
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(_follow_up_url(student_profile), {}, format="json")

    assert response.status_code == 400, response.data
    assert "due_at" in response.data["error"]["details"]


@pytest.mark.django_db
def test_a_follow_up_works_for_a_student_not_yet_on_any_batch(
    api_client_no_csrf, counsellor_user, other_student_profile, follow_up_type
):
    """A follow-up may be the *reason* a registration is still pending — it
    must not require an enrolment that does not exist yet."""
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        _follow_up_url(other_student_profile),
        {"due_at": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 201, response.data
    activity = Activity.objects.get(pk=response.data["id"])
    assert activity.enrollment_id is None
    assert activity.branch_id == other_student_profile.branch_id


@pytest.mark.django_db
def test_a_student_outside_the_callers_branch_404s(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, other_branch, other_branch_student
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        _follow_up_url(other_branch_student),
        {"due_at": (timezone.now() + timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 404
