"""Production settings — the strictest configuration. Fails closed."""

from .guards import require_environment
from .hardened import *
from .hardened import configure_error_reporting, env

ENVIRONMENT = require_environment("production")

# Interactive docs are off unless explicitly enabled; the schema is still
# generated and published from CI for API consumers.
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

# Demo/fake data seeding is never permitted here.
ALLOW_DEMO_SEED = False

configure_error_reporting(ENVIRONMENT)
