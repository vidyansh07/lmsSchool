"""Multi-factor authentication (ERP Phase 5, ADR-05).

Covers:

- the full flow: enrol -> confirm (ten recovery codes, shown once) -> a
  fresh login lands in the pending-MFA state -> verify with TOTP completes
  it;
- verify with an emailed code, and with a recovery code (and that a spent
  recovery code cannot be reused);
- replay of an already-accepted TOTP step is refused, deterministically;
- every method's failure reaches the caller as the same generic
  ``invalid_code`` — never a hint about which factor was wrong;
- a pending-MFA session is anonymous to every other endpoint — a genuine
  authorization test, not just a login-response-shape assertion;
- policy-driven requirement: an empty `mfa_required_roles` never forces
  anyone into MFA without a device of their own choosing; a required role
  is exempt within its own account's grace period and caught once past it;
- disable requires a fresh step-up and genuinely removes the device and
  every recovery code; regenerate invalidates the old ten; step-up itself
  accepts a TOTP or a recovery code as an alternative to password/email.

``MFA_ENCRYPTION_KEY`` absent in a would-be-deployed environment is covered
by ``tests/test_security_config.py`` (same parametrized boot-failure suite
every other required secret uses), not duplicated here.
"""

from __future__ import annotations

import re
from datetime import timedelta

import pyotp
import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.mfa import MfaDevice, RecoveryCode, verify_totp_code
from apps.accounts.roles import UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.policies.services import update_policy
from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
SEND_CODE = "/api/v1/auth/mfa/send-email-code/"
VERIFY = "/api/v1/auth/mfa/verify/"
ENROL = "/api/v1/auth/mfa/totp/enrol/"
CONFIRM = "/api/v1/auth/mfa/totp/confirm/"
DISABLE = "/api/v1/auth/mfa/totp/disable/"
REGEN = "/api/v1/auth/mfa/recovery/regenerate/"
STEP_UP = "/api/v1/auth/step-up/"
ME = "/api/v1/auth/me/"

_CODE_RE = re.compile(r"one-time code is: (\d{6})")


def _extract_email_code(body: str) -> str:
    match = _CODE_RE.search(body)
    assert match is not None
    return match.group(1)


def _enrol_and_confirm(client, user) -> tuple[str, list[str]]:
    """Enrol and confirm through the real endpoints. Returns the raw TOTP
    secret and the ten recovery codes, and resets the device's replay guard
    so a follow-up TOTP call in the same test is not treated as a replay of
    the code that confirmed enrolment."""
    enrolled = client.post(ENROL, format="json")
    assert enrolled.status_code == 200, enrolled.json()
    secret = enrolled.json()["secret"]
    assert enrolled.json()["secret_uri"].startswith("otpauth://totp/")
    assert "<svg" in enrolled.json()["qr_svg"]

    code = pyotp.TOTP(secret).now()
    confirmed = client.post(CONFIRM, {"code": code}, format="json")
    assert confirmed.status_code == 200, confirmed.json()
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10

    MfaDevice.objects.filter(user=user).update(last_used_step=None)
    return secret, codes


def _require_role(role: str, *, admin_user, grace_days: int = 7) -> None:
    update_policy(
        actor=admin_user,
        category="authentication",
        key="mfa_required_roles",
        value=[role],
        reason="test",
        confirm="mfa_required_roles",
    )
    update_policy(
        actor=admin_user,
        category="authentication",
        key="mfa_grace_days",
        value=grace_days,
        reason="test",
    )


# ---------------------------------------------------------------------------
# Enrol -> confirm -> login-with-pending-state -> verify (TOTP)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enrol_confirm_login_pending_then_verify_with_totp(
    api_client_no_csrf, student, django_capture_on_commit_callbacks
):
    client = api_client_no_csrf
    client.force_login(student)
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        secret, _codes = _enrol_and_confirm(client, student)

    student.refresh_from_db()
    assert student.mfa_enrolled_at is not None
    device = MfaDevice.objects.get(user=student)
    assert device.confirmed_at is not None

    # mfa.enrolled emails the user, bypassing notification preferences.
    assert any("Two-factor authentication turned on" in m.subject for m in mail.outbox)

    actions = set(AuditLog.objects.filter(actor=student).values_list("action", flat=True))
    assert AuditAction.MFA_CONFIRMED in actions
    assert AuditAction.MFA_ENROLLED in actions

    client.logout()
    login_response = client.post(
        LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json"
    )
    assert login_response.status_code == 200, login_response.json()
    body = login_response.json()
    assert body["mfa_required"] is True
    assert body["methods"] == ["totp", "email", "recovery"]
    assert body["expires_in"] == 300
    assert client.session.get("mfa_pending") is not None

    pending_action = AuditLog.objects.filter(actor=student, action=AuditAction.LOGIN_PENDING)
    assert pending_action.exists()

    # Anonymous to every other endpoint (genuine authorization, not just a
    # response-shape assertion) — the session was never django-logged-in.
    assert client.get(ME).status_code in (401, 403)
    assert client.post(ENROL, format="json").status_code in (401, 403)
    assert client.post(LOGOUT, format="json").status_code in (401, 403)

    code = pyotp.TOTP(secret).now()
    verified = client.post(VERIFY, {"method": "totp", "code": code}, format="json")
    assert verified.status_code == 200, verified.json()
    assert verified.json()["email"] == student.email
    assert client.session.get("mfa_pending") is None

    # Now genuinely signed in.
    assert client.get(ME).status_code == 200

    assert AuditLog.objects.filter(
        actor=student, action=AuditAction.MFA_VERIFIED, context__method="totp"
    ).exists()


@pytest.mark.django_db
def test_replay_of_an_old_totp_step_is_refused(student):
    """Direct, deterministic check of the core guarantee: the exact same
    code cannot verify twice, regardless of the ±1 step tolerance window."""
    from apps.accounts import mfa

    device, secret = mfa.start_enrolment(user=student)
    code = pyotp.TOTP(secret).now()
    mfa.confirm_enrolment(user=student, code=code)
    device.refresh_from_db()
    used_step = device.last_used_step
    assert used_step is not None

    # The exact code that confirmed enrolment cannot verify again: whatever
    # step it matches now (the same one, or — across a boundary — an older
    # one) is at or before `last_used_step` either way, so this is
    # deterministic regardless of how much wall-clock time this line runs
    # after the one above.
    assert verify_totp_code(user=student, code=code) is False
    device.refresh_from_db()
    assert device.last_used_step == used_step


# ---------------------------------------------------------------------------
# Verify with an emailed code
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_login_pending_then_verify_with_email_code(api_client_no_csrf, student, admin_user):
    _require_role(UserRole.STUDENT, admin_user=admin_user, grace_days=0)
    client = api_client_no_csrf
    mail.outbox.clear()

    login_response = client.post(
        LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json"
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["mfa_required"] is True
    assert body["methods"] == ["email"]  # no device, no recovery codes yet

    sent = client.post(SEND_CODE, format="json")
    assert sent.status_code == 204, sent.content
    assert len(mail.outbox) == 1
    code = _extract_email_code(mail.outbox[0].body)

    verified = client.post(VERIFY, {"method": "email", "code": code}, format="json")
    assert verified.status_code == 200, verified.json()
    assert client.get(ME).status_code == 200


# ---------------------------------------------------------------------------
# Verify with a recovery code, and single-use
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_login_pending_then_verify_with_recovery_code_and_cannot_reuse_it(
    api_client_no_csrf, student
):
    client = api_client_no_csrf
    client.force_login(student)
    _secret, codes = _enrol_and_confirm(client, student)
    spent_code = codes[0]
    client.logout()

    login_response = client.post(
        LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json"
    )
    assert login_response.json()["mfa_required"] is True

    verified = client.post(VERIFY, {"method": "recovery", "code": spent_code}, format="json")
    assert verified.status_code == 200, verified.json()
    assert client.get(ME).status_code == 200
    assert RecoveryCode.objects.filter(user=student, used_at__isnull=False).count() == 1

    assert AuditLog.objects.filter(actor=student, action=AuditAction.MFA_RECOVERY_USED).exists()

    # The same code cannot be used again on a second pending sign-in.
    client.logout()
    second_login = client.post(
        LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json"
    )
    assert second_login.json()["mfa_required"] is True
    reused = client.post(VERIFY, {"method": "recovery", "code": spent_code}, format="json")
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_code"
    assert client.get(ME).status_code in (401, 403)


# ---------------------------------------------------------------------------
# No method's failure is distinguishable from another's
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_wrong_code_fails_the_same_way_for_every_method(api_client_no_csrf, student):
    client = api_client_no_csrf
    client.force_login(student)
    secret, _codes = _enrol_and_confirm(client, student)
    client.logout()

    client.post(LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json")

    right_totp = pyotp.TOTP(secret).now()
    wrong_totp_code = "000000" if right_totp != "000000" else "111111"

    wrong_totp = client.post(VERIFY, {"method": "totp", "code": wrong_totp_code}, format="json")
    wrong_email = client.post(VERIFY, {"method": "email", "code": "000000"}, format="json")
    wrong_recovery = client.post(
        VERIFY, {"method": "recovery", "code": "FFFFF-FFFFF"}, format="json"
    )

    for response in (wrong_totp, wrong_email, wrong_recovery):
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "invalid_code"
        assert body["error"]["message"] == wrong_totp.json()["error"]["message"]

    # None of them ever established the session.
    assert client.get(ME).status_code in (401, 403)
    assert AuditLog.objects.filter(actor=student, action=AuditAction.MFA_FAILED).count() == 3


# ---------------------------------------------------------------------------
# Policy-driven requirement and the grace period
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_empty_required_roles_never_forces_mfa_without_a_device(api_client_no_csrf, student):
    """The default: no policy row at all. A plain login still works exactly
    as it did before this phase."""
    client = api_client_no_csrf
    response = client.post(
        LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json"
    )
    assert response.status_code == 200
    assert "mfa_required" not in response.json()
    assert client.get(ME).status_code == 200


@pytest.mark.django_db
def test_required_role_within_its_grace_period_is_exempt(api_client_no_csrf, admin_user):
    """A required role's account, still inside mfa_grace_days of its own
    date_joined, signs in normally — the grace period this phase promises."""
    _require_role(UserRole.ADMIN, admin_user=admin_user, grace_days=7)
    client = api_client_no_csrf
    response = client.post(
        LOGIN, {"email": admin_user.email, "password": TEST_PASSWORD}, format="json"
    )
    assert response.status_code == 200
    assert "mfa_required" not in response.json()


@pytest.mark.django_db
def test_required_role_past_its_grace_period_is_forced_into_pending(api_client_no_csrf, admin_user):
    _require_role(UserRole.ADMIN, admin_user=admin_user, grace_days=7)
    admin_user.date_joined = timezone.now() - timedelta(days=30)
    admin_user.save(update_fields=["date_joined"])

    client = api_client_no_csrf
    response = client.post(
        LOGIN, {"email": admin_user.email, "password": TEST_PASSWORD}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is True
    assert body["methods"] == ["email"]


# ---------------------------------------------------------------------------
# Disable (step-up required, genuinely removes everything)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_disable_requires_step_up_and_removes_device_and_codes(
    api_client_no_csrf, student, django_capture_on_commit_callbacks
):
    client = api_client_no_csrf
    client.force_login(student)
    _enrol_and_confirm(client, student)
    mail.outbox.clear()

    refused = client.post(DISABLE, format="json")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"
    assert MfaDevice.objects.filter(user=student).exists()

    stepped = client.post(STEP_UP, {"password": TEST_PASSWORD}, format="json")
    assert stepped.status_code == 204

    with django_capture_on_commit_callbacks(execute=True):
        disabled = client.post(DISABLE, format="json")
    assert disabled.status_code == 204

    assert not MfaDevice.objects.filter(user=student).exists()
    assert not RecoveryCode.objects.filter(user=student).exists()
    student.refresh_from_db()
    assert student.mfa_enrolled_at is None
    assert any("Two-factor authentication turned off" in m.subject for m in mail.outbox)
    assert AuditLog.objects.filter(actor=student, action=AuditAction.MFA_DISABLED).exists()


# ---------------------------------------------------------------------------
# Regenerate (step-up required, invalidates the old ten)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_regenerate_invalidates_old_recovery_codes(api_client_no_csrf, student):
    client = api_client_no_csrf
    client.force_login(student)
    _secret, first_codes = _enrol_and_confirm(client, student)

    refused = client.post(REGEN, format="json")
    assert refused.status_code == 403

    client.post(STEP_UP, {"password": TEST_PASSWORD}, format="json")
    regenerated = client.post(REGEN, format="json")
    assert regenerated.status_code == 200
    second_codes = regenerated.json()["recovery_codes"]
    assert len(second_codes) == 10
    assert set(first_codes).isdisjoint(second_codes)
    assert RecoveryCode.objects.filter(user=student).count() == 10

    client.logout()
    client.post(LOGIN, {"email": student.email, "password": TEST_PASSWORD}, format="json")
    old_code_attempt = client.post(
        VERIFY, {"method": "recovery", "code": first_codes[0]}, format="json"
    )
    assert old_code_attempt.status_code == 400


# ---------------------------------------------------------------------------
# Step-up accepts TOTP and recovery as alternatives (extends Phase 4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_step_up_accepts_totp_and_recovery_as_alternatives(api_client_no_csrf, student):
    client = api_client_no_csrf
    client.force_login(student)
    secret, codes = _enrol_and_confirm(client, student)

    totp_code = pyotp.TOTP(secret).now()
    stepped = client.post(STEP_UP, {"method": "totp", "code": totp_code}, format="json")
    assert stepped.status_code == 204

    # A brand-new session, so step-up is stale again.
    client.logout()
    client.force_login(student)
    stepped_recovery = client.post(STEP_UP, {"method": "recovery", "code": codes[1]}, format="json")
    assert stepped_recovery.status_code == 204
    assert RecoveryCode.objects.filter(user=student, used_at__isnull=False).count() == 1


@pytest.mark.django_db
def test_step_up_rejects_method_alongside_a_password(api_client_no_csrf, student):
    client = api_client_no_csrf
    client.force_login(student)
    response = client.post(
        STEP_UP,
        {"password": TEST_PASSWORD, "method": "totp"},
        format="json",
    )
    assert response.status_code == 400
