"""Shared development server settings (deployed, network-reachable).

Production-shaped security with developer-friendly diagnostics: DEBUG stays
off and cookies stay Secure because this environment is reachable over the
network, but API docs are on and the log level is verbose.
"""

from .guards import require_environment
from .hardened import *
from .hardened import configure_error_reporting, env

ENVIRONMENT = require_environment("development")

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_PRELOAD = False
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="DEBUG")
LOGGING["root"]["level"] = LOG_LEVEL

ALLOW_DEMO_SEED = True

configure_error_reporting(ENVIRONMENT)
