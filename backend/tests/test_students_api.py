"""Student CRUD, self-service profile editing and fee status."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.students.models import StudentProfile

STUDENTS_URL = "/api/v1/students/"
ME_URL = "/api/v1/students/me/"


@pytest.mark.django_db
def test_admin_creates_student_with_account_and_profile(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "New.Student@Example.test",
            "first_name": "New",
            "last_name": "Student",
            "profile": {"city": "Jaipur", "qualification": "bachelors"},
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["student_id"].startswith("GRS-S-")
    assert body["city"] == "Jaipur"

    user = User.objects.get(email="new.student@example.test")
    assert user.role == "student"
    assert StudentProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_student_ids_are_sequential_and_unique(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    ids = []
    for index in range(3):
        response = api_client_no_csrf.post(
            STUDENTS_URL,
            {"email": f"seq{index}@example.test", "first_name": f"Seq{index}"},
            format="json",
        )
        ids.append(response.json()["student_id"])
    assert len(set(ids)) == 3
    assert ids == sorted(ids)


@pytest.mark.django_db(transaction=True)
def test_creating_a_student_is_atomic(admin_user, monkeypatch):
    """If the profile cannot be written, the account must not be left behind."""
    from apps.students import services

    def explode(*args, **kwargs):
        raise RuntimeError("profile write failed")

    monkeypatch.setattr(services, "next_student_id", explode)

    with pytest.raises(RuntimeError):
        services.create_student(
            email="rollback@example.test",
            first_name="Roll",
            actor=admin_user,
            send_invitation=False,
        )

    assert not User.objects.filter(email="rollback@example.test").exists()
    assert not StudentProfile.objects.filter(user__email="rollback@example.test").exists()


@pytest.mark.django_db
def test_student_list_is_paginated_filtered_and_searchable(
    api_client_no_csrf, admin_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(admin_user)

    page = api_client_no_csrf.get(f"{STUDENTS_URL}?page_size=1").json()
    assert page["count"] == 2
    assert len(page["results"]) == 1

    searched = api_client_no_csrf.get(f"{STUDENTS_URL}?search={student_profile.student_id}").json()
    assert searched["count"] == 1

    filtered = api_client_no_csrf.get(f"{STUDENTS_URL}?fee_status=pending").json()
    assert filtered["count"] == 2

    by_city = api_client_no_csrf.get(f"{STUDENTS_URL}?city=Jaipur").json()
    assert by_city["count"] == 1


@pytest.mark.django_db
def test_student_reads_own_profile_without_an_identifier(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(ME_URL).json()
    assert body["student_id"] == student_profile.student_id
    assert body["user"]["email"] == student_profile.user.email


@pytest.mark.django_db
def test_student_updates_permitted_fields(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        ME_URL,
        {"city": "Kota", "emergency_contact_name": "A Relative", "guardian_phone": "+919876543210"},
        format="json",
    )
    assert response.status_code == 200
    student_profile.refresh_from_db()
    assert student_profile.city == "Kota"
    assert student_profile.guardian_phone == "+919876543210"


@pytest.mark.django_db
def test_student_profile_update_is_audited(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    api_client_no_csrf.patch(ME_URL, {"city": "Ajmer"}, format="json")
    entry = AuditLog.objects.filter(action=AuditAction.STUDENT_UPDATED).first()
    assert entry is not None
    assert entry.context["changed_fields"] == ["city"]


@pytest.mark.django_db
def test_invalid_profile_data_is_rejected(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        ME_URL, {"guardian_phone": "not a phone number"}, format="json"
    )
    assert response.status_code == 400
    assert "guardian_phone" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_completion_percentage_reflects_filled_fields(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    before = api_client_no_csrf.get(ME_URL).json()["completion_percent"]
    api_client_no_csrf.patch(
        ME_URL, {"date_of_birth": "2000-01-01", "institution": "Grras"}, format="json"
    )
    after = api_client_no_csrf.get(ME_URL).json()["completion_percent"]
    assert after > before


@pytest.mark.django_db
def test_non_student_cannot_use_the_student_self_endpoint(api_client_no_csrf, trainer):
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(ME_URL).status_code == 403


@pytest.mark.django_db
def test_admin_sets_fee_status_and_it_is_attributed(
    api_client_no_csrf, admin_user, student_profile
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{STUDENTS_URL}{student_profile.pk}/fee-status/",
        {"fee_status": "partial", "note": "first instalment received"},
    )
    assert response.status_code == 200

    student_profile.refresh_from_db()
    assert student_profile.fee_status == "partial"
    assert student_profile.fee_status_updated_by == admin_user
    assert student_profile.fee_status_updated_at is not None

    entry = AuditLog.objects.filter(action=AuditAction.STUDENT_FEE_STATUS_CHANGED).first()
    assert entry.context["from"] == "pending"
    assert entry.context["to"] == "partial"


@pytest.mark.django_db
def test_fee_status_rejects_an_unknown_value(api_client_no_csrf, admin_user, student_profile):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{STUDENTS_URL}{student_profile.pk}/fee-status/", {"fee_status": "free"}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_student_can_read_but_not_change_their_fee_status(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(ME_URL).json()["fee_status"] == "pending"


@pytest.mark.django_db
def test_admin_can_edit_any_student_including_notes(
    api_client_no_csrf, admin_user, student_profile
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"{STUDENTS_URL}{student_profile.pk}/",
        {"city": "Bikaner", "notes": "call back next week"},
        format="json",
    )
    assert response.status_code == 200
    student_profile.refresh_from_db()
    assert student_profile.notes == "call back next week"
