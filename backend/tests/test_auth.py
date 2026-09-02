"""Authentication foundation tests."""

from __future__ import annotations

import pytest
from django.urls import reverse

from tests.conftest import TEST_PASSWORD

LOGIN_URL = "/api/v1/auth/login/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/auth/me/"
CSRF_URL = "/api/v1/auth/csrf/"


@pytest.mark.django_db
def test_csrf_endpoint_sets_cookie(api_client):
    response = api_client.get(CSRF_URL)
    assert response.status_code == 200
    assert "grras_csrftoken" in response.cookies


@pytest.mark.django_db
def test_login_succeeds_and_returns_the_user(api_client_no_csrf, student):
    response = api_client_no_csrf.post(
        LOGIN_URL, {"email": student.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["email"] == student.email
    # The response must never carry credential material.
    assert "password" not in response.content.decode()


@pytest.mark.django_db
def test_login_is_case_insensitive_on_email(api_client_no_csrf, student):
    response = api_client_no_csrf.post(
        LOGIN_URL, {"email": student.email.upper(), "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_failure_is_generic_for_unknown_and_wrong_password(api_client_no_csrf, student):
    """Responses must not let an attacker tell which accounts exist."""
    unknown = api_client_no_csrf.post(
        LOGIN_URL, {"email": "nobody@example.test", "password": "wrong-password-value"}
    )
    wrong = api_client_no_csrf.post(
        LOGIN_URL, {"email": student.email, "password": "wrong-password-value"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert (
        unknown.json()["error"]["message"]
        == wrong.json()["error"]["message"]
        == "Invalid credentials."
    )


@pytest.mark.django_db
def test_login_rejects_unknown_fields(api_client_no_csrf, student):
    response = api_client_no_csrf.post(
        LOGIN_URL,
        {"email": student.email, "password": TEST_PASSWORD, "is_superuser": True},
    )
    assert response.status_code == 400
    assert "is_superuser" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_login_requires_csrf_token_from_a_browser_client(api_client, student):
    """Session auth without CSRF enforcement would be cross-site forgeable."""
    response = api_client.post(LOGIN_URL, {"email": student.email, "password": TEST_PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


@pytest.mark.django_db
def test_inactive_user_cannot_authenticate(api_client_no_csrf, student):
    student.is_active = False
    student.save()
    response = api_client_no_csrf.post(
        LOGIN_URL, {"email": student.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_me_requires_authentication(api_client_no_csrf):
    response = api_client_no_csrf.get(ME_URL)
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] in ("authentication_required", "permission_denied")


@pytest.mark.django_db
def test_me_returns_the_session_user(api_client_no_csrf, trainer):
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.get(ME_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == trainer.email
    assert body["role"] == "trainer"
    assert "is_superuser" not in body
    assert "password" not in body


@pytest.mark.django_db
def test_logout_ends_the_session(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.post(LOGOUT_URL).status_code == 200
    assert api_client_no_csrf.get(ME_URL).status_code in (401, 403)


@pytest.mark.django_db
def test_login_is_rate_limited(api_client_no_csrf, settings, student):
    from django.core.cache import cache

    cache.clear()
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "auth": "3/min",
        },
    }
    from apps.common.throttling import AuthEndpointThrottle

    AuthEndpointThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    statuses = [
        api_client_no_csrf.post(
            LOGIN_URL, {"email": student.email, "password": "wrong-password-value"}
        ).status_code
        for _ in range(5)
    ]
    assert 429 in statuses
    cache.clear()


@pytest.mark.django_db
def test_session_cookie_flags_are_hardened(settings):
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    # CSRF cookie must stay readable by the SPA to be echoed in a header.
    assert settings.CSRF_COOKIE_HTTPONLY is False


@pytest.mark.django_db
def test_admin_login_page_is_reachable(client):
    assert client.get(reverse("admin:login")).status_code == 200


@pytest.mark.django_db
def test_csrf_failures_use_one_code_regardless_of_session_state(api_client, student):
    """DRF's own CSRF check and the explicit mixin must answer identically.

    Session authentication runs its own CSRF check before view code, reporting a
    generic permission error that names the server-side reason. Both paths are
    normalised to `csrf_failed` with no reason attached.
    """
    anonymous = api_client.post(LOGIN_URL, {"email": student.email, "password": TEST_PASSWORD})

    api_client.force_login(student)
    authenticated = api_client.post(
        "/api/v1/auth/password/change/",
        {"current_password": TEST_PASSWORD, "new_password": "a-brand-new-passphrase"},
    )

    for response in (anonymous, authenticated):
        body = response.json()["error"]
        assert response.status_code == 403
        assert body["code"] == "csrf_failed"
        # The reason describes server state and must not be echoed back.
        assert "CSRF Failed" not in body["message"]
        assert "token missing" not in body["message"].lower()
        assert body.get("details") is None


# ---------------------------------------------------------------------------
# §14.1 — session lifetime and revocation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signing_out_everywhere_ends_other_sessions(client, django_user_model, student):
    """One person, two browsers, one compromise.

    "Sign out everywhere" is only worth having if it reaches the *other*
    session. A test that logs in once and signs out once would pass on an
    implementation that only ends the session making the request — which is
    exactly the implementation somebody writes by accident.
    """
    from django.test import Client

    first, second = Client(), Client()
    for browser in (first, second):
        assert (
            browser.post(
                "/api/v1/auth/login/",
                {"email": student.email, "password": TEST_PASSWORD},
                content_type="application/json",
            ).status_code
            == 200
        )
        assert browser.get("/api/v1/auth/me/").status_code == 200

    assert first.post("/api/v1/auth/logout-all/").status_code in (200, 204)

    assert first.get("/api/v1/auth/me/").status_code == 403
    assert second.get("/api/v1/auth/me/").status_code == 403, "the other browser is still signed in"


@pytest.mark.django_db
def test_a_session_does_not_outlive_its_cookie(client, student, settings):
    """§14.1 session expiry. Twelve hours by default, and enforced by Django's
    session backend rather than by anything this project wrote — which is worth
    asserting precisely because it is easy to assume."""
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    assert settings.SESSION_COOKIE_AGE <= 24 * 60 * 60

    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": student.email, "password": TEST_PASSWORD},
            content_type="application/json",
        ).status_code
        == 200
    )

    session = Session.objects.get(session_key=client.session.session_key)
    assert session.expire_date <= timezone.now() + timezone.timedelta(
        seconds=settings.SESSION_COOKIE_AGE + 5
    )

    # Expire it the way time would, and the session stops working.
    session.expire_date = timezone.now() - timezone.timedelta(seconds=1)
    session.save(update_fields=["expire_date"])
    assert client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_a_reset_token_expires(student, settings):
    from django.utils import timezone

    from apps.accounts.models import AccountToken, TokenPurpose

    token, _raw = AccountToken.issue(user=student, purpose=TokenPurpose.PASSWORD_RESET)
    assert token.expires_at <= timezone.now() + timezone.timedelta(
        hours=settings.AUTH_TOKEN_RESET_TTL_HOURS, minutes=1
    )
    assert settings.AUTH_TOKEN_RESET_TTL_HOURS <= 24
