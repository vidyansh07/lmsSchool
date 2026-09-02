"""Mandatory Phase 1 security tests.

Each test here corresponds to a specific attack. They are grouped by the OWASP
category they defend so a reviewer can map the suite to the threat model.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import UserRole
from apps.accounts.roles import Capability, capabilities_for
from tests.conftest import TEST_PASSWORD

USERS_URL = "/api/v1/users/"
STUDENTS_URL = "/api/v1/students/"
TRAINERS_URL = "/api/v1/trainers/"
ME_URL = "/api/v1/auth/me/"


# ---------------------------------------------------------------------------
# Broken access control
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [USERS_URL, STUDENTS_URL, TRAINERS_URL, ME_URL, "/api/v1/students/me/", "/api/v1/trainers/me/"],
)
def test_anonymous_users_cannot_access_protected_endpoints(api_client_no_csrf, url):
    response = api_client_no_csrf.get(url)
    assert response.status_code in (401, 403)
    assert "error" in response.json()


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["student", "trainer"])
def test_non_admins_cannot_list_users(api_client_no_csrf, request, fixture_name):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture_name))
    response = api_client_no_csrf.get(USERS_URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_trainer_cannot_access_admin_functions(api_client_no_csrf, trainer, student):
    """A trainer has no user-administration capability of any kind."""
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(USERS_URL).status_code == 403
    assert (
        api_client_no_csrf.post(
            USERS_URL, {"email": "x@example.test", "first_name": "X", "role": "student"}
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.patch(
            f"{USERS_URL}{student.pk}/", {"first_name": "Hacked"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"{USERS_URL}{student.pk}/set-active/", {"is_active": False}
        ).status_code
        == 403
    )
    assert api_client_no_csrf.get(STUDENTS_URL).status_code == 403


@pytest.mark.django_db
def test_student_cannot_list_students_or_trainers(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(STUDENTS_URL).status_code == 403
    assert api_client_no_csrf.get(TRAINERS_URL).status_code == 403


# ---------------------------------------------------------------------------
# IDOR — insecure direct object references
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_student_cannot_read_another_students_record(
    api_client_no_csrf, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"{STUDENTS_URL}{other_student_profile.pk}/")
    assert response.status_code == 403
    assert other_student_profile.student_id not in response.content.decode()


@pytest.mark.django_db
def test_student_cannot_edit_another_students_record(
    api_client_no_csrf, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        f"{STUDENTS_URL}{other_student_profile.pk}/", {"city": "Tampered"}, format="json"
    )
    assert response.status_code == 403
    other_student_profile.refresh_from_db()
    assert other_student_profile.city != "Tampered"


@pytest.mark.django_db
def test_student_can_read_and_edit_their_own_record_by_id(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(f"{STUDENTS_URL}{student_profile.pk}/").status_code == 200
    response = api_client_no_csrf.patch(
        f"{STUDENTS_URL}{student_profile.pk}/", {"city": "Udaipur"}, format="json"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_student_cannot_read_a_trainer_record(api_client_no_csrf, student, trainer_profile):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get(f"{TRAINERS_URL}{trainer_profile.pk}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_trainer_cannot_read_another_trainers_record(api_client_no_csrf, trainer, trainer_profile):
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(f"{TRAINERS_URL}{trainer_profile.pk}/").status_code == 403


@pytest.mark.django_db
def test_trainer_cannot_read_a_student_record(api_client_no_csrf, trainer, student_profile):
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(f"{STUDENTS_URL}{student_profile.pk}/").status_code == 403


@pytest.mark.django_db
def test_a_missing_record_and_a_forbidden_record_both_refuse(api_client_no_csrf, student_profile):
    """A 404 for one and 403 for the other would leak which ids exist."""
    import uuid

    api_client_no_csrf.force_login(student_profile.user)
    nonexistent = api_client_no_csrf.get(f"{STUDENTS_URL}{uuid.uuid4()}/")
    assert nonexistent.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Privilege escalation / mass assignment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"role": "admin"},
        {"role": "ADMIN"},
        {"is_staff": True},
        {"is_superuser": True},
        {"is_active": False},
        {"is_email_verified": True},
        {"first_name": "Legit", "role": "admin"},
    ],
)
def test_student_cannot_escalate_privileges_through_the_self_endpoint(
    api_client_no_csrf, student, payload
):
    """The exact attack named in the specification: {"role": "ADMIN"}."""
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.patch(ME_URL, payload, format="json")

    assert response.status_code == 400
    offending = set(payload) - {"first_name"}
    assert offending & set(response.json()["error"]["details"])

    student.refresh_from_db()
    assert student.role == UserRole.STUDENT
    assert student.is_staff is False
    assert student.is_superuser is False
    assert student.is_active is True


@pytest.mark.django_db
def test_trainer_cannot_change_their_own_role(api_client_no_csrf, trainer):
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.patch(ME_URL, {"role": "admin"}, format="json")
    assert response.status_code == 400
    trainer.refresh_from_db()
    assert trainer.role == UserRole.TRAINER


@pytest.mark.django_db
def test_student_cannot_set_their_own_fee_status(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        "/api/v1/students/me/", {"fee_status": "paid"}, format="json"
    )
    assert response.status_code == 400
    assert "fee_status" in response.json()["error"]["details"]

    student_profile.refresh_from_db()
    assert student_profile.fee_status == "pending"


@pytest.mark.django_db
def test_student_cannot_call_the_fee_status_endpoint(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"{STUDENTS_URL}{student_profile.pk}/fee-status/", {"fee_status": "paid"}
    )
    assert response.status_code == 403
    student_profile.refresh_from_db()
    assert student_profile.fee_status == "pending"


@pytest.mark.django_db
def test_student_cannot_change_their_own_student_id(api_client_no_csrf, student_profile):
    original = student_profile.student_id
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        "/api/v1/students/me/", {"student_id": "GRS-S-99999"}, format="json"
    )
    assert response.status_code == 400
    student_profile.refresh_from_db()
    assert student_profile.student_id == original


@pytest.mark.django_db
def test_student_cannot_write_internal_notes(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.patch(
        "/api/v1/students/me/", {"notes": "please give me a discount"}, format="json"
    )
    assert response.status_code == 400
    student_profile.refresh_from_db()
    assert student_profile.notes == ""


@pytest.mark.django_db
def test_student_never_sees_internal_notes(api_client_no_csrf, admin_user, student_profile):
    student_profile.notes = "internal: fee follow-up needed"
    student_profile.save()

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/students/me/").content.decode()
    assert "internal: fee follow-up" not in body
    assert "notes" not in body


@pytest.mark.django_db
def test_trainer_cannot_make_themselves_available_for_assignment_fields_they_do_not_own(
    api_client_no_csrf, trainer_profile
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        "/api/v1/trainers/me/", {"is_accepting_assignments": False}, format="json"
    )
    assert response.status_code == 400
    assert "is_accepting_assignments" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_trainer_cannot_change_their_own_trainer_id(api_client_no_csrf, trainer_profile):
    original = trainer_profile.trainer_id
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.patch("/api/v1/trainers/me/", {"trainer_id": "GRS-T-00001"}, format="json")
    trainer_profile.refresh_from_db()
    assert trainer_profile.trainer_id == original


# ---------------------------------------------------------------------------
# Account status
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inactive_users_cannot_authenticate(api_client_no_csrf, student):
    student.is_active = False
    student.save()
    response = api_client_no_csrf.post(
        "/api/v1/auth/login/", {"email": student.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_deactivation_takes_effect_on_the_next_request(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(ME_URL).status_code == 200

    student.is_active = False
    student.save()
    assert api_client_no_csrf.get(ME_URL).status_code in (401, 403)


# ---------------------------------------------------------------------------
# The capability matrix itself
# ---------------------------------------------------------------------------


def test_students_and_trainers_hold_only_self_service_capabilities():
    for role in (UserRole.STUDENT, UserRole.TRAINER):
        capabilities = capabilities_for(role)
        assert capabilities == frozenset(
            {Capability.PROFILE_VIEW_OWN, Capability.PROFILE_UPDATE_OWN}
        ), role


def test_only_admins_hold_management_capabilities():
    admin = capabilities_for(UserRole.ADMIN)
    for capability in (
        Capability.USER_CREATE,
        Capability.USER_SET_ACTIVE,
        Capability.USER_CHANGE_ROLE,
        Capability.STUDENT_SET_FEE_STATUS,
        Capability.TRAINER_UPDATE_ANY,
    ):
        assert capability in admin
        assert capability not in capabilities_for(UserRole.STUDENT)
        assert capability not in capabilities_for(UserRole.TRAINER)


def test_an_unknown_role_gets_no_management_capabilities():
    """Fail closed: a role added to the enum but not the matrix grants nothing."""
    capabilities = capabilities_for("coordinator")
    assert Capability.USER_VIEW_ANY not in capabilities
    assert capabilities == frozenset({Capability.PROFILE_VIEW_OWN, Capability.PROFILE_UPDATE_OWN})


@pytest.mark.django_db
def test_capability_check_refuses_an_inactive_user(student):
    from apps.accounts.roles import has_capability

    student.role = UserRole.ADMIN
    student.is_active = False
    assert has_capability(student, Capability.USER_VIEW_ANY) is False


def test_anonymous_users_hold_no_capabilities():
    from django.contrib.auth.models import AnonymousUser

    from apps.accounts.roles import has_capability

    assert has_capability(AnonymousUser(), Capability.PROFILE_VIEW_OWN) is False
    assert has_capability(None, Capability.USER_VIEW_ANY) is False


@pytest.mark.django_db
def test_a_view_that_declares_no_capability_denies_everyone(admin_user):
    """Fail closed: forgetting `required_capability` must not open a view up."""
    from rest_framework.test import APIRequestFactory

    from apps.common.permissions import HasCapability

    class ViewWithoutCapability:
        pass

    request = APIRequestFactory().get("/")
    request.user = admin_user
    assert HasCapability().has_permission(request, ViewWithoutCapability()) is False


# ---------------------------------------------------------------------------
# The five-role ladder (Phase 4)
# ---------------------------------------------------------------------------


def test_the_capability_ladder_is_monotonic():
    """Superadmin ⊇ admin ⊇ manager. A gap would be a privilege inversion."""
    superadmin = capabilities_for(UserRole.SUPERADMIN)
    admin = capabilities_for(UserRole.ADMIN)
    manager = capabilities_for(UserRole.MANAGER)

    assert manager < admin < superadmin


def test_superadmin_holds_every_capability():
    """A superadmin must never be locked out of a capability added later."""
    assert capabilities_for(UserRole.SUPERADMIN) == frozenset(Capability.values)


def test_a_manager_cannot_change_who_somebody_is():
    """Running the school and granting yourself power stay separate."""
    manager = capabilities_for(UserRole.MANAGER)
    for capability in (
        Capability.USER_CREATE,
        Capability.USER_UPDATE_ANY,
        Capability.USER_SET_ACTIVE,
        Capability.USER_CHANGE_ROLE,
        Capability.PLATFORM_CONFIGURE,
        Capability.ACADEMIC_CONFIGURE,
        Capability.AUDIT_VIEW,
    ):
        assert capability not in manager, capability


def test_a_manager_can_run_academic_operations():
    manager = capabilities_for(UserRole.MANAGER)
    for capability in (
        Capability.STUDENT_CREATE,
        Capability.COURSE_CREATE,
        Capability.BATCH_CREATE,
        Capability.ENROLMENT_CREATE,
        Capability.ENROLMENT_UPDATE_ANY,
    ):
        assert capability in manager, capability


def test_platform_configuration_is_superadmin_only():
    for role in (UserRole.ADMIN, UserRole.MANAGER, UserRole.TRAINER, UserRole.STUDENT):
        assert Capability.PLATFORM_CONFIGURE not in capabilities_for(role), role


def test_trainers_and_students_still_hold_only_self_service_capabilities():
    """Adding roles must not have widened the scoped ones."""
    for role in (UserRole.STUDENT, UserRole.TRAINER):
        assert capabilities_for(role) == frozenset(
            {Capability.PROFILE_VIEW_OWN, Capability.PROFILE_UPDATE_OWN}
        ), role


@pytest.mark.django_db
def test_a_manager_can_reach_academic_endpoints_but_not_user_administration(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    from apps.accounts.models import User

    manager = User.objects.create_user(
        email="manager@example.test",
        password=TEST_PASSWORD,
        first_name="Mia",
        last_name="Manager",
        role=UserRole.MANAGER,
    )
    api_client_no_csrf.force_login(manager)

    # Academic operations: allowed.
    assert api_client_no_csrf.get(STUDENTS_URL).status_code == 200
    assert api_client_no_csrf.get("/api/v1/courses/").status_code == 200
    assert api_client_no_csrf.get("/api/v1/batches/").status_code == 200

    # Changing an account: refused.
    assert (
        api_client_no_csrf.patch(
            f"{USERS_URL}{student_profile.user.id}/", {"role": "admin"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"{USERS_URL}{student_profile.user.id}/set-active/", {"is_active": False}
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_superadmin_reaches_everything_an_admin_can(api_client_no_csrf, student_profile):
    from apps.accounts.models import User

    superadmin = User.objects.create_user(
        email="root@example.test",
        password=TEST_PASSWORD,
        first_name="Root",
        last_name="Operator",
        role=UserRole.SUPERADMIN,
    )
    api_client_no_csrf.force_login(superadmin)

    for url in (USERS_URL, STUDENTS_URL, TRAINERS_URL, "/api/v1/courses/", "/api/v1/batches/"):
        assert api_client_no_csrf.get(url).status_code == 200, url


# ---------------------------------------------------------------------------
# Role granting — nobody hands out authority they do not hold
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_cannot_promote_anybody_to_superadmin(
    api_client_no_csrf, admin_user, student
):
    """The escalation that adding SUPERADMIN in Phase 4 would otherwise open.

    An administrator holds `user.change_role`. Without a containment rule they
    could set a role that grants `platform.configure` — a capability the ladder
    deliberately withholds from them — and then use the promoted account.
    """
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{student.id}/", {"role": "superadmin"}, format="json"
    )

    assert response.status_code == 400
    student.refresh_from_db()
    assert student.role == UserRole.STUDENT


@pytest.mark.django_db
def test_an_administrator_cannot_promote_their_own_account(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{admin_user.id}/", {"role": "superadmin"}, format="json"
    )

    assert response.status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.role == UserRole.ADMIN


@pytest.mark.django_db
def test_an_administrator_may_still_appoint_a_manager(api_client_no_csrf, admin_user, student):
    """A manager holds strictly less than an administrator, so this is allowed."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{student.id}/", {"role": "manager"}, format="json"
    )

    assert response.status_code == 200
    student.refresh_from_db()
    assert student.role == UserRole.MANAGER


@pytest.mark.django_db
def test_a_superadmin_may_appoint_a_superadmin(api_client_no_csrf, db, student):
    from apps.accounts.models import User

    boss = User.objects.create_user(
        email="boss@example.test",
        password="Sup3r-Str0ng-Pass!42",
        first_name="Root",
        role=UserRole.SUPERADMIN,
    )
    api_client_no_csrf.force_login(boss)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{student.id}/", {"role": "superadmin"}, format="json"
    )

    assert response.status_code == 200
    student.refresh_from_db()
    assert student.role == UserRole.SUPERADMIN


@pytest.mark.django_db
def test_creating_a_user_obeys_the_same_rule(admin_user):
    from apps.accounts.services import create_user
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        create_user(
            email="escalate@example.test",
            password=None,
            first_name="Nope",
            role=UserRole.SUPERADMIN,
            actor=admin_user,
            send_invitation=False,
        )


@pytest.mark.django_db
def test_a_refused_promotion_is_recorded(admin_user, student):
    from apps.accounts.services import update_user
    from apps.audit.models import AuditAction, AuditLog
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        update_user(user=student, actor=admin_user, role=UserRole.SUPERADMIN)

    # A failure entry is queued rather than written inline, so it survives the
    # rollback of the request it describes. Calling the service directly, the
    # queue has to be drained by hand — the middleware does it in a real request.
    from apps.audit.services import flush_deferred
    from apps.common.request_context import take_deferred_audits

    flush_deferred(take_deferred_audits())

    entry = AuditLog.objects.filter(action=AuditAction.USER_ROLE_CHANGED).first()
    assert entry is not None
    assert entry.context["attempted"] == UserRole.SUPERADMIN
    assert entry.context["refused"] == "not_held_by_actor"
