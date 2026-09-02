"""Administrator user management: listing, creation, editing, activation."""

from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog

USERS_URL = "/api/v1/users/"


@pytest.mark.django_db
def test_admin_can_list_users_with_pagination(api_client_no_csrf, admin_user, student, trainer):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}?page_size=2").json()
    assert body["count"] == 3
    assert body["page_size"] == 2
    assert len(body["results"]) == 2


@pytest.mark.django_db
def test_user_list_can_be_filtered_by_role(api_client_no_csrf, admin_user, student, trainer):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}?role=trainer").json()
    assert body["count"] == 1
    assert body["results"][0]["email"] == trainer.email


@pytest.mark.django_db
def test_user_list_can_be_filtered_by_status(api_client_no_csrf, admin_user, student):
    student.is_active = False
    student.save()
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{USERS_URL}?is_active=false").json()["count"] == 1
    assert api_client_no_csrf.get(f"{USERS_URL}?is_active=true").json()["count"] == 1


@pytest.mark.django_db
def test_user_search_matches_name_and_email(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{USERS_URL}?search=Sam").json()["count"] == 1
    assert api_client_no_csrf.get(f"{USERS_URL}?search=student@example").json()["count"] == 1
    assert api_client_no_csrf.get(f"{USERS_URL}?search=nothing-matches").json()["count"] == 0


@pytest.mark.django_db
def test_user_search_matches_student_id(api_client_no_csrf, admin_user, student_profile):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}?search={student_profile.student_id}").json()
    assert body["count"] == 1
    assert body["results"][0]["email"] == student_profile.user.email


@pytest.mark.django_db
def test_user_search_matches_trainer_id(api_client_no_csrf, admin_user, trainer_profile):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}?search={trainer_profile.trainer_id}").json()
    assert body["count"] == 1


@pytest.mark.django_db
def test_user_list_can_be_sorted(api_client_no_csrf, admin_user, student, trainer):
    api_client_no_csrf.force_login(admin_user)
    emails = [
        row["email"]
        for row in api_client_no_csrf.get(f"{USERS_URL}?ordering=email").json()["results"]
    ]
    assert emails == sorted(emails)


@pytest.mark.django_db
def test_admin_can_create_a_user_who_sets_their_own_password(
    api_client_no_csrf, admin_user, django_capture_on_commit_callbacks
):
    mail.outbox.clear()
    api_client_no_csrf.force_login(admin_user)
    # The invitation is sent from an on_commit hook, so no email goes out if the
    # account creation rolls back. Capturing the callbacks runs them here.
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client_no_csrf.post(
            USERS_URL,
            {"email": "New.Person@Example.test", "first_name": "New", "role": "trainer"},
        )
    assert response.status_code == 201
    created = User.objects.get(email="new.person@example.test")
    assert created.role == UserRole.TRAINER
    # No usable password, and an invitation link was sent instead.
    assert not created.has_usable_password()
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_create_rejects_a_duplicate_email(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        USERS_URL, {"email": student.email.upper(), "first_name": "Dup", "role": "student"}
    )
    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_admin_can_edit_a_user(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"{USERS_URL}{student.pk}/", {"first_name": "Samuel"}, format="json"
    )
    assert response.status_code == 200
    student.refresh_from_db()
    assert student.first_name == "Samuel"


@pytest.mark.django_db
def test_role_change_is_audited_separately(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(f"{USERS_URL}{student.pk}/", {"role": "trainer"}, format="json")
    entry = AuditLog.objects.filter(action=AuditAction.USER_ROLE_CHANGED).first()
    assert entry is not None
    assert entry.context["from"] == "student"
    assert entry.context["to"] == "trainer"


@pytest.mark.django_db
def test_admin_can_deactivate_and_reactivate(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    url = f"{USERS_URL}{student.pk}/set-active/"

    assert (
        api_client_no_csrf.post(url, {"is_active": False, "reason": "left the course"}).status_code
        == 200
    )
    student.refresh_from_db()
    assert student.is_active is False
    assert AuditLog.objects.filter(action=AuditAction.USER_DEACTIVATED).exists()

    assert api_client_no_csrf.post(url, {"is_active": True}).status_code == 200
    student.refresh_from_db()
    assert student.is_active is True
    assert AuditLog.objects.filter(action=AuditAction.USER_ACTIVATED).exists()


@pytest.mark.django_db
def test_admin_cannot_deactivate_their_own_account(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{USERS_URL}{admin_user.pk}/set-active/", {"is_active": False}
    )
    assert response.status_code == 409
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


@pytest.mark.django_db
def test_deactivation_destroys_the_users_sessions(api_client_no_csrf, admin_user, student):
    from django.contrib.sessions.models import Session

    student_client = api_client_no_csrf.__class__()
    student_client.force_login(student)
    assert Session.objects.count() >= 1

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"{USERS_URL}{student.pk}/set-active/", {"is_active": False})

    # The student's own session is gone; the admin's remains.
    assert student_client.get("/api/v1/auth/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_user_detail_never_exposes_credentials(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}{student.pk}/").content.decode()
    assert "password" not in body
    assert "is_superuser" not in body
