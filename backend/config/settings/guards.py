"""Boot-time configuration guards.

These exist to make a whole class of production incidents impossible:
a process started with development settings must never be able to reach a
production database or run with production secrets (and vice versa).

Every settings module declares its ``ENVIRONMENT`` and calls
:func:`require_environment`. The process refuses to start when the declared
environment does not match the ``DJANGO_ENV`` variable supplied by the
runtime, so a mis-wired deployment fails loudly at boot instead of silently
writing to the wrong database.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.exceptions import ImproperlyConfigured

ENVIRONMENTS = ("local", "development", "staging", "production", "test")


def require_environment(expected: str) -> str:
    """Assert that ``DJANGO_ENV`` matches the loaded settings module."""
    if expected not in ENVIRONMENTS:
        raise ImproperlyConfigured(
            f"Unknown environment {expected!r}. Expected one of {ENVIRONMENTS}."
        )
    actual = os.environ.get("DJANGO_ENV")
    if actual is None:
        # Explicit opt-in keeps single-command local usage ergonomic while
        # still failing closed for deployed environments.
        if expected in ("local", "test"):
            os.environ["DJANGO_ENV"] = expected
            return expected
        raise ImproperlyConfigured(
            f"DJANGO_ENV is not set but settings for {expected!r} were loaded. "
            "Set DJANGO_ENV explicitly in deployed environments."
        )
    if actual != expected:
        raise ImproperlyConfigured(
            f"Environment mismatch: DJANGO_ENV={actual!r} but "
            f"config.settings.{expected} was loaded. Refusing to start so that "
            "one environment cannot accidentally use another's configuration."
        )
    return expected


def require_setting(name: str, value: Any) -> Any:
    """Fail fast when a required deployment setting is missing or empty."""
    if value in (None, "", [], {}):
        raise ImproperlyConfigured(
            f"{name} must be set in this environment. Supply it through the "
            "runtime secret manager; it is intentionally not defaulted."
        )
    return value


def forbid_sqlite(databases: dict[str, dict[str, Any]]) -> None:
    """PostgreSQL is the only supported database outside the test environment."""
    engine = databases.get("default", {}).get("ENGINE", "")
    if "sqlite" in engine:
        raise ImproperlyConfigured(
            "SQLite is not a supported database for this environment. "
            "Set DATABASE_URL to a PostgreSQL DSN."
        )


#: Django's own ``--deploy`` check enforces these thresholds. Applying them at
#: boot means a weak key fails the deployment instead of merely a lint run.
MIN_SECRET_KEY_LENGTH = 50
MIN_SECRET_KEY_UNIQUE_CHARS = 5


def forbid_insecure_secret(secret_key: str, marker: str) -> None:
    """Refuse to boot a deployed environment with a weak or shared secret key."""
    if not secret_key or marker in secret_key or secret_key.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is unset or still a development placeholder. "
            "Generate a unique value per environment and inject it as a secret."
        )
    if (
        len(secret_key) < MIN_SECRET_KEY_LENGTH
        or len(set(secret_key)) < MIN_SECRET_KEY_UNIQUE_CHARS
    ):
        raise ImproperlyConfigured(
            f"DJANGO_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters "
            f"with at least {MIN_SECRET_KEY_UNIQUE_CHARS} distinct characters. "
            'Generate one with: python -c "import secrets;print(secrets.token_urlsafe(64))"'
        )
