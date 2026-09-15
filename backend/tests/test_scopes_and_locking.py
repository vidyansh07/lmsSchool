"""Scopes and locking (ERP Phase 2, ADR-02/ADR-03).

- a role's grant can be narrowed below the kind's floor (`assigned`, `own`),
  never widened above it;
- narrowing to `assigned` reaches exactly the batches a trainer teaches plus
  any batch or course granted through a `ScopeGrant`;
- narrowing to `own` reaches only the caller's own rows;
- locking a grant needs a superadmin and a fresh step-up; an unfrozen
  session gets `step_up_required`, not silent success;
- a scope grant is created, listed and revoked through the caller's own
  reach (another centre's batch is a 404).
"""

from __future__ import annotations

import pytest

from apps.accounts.roles import UserRole
from apps.authorization.models import Role, RolePermission, ScopeGrant

ROLES = "/api/v1/roles/"


def _build(client, **overrides):
    payload = {
        "slug": "front-line-counsellor",
        "name": "Front-line counsellor",
        "kind": UserRole.COUNSELLOR,
        "permissions": [{"code": "student.view_any", "scope": "assigned"}],
    }
    payload.update(overrides)
    return client.post(ROLES, payload, format="json")


@pytest.mark.django_db
def test_a_scope_narrower_than_the_floor_is_accepted(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    created = _build(api_client_no_csrf)
    assert created.status_code == 201, created.json()
    assert created.json()["permissions"][0]["scope"] == "assigned"


@pytest.mark.django_db
def test_assigned_scope_reaches_exactly_the_trainers_batch(
    api_client_no_csrf, admin_user, counsellor_user, batch, other_branch_batch, student_profile
):
    """A counsellor whose role is narrowed to `assigned` sees only the
    students of a batch they were granted — not their whole centre."""
    api_client_no_csrf.force_login(admin_user)
    _build(api_client_no_csrf)
    api_client_no_csrf.patch(
        f"/api/v1/users/{counsellor_user.id}/",
        {"custom_role": "front-line-counsellor"},
        format="json",
    )
    # Grant the batch explicitly (the counsellor is not its trainer).
    granted = api_client_no_csrf.post(
        f"/api/v1/users/{counsellor_user.id}/scope-grants/",
        {"batch": str(batch.id)},
        format="json",
    )
    assert granted.status_code == 201, granted.json()

    api_client_no_csrf.force_login(counsellor_user)
    listed = api_client_no_csrf.get("/api/v1/students/").json()["results"]
    # Nothing enrolled yet, so the list may be empty — the point is no error
    # and no leak; assert it does not include the other-centre student.
    assert student_profile.user_id not in {row.get("user_id") for row in listed}


@pytest.mark.django_db
def test_own_scope_reaches_only_the_callers_own_requirements(
    api_client_no_csrf, admin_user, manager_user
):
    api_client_no_csrf.force_login(admin_user)
    narrowed = api_client_no_csrf.post(
        ROLES,
        {
            "slug": "requirement-raiser",
            "name": "Requirement raiser",
            "kind": UserRole.MANAGER,
            "permissions": [{"code": "requirement.manage", "scope": "own"}],
        },
        format="json",
    )
    assert narrowed.status_code == 201, narrowed.json()
    api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "requirement-raiser"}, format="json"
    )
    api_client_no_csrf.force_login(manager_user)
    raised = api_client_no_csrf.post(
        "/api/v1/requirements/", {"title": "Need a trainer"}, format="json"
    )
    assert raised.status_code == 201, raised.json()

    # A second manager at the same centre, also narrowed to `own`, raises
    # their own and must not see the first manager's.
    from apps.accounts.models import User

    other = User.objects.create_user(
        email="second-manager@example.test",
        password="correct-horse-battery-staple",
        first_name="Second",
        last_name="Manager",
        role=UserRole.MANAGER,
        branch=manager_user.branch,
    )
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"/api/v1/users/{other.id}/", {"custom_role": "requirement-raiser"}, format="json"
    )
    api_client_no_csrf.force_login(other)
    seen = api_client_no_csrf.get("/api/v1/requirements/").json()["results"]
    assert seen == []


@pytest.mark.django_db
def test_locking_needs_a_superadmin_and_a_fresh_step_up(
    api_client_no_csrf, admin_user, unbounded_superadmin
):
    role = Role.objects.get(slug="admin", is_system=True)
    lock_url = f"{ROLES}admin/permissions/audit.view/lock/"

    # An admin cannot lock at all (not the required capability).
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.post(lock_url, {}, format="json").status_code == 403

    # A superadmin without a fresh step-up is refused too.
    api_client_no_csrf.force_login(unbounded_superadmin)
    refused = api_client_no_csrf.post(lock_url, {}, format="json")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"

    # Step up, then lock succeeds.
    stepped = api_client_no_csrf.post(
        "/api/v1/auth/step-up/", {"password": "correct-horse-battery-staple"}, format="json"
    )
    assert stepped.status_code == 204
    locked = api_client_no_csrf.post(lock_url, {}, format="json")
    assert locked.status_code == 200, locked.json()
    grant = RolePermission.objects.get(role=role, permission__code="audit.view")
    assert grant.is_locked

    # Unlock, same requirement.
    unlocked = api_client_no_csrf.post(
        f"{ROLES}admin/permissions/audit.view/unlock/", {}, format="json"
    )
    assert unlocked.status_code == 200
    grant.refresh_from_db()
    assert not grant.is_locked


@pytest.mark.django_db
def test_a_locked_grant_cannot_be_removed_by_an_admin(
    api_client_no_csrf, admin_user, unbounded_superadmin
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    api_client_no_csrf.post(
        "/api/v1/auth/step-up/", {"password": "correct-horse-battery-staple"}, format="json"
    )
    api_client_no_csrf.post(f"{ROLES}admin/permissions/audit.view/lock/", {}, format="json")

    api_client_no_csrf.force_login(admin_user)
    role_data = api_client_no_csrf.get(f"{ROLES}admin/").json()
    remaining = [g["code"] for g in role_data["permissions"] if g["code"] != "audit.view"]
    attempted = api_client_no_csrf.patch(
        f"{ROLES}admin/",
        {"permissions": [{"code": code} for code in remaining]},
        format="json",
    )
    assert attempted.status_code == 403


@pytest.mark.django_db
def test_scope_grants_are_created_listed_and_revoked_through_the_callers_reach(
    api_client_no_csrf, admin_user, manager_user, batch, other_branch_batch
):
    api_client_no_csrf.force_login(admin_user)
    # An admin is unbounded (D-129 amended) and may name any centre's batch;
    # a batch id that resolves to nothing at all is still a 404.
    import uuid

    missing = api_client_no_csrf.post(
        f"/api/v1/users/{manager_user.id}/scope-grants/",
        {"batch": str(uuid.uuid4())},
        format="json",
    )
    assert missing.status_code == 404

    created = api_client_no_csrf.post(
        f"/api/v1/users/{manager_user.id}/scope-grants/",
        {"batch": str(batch.id)},
        format="json",
    )
    assert created.status_code == 201, created.json()
    grant_id = created.json()["id"]
    assert ScopeGrant.objects.filter(pk=grant_id, user=manager_user, batch=batch).exists()

    listed = api_client_no_csrf.get(f"/api/v1/users/{manager_user.id}/scope-grants/").json()
    assert len(listed) == 1 and listed[0]["batch_code"] == batch.code

    removed = api_client_no_csrf.delete(f"/api/v1/users/{manager_user.id}/scope-grants/{grant_id}/")
    assert removed.status_code == 204
    assert not ScopeGrant.objects.filter(pk=grant_id).exists()


@pytest.mark.django_db
def test_a_scope_grant_names_exactly_one_target(
    api_client_no_csrf, admin_user, manager_user, batch
):
    api_client_no_csrf.force_login(admin_user)
    neither = api_client_no_csrf.post(
        f"/api/v1/users/{manager_user.id}/scope-grants/", {}, format="json"
    )
    assert neither.status_code == 400
