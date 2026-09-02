"""Password change and reset flows."""

from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts.models import AccountToken, TokenPurpose, User
from apps.audit.models import AuditAction, AuditLog
from tests.conftest import NEW_PASSWORD, TEST_PASSWORD

CHANGE_URL = "/api/v1/auth/password/change/"
RESET_URL = "/api/v1/auth/password/reset/"
CONFIRM_URL = "/api/v1/auth/password/reset/confirm/"
LOGIN_URL = "/api/v1/auth/login/"


def _issue_reset(user: User) -> str:
    _, raw = AccountToken.issue(user=user, purpose=TokenPurpose.PASSWORD_RESET)
    return raw


# --- Change ----------------------------------------------------------------


@pytest.mark.django_db
def test_password_change_succeeds_and_new_password_works(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(
        CHANGE_URL, {"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 200

    student.refresh_from_db()
    assert student.check_password(NEW_PASSWORD)
    assert not student.check_password(TEST_PASSWORD)


@pytest.mark.django_db
def test_password_change_requires_the_current_password(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(
        CHANGE_URL, {"current_password": "not-the-right-one", "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400
    assert "current_password" in response.json()["error"]["details"]
    student.refresh_from_db()
    assert student.check_password(TEST_PASSWORD)


@pytest.mark.django_db
def test_password_change_rejects_a_weak_password(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(
        CHANGE_URL, {"current_password": TEST_PASSWORD, "new_password": "password"}
    )
    assert response.status_code == 400
    assert "new_password" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_password_change_rejects_reusing_the_same_password(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(
        CHANGE_URL, {"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_password_change_requires_authentication(api_client_no_csrf):
    response = api_client_no_csrf.post(
        CHANGE_URL, {"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_password_change_is_audited_without_the_password(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    api_client_no_csrf.post(
        CHANGE_URL, {"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD}
    )
    entry = AuditLog.objects.filter(action=AuditAction.PASSWORD_CHANGED).first()
    assert entry is not None
    serialised = str(entry.context) + entry.actor_label
    assert TEST_PASSWORD not in serialised
    assert NEW_PASSWORD not in serialised


# --- Reset request ---------------------------------------------------------


@pytest.mark.django_db
def test_reset_request_response_is_identical_for_known_and_unknown_addresses(
    api_client_no_csrf, student
):
    """The single most important anti-enumeration property of this endpoint."""
    known = api_client_no_csrf.post(RESET_URL, {"email": student.email})
    unknown = api_client_no_csrf.post(RESET_URL, {"email": "nobody@example.test"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


@pytest.mark.django_db
def test_reset_request_sends_mail_only_for_a_real_account(api_client_no_csrf, student):
    mail.outbox.clear()
    api_client_no_csrf.post(RESET_URL, {"email": "nobody@example.test"})
    assert len(mail.outbox) == 0

    api_client_no_csrf.post(RESET_URL, {"email": student.email})
    assert len(mail.outbox) == 1
    assert student.email in mail.outbox[0].to


@pytest.mark.django_db
def test_reset_email_contains_a_link_and_never_the_stored_hash(api_client_no_csrf, student):
    mail.outbox.clear()
    api_client_no_csrf.post(RESET_URL, {"email": student.email})
    body = mail.outbox[0].body
    token = AccountToken.objects.get(user=student, purpose=TokenPurpose.PASSWORD_RESET)
    assert "/reset-password?" in body
    assert token.token_hash not in body


@pytest.mark.django_db
def test_reset_request_for_an_inactive_account_looks_identical(api_client_no_csrf, student):
    student.is_active = False
    student.save()
    mail.outbox.clear()
    response = api_client_no_csrf.post(RESET_URL, {"email": student.email})
    assert response.status_code == 202
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_reset_request_is_rate_limited(api_client_no_csrf, settings, student):
    from django.core.cache import cache

    from apps.common.throttling import AuthEndpointThrottle

    cache.clear()
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "auth": "3/min",
        },
    }
    AuthEndpointThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    statuses = [
        api_client_no_csrf.post(RESET_URL, {"email": student.email}).status_code for _ in range(5)
    ]
    assert 429 in statuses
    cache.clear()


# --- Reset confirm ---------------------------------------------------------


@pytest.mark.django_db
def test_reset_confirm_sets_the_new_password(api_client_no_csrf, student):
    raw = _issue_reset(student)
    response = api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 200

    student.refresh_from_db()
    assert student.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_reset_token_is_single_use(api_client_no_csrf, student):
    raw = _issue_reset(student)
    first = api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    second = api_client_no_csrf.post(
        CONFIRM_URL, {"token": raw, "new_password": "yet-another-passphrase-9"}
    )
    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_expired_reset_token_is_refused(api_client_no_csrf, student):
    from django.utils import timezone

    raw = _issue_reset(student)
    AccountToken.objects.filter(user=student).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    response = api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_unknown_and_used_tokens_are_indistinguishable(api_client_no_csrf, student):
    raw = _issue_reset(student)
    api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    used = api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    unknown = api_client_no_csrf.post(
        CONFIRM_URL, {"token": "not-a-real-token", "new_password": NEW_PASSWORD}
    )
    assert used.json()["error"] == {
        **unknown.json()["error"],
        "request_id": used.json()["error"]["request_id"],
    }


@pytest.mark.django_db
def test_issuing_a_new_token_invalidates_the_previous_one(api_client_no_csrf, student):
    first_raw = _issue_reset(student)
    _issue_reset(student)
    response = api_client_no_csrf.post(
        CONFIRM_URL, {"token": first_raw, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_only_the_token_hash_is_stored(student):
    raw = _issue_reset(student)
    token = AccountToken.objects.get(user=student, purpose=TokenPurpose.PASSWORD_RESET)
    assert token.token_hash != raw
    assert raw not in token.token_hash
    assert token.token_hash == AccountToken.hash_token(raw)


@pytest.mark.django_db
def test_reset_signs_out_existing_sessions(api_client_no_csrf, student):
    from django.contrib.sessions.models import Session

    api_client_no_csrf.force_login(student)
    assert Session.objects.exists()

    raw = _issue_reset(student)
    api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    assert not Session.objects.exists()


@pytest.mark.django_db
def test_reset_is_audited(api_client_no_csrf, student):
    raw = _issue_reset(student)
    api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    assert AuditLog.objects.filter(action=AuditAction.PASSWORD_RESET_COMPLETED).exists()


@pytest.mark.django_db
def test_failed_reset_is_audited_without_the_token(api_client_no_csrf):
    api_client_no_csrf.post(
        CONFIRM_URL, {"token": "guessed-token-value", "new_password": NEW_PASSWORD}
    )
    entry = AuditLog.objects.filter(action=AuditAction.PASSWORD_RESET_FAILED).first()
    assert entry is not None
    assert "guessed-token-value" not in str(entry.context)


@pytest.mark.django_db
def test_reset_then_login_with_the_new_password(api_client_no_csrf, student):
    raw = _issue_reset(student)
    api_client_no_csrf.post(CONFIRM_URL, {"token": raw, "new_password": NEW_PASSWORD})
    response = api_client_no_csrf.post(
        LOGIN_URL, {"email": student.email, "password": NEW_PASSWORD}
    )
    assert response.status_code == 200
