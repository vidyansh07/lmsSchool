"""Email one-time codes (ERP Phase 4, ADR-05).

Covers:

- happy path: request a code by email, verify it, obtain a fresh step-up;
- a wrong code refuses and leaves the session unstepped;
- exactly one of ``password``/``code`` is required, never both, never neither;
- unknown fields are rejected (mass-assignment defence);
- expiry;
- the attempt limit — 5 wrong attempts void the code, and a 6th attempt with
  the *right* code still fails because the code is already void;
- the 60-second resend cooldown, per-user and per-IP hourly send caps, all
  answered as DRF's own ``Throttled`` (429 ``rate_limited``);
- every outcome (sent, verified, failed, throttled) is audited;
- the genuine concurrency case — two simultaneous verify attempts on the same
  valid code — using real threads on real connections, not a sequential
  double-call;
- the plaintext code never appears in any ``AuditLog`` row's context.
"""

from __future__ import annotations

import re
import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import Throttled

from apps.accounts import stepup
from apps.accounts.otp import (
    MAX_ATTEMPTS,
    OneTimeCode,
    OtpPurpose,
    send_email_code,
    verify_email_code,
)
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import flush_deferred
from apps.common.request_context import take_deferred_audits
from tests.conftest import TEST_PASSWORD


def _flush_deferred_audits() -> None:
    """Write queued (non-success) audit entries written by a direct service
    call. A real request's middleware does this after the response; these
    tests call the service directly, so nothing does it for them."""
    flush_deferred(take_deferred_audits())


STEP_UP = "/api/v1/auth/step-up/"
REQUEST_CODE = "/api/v1/auth/step-up/request-code/"

_CODE_RE = re.compile(r"one-time code is: (\d{6})")


def _extract_code(body: str) -> str:
    match = _CODE_RE.search(body)
    assert match is not None
    return match.group(1)


def _wrong_code(right: str) -> str:
    """A code guaranteed not to match, without ever printing `right`."""
    return "000000" if right != "000000" else "111111"


def _seed_code(*, user, purpose=OtpPurpose.STEP_UP, minutes_ago=0, request_ip=None):
    """A row for counting/expiry tests. The hash is a placeholder — these
    tests only ever check *how many* rows exist or *when*, never verify
    against this row's code."""
    row = OneTimeCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash="0" * 64,
        salt="0" * 32,
        sent_to=user.email,
        expires_at=timezone.now() + timedelta(minutes=10),
        request_ip=request_ip,
    )
    if minutes_ago:
        OneTimeCode.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
    return row


# ---------------------------------------------------------------------------
# Happy path and the API contract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_then_verify_grants_step_up(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    mail.outbox.clear()

    requested = api_client_no_csrf.post(REQUEST_CODE, format="json")
    assert requested.status_code == 202, requested.json()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [student.email]
    code = _extract_code(mail.outbox[0].body)

    stepped = api_client_no_csrf.post(STEP_UP, {"code": code}, format="json")
    assert stepped.status_code == 204, stepped.content

    assert api_client_no_csrf.session.get(stepup.SESSION_KEY) is not None
    row = OneTimeCode.objects.get(user=student, purpose=OtpPurpose.STEP_UP)
    assert row.consumed_at is not None

    actions = set(AuditLog.objects.filter(actor=student).values_list("action", flat=True))
    assert AuditAction.OTP_SENT in actions
    assert AuditAction.OTP_VERIFIED in actions
    assert AuditAction.STEP_UP_SUCCEEDED in actions


@pytest.mark.django_db
def test_wrong_code_is_refused_and_leaves_step_up_stale(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    mail.outbox.clear()
    send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    code = _extract_code(mail.outbox[0].body)

    refused = api_client_no_csrf.post(STEP_UP, {"code": _wrong_code(code)}, format="json")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"
    assert api_client_no_csrf.session.get(stepup.SESSION_KEY) is None


@pytest.mark.django_db
def test_password_or_code_but_not_both_or_neither(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)

    both = api_client_no_csrf.post(
        STEP_UP, {"password": TEST_PASSWORD, "code": "123456"}, format="json"
    )
    assert both.status_code == 400

    neither = api_client_no_csrf.post(STEP_UP, {}, format="json")
    assert neither.status_code == 400

    # The password path still works on its own — this phase only adds an
    # alternative, it does not touch the existing one.
    password_only = api_client_no_csrf.post(STEP_UP, {"password": TEST_PASSWORD}, format="json")
    assert password_only.status_code == 204


@pytest.mark.django_db
def test_unknown_field_is_rejected(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(STEP_UP, {"code": "123456", "extra": "nope"}, format="json")
    assert response.status_code == 400
    assert "extra" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_purpose_choices_reserve_room_for_future_phases():
    """Phase 5 (login) and a future enrolment flow reuse this exact model."""
    assert {choice for choice, _label in OtpPurpose.choices} == {"step_up", "login", "enrol"}


# ---------------------------------------------------------------------------
# Expiry and the attempt limit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_expired_code_is_refused(student):
    mail.outbox.clear()
    row = send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    code = _extract_code(mail.outbox[0].body)
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save(update_fields=["expires_at"])

    assert verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=code) is False
    row.refresh_from_db()
    assert row.consumed_at is None


@pytest.mark.django_db
def test_five_wrong_attempts_void_the_code_even_for_a_later_correct_guess(student):
    mail.outbox.clear()
    send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    code = _extract_code(mail.outbox[0].body)
    wrong = _wrong_code(code)

    for _ in range(MAX_ATTEMPTS):
        assert verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=wrong) is False

    # The 6th attempt, even with the right code, still fails: void is void.
    assert verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=code) is False
    _flush_deferred_audits()

    row = OneTimeCode.objects.get(user=student, purpose=OtpPurpose.STEP_UP)
    assert row.attempts == MAX_ATTEMPTS
    assert row.consumed_at is None

    failures = AuditLog.objects.filter(actor=student, action=AuditAction.OTP_FAILED).count()
    assert failures == MAX_ATTEMPTS + 1


# ---------------------------------------------------------------------------
# Throttles
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resend_before_sixty_seconds_is_throttled(student):
    send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    with pytest.raises(Throttled):
        send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    _flush_deferred_audits()
    assert OneTimeCode.objects.filter(user=student, purpose=OtpPurpose.STEP_UP).count() == 1

    actions = list(
        AuditLog.objects.filter(actor=student, action=AuditAction.OTP_THROTTLED).values_list(
            "context", flat=True
        )
    )
    assert actions and actions[0]["reason"] == "resend_too_soon"


@pytest.mark.django_db
def test_resend_too_soon_answers_429_from_the_endpoint(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    first = api_client_no_csrf.post(REQUEST_CODE, format="json")
    assert first.status_code == 202

    second = api_client_no_csrf.post(REQUEST_CODE, format="json")
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


@pytest.mark.django_db
def test_five_sends_per_user_per_hour_then_throttled(student):
    for step in range(5):
        _seed_code(user=student, minutes_ago=10 + step)

    with pytest.raises(Throttled):
        send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    assert OneTimeCode.objects.filter(user=student, purpose=OtpPurpose.STEP_UP).count() == 5


@pytest.mark.django_db
def test_twenty_sends_per_ip_per_hour_then_throttled(student, trainer):
    ip = "203.0.113.5"
    for _step in range(20):
        _seed_code(user=student, minutes_ago=5, request_ip=ip)

    # A different user, at the same IP, comfortably past their own cooldown
    # and nowhere near their own per-user cap: only the IP cap can fire.
    with pytest.raises(Throttled):
        send_email_code(user=trainer, purpose=OtpPurpose.STEP_UP, request_ip=ip)
    assert OneTimeCode.objects.filter(user=trainer).count() == 0


# ---------------------------------------------------------------------------
# Concurrency: two verifies on the same code, at once
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_verifies_only_one_succeeds(student):
    """§Phase 4 gate test: the case a single-threaded call cannot reach.

    ``select_for_update`` serialises the two attempts on the row: whichever
    thread commits first consumes the code, and the other's select then finds
    no unconsumed row left to match against — it fails, but not because it
    guessed wrong, so `attempts` stays untouched.
    """
    mail.outbox.clear()
    send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    code = _extract_code(mail.outbox[0].body)

    results: list[bool] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=code))
        except Exception as exc:  # pragma: no cover - surfaced via `errors`
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert sorted(results) == [False, True]

    row = OneTimeCode.objects.get(user=student, purpose=OtpPurpose.STEP_UP)
    assert row.consumed_at is not None
    assert row.attempts == 0


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_sends_only_one_succeeds(student):
    """The send-side counterpart of the verify concurrency test above.

    ``send_email_code`` is a count-then-create against the resend cooldown:
    without serialising it, two requests racing on an empty history could
    both read "no code sent yet" and both create a row, defeating the
    60-second cooldown between them. The advisory lock taken at the top of
    the function forces the second caller's checks to run only after the
    first's row already exists, so exactly one send succeeds and the other
    is throttled — never both, and never a lost row.
    """
    results: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        try:
            barrier.wait(timeout=5)
            send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
            results.append("sent")
        except Throttled:
            results.append("throttled")
        except Exception as exc:  # pragma: no cover - surfaced via `errors`
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert sorted(results) == ["sent", "throttled"]
    assert OneTimeCode.objects.filter(user=student, purpose=OtpPurpose.STEP_UP).count() == 1


# ---------------------------------------------------------------------------
# Secrecy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_code_never_appears_in_any_audit_context(student):
    mail.outbox.clear()
    send_email_code(user=student, purpose=OtpPurpose.STEP_UP)
    code = _extract_code(mail.outbox[0].body)

    verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=_wrong_code(code))
    verify_email_code(user=student, purpose=OtpPurpose.STEP_UP, code=code)
    _flush_deferred_audits()

    contexts = AuditLog.objects.filter(
        action__in=[
            AuditAction.OTP_SENT,
            AuditAction.OTP_VERIFIED,
            AuditAction.OTP_FAILED,
            AuditAction.OTP_THROTTLED,
        ]
    ).values_list("context", flat=True)

    # A boolean, not the code itself, is what reaches the assert below — so a
    # failure here never prints the raw code into the test output.
    leaked = any(code in str(context) for context in contexts)
    assert leaked is False

    # And never in the row itself, beyond its one-way hash.
    row = OneTimeCode.objects.get(user=student, purpose=OtpPurpose.STEP_UP)
    stored_leaked = code in row.code_hash
    assert stored_leaked is False
