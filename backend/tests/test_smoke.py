"""Phase 0 smoke tests.

These correspond one-to-one with the foundation guarantees: the backend
starts, the database connects, the API answers, and the health endpoint works.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.urls import reverse


def test_backend_boots_and_settings_are_consistent(settings):
    """The application object loads and reports the expected environment."""
    assert settings.ENVIRONMENT == "test"
    assert settings.AUTH_USER_MODEL == "accounts.User"


@pytest.mark.django_db
def test_database_connection_is_postgresql():
    """The test database is real PostgreSQL, not a SQLite stand-in."""
    assert "postgresql" in connection.settings_dict["ENGINE"]
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


def test_api_root_lists_versions(client):
    response = client.get("/api/")
    assert response.status_code == 200
    body = response.json()
    assert body["versions"]["v1"] == "/api/v1/"
    # The discovery document must not leak configuration.
    assert "DATABASES" not in response.content.decode()


@pytest.mark.django_db
def test_openapi_schema_is_generated(client):
    response = client.get(reverse("schema"))
    assert response.status_code == 200
    assert b"openapi" in response.content


def test_request_id_header_is_returned(client):
    response = client.get("/api/")
    assert response["X-Request-ID"]


def test_supplied_request_id_is_echoed_when_well_formed(client):
    response = client.get("/api/", headers={"x-request-id": "abc-123-def-456"})
    assert response["X-Request-ID"] == "abc-123-def-456"


def test_malformed_request_id_is_replaced(client):
    """A hostile id must never be reflected into headers or logs."""
    response = client.get("/api/", headers={"x-request-id": "bad\r\nInjected: 1"})
    assert response["X-Request-ID"] != "bad\r\nInjected: 1"
