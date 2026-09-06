"""The staging seed command is safe and idempotent."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User, UserRole

SEED_PASSWORD = "Staging-Demo-Passw0rd!"


@pytest.mark.django_db
def test_seed_creates_an_account_for_every_role():
    """§15.5: every role in the model must be signable-in on a demo environment.

    A role nobody can sign in as is a role nobody exercises, and "the manager
    cannot do X" then gets discovered by a manager instead of by a reviewer.
    """
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")

    for role in UserRole.values:
        assert User.objects.filter(role=role).exists(), f"no demo account for {role}"

    assert User.objects.filter(role=UserRole.SUPERADMIN).count() == 1
    assert User.objects.filter(role=UserRole.MANAGER).count() == 1
    assert User.objects.filter(role=UserRole.COUNSELLOR).count() == 1
    assert User.objects.filter(role=UserRole.ADMIN).count() == 2
    assert User.objects.filter(role=UserRole.TRAINER).count() == 5
    assert User.objects.filter(role=UserRole.STUDENT).count() == 20
    # Every seeded address must be undeliverable (RFC 2606 reserved TLD).
    assert User.objects.exclude(email__endswith="@demo.grras.invalid").count() == 0


@pytest.mark.django_db
def test_seed_creates_profiles_for_students_and_trainers():
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile

    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")

    assert StudentProfile.objects.count() == 20
    assert TrainerProfile.objects.count() == 5
    assert all(p.student_id.startswith("GRS-S-") for p in StudentProfile.objects.all())
    assert all(p.trainer_id.startswith("GRS-T-") for p in TrainerProfile.objects.all())
    # Realistic but plainly fake: varied fee states and populated addresses.
    assert StudentProfile.objects.values("fee_status").distinct().count() > 1
    assert StudentProfile.objects.exclude(city="").count() == 20


@pytest.mark.django_db
def test_seeded_profiles_are_not_duplicated_on_a_second_run():
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile

    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")
        call_command("seed_demo_data")

    assert StudentProfile.objects.count() == 20
    assert TrainerProfile.objects.count() == 5


@pytest.mark.django_db
def test_seed_is_idempotent():
    """Running it twice produces the roster once.

    Compared against the roster the command builds rather than a number typed
    here: what this test is about is the *second* run creating nobody, and a
    literal count turns every new demo account into a failure in a test that has
    nothing to say about them.
    """
    from apps.accounts.management.commands.seed_demo_data import build_demo_accounts

    expected = len(build_demo_accounts())

    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")
        after_first_run = User.objects.count()
        call_command("seed_demo_data")

    assert after_first_run == expected
    assert User.objects.count() == expected


@pytest.mark.django_db
def test_seed_refuses_without_a_password():
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": ""}):
        with pytest.raises(CommandError, match="DEMO_USER_PASSWORD"):
            call_command("seed_demo_data")


@pytest.mark.django_db
def test_seed_refuses_a_weak_password():
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": "password"}):
        with pytest.raises(CommandError, match="password policy"):
            call_command("seed_demo_data")


@pytest.mark.django_db
def test_seed_is_blocked_where_demo_data_is_not_allowed(settings):
    settings.ALLOW_DEMO_SEED = False
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        with pytest.raises(CommandError, match="must never run against production"):
            call_command("seed_demo_data")


@pytest.mark.django_db
def test_seeded_admin_can_sign_in(api_client_no_csrf):
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")
    response = api_client_no_csrf.post(
        "/api/v1/auth/login/",
        {"email": "admin@demo.grras.invalid", "password": SEED_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
