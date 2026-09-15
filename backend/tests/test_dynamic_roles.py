"""Roles as rows (ERP Phase 1, ADR-01).

- the seed reproduces the code matrix exactly, so nothing changes on day one;
- the catalog rows equal the enum both ways, and the sync command keeps it so;
- an administrator builds a custom role narrower than a manager and assigns
  it; the holder's capabilities are the custom set, cached, and revoked on
  the next request after a change;
- the ladder holds: a manager cannot build or assign a role wider than
  themselves (403, not 400); superadmin-only codes are refused on other
  kinds; a wider scope than the kind's floor is refused;
- a system role keeps its name and cannot be removed; a role with holders
  cannot be removed; a removed role sits in the bin;
- the matrix names the five states.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.accounts.roles import ROLE_CAPABILITIES, Capability, UserRole, capabilities_for
from apps.authorization.models import Permission, Role, RolePermission

ROLES = "/api/v1/roles/"


@pytest.mark.django_db
def test_the_seed_reproduces_the_code_matrix():
    for kind, expected in ROLE_CAPABILITIES.items():
        role = Role.objects.get(slug=kind, is_system=True)
        assert role.codes == frozenset(expected), kind
        assert capabilities_for(kind) == frozenset(expected), kind


@pytest.mark.django_db
def test_the_catalog_equals_the_enum_both_ways():
    rows = set(Permission.objects.filter(is_active=True).values_list("code", flat=True))
    assert rows == set(Capability.values)
    call_command("sync_permissions")  # idempotent
    assert Permission.objects.filter(is_active=True).count() == len(Capability.values)
    assert Role.objects.filter(is_system=True).count() == 6


@pytest.mark.django_db
def test_superadmin_only_codes_are_locked_and_absent_elsewhere():
    purge = Permission.objects.get(code="record.purge")
    grants = RolePermission.objects.filter(permission=purge)
    assert {g.role.slug for g in grants} == {"superadmin"}
    assert grants.get().is_locked


def _custom(client, **overrides):
    payload = {
        "slug": "placement-coordinator",
        "name": "Placement coordinator",
        "kind": UserRole.MANAGER,
        "description": "Runs placement work; no fees.",
        "permissions": [
            {"code": code}
            for code in sorted(ROLE_CAPABILITIES[UserRole.MANAGER] - {"dsr.view_any", "dsr.review"})
        ],
    }
    payload.update(overrides)
    return client.post(ROLES, payload, format="json")


@pytest.mark.django_db
def test_an_administrator_builds_a_narrower_role_and_assigns_it(
    api_client_no_csrf, admin_user, manager_user
):
    api_client_no_csrf.force_login(admin_user)
    created = _custom(api_client_no_csrf)
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["kind"] == "manager" and body["is_system"] is False
    codes = {row["code"] for row in body["permissions"]}
    assert "dsr.view_any" not in codes and "batch.view_any" in codes

    # Assign it: the holder's set becomes the custom set.
    assigned = api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "placement-coordinator"}, format="json"
    )
    assert assigned.status_code == 200, assigned.json()
    assert assigned.json()["custom_role"] == "placement-coordinator"
    manager_user.refresh_from_db()
    assert "dsr.view_any" not in manager_user.capabilities
    assert "batch.view_any" in manager_user.capabilities

    # The refusal is real, not cosmetic.
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.get("/api/v1/dsr/").status_code == 403
    assert api_client_no_csrf.get("/api/v1/batches/").status_code == 200

    # Widening the role reaches the holder on their next request.
    api_client_no_csrf.force_login(admin_user)
    widened = api_client_no_csrf.patch(
        f"{ROLES}placement-coordinator/",
        {"permissions": [{"code": code} for code in sorted(codes | {"dsr.view_any"})]},
        format="json",
    )
    assert widened.status_code == 200, widened.json()
    manager_user.refresh_from_db()
    assert "dsr.view_any" in manager_user.capabilities
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.get("/api/v1/dsr/").status_code == 200


@pytest.mark.django_db
def test_the_ladder_holds_for_custom_roles(api_client_no_csrf, admin_user, manager_user):
    # A manager holds role.view? No — only admins manage roles at all.
    api_client_no_csrf.force_login(manager_user)
    assert _custom(api_client_no_csrf).status_code == 403

    # An administrator cannot build a role holding what they do not.
    api_client_no_csrf.force_login(admin_user)
    wider = _custom(
        api_client_no_csrf,
        slug="too-wide",
        kind=UserRole.ADMIN,
        permissions=[{"code": "platform.configure"}],
    )
    assert wider.status_code == 400  # superadmin-only on a non-superadmin kind
    assert "platform.configure" in str(wider.json())

    beyond = _custom(
        api_client_no_csrf,
        slug="beyond",
        kind=UserRole.ADMIN,
        permissions=[{"code": "record.view_deleted"}, {"code": "audit.view"}],
    )
    assert beyond.status_code == 201  # admins hold both
    # A scope wider than the kind's floor is refused.
    scoped = _custom(
        api_client_no_csrf,
        slug="everywhere-manager",
        permissions=[{"code": "student.view_any", "scope": "all"}],
    )
    assert scoped.status_code == 400
    assert "wider" in str(scoped.json())

    # A custom role of another kind cannot be put on this account.
    ok = _custom(api_client_no_csrf, slug="front-desk", kind=UserRole.COUNSELLOR, permissions=[])
    assert ok.status_code == 201
    mismatch = api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "front-desk"}, format="json"
    )
    assert mismatch.status_code == 400
    assert "custom_role" in mismatch.json()["error"]["details"]


@pytest.mark.django_db
def test_a_manager_with_a_custom_role_cannot_grant_more_than_it(
    api_client_no_csrf, admin_user, manager_user, counsellor_user
):
    """The ladder compares effective sets: a narrowed manager cannot hand a
    counsellor the full counsellor kind (which now holds more than them)."""
    api_client_no_csrf.force_login(admin_user)
    narrow = _custom(
        api_client_no_csrf,
        slug="narrow-manager",
        permissions=[{"code": "student.view_any"}, {"code": "user.view_any"}],
    )
    assert narrow.status_code == 201
    api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "narrow-manager"}, format="json"
    )
    manager_user.refresh_from_db()
    from apps.accounts.roles import can_administer, can_grant_role

    assert not can_grant_role(manager_user, UserRole.COUNSELLOR)
    assert not can_administer(manager_user, counsellor_user)


@pytest.mark.django_db
def test_system_roles_are_protected_and_holders_block_removal(
    api_client_no_csrf, admin_user, manager_user, unbounded_superadmin
):
    api_client_no_csrf.force_login(admin_user)
    renamed = api_client_no_csrf.patch(f"{ROLES}manager/", {"name": "Boss"}, format="json")
    assert renamed.status_code == 400
    described = api_client_no_csrf.patch(
        f"{ROLES}manager/", {"description": "Runs a centre."}, format="json"
    )
    assert described.status_code == 200 and described.json()["description"] == "Runs a centre."
    removed = api_client_no_csrf.delete(f"{ROLES}manager/", {"reason": "no"}, format="json")
    assert removed.status_code == 400

    assert _custom(api_client_no_csrf).status_code == 201
    api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "placement-coordinator"}, format="json"
    )
    blocked = api_client_no_csrf.delete(
        f"{ROLES}placement-coordinator/", {"reason": "done"}, format="json"
    )
    assert blocked.status_code == 409
    api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": None}, format="json"
    )
    gone = api_client_no_csrf.delete(
        f"{ROLES}placement-coordinator/", {"reason": "done"}, format="json"
    )
    assert gone.status_code == 204
    assert not Role.objects.filter(slug="placement-coordinator").exists()
    assert Role.all_objects.get(slug="placement-coordinator").delete_reason == "done"

    # The superadmin role is locked; only a superadmin edits it.
    locked = api_client_no_csrf.patch(f"{ROLES}superadmin/", {"description": "x"}, format="json")
    assert locked.status_code == 403
    api_client_no_csrf.force_login(unbounded_superadmin)
    assert (
        api_client_no_csrf.patch(
            f"{ROLES}superadmin/", {"description": "x"}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_the_matrix_names_the_five_states(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    _custom(
        api_client_no_csrf,
        slug="auditor",
        kind=UserRole.MANAGER,
        permissions=[{"code": "audit.view"}]
        if "audit.view" in ROLE_CAPABILITIES[UserRole.ADMIN]
        else [],
    )
    body = api_client_no_csrf.get(f"{ROLES}matrix/").json()
    cells = body["cells"]
    assert cells["superadmin"]["record.purge"] == "system"
    assert cells["admin"]["record.purge"] == "denied"
    assert cells["manager"]["batch.view_any"] == "inherited"
    assert cells["auditor"]["audit.view"] == "explicit"
    assert cells["auditor"]["batch.view_any"] == "denied"
    assert {row["slug"] for row in body["roles"]} >= {"superadmin", "admin", "manager", "auditor"}
    assert len(body["permissions"]) == len(Capability.values)


@pytest.mark.django_db
def test_a_disabled_custom_role_falls_back_to_the_kind(
    api_client_no_csrf, admin_user, manager_user
):
    api_client_no_csrf.force_login(admin_user)
    _custom(api_client_no_csrf)
    api_client_no_csrf.patch(
        f"/api/v1/users/{manager_user.id}/", {"custom_role": "placement-coordinator"}, format="json"
    )
    manager_user.refresh_from_db()
    assert "dsr.view_any" not in manager_user.capabilities
    api_client_no_csrf.patch(
        f"{ROLES}placement-coordinator/", {"status": "disabled"}, format="json"
    )
    manager_user.refresh_from_db()
    assert "dsr.view_any" in manager_user.capabilities  # the system manager set


@pytest.mark.django_db
def test_the_switch_falls_back_to_the_code_matrix(settings, admin_user, manager_user):
    settings.DYNAMIC_ROLES_ENABLED = False
    from django.core.cache import cache

    cache.clear()
    assert manager_user.capabilities == ROLE_CAPABILITIES[UserRole.MANAGER]
