"""Trainer CRUD and self-service profile editing."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.trainers.models import TrainerProfile

TRAINERS_URL = "/api/v1/trainers/"
ME_URL = "/api/v1/trainers/me/"


@pytest.mark.django_db
def test_admin_creates_trainer_with_account_and_profile(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        TRAINERS_URL,
        {
            "email": "new.trainer@example.test",
            "first_name": "New",
            "last_name": "Trainer",
            "profile": {
                "professional_title": "Python Trainer",
                "skills": ["Python", "Django"],
                "years_of_experience": 6,
            },
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trainer_id"].startswith("GRS-T-")
    assert body["skills"] == ["Python", "Django"]

    user = User.objects.get(email="new.trainer@example.test")
    assert user.role == "trainer"
    assert TrainerProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_trainer_reads_and_updates_own_profile(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(ME_URL).json()["trainer_id"] == trainer_profile.trainer_id

    response = api_client_no_csrf.patch(
        ME_URL,
        {"bio": "Fifteen years teaching Linux.", "years_of_experience": 15},
        format="json",
    )
    assert response.status_code == 200
    trainer_profile.refresh_from_db()
    assert trainer_profile.years_of_experience == 15


@pytest.mark.django_db
def test_skills_are_deduplicated_and_bounded(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        ME_URL, {"skills": ["Linux", "linux", "  Linux  ", "Bash"]}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["skills"] == ["Linux", "Bash"]

    too_many = api_client_no_csrf.patch(
        ME_URL, {"skills": [f"skill-{index}" for index in range(40)]}, format="json"
    )
    assert too_many.status_code == 400


@pytest.mark.django_db
def test_professional_links_must_be_https_and_known_keys(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)

    assert (
        api_client_no_csrf.patch(
            ME_URL, {"professional_links": {"linkedin": "https://example.test/in/x"}}, format="json"
        ).status_code
        == 200
    )

    for payload in (
        {"linkedin": "http://example.test/in/x"},
        {"linkedin": "javascript:alert(1)"},
        {"myspace": "https://example.test"},
    ):
        response = api_client_no_csrf.patch(ME_URL, {"professional_links": payload}, format="json")
        assert response.status_code == 400, payload


@pytest.mark.django_db
def test_trainer_update_is_audited(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.patch(ME_URL, {"expertise": "Networking"}, format="json")
    entry = AuditLog.objects.filter(action=AuditAction.TRAINER_UPDATED).first()
    assert entry is not None
    assert entry.context["changed_fields"] == ["expertise"]


@pytest.mark.django_db
def test_admin_can_filter_trainers_by_skill_and_availability(
    api_client_no_csrf, admin_user, trainer_profile
):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{TRAINERS_URL}?skill=Linux").json()["count"] == 1
    assert api_client_no_csrf.get(f"{TRAINERS_URL}?skill=Cobol").json()["count"] == 0
    assert (
        api_client_no_csrf.get(f"{TRAINERS_URL}?is_accepting_assignments=true").json()["count"] == 1
    )


@pytest.mark.django_db
def test_admin_can_set_trainer_availability(api_client_no_csrf, admin_user, trainer_profile):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"{TRAINERS_URL}{trainer_profile.pk}/", {"is_accepting_assignments": False}, format="json"
    )
    assert response.status_code == 200
    trainer_profile.refresh_from_db()
    assert trainer_profile.is_accepting_assignments is False


@pytest.mark.django_db
def test_non_trainer_cannot_use_the_trainer_self_endpoint(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(ME_URL).status_code == 403
