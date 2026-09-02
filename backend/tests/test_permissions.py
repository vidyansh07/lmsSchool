"""Authorization is enforced on the server, for every role."""

from __future__ import annotations

import pytest

USERS_URL = "/api/v1/users/"


@pytest.mark.django_db
def test_anonymous_callers_are_refused(api_client_no_csrf):
    assert api_client_no_csrf.get(USERS_URL).status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["student", "trainer"])
def test_non_admin_roles_are_refused(api_client_no_csrf, request, fixture_name):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture_name))
    response = api_client_no_csrf.get(USERS_URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_admin_role_is_allowed_and_response_is_paginated(api_client_no_csrf, admin_user, student):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(USERS_URL)
    assert response.status_code == 200
    body = response.json()
    assert {"count", "page", "page_size", "total_pages", "results"} <= set(body)
    assert body["count"] == 2
    assert all("password" not in entry for entry in body["results"])


@pytest.mark.django_db
def test_page_size_is_capped(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{USERS_URL}?page_size=10000").json()
    assert body["page_size"] <= 100


@pytest.mark.django_db
def test_deactivated_user_loses_access_immediately(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(USERS_URL).status_code == 200
    admin_user.is_active = False
    admin_user.save()
    assert api_client_no_csrf.get(USERS_URL).status_code in (401, 403)


@pytest.mark.django_db
def test_role_cannot_be_escalated_through_the_api(api_client_no_csrf, student):
    """No Phase 0 endpoint accepts a client-supplied role."""
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get("/api/v1/auth/me/")
    assert response.json()["role"] == "student"
    # The user serializer is read-only end to end.
    from apps.accounts.serializers import UserSerializer

    assert set(UserSerializer.Meta.read_only_fields) == set(UserSerializer.Meta.fields)
