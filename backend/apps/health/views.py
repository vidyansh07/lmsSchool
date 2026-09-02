"""Health endpoints.

``/health/live/``  — process is up. Never touches dependencies, so a database
                     blip cannot cause the orchestrator to kill healthy pods.
``/health/ready/`` — the instance can serve traffic: every registered
                     dependency check passed.

Both are unauthenticated (probes cannot hold credentials) and therefore expose
no configuration: no hostnames, no versions of dependencies, no settings.

Both are also exempt from ``ATOMIC_REQUESTS``: a probe must not open a database
transaction, or a database hiccup would fail liveness and get healthy instances
restarted.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from . import checks


@transaction.non_atomic_requests
@require_GET
@never_cache
def liveness(_request) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": settings.PROJECT_NAME})


# Readiness queries the database through the check registry but must not
# hold a transaction open while doing so.
@transaction.non_atomic_requests
@require_GET
@never_cache
def readiness(_request) -> JsonResponse:
    # Resolved at call time so newly registered checks are picked up.
    results = [check() for check in checks.READINESS_CHECKS]
    healthy = all(result.healthy for result in results)
    return JsonResponse(
        {
            "status": "ok" if healthy else "degraded",
            "checks": {result.name: result.as_dict() for result in results},
        },
        status=200 if healthy else 503,
    )
