"""Audit logging foundation."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditLog, AuditResult
from apps.audit.services import record
from tests.conftest import TEST_PASSWORD


@pytest.mark.django_db
def test_successful_login_is_recorded(api_client_no_csrf, student):
    api_client_no_csrf.post(
        "/api/v1/auth/login/", {"email": student.email, "password": TEST_PASSWORD}
    )
    entry = AuditLog.objects.filter(action=AuditAction.LOGIN_SUCCEEDED).first()
    assert entry is not None
    assert entry.actor_id == student.pk
    assert entry.result == AuditResult.SUCCESS
    assert entry.request_id


@pytest.mark.django_db
def test_failed_login_is_recorded_without_the_password(api_client_no_csrf, student):
    api_client_no_csrf.post(
        "/api/v1/auth/login/", {"email": student.email, "password": "wrong-password-value"}
    )
    entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).first()
    assert entry is not None
    assert entry.result == AuditResult.FAILURE
    assert "wrong-password-value" not in str(entry.context)
    assert entry.actor is None


@pytest.mark.django_db
def test_recorded_context_is_scrubbed_of_secrets():
    entry = record(
        action=AuditAction.USER_UPDATED,
        resource_type="user",
        resource_id="1",
        context={
            "password": "hunter2-hunter2",
            "nested": {"api_key": "abcd", "keep": "visible"},
            "token": "xyz",
        },
    )
    assert entry.context["password"] == "[redacted]"
    assert entry.context["token"] == "[redacted]"
    assert entry.context["nested"]["api_key"] == "[redacted]"
    assert entry.context["nested"]["keep"] == "visible"


@pytest.mark.django_db
def test_audit_entries_are_append_only():
    entry = record(action=AuditAction.USER_CREATED, resource_type="user", resource_id="1")
    entry.action = AuditAction.USER_DEACTIVATED
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db
def test_audit_survives_actor_deletion(student):
    record(action=AuditAction.LOGIN_SUCCEEDED, actor=student, resource_type="user")
    student.delete()
    entry = AuditLog.objects.first()
    assert entry.actor is None
    assert entry.actor_label == "student@example.test"


@pytest.mark.django_db
def test_service_layer_records_user_creation(admin_user):
    from apps.accounts.services import create_user

    created = create_user(
        email="new.person@example.test",
        password=TEST_PASSWORD,
        first_name="New",
        actor=admin_user,
    )
    entry = AuditLog.objects.filter(action=AuditAction.USER_CREATED).first()
    assert entry.resource_id == str(created.pk)
    assert entry.actor_id == admin_user.pk


@pytest.mark.django_db
def test_failure_audits_survive_the_rollback_they_record(api_client_no_csrf, student):
    """Regression guard for a real defect found during Phase 1.

    ``ATOMIC_REQUESTS`` wraps each request in a transaction and DRF marks that
    transaction for rollback whenever it turns an exception into an error
    response. A failure audit written inline was therefore discarded by the very
    failure it was recording. Failure entries are now queued and written by
    middleware, outside the request transaction.
    """
    api_client_no_csrf.post(
        "/api/v1/auth/password/reset/confirm/",
        {"token": "a-token-that-does-not-exist", "new_password": "some-new-passphrase-1"},
    )
    entry = AuditLog.objects.filter(action=AuditAction.PASSWORD_RESET_FAILED).first()
    assert entry is not None
    assert entry.result == AuditResult.FAILURE
    assert "a-token-that-does-not-exist" not in str(entry.context)


@pytest.mark.django_db
def test_wrong_current_password_is_audited_as_a_failure(api_client_no_csrf, student):
    from tests.conftest import NEW_PASSWORD

    api_client_no_csrf.force_login(student)
    api_client_no_csrf.post(
        "/api/v1/auth/password/change/",
        {"current_password": "wrong-current-password", "new_password": NEW_PASSWORD},
    )
    entry = AuditLog.objects.filter(
        action=AuditAction.PASSWORD_CHANGED, result=AuditResult.FAILURE
    ).first()
    assert entry is not None
    assert "wrong-current-password" not in str(entry.context)


@pytest.mark.django_db
def test_successful_actions_are_written_inside_their_own_transaction():
    """A success audit must commit with the change it describes, not after it."""
    from apps.audit.services import record as record_entry

    entry = record_entry(action=AuditAction.USER_UPDATED, resource_type="user", resource_id="1")
    assert entry is not None  # written inline, so an instance comes back
    assert AuditLog.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_deferred_entries_carry_the_actor_and_request_metadata(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    api_client_no_csrf.post(
        "/api/v1/auth/password/change/",
        {"current_password": "definitely-wrong", "new_password": "another-passphrase-77"},
    )
    entry = AuditLog.objects.filter(
        action=AuditAction.PASSWORD_CHANGED, result=AuditResult.FAILURE
    ).first()
    assert entry.actor_id == student.pk
    assert entry.request_id
    assert entry.request_path == "/api/v1/auth/password/change/"
