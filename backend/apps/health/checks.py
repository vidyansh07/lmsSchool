"""Health check registry.

Adding a dependency later (Redis, a Celery worker, object storage) means
writing one function and appending it to ``READINESS_CHECKS`` — no change to
the view, the URL or the response contract.

Checks return a component name, a boolean, and a short human-readable status.
They deliberately never return connection strings, hostnames, credentials or
version details: a health endpoint is usually reachable without authentication
and must not become a reconnaissance surface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from django.conf import settings
from django.core.cache import cache
from django.db import connections

logger = logging.getLogger("grras.health")

_CACHE_PROBE_KEY = "health:probe"


@dataclass(frozen=True)
class CheckResult:
    name: str
    healthy: bool
    detail: str
    duration_ms: float

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.healthy else "error",
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 2),
        }


def _timed(name: str, probe: Callable[[], str]) -> CheckResult:
    started = perf_counter()
    try:
        detail = probe()
        healthy = True
    except Exception:
        # Full detail goes to the log; the response stays generic.
        logger.exception("Health check failed", extra={"context": {"check": name}})
        detail = "unavailable"
        healthy = False
    return CheckResult(name, healthy, detail, (perf_counter() - started) * 1000)


def check_database() -> CheckResult:
    """Round-trip a trivial query on the default connection."""

    def probe() -> str:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "connected"

    return _timed("database", probe)


def check_cache() -> CheckResult:
    """Write/read/delete a probe key.

    With the local-memory backend this only proves the process is sane; once
    CACHE_URL points at Redis it becomes a real dependency check, and rate
    limiting depends on it.
    """

    def probe() -> str:
        cache.set(_CACHE_PROBE_KEY, "1", timeout=10)
        if cache.get(_CACHE_PROBE_KEY) != "1":
            raise RuntimeError("cache round-trip failed")
        cache.delete(_CACHE_PROBE_KEY)
        return "reachable" if settings.CACHE_URL else "local"

    return _timed("cache", probe)


#: Readiness = "can this instance serve traffic right now?"
#: Extend with the worker, broker and object-storage probes as they are added.
READINESS_CHECKS: list[Callable[[], CheckResult]] = [check_database, check_cache]
