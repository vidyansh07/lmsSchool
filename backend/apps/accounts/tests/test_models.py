"""Unit tests for the custom user model and manager."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from apps.accounts.models import User, UserRole

PASSWORD = "correct-horse-battery-staple"


@pytest.mark.django_db
def test_email_is_normalised_and_lowercased():
    user = User.objects.create_user(
        email="  Mixed.Case@Example.TEST ", password=PASSWORD, first_name="Mix"
    )
    assert user.email == "mixed.case@example.test"


@pytest.mark.django_db
def test_duplicate_email_is_rejected_case_insensitively():
    User.objects.create_user(email="dup@example.test", password=PASSWORD, first_name="One")
    with pytest.raises((IntegrityError, ValidationError)):
        User.objects.create_user(email="DUP@EXAMPLE.TEST", password=PASSWORD, first_name="Two")


@pytest.mark.django_db
def test_password_is_hashed_never_stored_in_clear():
    user = User.objects.create_user(email="hash@example.test", password=PASSWORD, first_name="Hash")
    assert user.password != PASSWORD
    assert user.check_password(PASSWORD)


@pytest.mark.django_db
def test_default_role_is_student():
    user = User.objects.create_user(email="role@example.test", password=PASSWORD, first_name="Role")
    assert user.role == UserRole.STUDENT
    assert user.is_student_role and not user.is_admin_role


@pytest.mark.django_db
def test_superuser_gets_admin_role_and_staff_flags():
    user = User.objects.create_superuser(
        email="root@example.test", password=PASSWORD, first_name="Root"
    )
    assert user.is_superuser and user.is_staff
    assert user.role == UserRole.ADMIN
    assert user.is_admin_role


@pytest.mark.django_db
def test_email_is_required():
    with pytest.raises(ValueError, match="email address is required"):
        User.objects.create_user(email="", password=PASSWORD, first_name="NoEmail")


@pytest.mark.django_db
def test_invalid_name_is_rejected_by_validation():
    with pytest.raises(ValidationError):
        User.objects.create_user(
            email="badname@example.test", password=PASSWORD, first_name="<script>x</script>"
        )


@pytest.mark.django_db
def test_uuid_primary_key_is_not_sequential():
    first = User.objects.create_user(email="a@example.test", password=PASSWORD, first_name="A")
    second = User.objects.create_user(email="b@example.test", password=PASSWORD, first_name="B")
    assert first.pk != second.pk
    assert len(str(first.pk)) == 36


@pytest.mark.django_db
def test_full_name_composition():
    user = User.objects.create_user(
        email="name@example.test", password=PASSWORD, first_name="Grace", last_name="Hopper"
    )
    assert user.full_name == "Grace Hopper"
    assert user.get_short_name() == "Grace"
