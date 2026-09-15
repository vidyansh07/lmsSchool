"""Session management (ERP Phase 6, ADR-06).

Covers:

- a `UserSession` row is written at a plain login and at an MFA-completed
  one, and not before (a pending-MFA login writes nothing);
- `is_current` in the list correctly names the session making the request;
- revoking the *current* session through the per-session endpoint is
  refused with a clear `409 current_session`, pointing at logout instead;
- `revoke-others` ends every other session and leaves the current one able
  to keep working, while the ended ones are genuinely signed out;
- `last_seen_at` is touched by the guarded update at most once per five
  minutes — checked directly against the guard, not by sleeping;
- new-device detection fires for a genuinely new browser-family/IP-network
  combination and does not fire on a repeat of the same one;
- an administrator holding `session.revoke_any` can revoke another user's
  session within their branch scope, is refused with `403 step_up_required`
  without a fresh step-up, and cannot reach another centre's user (404);
  the target user is notified.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.roles import UserRole
from apps.accounts.sessions import UserSession, hash_session_key, touch_last_seen
from apps.audit.models import AuditAction, AuditLog
from apps.authorization.resolver import forget_roles
from apps.authorization.services import create_role
from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login/"
VERIFY = "/api/v1/auth/mfa/verify/"
ENROL = "/api/v1/auth/mfa/totp/enrol/"
CONFIRM = "/api/v1/auth/mfa/totp/confirm/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"
SESSIONS = "/api/v1/auth/sessions/"
REVOKE_OTHERS = "/api/v1/auth/sessions/revoke-others/"
STEP_UP = "/api/v1/auth/step-up/"

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)
SAFARI_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def _login(client, user, *, user_agent: str = CHROME_WINDOWS):
    return client.post(
        LOGIN,
        {"email": user.email, "password": TEST_PASSWORD},
        format="json",
        HTTP_USER_AGENT=user_agent,
    )


def _grant_session_capabilities(*, actor, holder, slug: str):
    """Build a custom role of ``holder``'s own kind (so their `role` field,
    and therefore their branch scope, is unchanged) holding just the two
    session capabilities, and assign it — the only way to observe branch
    scoping on `session.revoke_any`, since the system ADMIN role that holds
    it by default is deliberately unbounded (D-129 amended)."""
    role = create_role(
        actor=actor,
        slug=slug,
        name=slug,
        kind=holder.role,
        permissions=[{"code": "session.view_any"}, {"code": "session.revoke_any"}],
    )
    holder.custom_role = role
    holder.save(update_fields=["custom_role"])
    forget_roles()
    return role


# ---------------------------------------------------------------------------
# Written at login
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_session_row_created_at_plain_login(api_client_no_csrf, student):
    response = _login(api_client_no_csrf, student)
    assert response.status_code == 200, response.json()

    row = UserSession.objects.get(user=student)
    assert row.revoked_at is None
    assert row.device_label == "Chrome on Windows"
    assert row.session_key_hash == hash_session_key(api_client_no_csrf.session.session_key)


@pytest.mark.django_db
def test_no_session_row_while_mfa_is_pending(api_client_no_csrf, student, admin_user):
    from apps.policies.services import update_policy

    update_policy(
        actor=admin_user,
        category="authentication",
        key="mfa_required_roles",
        value=[UserRole.STUDENT],
        reason="test",
        confirm="mfa_required_roles",
    )
    update_policy(
        actor=admin_user,
        category="authentication",
        key="mfa_grace_days",
        value=0,
        reason="test",
    )

    response = _login(api_client_no_csrf, student)
    assert response.json()["mfa_required"] is True
    assert UserSession.objects.filter(user=student).count() == 0


@pytest.mark.django_db
def test_session_row_created_at_mfa_completed_login(api_client_no_csrf, student):
    import pyotp

    from apps.accounts.mfa import MfaDevice

    client = api_client_no_csrf
    client.force_login(student)
    enrolled = client.post(ENROL, format="json")
    secret = enrolled.json()["secret"]
    confirmed = client.post(CONFIRM, {"code": pyotp.TOTP(secret).now()}, format="json")
    assert confirmed.status_code == 200, confirmed.json()
    # The step that confirmed enrolment must not count as a replay of the
    # step used to verify the login below (same reset `test_mfa.py` uses).
    MfaDevice.objects.filter(user=student).update(last_used_step=None)
    client.logout()
    # force_login/logout above never went through LoginView, so no row exists yet.
    assert UserSession.objects.filter(user=student).count() == 0

    login_response = _login(client, student)
    assert login_response.json()["mfa_required"] is True
    assert UserSession.objects.filter(user=student).count() == 0

    code = pyotp.TOTP(secret).now()
    verified = client.post(VERIFY, {"method": "totp", "code": code}, format="json")
    assert verified.status_code == 200, verified.json()

    row = UserSession.objects.get(user=student)
    assert row.session_key_hash == hash_session_key(client.session.session_key)


# ---------------------------------------------------------------------------
# Listing and is_current
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_is_current_names_the_requesting_session(student):
    client_a, client_b = APIClient(), APIClient()
    assert _login(client_a, student).status_code == 200
    assert _login(client_b, student).status_code == 200

    body = client_a.get(SESSIONS, format="json").json()
    assert len(body) == 2
    current_rows = [row for row in body if row["is_current"]]
    assert len(current_rows) == 1
    a_hash = hash_session_key(client_a.session.session_key)
    current_row_id = current_rows[0]["id"]
    assert UserSession.objects.get(pk=current_row_id).session_key_hash == a_hash

    # From client B's point of view, its own session is the current one.
    body_b = client_b.get(SESSIONS, format="json").json()
    current_from_b = next(row for row in body_b if row["is_current"])
    assert current_from_b["id"] != current_row_id


# ---------------------------------------------------------------------------
# Revoking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_revoking_the_current_session_is_refused(student):
    client = APIClient()
    _login(client, student)
    own_id = client.get(SESSIONS, format="json").json()[0]["id"]

    refused = client.delete(f"{SESSIONS}{own_id}/", format="json")
    assert refused.status_code == 409, refused.json()
    assert refused.json()["error"]["code"] == "current_session"

    # Refusing did not touch it: still there, still usable.
    assert client.get(ME).status_code == 200


@pytest.mark.django_db
def test_revoking_another_of_my_sessions_signs_it_out(student):
    client_a, client_b = APIClient(), APIClient()
    _login(client_a, student)
    _login(client_b, student)
    assert client_b.get(ME).status_code == 200

    other_id = next(
        row["id"] for row in client_a.get(SESSIONS, format="json").json() if not row["is_current"]
    )
    revoked = client_a.delete(f"{SESSIONS}{other_id}/", format="json")
    assert revoked.status_code == 204

    # The other browser is genuinely signed out, not just delisted.
    assert client_b.get(ME).status_code in (401, 403)
    # A's own session survives and is the only one left.
    remaining = client_a.get(SESSIONS, format="json").json()
    assert len(remaining) == 1
    assert remaining[0]["is_current"] is True

    assert AuditLog.objects.filter(actor=student, action=AuditAction.SESSION_REVOKED).exists()


@pytest.mark.django_db
def test_revoking_an_unknown_or_foreign_session_is_404(student, trainer):
    client = APIClient()
    _login(client, student)
    other_client = APIClient()
    _login(other_client, trainer)
    trainer_session_id = other_client.get(SESSIONS, format="json").json()[0]["id"]

    # Somebody else's session id is a 404 through my own endpoint, not a 403
    # that would confirm it exists.
    assert client.delete(f"{SESSIONS}{trainer_session_id}/", format="json").status_code == 404


@pytest.mark.django_db
def test_revoke_others_leaves_only_the_current_session(student):
    client_a, client_b, client_c = APIClient(), APIClient(), APIClient()
    _login(client_a, student)
    _login(client_b, student)
    _login(client_c, student)

    response = client_a.post(REVOKE_OTHERS, format="json")
    assert response.status_code == 200, response.json()
    assert "2" in response.json()["detail"]

    remaining = client_a.get(SESSIONS, format="json").json()
    assert len(remaining) == 1
    assert remaining[0]["is_current"] is True

    assert client_a.get(ME).status_code == 200
    assert client_b.get(ME).status_code in (401, 403)
    assert client_c.get(ME).status_code in (401, 403)


# ---------------------------------------------------------------------------
# last_seen_at, touched at most once per five minutes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_last_seen_at_is_touched_at_most_once_per_five_minutes(student):
    row = UserSession.objects.create(
        user=student,
        session_key_hash=hash_session_key("a-fake-session-key"),
        device_label="Chrome on Windows",
        last_seen_at=timezone.now(),
    )
    fresh_stamp = row.last_seen_at

    # Recently touched: the guarded UPDATE matches nothing.
    touch_last_seen("a-fake-session-key")
    row.refresh_from_db()
    assert row.last_seen_at == fresh_stamp

    # Stale: now it updates.
    stale = timezone.now() - timedelta(minutes=10)
    UserSession.objects.filter(pk=row.pk).update(last_seen_at=stale)
    touch_last_seen("a-fake-session-key")
    row.refresh_from_db()
    assert row.last_seen_at > stale


@pytest.mark.django_db
def test_logout_marks_the_session_revoked(student):
    client = APIClient()
    _login(client, student)
    row = UserSession.objects.get(user=student)
    assert row.revoked_at is None

    assert client.post(LOGOUT, format="json").status_code == 200
    row.refresh_from_db()
    assert row.revoked_at is not None


# ---------------------------------------------------------------------------
# New-device detection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_new_device_detection_fires_once_then_not_again(
    student, django_capture_on_commit_callbacks
):
    mail.outbox.clear()
    client = APIClient()
    with django_capture_on_commit_callbacks(execute=True):
        assert _login(client, student, user_agent=CHROME_WINDOWS).status_code == 200

    assert any("New sign-in" in message.subject for message in mail.outbox)
    assert AuditLog.objects.filter(
        actor=student, action=AuditAction.SESSION_NEW_DEVICE_DETECTED
    ).exists()

    client.post(LOGOUT, format="json")
    mail.outbox.clear()

    # Same browser family, same network: not new any more.
    with django_capture_on_commit_callbacks(execute=True):
        assert _login(client, student, user_agent=CHROME_WINDOWS).status_code == 200
    assert mail.outbox == []
    assert (
        AuditLog.objects.filter(
            actor=student, action=AuditAction.SESSION_NEW_DEVICE_DETECTED
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_new_device_detection_fires_again_for_a_different_browser_family(
    student, django_capture_on_commit_callbacks
):
    client = APIClient()
    with django_capture_on_commit_callbacks(execute=True):
        _login(client, student, user_agent=CHROME_WINDOWS)
    client.post(LOGOUT, format="json")
    mail.outbox.clear()

    other_client = APIClient()
    with django_capture_on_commit_callbacks(execute=True):
        assert _login(other_client, student, user_agent=SAFARI_IOS).status_code == 200
    assert any("New sign-in" in message.subject for message in mail.outbox)
    assert (
        AuditLog.objects.filter(
            actor=student, action=AuditAction.SESSION_NEW_DEVICE_DETECTED
        ).count()
        == 2
    )


# ---------------------------------------------------------------------------
# Administrator revoke: capability, step-up, branch scope, notification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_revoke_requires_capability_and_fresh_step_up(
    api_client_no_csrf, admin_user, student, django_capture_on_commit_callbacks
):
    device_client = APIClient()
    _login(device_client, student)
    session_id = UserSession.objects.get(user=student).id
    mail.outbox.clear()

    # A caller without the capability at all is refused outright.
    plain_client = APIClient()
    plain_client.force_login(student)
    denied = plain_client.delete(
        f"/api/v1/users/{student.id}/sessions/{session_id}/", format="json"
    )
    assert denied.status_code == 403

    api_client_no_csrf.force_login(admin_user)
    without_step_up = api_client_no_csrf.delete(
        f"/api/v1/users/{student.id}/sessions/{session_id}/", format="json"
    )
    assert without_step_up.status_code == 403
    assert without_step_up.json()["error"]["code"] == "step_up_required"
    assert UserSession.objects.get(pk=session_id).revoked_at is None

    stepped = api_client_no_csrf.post(STEP_UP, {"password": TEST_PASSWORD}, format="json")
    assert stepped.status_code == 204

    with django_capture_on_commit_callbacks(execute=True):
        revoked = api_client_no_csrf.delete(
            f"/api/v1/users/{student.id}/sessions/{session_id}/", format="json"
        )
    assert revoked.status_code == 204, revoked.content
    assert UserSession.objects.get(pk=session_id).revoked_at is not None
    assert device_client.get(ME).status_code in (401, 403)

    assert AuditLog.objects.filter(
        actor=admin_user, action=AuditAction.SESSION_REVOKED_BY_ADMIN, resource_id=str(session_id)
    ).exists()
    assert any("ended by an administrator" in message.subject for message in mail.outbox)


@pytest.mark.django_db
def test_admin_lists_a_users_sessions(api_client_no_csrf, admin_user, student):
    _login(APIClient(), student)
    api_client_no_csrf.force_login(admin_user)
    listed = api_client_no_csrf.get(f"/api/v1/users/{student.id}/sessions/", format="json")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.django_db
def test_branch_scoped_holder_of_revoke_any_cannot_reach_another_centre(
    admin_user, manager_user, student, other_branch_student
):
    """`session.revoke_any` is scoped `all, branch` (PERMISSION_CATALOG.md).
    The system ADMIN role holds it unbounded (D-129 amended: administrators
    see every centre), so the branch boundary is exercised the way ADR-02
    always is: a role whose *kind* is branch-bound (manager) built with just
    these two capabilities."""
    _grant_session_capabilities(
        actor=admin_user, holder=manager_user, slug="session-admin-for-test"
    )

    own_branch_client = APIClient()
    _login(own_branch_client, student)
    own_session_id = UserSession.objects.get(user=student).id

    other_branch_client = APIClient()
    _login(other_branch_client, other_branch_student.user)
    foreign_session_id = UserSession.objects.get(user=other_branch_student.user).id

    scoped = APIClient()
    scoped.force_login(manager_user)
    scoped.post(STEP_UP, {"password": TEST_PASSWORD}, format="json")

    # Same centre: reachable, and revoking it actually works.
    ok = scoped.delete(f"/api/v1/users/{student.id}/sessions/{own_session_id}/", format="json")
    assert ok.status_code == 204, ok.json()

    # The other centre's account is not visible at all — a 404, not a 403.
    listed = scoped.get(f"/api/v1/users/{other_branch_student.user.id}/sessions/", format="json")
    assert listed.status_code == 404

    blocked = scoped.delete(
        f"/api/v1/users/{other_branch_student.user.id}/sessions/{foreign_session_id}/",
        format="json",
    )
    assert blocked.status_code == 404
    assert UserSession.objects.get(pk=foreign_session_id).revoked_at is None
