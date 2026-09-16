"""`GET /saved-filters/?screen=` · `POST` · `DELETE /saved-filters/{id}/`
(ERP Phase 11, `API_CONTRACTS.md` "Search and productivity",
`DATA_MODEL.md` `SavedFilter`).

The one thing this suite exists to prove: a saved filter is scoped to
exactly one row per owner, never a capability tier — a user only ever
sees or deletes their *own* rows, including against a guessed id, and this
holds for an administrator exactly as it holds for anyone else. `POST` is
also proven idempotent by `(screen, name)`, per `saved_filters.save_filter`'s
documented reading of the terse contract.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/saved-filters/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _detail_url(filter_id) -> str:
    return f"/api/v1/saved-filters/{filter_id}/"


def _save(user, *, screen="students-list", name="My filter", filters=None):
    body = {"screen": screen, "name": name, "filters": filters or {"fee_status": "pending"}}
    return _client(user).post(LIST_URL, body, format="json")


# ---------------------------------------------------------------------------
# Create / list
# ---------------------------------------------------------------------------


def test_a_user_creates_and_lists_their_own_filter(admin_user):
    response = _save(admin_user)
    assert response.status_code == 201
    body = response.json()
    assert body["screen"] == "students-list"
    assert body["name"] == "My filter"
    assert body["filters"] == {"fee_status": "pending"}
    assert "user" not in body

    listed = _client(admin_user).get(LIST_URL).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_the_screen_query_param_narrows_the_list(admin_user):
    _save(admin_user, screen="students-list", name="A")
    _save(admin_user, screen="batches-list", name="B")

    listed = _client(admin_user).get(f"{LIST_URL}?screen=students-list").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "A"


def test_re_saving_the_same_screen_and_name_upserts_rather_than_duplicates(admin_user):
    """`API_CONTRACTS.md` gives this one terse line and no explicit conflict
    rule; `saved_filters.save_filter` reads a re-save under the same
    `(screen, name)` as an update, the way a named preset ordinarily behaves
    — not a 409 demanding the old one be deleted first."""
    from apps.reporting.models import SavedFilter

    first = _save(admin_user, filters={"fee_status": "pending"})
    second = _save(admin_user, filters={"fee_status": "paid"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["filters"] == {"fee_status": "paid"}
    assert SavedFilter.objects.filter(user=admin_user, screen="students-list").count() == 1


def test_the_same_name_on_a_different_screen_is_a_separate_row(admin_user):
    _save(admin_user, screen="students-list", name="Same name")
    _save(admin_user, screen="batches-list", name="Same name")

    from apps.reporting.models import SavedFilter

    assert SavedFilter.objects.filter(user=admin_user, name="Same name").count() == 2


def test_an_unknown_field_is_rejected(admin_user):
    response = _client(admin_user).post(
        LIST_URL,
        {"screen": "students-list", "name": "X", "filters": {}, "not_a_real_field": 1},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Per-user isolation — the one place "scope" means literally one row
# ---------------------------------------------------------------------------


def test_a_user_never_sees_another_users_saved_filter(admin_user, manager_user):
    _save(admin_user, name="Admin's filter")
    _save(manager_user, name="Manager's filter")

    admin_listed = _client(admin_user).get(LIST_URL).json()
    manager_listed = _client(manager_user).get(LIST_URL).json()

    assert [row["name"] for row in admin_listed] == ["Admin's filter"]
    assert [row["name"] for row in manager_listed] == ["Manager's filter"]


def test_a_user_cannot_delete_another_users_filter_even_with_a_guessed_id(admin_user, manager_user):
    created = _save(manager_user, name="Manager's filter").json()

    response = _client(admin_user).delete(_detail_url(created["id"]))
    assert response.status_code == 404

    from apps.reporting.models import SavedFilter

    assert SavedFilter.objects.filter(pk=created["id"]).exists()


def test_an_administrator_does_not_get_a_broader_reach_than_anyone_else(admin_user, manager_user):
    """Scope here is `user=request.user`, never a capability tier — holding
    `student.view_any` or any other administrator capability must not widen
    what saved filters an administrator may see or delete."""
    created = _save(manager_user, name="Manager's private filter").json()

    admin_listed = _client(admin_user).get(LIST_URL).json()
    assert admin_listed == []

    response = _client(admin_user).delete(_detail_url(created["id"]))
    assert response.status_code == 404


def test_the_owner_deletes_their_own_filter(admin_user):
    created = _save(admin_user).json()

    response = _client(admin_user).delete(_detail_url(created["id"]))
    assert response.status_code == 204

    from apps.reporting.models import SavedFilter

    assert not SavedFilter.objects.filter(pk=created["id"]).exists()


def test_deleting_a_nonexistent_id_is_a_404(admin_user):
    import uuid

    response = _client(admin_user).delete(_detail_url(uuid.uuid4()))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_saved_filters_require_authentication():
    client = APIClient()
    assert client.get(LIST_URL).status_code in (401, 403)
    assert client.post(LIST_URL, {}, format="json").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_saving_and_deleting_a_filter_is_audited(admin_user):
    from apps.audit.models import AuditAction, AuditLog

    created = _save(admin_user).json()
    assert AuditLog.objects.filter(
        action=AuditAction.SAVED_FILTER_CREATED, actor=admin_user
    ).exists()

    _client(admin_user).delete(_detail_url(created["id"]))
    assert AuditLog.objects.filter(
        action=AuditAction.SAVED_FILTER_DELETED, actor=admin_user
    ).exists()
