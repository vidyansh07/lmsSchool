"""Configuration-level security guarantees.

These tests assert the *settings* are safe, which catches an entire class of
deployment mistakes no request-level test would notice.

Settings modules that must fail are loaded in a subprocess: importing them in
-process would leave a half-initialised module in ``sys.modules`` and make the
result depend on test ordering.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.guards import forbid_insecure_secret, forbid_sqlite, require_environment

BACKEND_DIR = Path(__file__).resolve().parents[1]

# A syntactically valid, obviously fake secret used only to load settings.
FAKE_SECRET_KEY = "test-only-3Qv7pLxN2rW9zKmT8bYcF4dHsJ6gA1eU5nR0iOqZwXyVbMlP"

PROD_ENV = {
    "DJANGO_ENV": "production",
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": FAKE_SECRET_KEY,
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "CSRF_TRUSTED_ORIGINS": "https://app.example.com",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "DATABASE_URL": "postgres://user:pass@db.example.com:5432/lms",
    "CACHE_URL": "redis://cache.example.com:6379/0",
    "EMAIL_HOST": "smtp.example.com",
    "DEFAULT_FROM_EMAIL": "no-reply@example.com",
    "FRONTEND_BASE_URL": "https://app.example.com",
    "SENTRY_DSN": "",
}


def _run_django(args: list[str], overrides: dict[str, str]) -> subprocess.CompletedProcess:
    env = {**os.environ, **PROD_ENV, **overrides}
    return subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- Guard unit tests ------------------------------------------------------


def test_environment_mismatch_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("DJANGO_ENV", "production")
    with pytest.raises(ImproperlyConfigured, match="Environment mismatch"):
        require_environment("staging")


def test_deployed_environment_requires_django_env(monkeypatch):
    monkeypatch.delenv("DJANGO_ENV", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_ENV is not set"):
        require_environment("production")


def test_sqlite_is_rejected():
    with pytest.raises(ImproperlyConfigured, match="SQLite"):
        forbid_sqlite({"default": {"ENGINE": "django.db.backends.sqlite3"}})


@pytest.mark.parametrize(
    "value",
    [
        "",
        "insecure-development-key-local-only",
        "django-insecure-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmn",
        "short-key",
        "y" * 64,  # long but almost no entropy
    ],
)
def test_weak_secret_keys_are_rejected(value):
    with pytest.raises(ImproperlyConfigured):
        forbid_insecure_secret(value, "insecure-development-key")


def test_a_strong_secret_key_is_accepted():
    forbid_insecure_secret(FAKE_SECRET_KEY, "insecure-development-key")


# --- Whole-configuration tests --------------------------------------------


def test_production_settings_load_and_are_hardened():
    """Print the security-relevant settings from a real production boot."""
    script = (
        "import django;django.setup();"
        "from django.conf import settings as s;"
        "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT,"
        "s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_CONTENT_TYPE_NOSNIFF,"
        "s.X_FRAME_OPTIONS, s.ALLOW_DEMO_SEED, s.ALLOWED_HOSTS, s.CORS_ALLOWED_ORIGINS,"
        "s.DATABASES['default']['ATOMIC_REQUESTS'], s.SECURE_PROXY_SSL_HEADER,"
        "'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE)"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env={**os.environ, **PROD_ENV},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout.strip()
    assert out == (
        "False True True True 31536000 True True DENY False ['api.example.com'] "
        "['https://app.example.com'] True ('HTTP_X_FORWARDED_PROTO', 'https') True"
    ), out


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"DJANGO_SECRET_KEY": ""}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_ALLOWED_HOSTS": ""}, "DJANGO_ALLOWED_HOSTS"),
        ({"CACHE_URL": ""}, "CACHE_URL"),
        ({"EMAIL_HOST": ""}, "EMAIL_HOST"),
        ({"DEFAULT_FROM_EMAIL": ""}, "DEFAULT_FROM_EMAIL"),
        ({"FRONTEND_BASE_URL": ""}, "FRONTEND_BASE_URL"),
        ({"DATABASE_URL": ""}, "DATABASE_URL"),
        ({"DJANGO_ENV": "local"}, "Environment mismatch"),
    ],
)
def test_production_refuses_to_start_with_missing_or_wrong_configuration(overrides, expected):
    result = _run_django(["check"], overrides)
    assert result.returncode != 0
    assert expected in (result.stdout + result.stderr)


def test_django_deployment_checks_pass_for_production():
    """`manage.py check --deploy` must be clean, warnings included."""
    result = _run_django(["check", "--deploy", "--fail-level", "WARNING"], {})
    assert result.returncode == 0, result.stdout + result.stderr


def test_django_deployment_checks_pass_for_staging():
    result = _run_django(
        ["check", "--deploy", "--fail-level", "WARNING"],
        {"DJANGO_ENV": "staging", "DJANGO_SETTINGS_MODULE": "config.settings.staging"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- Runtime security posture ---------------------------------------------


def test_default_permission_class_denies_by_default(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "apps.common.permissions.IsActiveUser",
    )


def test_password_policy_requires_twelve_characters(settings):
    length_validator = next(
        validator
        for validator in settings.AUTH_PASSWORD_VALIDATORS
        if validator["NAME"].endswith("MinimumLengthValidator")
    )
    assert length_validator["OPTIONS"]["min_length"] >= 12


def test_security_headers_are_present_on_responses(client):
    response = client.get("/api/")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response["Permissions-Policy"]
    assert response["X-Frame-Options"] == "DENY"


def test_cors_never_allows_a_wildcard_origin(settings):
    assert getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) is False
    assert "*" not in settings.CORS_ALLOWED_ORIGINS
    assert settings.CORS_ALLOW_CREDENTIALS is True


def test_forwarded_proto_is_not_trusted_without_a_proxy(settings):
    """A directly reachable app must not believe a client-supplied protocol."""
    assert settings.SECURE_PROXY_SSL_HEADER is None
