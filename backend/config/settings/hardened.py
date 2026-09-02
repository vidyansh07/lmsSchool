"""Security baseline shared by every network-reachable deployment.

Imported by ``development``, ``staging`` and ``production``. It contains no
environment assertion of its own so that each concrete module keeps a single,
unambiguous ``DJANGO_ENV`` guard.

Nothing here has a usable default for a secret: every credential and host list
must be injected by the runtime secret manager. A missing value raises
``ImproperlyConfigured`` at boot instead of starting an insecure process.
"""

from __future__ import annotations

import sys
import warnings

from django.core.exceptions import ImproperlyConfigured

from apps.common.storage import check_storage_configuration

from .base import *
from .base import (
    CELERY_BROKER_URL,
    DEV_SECRET_KEY_MARKER,
    MIDDLEWARE,
    REST_FRAMEWORK,
    STORAGES,
    env,
)
from .guards import forbid_insecure_secret, forbid_sqlite, require_setting

DEBUG = False  # never configurable in a deployed environment

SECRET_KEY = require_setting("DJANGO_SECRET_KEY", env.str("DJANGO_SECRET_KEY", default=""))
forbid_insecure_secret(SECRET_KEY, DEV_SECRET_KEY_MARKER)

ALLOWED_HOSTS = require_setting(
    "DJANGO_ALLOWED_HOSTS", env.list("DJANGO_ALLOWED_HOSTS", default=[])
)
CSRF_TRUSTED_ORIGINS = require_setting(
    "CSRF_TRUSTED_ORIGINS", env.list("CSRF_TRUSTED_ORIGINS", default=[])
)
CORS_ALLOWED_ORIGINS = require_setting(
    "CORS_ALLOWED_ORIGINS", env.list("CORS_ALLOWED_ORIGINS", default=[])
)

# --- Transport & cookies ---------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --- Cache is mandatory ----------------------------------------------------
# Rate limiting is only correct when every worker shares one counter store; a
# per-process cache silently multiplies each limit by the worker count.
CACHE_URL = require_setting("CACHE_URL", env.str("CACHE_URL", default=""))
CACHES = {"default": env.cache_url_config(CACHE_URL)}

# --- Database --------------------------------------------------------------
DATABASE_URL = require_setting("DATABASE_URL", env.str("DATABASE_URL", default=""))
DATABASES = {"default": env.db_url_config(DATABASE_URL)}
# Persistent connections are safe here because the concurrency is bounded:
# gunicorn runs a fixed number of workers and threads, so the peak connection
# count is `GUNICORN_WORKERS x GUNICORN_THREADS` per instance.
#
# **Sizing rule.** PostgreSQL's `max_connections` must exceed
# `instances x workers x threads`, plus headroom for migrations and psql. With
# the entrypoint defaults (3 workers, 2 threads) that is 6 per instance. Beyond
# a handful of instances, put PgBouncer in front rather than raising
# `max_connections` — each PostgreSQL connection costs real memory.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"]["sslmode"] = env.str("DATABASE_SSL_MODE", default="require")
forbid_sqlite(DATABASES)

# --- Static files ----------------------------------------------------------
MIDDLEWARE = MIDDLEWARE.copy()
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Student work must not sit on a container volume that dies with the container,
# and must not sit in a bucket anyone can read. Both failures are silent, so
# both are checked at boot rather than discovered later.
if env.str("FILE_STORAGE_BACKEND", default="local") != "s3":
    warnings.warn(
        "FILE_STORAGE_BACKEND is not 's3': uploaded student files are on local disk "
        "and will not survive a container replacement.",
        stacklevel=2,
    )
check_storage_configuration(sys.modules[__name__])

# --- Background work -------------------------------------------------------
# Eager mode runs "background" tasks inside the request that queued them. On a
# laptop that is a convenience; in a deployment it means the slow work the
# queue exists to move out of the request is still in it, and nobody notices
# until a mail provider hangs and takes the web workers with it.
# Resolved in `base` — it falls back to CACHE_URL, so a single Redis serves
# both unless the deployment splits them. Required either way.
CELERY_BROKER_URL = require_setting("CELERY_BROKER_URL", CELERY_BROKER_URL)
if env.bool("CELERY_TASK_ALWAYS_EAGER", default=False):
    raise ImproperlyConfigured(
        "CELERY_TASK_ALWAYS_EAGER must be off in a deployed environment: it runs "
        "queued work inside the HTTP request."
    )
CELERY_TASK_ALWAYS_EAGER = False

# --- API surface -----------------------------------------------------------
REST_FRAMEWORK = {**REST_FRAMEWORK}
# Number of trusted reverse proxies in front of the app. Throttling and audit
# logging use it to pick the real client IP out of X-Forwarded-For.
NUM_PROXIES = env.int("NUM_PROXIES", default=1)
REST_FRAMEWORK["NUM_PROXIES"] = NUM_PROXIES

# Trust the proxy's protocol header only when a proxy is actually declared.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if NUM_PROXIES else None

# --- Email -----------------------------------------------------------------
# A deployed environment that cannot send mail cannot reset a password, so the
# SMTP host is required rather than silently defaulting to the console.
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
if EMAIL_BACKEND.endswith("smtp.EmailBackend"):
    EMAIL_HOST = require_setting("EMAIL_HOST", env.str("EMAIL_HOST", default=""))
DEFAULT_FROM_EMAIL = require_setting(
    "DEFAULT_FROM_EMAIL", env.str("DEFAULT_FROM_EMAIL", default="")
)
FRONTEND_BASE_URL = require_setting(
    "FRONTEND_BASE_URL", env.str("FRONTEND_BASE_URL", default="")
).rstrip("/")

# --- Observability ---------------------------------------------------------
LOG_FORMAT = env.str("DJANGO_LOG_FORMAT", default="json")
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="INFO")
LOGGING["handlers"]["console"]["formatter"] = LOG_FORMAT
LOGGING["root"]["level"] = LOG_LEVEL


def configure_error_reporting(environment: str) -> None:
    """Initialise Sentry when a DSN is configured. PII is never sent."""
    dsn = env.str("SENTRY_DSN", default="")
    if not dsn:  # pragma: no cover - depends on deployment configuration
        return
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=env.str("APP_VERSION", default="0.1.0"),
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
        max_request_body_size="never",
    )
