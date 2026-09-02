"""ASGI entry point.

Present so async workers or websockets can be adopted later without a project
restructure. The WSGI path is what the Phase 0 stack actually runs.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
