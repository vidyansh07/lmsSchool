"""Setting an installation up for GRRAS Jaipur.

GRRAS runs two places in Jaipur: the corporate office and Himmat Nagar. The
command fills those in so an operator does not type them by hand, and it is run
more than once — on a fresh database, on staging, and after a restore. These
tests assert the properties that make it safe to re-run: that it converges,
that it renames the existing centre instead of making a third one, that nothing
already pointing at that centre moves, and that it does not undo an operator's
own decision to close an office.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import User, UserRole
from apps.authorization.models import Role
from apps.organisation.management.commands.setup_grras_jaipur import (
    CORPORATE,
    HIMMAT_NAGAR,
    PLACEMENT_OFFICER,
)
from apps.organisation.models import Branch

pytestmark = pytest.mark.django_db


def run() -> str:
    out = StringIO()
    call_command("setup_grras_jaipur", stdout=out)
    return out.getvalue()


def test_creates_both_jaipur_offices():
    run()

    offices = {branch.code: branch for branch in Branch.objects.all()}
    assert offices[CORPORATE["code"]].name == "GRRAS Corporate"
    assert offices[HIMMAT_NAGAR["code"]].name == "GRRAS Himmat Nagar"
    assert {office.city for office in offices.values()} == {"Jaipur"}


def test_renames_the_migration_centre_rather_than_adding_a_third():
    # The first migration leaves a centre coded MAIN. Every student, batch and
    # payment in an existing database points at it, so it has to be the same
    # row afterwards, not a replacement.
    original = Branch.objects.get(code=CORPORATE["code"])
    original_id = original.pk

    run()

    assert Branch.objects.count() == 2
    corporate = Branch.objects.get(code=CORPORATE["code"])
    assert corporate.pk == original_id, "existing rows would have been orphaned"
    assert corporate.name == "GRRAS Corporate"


def test_a_second_run_changes_nothing():
    run()
    before = {(b.pk, b.code, b.name, b.city) for b in Branch.objects.all()}
    roles_before = Role.all_objects.count()

    second = run()

    assert {(b.pk, b.code, b.name, b.city) for b in Branch.objects.all()} == before
    assert Role.all_objects.count() == roles_before
    assert "created" not in second


def test_leaves_a_closed_office_closed():
    # Deactivating an office is an operational decision. The command corrects
    # typos, not decisions.
    run()
    himmat = Branch.objects.get(code=HIMMAT_NAGAR["code"])
    himmat.is_active = False
    himmat.save(update_fields=["is_active"])

    run()

    himmat.refresh_from_db()
    assert himmat.is_active is False


def test_seeds_the_placement_officer_role(django_user_model):
    django_user_model.objects.create_user(
        email="owner@grras.invalid",
        password="Setup-Test-Passw0rd!",
        role=UserRole.SUPERADMIN,
        first_name="Owner",
        last_name="Grras",
    )

    run()

    role = Role.objects.get(slug=PLACEMENT_OFFICER["slug"])
    assert role.name == "Placement officer"
    codes = set(role.grants.values_list("permission__code", flat=True))
    assert "student.view_any" in codes
    # Placement does not handle money, so the role does not carry fees.
    assert not any(code.startswith("fee.") for code in codes)


def test_reports_rather_than_inventing_an_actor_when_there_is_no_administrator():
    assert not User.objects.filter(role=UserRole.SUPERADMIN).exists()

    output = run()

    assert Role.objects.filter(slug=PLACEMENT_OFFICER["slug"]).count() == 0
    assert "skipped" in output


def test_does_not_make_a_twin_of_a_binned_role(django_user_model):
    django_user_model.objects.create_user(
        email="owner@grras.invalid",
        password="Setup-Test-Passw0rd!",
        role=UserRole.SUPERADMIN,
        first_name="Owner",
        last_name="Grras",
    )
    run()
    role = Role.objects.get(slug=PLACEMENT_OFFICER["slug"])
    role.deleted_at = role.created_at
    role.save(update_fields=["deleted_at"])

    run()

    assert Role.all_objects.filter(slug=PLACEMENT_OFFICER["slug"]).count() == 1
