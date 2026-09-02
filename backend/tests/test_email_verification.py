"""Email verification flow."""

from __future__ import annotations

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import AccountToken, TokenPurpose
from apps.audit.models import AuditAction, AuditLog

REQUEST_URL = "/api/v1/auth/email/verify/"
CONFIRM_URL = "/api/v1/auth/email/verify/confirm/"


@pytest.mark.django_db
def test_new_accounts_start_unverified(student):
    assert student.is_email_verified is False
    assert student.email_verified_at is None


@pytest.mark.django_db
def test_request_sends_a_verification_email(api_client_no_csrf, student):
    mail.outbox.clear()
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(REQUEST_URL)
    assert response.status_code == 202
    assert len(mail.outbox) == 1
    assert "/verify-email?" in mail.outbox[0].body


@pytest.mark.django_db
def test_request_requires_authentication(api_client_no_csrf):
    assert api_client_no_csrf.post(REQUEST_URL).status_code in (401, 403)


@pytest.mark.django_db
def test_confirm_marks_the_address_verified(api_client_no_csrf, student):
    _, raw = AccountToken.issue(user=student, purpose=TokenPurpose.EMAIL_VERIFICATION)
    response = api_client_no_csrf.post(CONFIRM_URL, {"token": raw})
    assert response.status_code == 200

    student.refresh_from_db()
    assert student.is_email_verified is True
    assert student.email_verified_at is not None


@pytest.mark.django_db
def test_verification_token_is_single_use(api_client_no_csrf, student):
    _, raw = AccountToken.issue(user=student, purpose=TokenPurpose.EMAIL_VERIFICATION)
    assert api_client_no_csrf.post(CONFIRM_URL, {"token": raw}).status_code == 200
    assert api_client_no_csrf.post(CONFIRM_URL, {"token": raw}).status_code == 400


@pytest.mark.django_db
def test_expired_verification_token_is_refused(api_client_no_csrf, student):
    _, raw = AccountToken.issue(user=student, purpose=TokenPurpose.EMAIL_VERIFICATION)
    AccountToken.objects.filter(user=student).update(
        expires_at=timezone.now() - timezone.timedelta(seconds=1)
    )
    response = api_client_no_csrf.post(CONFIRM_URL, {"token": raw})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_invalid_verification_token_is_refused(api_client_no_csrf):
    response = api_client_no_csrf.post(CONFIRM_URL, {"token": "definitely-not-valid"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_reset_token_cannot_be_used_to_verify_an_address(api_client_no_csrf, student):
    """Tokens are scoped to their purpose, so one flow cannot feed another."""
    _, raw = AccountToken.issue(user=student, purpose=TokenPurpose.PASSWORD_RESET)
    assert api_client_no_csrf.post(CONFIRM_URL, {"token": raw}).status_code == 400
    student.refresh_from_db()
    assert student.is_email_verified is False


@pytest.mark.django_db
def test_verification_is_audited(api_client_no_csrf, student):
    _, raw = AccountToken.issue(user=student, purpose=TokenPurpose.EMAIL_VERIFICATION)
    api_client_no_csrf.post(CONFIRM_URL, {"token": raw})
    assert AuditLog.objects.filter(action=AuditAction.EMAIL_VERIFIED).exists()


@pytest.mark.django_db
def test_already_verified_account_does_not_issue_another_token(api_client_no_csrf, student):
    student.is_email_verified = True
    student.save()
    mail.outbox.clear()
    api_client_no_csrf.force_login(student)
    api_client_no_csrf.post(REQUEST_URL)
    assert len(mail.outbox) == 0
