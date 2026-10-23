"""The new-student form's own fields: middle name, gender, owner, and the
extra ways to reach somebody.

The one that matters is the last. A student's account email is their login
and is unique across the institute; the extra addresses on the form are
contacts and must never become either of those things. These tests fix that
boundary in place.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.students.models import ContactKind, StudentContact, StudentProfile

pytestmark = pytest.mark.django_db

STUDENTS = "/api/v1/students/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _payload(**overrides):
    body = {
        "email": "ravi@example.test",
        "first_name": "Ravi",
        "middle_name": "Kumar",
        "last_name": "Sharma",
        "phone": "+919876543210",
        "profile": {"gender": "male", "city": "Jaipur"},
    }
    body.update(overrides)
    return body


def test_a_student_is_created_with_a_middle_name_and_a_gender(api_client_no_csrf, admin_user):
    created = _client(admin_user).post(STUDENTS, _payload(), format="json")
    assert created.status_code == 201, created.content

    profile = StudentProfile.objects.get(pk=created.json()["id"])
    assert profile.user.middle_name == "Kumar"
    assert profile.gender == "male"
    # The full name reads first, middle, last — in that order, with no double
    # space when the middle one is absent.
    assert profile.user.full_name == "Ravi Kumar Sharma"


def test_a_name_with_no_middle_part_has_no_double_space(api_client_no_csrf, admin_user):
    created = _client(admin_user).post(STUDENTS, _payload(middle_name=""), format="json")
    profile = StudentProfile.objects.get(pk=created.json()["id"])
    assert profile.user.full_name == "Ravi Sharma"


def test_the_extra_contacts_are_kept_and_the_first_ones_are_not_duplicated(
    api_client_no_csrf, admin_user
):
    created = _client(admin_user).post(
        STUDENTS,
        _payload(
            contacts=[
                # The account's own number, sent again by a form that draws
                # every box: dropped rather than stored twice.
                {"kind": "mobile", "code": "+91", "value": "+919876543210"},
                {"kind": "mobile", "code": "+91", "value": "9829012345"},
                {"kind": "landline", "code": "0141", "value": "2345678"},
                {"kind": "email", "value": "ravi.home@example.test"},
                {"kind": "email", "value": "RAVI@example.test"},
            ]
        ),
        format="json",
    )
    assert created.status_code == 201, created.content
    profile = StudentProfile.objects.get(pk=created.json()["id"])

    stored = {(row.kind, row.value) for row in profile.contacts.all()}
    assert stored == {
        (ContactKind.MOBILE, "9829012345"),
        (ContactKind.LANDLINE, "2345678"),
        (ContactKind.EMAIL, "ravi.home@example.test"),
    }
    # The account's own address, in any casing, is not repeated as a contact.
    assert not profile.contacts.filter(value__iexact="ravi@example.test").exists()


def test_a_contact_email_is_not_a_login(api_client_no_csrf, admin_user):
    """Two students may share a family address. The accounts stay separate,
    and nothing about a contact row makes one of them able to sign in as the
    other."""
    client = _client(admin_user)
    first = client.post(
        STUDENTS,
        _payload(contacts=[{"kind": "email", "value": "family@example.test"}]),
        format="json",
    )
    second = client.post(
        STUDENTS,
        _payload(
            email="priya@example.test",
            first_name="Priya",
            phone="+919876500000",
            contacts=[{"kind": "email", "value": "family@example.test"}],
        ),
        format="json",
    )
    assert first.status_code == 201
    assert second.status_code == 201, second.content
    assert StudentContact.objects.filter(value="family@example.test").count() == 2

    from apps.accounts.models import User

    # And no account was created for the shared address.
    assert not User.objects.filter(email="family@example.test").exists()


def test_the_same_contact_twice_on_one_student_is_stored_once(api_client_no_csrf, admin_user):
    created = _client(admin_user).post(
        STUDENTS,
        _payload(
            contacts=[
                {"kind": "mobile", "code": "+91", "value": "9829012345"},
                {"kind": "mobile", "code": "+91", "value": "9829012345"},
            ]
        ),
        format="json",
    )
    profile = StudentProfile.objects.get(pk=created.json()["id"])
    assert profile.contacts.filter(kind=ContactKind.MOBILE).count() == 1


def test_an_owner_can_be_set_by_the_desk_and_never_by_the_student(
    api_client_no_csrf, admin_user, counsellor_user
):
    created = _client(admin_user).post(
        STUDENTS, _payload(profile={"owner": str(counsellor_user.pk)}), format="json"
    )
    assert created.status_code == 201, created.content
    profile = StudentProfile.objects.get(pk=created.json()["id"])
    assert profile.owner_id == counsellor_user.pk

    # A student editing their own profile cannot reassign themselves.
    refused = _client(profile.user).patch(
        "/api/v1/students/me/", {"owner": str(admin_user.pk)}, format="json"
    )
    assert refused.status_code == 400
    profile.refresh_from_db()
    assert profile.owner_id == counsellor_user.pk


def test_an_unknown_contact_kind_is_refused(api_client_no_csrf, admin_user):
    response = _client(admin_user).post(
        STUDENTS,
        _payload(contacts=[{"kind": "telegram", "value": "@ravi"}]),
        format="json",
    )
    assert response.status_code == 400
