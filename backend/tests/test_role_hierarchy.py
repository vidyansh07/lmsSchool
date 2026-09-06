"""§11.1 — authority flows downward, and only downward.

Two rules used to be confused with each other. ``can_grant_role`` answers "which
role may I hand out?", and it was enforced. Nothing answered "whose account may
I touch at all?", so an administrator could not promote anybody above
themselves but could edit a superadmin's email address — and then send that
address a password-reset link — or simply deactivate them. Authority flowed
upward through a door nobody had thought to close.

Every direction is checked here, including the ones that should work. A test
file that only proves refusals will happily pass on a system where nothing works
at all.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import User, UserRole
from apps.accounts.roles import can_administer
from apps.accounts.services import set_user_active, update_user
from apps.common.exceptions import ApplicationError, AuthorityError

PASSWORD = "Str0ng-Passphrase!42"

#: Every ordered pair of roles, and whether the first may administer the second.
#: Written out rather than computed: this table *is* the policy, and a reviewer
#: should be able to read it without running anything.
AUTHORITY = {
    (UserRole.SUPERADMIN, UserRole.SUPERADMIN): True,  # so a compromised one can be stopped
    (UserRole.SUPERADMIN, UserRole.ADMIN): True,
    (UserRole.SUPERADMIN, UserRole.MANAGER): True,
    (UserRole.SUPERADMIN, UserRole.TRAINER): True,
    (UserRole.SUPERADMIN, UserRole.STUDENT): True,
    (UserRole.ADMIN, UserRole.SUPERADMIN): False,  # the hole this file closed
    (UserRole.ADMIN, UserRole.ADMIN): False,  # peers cannot trade privileges
    (UserRole.ADMIN, UserRole.MANAGER): True,
    (UserRole.ADMIN, UserRole.TRAINER): True,
    (UserRole.ADMIN, UserRole.STUDENT): True,
    (UserRole.MANAGER, UserRole.SUPERADMIN): False,
    (UserRole.MANAGER, UserRole.ADMIN): False,
    (UserRole.MANAGER, UserRole.MANAGER): False,
    (UserRole.MANAGER, UserRole.TRAINER): True,
    (UserRole.MANAGER, UserRole.STUDENT): True,
    (UserRole.TRAINER, UserRole.SUPERADMIN): False,
    (UserRole.TRAINER, UserRole.ADMIN): False,
    (UserRole.TRAINER, UserRole.MANAGER): False,
    (UserRole.TRAINER, UserRole.TRAINER): False,
    (UserRole.TRAINER, UserRole.STUDENT): False,
    (UserRole.STUDENT, UserRole.SUPERADMIN): False,
    (UserRole.STUDENT, UserRole.ADMIN): False,
    (UserRole.STUDENT, UserRole.MANAGER): False,
    (UserRole.STUDENT, UserRole.TRAINER): False,
    (UserRole.STUDENT, UserRole.STUDENT): False,
}


def _person(role: str, tag: str = "") -> User:
    return User.objects.create_user(
        email=f"{role}{tag}@hierarchy.grras.invalid",
        password=PASSWORD,
        first_name=role.title(),
        last_name="Person",
        role=role,
    )


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("actor_role", "target_role", "allowed"),
    [(actor, target, allowed) for (actor, target), allowed in AUTHORITY.items()],
    ids=[f"{actor}-over-{target}" for actor, target in AUTHORITY],
)
def test_the_authority_table_holds(actor_role, target_role, allowed):
    actor = _person(actor_role, "-actor")
    target = _person(target_role, "-target")

    assert can_administer(actor, target) is allowed


@pytest.mark.django_db
def test_nobody_administers_themselves_through_the_staff_path():
    """Self-service is a different endpoint with a serializer that takes no role.

    Allowing it here would let somebody deactivate their own account, or hand
    themselves a role, through the screen built for administering other people.
    """
    for role in UserRole.values:
        person = _person(role)
        assert can_administer(person, person) is False


@pytest.mark.django_db
def test_an_inactive_administrator_has_no_authority():
    actor = _person(UserRole.ADMIN, "-actor")
    target = _person(UserRole.STUDENT, "-target")
    assert can_administer(actor, target) is True

    actor.is_active = False
    assert can_administer(actor, target) is False


@pytest.mark.django_db
def test_a_django_superuser_may_administer_anyone():
    """A platform operator is above the role ladder, not inside it."""
    operator = _person(UserRole.STUDENT, "-operator")
    operator.is_superuser = True

    for role in UserRole.values:
        assert can_administer(operator, _person(role, f"-{role}")) is True


# ---------------------------------------------------------------------------
# The rule reaches the service layer, not only the view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_cannot_edit_a_superadmin():
    """The original hole, stated plainly."""
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    with pytest.raises(ApplicationError, match="authority"):
        update_user(user=superadmin, actor=admin, first_name="Renamed")

    superadmin.refresh_from_db()
    assert superadmin.first_name == "Superadmin"


@pytest.mark.django_db
def test_an_administrator_cannot_change_a_superadmins_email():
    """The email is the account. Changing it and then asking for a password
    reset is the whole attack, and it needed no role change at all."""
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")
    original = superadmin.email

    with pytest.raises(ApplicationError, match="authority"):
        update_user(user=superadmin, actor=admin, email="attacker@hierarchy.grras.invalid")

    superadmin.refresh_from_db()
    assert superadmin.email == original


@pytest.mark.django_db
def test_an_administrator_cannot_deactivate_a_superadmin():
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    with pytest.raises(ApplicationError, match="authority"):
        set_user_active(user=superadmin, is_active=False, actor=admin)

    superadmin.refresh_from_db()
    assert superadmin.is_active is True


@pytest.mark.django_db
def test_an_administrator_cannot_edit_another_administrator():
    one = _person(UserRole.ADMIN, "-one")
    two = _person(UserRole.ADMIN, "-two")

    with pytest.raises(ApplicationError, match="authority"):
        update_user(user=two, actor=one, first_name="Renamed")


@pytest.mark.django_db
def test_a_manager_cannot_edit_an_administrator():
    manager = _person(UserRole.MANAGER, "-actor")
    admin = _person(UserRole.ADMIN, "-target")

    with pytest.raises(ApplicationError, match="authority"):
        update_user(user=admin, actor=manager, first_name="Renamed")


# ---------------------------------------------------------------------------
# And the things that must still work
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_superadmin_may_edit_every_field_of_an_administrator():
    """§11.2's promise, checked at the service: every administrator field."""
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    admin = _person(UserRole.ADMIN, "-target")

    updated = update_user(
        user=admin,
        actor=superadmin,
        first_name="Configured",
        last_name="Entirely",
        phone="+911234567890",
        role=UserRole.MANAGER,
    )

    assert updated.first_name == "Configured"
    assert updated.last_name == "Entirely"
    assert updated.phone == "+911234567890"
    assert updated.role == UserRole.MANAGER


@pytest.mark.django_db
def test_a_superadmin_may_deactivate_another_superadmin():
    """The one lateral move, and the reason for it: an institution whose top
    account cannot be stopped is worse off than one that can police itself."""
    one = _person(UserRole.SUPERADMIN, "-one")
    two = _person(UserRole.SUPERADMIN, "-two")

    set_user_active(user=two, is_active=False, actor=one, reason="Credentials leaked.")

    two.refresh_from_db()
    assert two.is_active is False


@pytest.mark.django_db
def test_an_administrator_may_still_administer_a_manager_and_below():
    admin = _person(UserRole.ADMIN, "-actor")

    for role in (UserRole.MANAGER, UserRole.TRAINER, UserRole.STUDENT):
        target = _person(role, "-target")
        assert update_user(user=target, actor=admin, first_name="Edited").first_name == "Edited"


@pytest.mark.django_db
def test_editing_your_own_profile_still_works():
    """The self-service path shares the service and must not be caught by the
    guard — the refusal is about administering *somebody else*."""
    person = _person(UserRole.TRAINER)

    updated = update_user(user=person, actor=person, first_name="Myself")
    assert updated.first_name == "Myself"


# ---------------------------------------------------------------------------
# Refusals are recorded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_refused_act_is_audited_with_both_roles():
    """ "Did anybody try?" has to have an answer, and the answer needs the shape
    of the attempt in it — who, over whom."""
    from apps.audit.models import AuditLog, AuditResult
    from apps.audit.services import flush_deferred
    from apps.common.request_context import take_deferred_audits

    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    with pytest.raises(ApplicationError):
        update_user(user=superadmin, actor=admin, first_name="Renamed")
    flush_deferred(take_deferred_audits())

    entry = AuditLog.objects.filter(result=AuditResult.DENIED).latest("created_at")
    assert entry.actor_id == admin.pk
    assert entry.context["refused"] == "outside_authority"
    assert entry.context["actor_role"] == UserRole.ADMIN
    assert entry.context["target_role"] == UserRole.SUPERADMIN


# ---------------------------------------------------------------------------
# Over the API, not only in Python
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_api_refuses_with_403_and_names_no_names(api_client_no_csrf):
    """A 403, not a 400.

    The request was well formed and the caller is who they say they are; they
    have no authority over that account. A validation error would tell the
    interface to highlight a field that does not exist. And the message says
    nothing about *why* — "you cannot edit a superadmin" tells an attacker which
    accounts are worth pursuing.
    """
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    api_client_no_csrf.force_login(admin)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{superadmin.id}/", {"first_name": "Renamed"}, format="json"
    )

    assert response.status_code == 403
    body = str(response.json())
    assert "superadmin" not in body.lower()
    assert "authority" in body.lower()


@pytest.mark.django_db
def test_the_api_refuses_deactivating_upward(api_client_no_csrf):
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    api_client_no_csrf.force_login(admin)
    response = api_client_no_csrf.post(
        f"/api/v1/users/{superadmin.id}/set-active/", {"is_active": False}, format="json"
    )

    assert response.status_code == 403
    superadmin.refresh_from_db()
    assert superadmin.is_active is True


@pytest.mark.django_db
def test_a_superadmin_configures_an_administrator_over_the_api(api_client_no_csrf):
    """§11.2, end to end: every administrator field, from a superadmin."""
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    admin = _person(UserRole.ADMIN, "-target")

    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{admin.id}/",
        {
            "first_name": "Configured",
            "last_name": "Entirely",
            "phone": "+911234567890",
            "role": UserRole.MANAGER,
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    admin.refresh_from_db()
    assert (admin.first_name, admin.role) == ("Configured", UserRole.MANAGER)


def test_the_authority_error_is_a_403():
    assert AuthorityError.status_code == 403


# ---------------------------------------------------------------------------
# §11.2 — configuring every field, including the identifier
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_changing_an_email_unverifies_it_and_ends_sessions(api_client_no_csrf, mailoutbox):
    """An administrator moving somebody's login identifier is not a field edit.

    Leaving the verified flag set would let an administrator hand an account an
    address they control and have it trusted. Leaving the session alive would
    let whoever held it keep the account after the identity moved.
    """
    from django.contrib.sessions.models import Session

    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    target = _person(UserRole.MANAGER, "-target")
    target.is_email_verified = True
    target.save(update_fields=["is_email_verified"])

    # Give the target a live session, the way signing in would.
    other = api_client_no_csrf.__class__()
    other.force_login(target)
    assert Session.objects.count() >= 1

    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{target.id}/", {"email": "moved@hierarchy.grras.invalid"}, format="json"
    )
    assert response.status_code == 200, response.json()

    target.refresh_from_db()
    assert target.email == "moved@hierarchy.grras.invalid"
    assert target.is_email_verified is False
    assert target.email_verified_at is None
    assert any("moved@hierarchy.grras.invalid" in message.to[0] for message in mailoutbox)


@pytest.mark.django_db
def test_an_email_change_is_audited_with_both_addresses(api_client_no_csrf):
    """ "Who changed this person's address, and when" is the first question
    asked after an account takeover."""
    from apps.audit.models import AuditAction, AuditLog

    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    target = _person(UserRole.STUDENT, "-target")
    before = target.email

    api_client_no_csrf.force_login(superadmin)
    api_client_no_csrf.patch(
        f"/api/v1/users/{target.id}/", {"email": "after@hierarchy.grras.invalid"}, format="json"
    )

    entry = AuditLog.objects.filter(action=AuditAction.USER_EMAIL_CHANGED).latest("created_at")
    assert entry.context["from"] == before
    assert entry.context["to"] == "after@hierarchy.grras.invalid"


@pytest.mark.django_db
def test_an_email_already_in_use_is_refused(api_client_no_csrf):
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    taken = _person(UserRole.TRAINER, "-taken")
    target = _person(UserRole.STUDENT, "-target")

    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{target.id}/", {"email": taken.email}, format="json"
    )

    assert response.status_code == 400
    target.refresh_from_db()
    assert target.email != taken.email


@pytest.mark.django_db
def test_an_administrator_cannot_hand_themselves_a_verified_address(api_client_no_csrf):
    """The field is not editable at all: verification is a fact only the inbox
    owner can establish, and an administrator asserting it is the whole risk."""
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    target = _person(UserRole.ADMIN, "-target")

    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.patch(
        f"/api/v1/users/{target.id}/", {"is_email_verified": True}, format="json"
    )

    assert response.status_code == 400  # unknown field, rejected outright
    target.refresh_from_db()
    assert target.is_email_verified is False


@pytest.mark.django_db
def test_an_administrator_can_send_a_reset_link_but_never_learns_it(api_client_no_csrf, mailoutbox):
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    target = _person(UserRole.ADMIN, "-target")

    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.post(
        f"/api/v1/users/{target.id}/credential-link/",
        {"action": "password_reset"},
        format="json",
    )

    assert response.status_code == 202
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [target.email]
    # The link went to the account holder; the response carries nothing.
    assert "token" not in str(response.json()).lower()


@pytest.mark.django_db
def test_sending_a_link_upward_is_refused(api_client_no_csrf, mailoutbox):
    """Triggering a reset on an account is, in practice, taking it."""
    admin = _person(UserRole.ADMIN, "-actor")
    superadmin = _person(UserRole.SUPERADMIN, "-target")

    api_client_no_csrf.force_login(admin)
    response = api_client_no_csrf.post(
        f"/api/v1/users/{superadmin.id}/credential-link/",
        {"action": "password_reset"},
        format="json",
    )

    assert response.status_code == 403
    assert mailoutbox == []


@pytest.mark.django_db
def test_the_audit_history_of_an_account_is_readable_on_its_screen(api_client_no_csrf):
    superadmin = _person(UserRole.SUPERADMIN, "-actor")
    target = _person(UserRole.MANAGER, "-target")

    api_client_no_csrf.force_login(superadmin)
    api_client_no_csrf.patch(f"/api/v1/users/{target.id}/", {"first_name": "Edited"}, format="json")

    history = api_client_no_csrf.get(f"/api/v1/users/{target.id}/audit/").json()
    assert history, "an account that was just edited has no history"
    assert history[0]["actor_label"] == superadmin.email
    assert history[0]["action_label"]


@pytest.mark.django_db
def test_reading_an_account_history_needs_the_audit_capability(api_client_no_csrf):
    """An audit trail everyone can read is a map of who administers whom."""
    manager = _person(UserRole.MANAGER, "-actor")
    target = _person(UserRole.STUDENT, "-target")

    api_client_no_csrf.force_login(manager)
    assert api_client_no_csrf.get(f"/api/v1/users/{target.id}/audit/").status_code == 403
