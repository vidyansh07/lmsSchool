"""Local developer machine / docker compose settings.

Relaxations here are deliberately scoped to this module: nothing in
``base.py`` is weakened, so staging and production cannot inherit them.
"""

from .base import *
from .base import CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS, env
from .guards import require_environment

ENVIRONMENT = require_environment("local")

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env.str(
    "DJANGO_SECRET_KEY",
    default="insecure-development-key-local-only-do-not-deploy",
)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]", "backend", "testserver"],
)

# Plain HTTP on localhost: cookies cannot be Secure or the browser drops them.
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:3000", "http://127.0.0.1:3000"]
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]

# --- Database connections --------------------------------------------------
# `runserver` handles each request on a new thread from an unbounded pool, and a
# persistent connection is held per thread. Under any real concurrency that
# exhausts PostgreSQL's `max_connections` and every request starts failing with
# "sorry, too many clients already".
#
# Deployed environments keep persistent connections because gunicorn's worker
# and thread counts are fixed, so the ceiling is knowable. See
# `config/settings/hardened.py` for the sizing rule.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=0)

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Local/test environments may create fake demo data.
ALLOW_DEMO_SEED = True
