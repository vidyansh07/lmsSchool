"""Error responses are uniform and leak nothing."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import GENERIC_SERVER_ERROR, api_exception_handler


def _envelope_is_valid(body: dict) -> bool:
    error = body.get("error", {})
    return {"code", "message", "request_id"} <= set(error)


@pytest.mark.django_db
def test_not_found_uses_the_shared_envelope(client):
    response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert _envelope_is_valid(response.json())


@pytest.mark.django_db
def test_validation_errors_include_field_details(api_client_no_csrf):
    response = api_client_no_csrf.post("/api/v1/auth/login/", {"email": "not-an-email"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "email" in body["error"]["details"]
    assert "password" in body["error"]["details"]


@pytest.mark.django_db
def test_method_not_allowed_is_wrapped(api_client_no_csrf):
    response = api_client_no_csrf.delete("/api/v1/auth/login/")
    assert response.status_code == 405
    assert _envelope_is_valid(response.json())


def test_unhandled_exceptions_never_leak_internals():
    """A crash returns a generic message plus a request id — nothing else."""
    factory = APIRequestFactory()
    request = factory.get("/api/v1/boom/")
    response = api_exception_handler(
        RuntimeError("secret db dsn postgres://u:p@h/db"), {"request": request}
    )
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = response.data
    assert body["error"]["message"] == GENERIC_SERVER_ERROR
    assert "postgres://" not in str(body)
    assert "RuntimeError" not in str(body)


def test_validation_error_shape():
    response = api_exception_handler(ValidationError({"field": ["bad"]}), {"request": None})
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"field": ["bad"]}


@pytest.mark.django_db
def test_authentication_error_message_is_not_mislabelled(api_client_no_csrf):
    """A 401/403 must not be reported to the client as a validation failure."""
    response = api_client_no_csrf.get("/api/v1/users/")
    body = response.json()["error"]
    assert body["code"] in ("authentication_required", "permission_denied")
    assert body["message"] != "The submitted data is invalid."
    assert body.get("details") is None


@pytest.mark.django_db
def test_permission_denied_message_is_specific(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get("/api/v1/users/").json()["error"]
    assert body["code"] == "permission_denied"
    assert "role" in body["message"].lower()
