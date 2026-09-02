"""Test settings — used by pytest and CI.

Deliberately fast and hermetic, but still exercises the real security code
paths (CSRF, permissions, throttling) so tests catch regressions in them.
"""

import tempfile
from pathlib import Path

from .base import *
from .base import env
from .guards import require_environment

ENVIRONMENT = require_environment("test")

DEBUG = False
# Fixed key so tests are deterministic. Contains DEV_SECRET_KEY_MARKER, so
# any deployed environment would refuse to start with it.
SECRET_KEY = "insecure-development-key-tests-only"  # nosec B105  # noqa: S105
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Fast, deterministic hashing keeps the suite quick without touching prod code.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "grras-lms-test",
    }
}

API_DOCS_ENABLED = True
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="CRITICAL")
LOGGING["root"]["level"] = LOG_LEVEL
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Uploaded files go to a throwaway directory, so a test run never writes into
# the working tree and one run cannot see another's files.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="grras-lms-test-media-"))

# Local/test environments may create fake demo data.
ALLOW_DEMO_SEED = True
