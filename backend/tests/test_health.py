"""Health endpoint behaviour."""

from __future__ import annotations

import pytest
from django.urls import reverse


def test_liveness_does_not_touch_the_database(client):
    """No ``db`` fixture on purpose.

    pytest-django blocks database access in tests that do not request it, so a
    passing call here proves liveness never opens a connection — including the
    transaction ATOMIC_REQUESTS would otherwise start.
    """
    response = client.get(reverse("health:live"))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_probe_views_are_exempt_from_atomic_requests():
    from apps.health import views

    for view in (views.liveness, views.readiness):
        assert "default" in getattr(view, "_non_atomic_requests", set())


@pytest.mark.django_db
def test_readiness_reports_each_component(client):
    response = client.get(reverse("health:ready"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["cache"]["status"] == "ok"


@pytest.mark.django_db
def test_readiness_returns_503_when_a_dependency_fails(client, monkeypatch):
    from apps.health import checks

    def broken() -> checks.CheckResult:
        return checks.CheckResult("database", False, "unavailable", 1.0)

    monkeypatch.setattr(checks, "READINESS_CHECKS", [broken])
    response = client.get(reverse("health:ready"))
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.django_db
def test_health_response_exposes_no_configuration(client, settings):
    body = client.get(reverse("health:ready")).content.decode()
    for secret in (settings.SECRET_KEY, str(settings.DATABASES["default"].get("PASSWORD", "x"))):
        assert secret not in body
    for leaky in ("ENGINE", "HOST", "NAME", "postgres://", "password"):
        assert leaky not in body


def test_cache_backend_client_is_installed(settings):
    """Deployed environments require CACHE_URL, so the Redis client must ship.

    Regression guard: a missing client only shows up as a failing readiness
    probe after deployment, which is far too late.
    """
    import importlib.util

    assert importlib.util.find_spec("redis") is not None, (
        "The `redis` package is required by django.core.cache.backends.redis.RedisCache, "
        "which every deployed environment uses via CACHE_URL."
    )
