"""The staging administrator provisioning command never bypasses identity checks."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import AccountToken, TokenPurpose, User, UserRole
from apps.organisation.models import Branch

EMAIL = "DeepRatan@GrrasSolutions.In"


@pytest.fixture
def staging_branch(db):
    return Branch.objects.create(code="JAI", name="Jaipur", city="Jaipur")


@pytest.mark.django_db
def test_command_refuses_to_run_outside_staging(settings, staging_branch):
    settings.ENVIRONMENT = "test"

    with pytest.raises(CommandError, match="only runs with the staging"):
        call_command(
            "provision_staging_admin",
            email=EMAIL,
            first_name="DeepRatan",
            last_name="Example",
            branch_code=staging_branch.code,
        )


@pytest.mark.django_db
def test_dry_run_changes_nothing(settings, staging_branch):
    settings.ENVIRONMENT = "staging"
    output = StringIO()

    call_command(
        "provision_staging_admin",
        email=EMAIL,
        first_name="DeepRatan",
        last_name="Example",
        branch_code=staging_branch.code,
        stdout=output,
    )

    assert "no data changed" in output.getvalue()
    assert not User.objects.filter(email__iexact=EMAIL).exists()


@pytest.mark.django_db
def test_apply_creates_a_bounded_app_admin_and_uses_normal_verification(
    settings, staging_branch, django_capture_on_commit_callbacks
):
    settings.ENVIRONMENT = "staging"

    with django_capture_on_commit_callbacks(execute=True):
        call_command(
            "provision_staging_admin",
            email=EMAIL,
            first_name="DeepRatan",
            last_name="Example",
            branch_code=staging_branch.code,
            apply=True,
        )

    user = User.objects.get(email="deepratan@grrassolutions.in")
    assert user.role == UserRole.ADMIN
    assert user.branch == staging_branch
    assert user.custom_role_id is None
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.is_email_verified is False
    assert user.has_usable_password() is False
    assert set(AccountToken.objects.filter(user=user).values_list("purpose", flat=True)) == {
        TokenPurpose.PASSWORD_RESET,
        TokenPurpose.EMAIL_VERIFICATION,
    }
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_repeating_the_command_does_not_duplicate_or_change_the_account(
    settings, staging_branch, django_capture_on_commit_callbacks
):
    settings.ENVIRONMENT = "staging"
    arguments = {
        "email": EMAIL,
        "first_name": "DeepRatan",
        "last_name": "Example",
        "branch_code": staging_branch.code,
        "apply": True,
    }

    with django_capture_on_commit_callbacks(execute=True):
        call_command("provision_staging_admin", **arguments)
    messages_after_creation = len(mail.outbox)

    call_command("provision_staging_admin", **arguments)

    assert User.objects.filter(email__iexact=EMAIL).count() == 1
    assert len(mail.outbox) == messages_after_creation


@pytest.mark.django_db
def test_existing_mismatched_account_is_never_silently_promoted(settings, staging_branch):
    settings.ENVIRONMENT = "staging"
    user = User.objects.create_user(
        email=EMAIL,
        first_name="DeepRatan",
        last_name="Example",
        role=UserRole.STUDENT,
        branch=staging_branch,
    )

    with pytest.raises(CommandError, match="Nothing was changed"):
        call_command(
            "provision_staging_admin",
            email=EMAIL,
            first_name="DeepRatan",
            last_name="Example",
            branch_code=staging_branch.code,
            apply=True,
        )

    user.refresh_from_db()
    assert user.role == UserRole.STUDENT
