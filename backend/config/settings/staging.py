"""Staging settings.

Staging is production with a different blast radius: identical security
posture, separate database, separate secrets, separate storage, and fake seed
data only. It is the last gate before a production release.
"""

from .guards import require_environment
from .hardened import *
from .hardened import configure_error_reporting, env

ENVIRONMENT = require_environment("staging")

# Reviewers use the interactive docs here and all staging data is fake.
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)

# Shorter HSTS window and no preload so a staging hostname stays reclaimable.
# Browser preload submission is effectively permanent, which is wrong for an
# environment that gets torn down and rebuilt. W021 is silenced for that
# reason, and only here — production keeps preload enabled.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Guards `manage.py seed_demo_data`: fake demo accounts may only exist here.
ALLOW_DEMO_SEED = True

configure_error_reporting(ENVIRONMENT)
