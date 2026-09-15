"""Email one-time codes (ADR-05) — a generic, reusable second factor.

Built in Phase 4 as one thing only: a way to prove control of the signed-in
user's own inbox. Wired in today as a second way to obtain step-up, alongside
the password (:func:`apps.accounts.stepup.step_up_with_password`).

The model is deliberately generic — ``purpose`` is a plain choice field, not
something baked into the shape of the row — so that Phase 5's pending-MFA
sign-in flow can reuse this exact model with ``purpose="login"`` without a
migration or a field rename. Only ``step_up`` is wired to anything today;
``login`` and ``enrol`` are reserved choices with no handling behind them yet.

Security properties (``docs/erp/SECURITY_DECISIONS.md`` "OTP (Phase 4)"):

* A 6-digit code from :func:`secrets.randbelow`, stored as
  ``SHA-256(salt + code)`` with a per-row salt from :func:`secrets.token_hex`.
  The raw code exists in memory only for the duration of one call and is
  never logged, never audited and never returned by any endpoint.
* 10-minute expiry; 5 verification attempts, after which the code is void
  even if the 6th guess would have been right; resend no sooner than 60
  seconds after the last code of the same purpose; at most 5 sends per user
  per hour and 20 per IP per hour.
* Verification runs under ``select_for_update()`` on the code row, so two
  concurrent verify attempts on the same code cannot both succeed — the
  second waits for the first's lock and then sees its ``consumed_at`` or its
  exhausted ``attempts``.
* Sending has the same shape of hazard, but there is no existing row to take
  ``select_for_update()`` on — the very first send of an hour has nothing to
  lock. ``send_email_code`` instead opens with a Postgres transaction-scoped
  advisory lock (``pg_advisory_xact_lock``), keyed on ``(user, purpose)`` and,
  when an IP is supplied, a second one keyed on that IP — always acquired in
  that order — before any cooldown or hourly-cap count is read. That makes
  the whole count-then-create a single serialised section per key, so two
  concurrent sends for the same user/purpose (or the same IP) cannot both
  pass a cap that only one of them should. The lock is released automatically
  when the transaction ends; acquiring the two locks in a fixed order rules
  out a deadlock between two callers who share only one of the two keys.
* Every outcome — sent, verified, failed, throttled — is audited with the
  purpose and, for a failure, a reason string. Never the code, under any key.

Why delivery bypasses the notification outbox entirely (D-070 extended)
-------------------------------------------------------------------------
``apps.notifications`` writes an ``EmailMessage`` row before queuing the
send, on purpose (D-069) — a broker outage should make mail late, not lost.
That is the right trade for a due-date reminder. It is the wrong trade here:
the body of this email *is* the credential, exactly as D-070 already found
for password-reset and verification mail, and for the same reason — an
outbox row is a database table an operations engineer can read, and a
queued task payload is a Redis key the same engineer can read. So the code
is emailed inline, through :mod:`apps.accounts.emails`, the same module and
the same pattern password-reset and account-created mail already use, on an
endpoint already throttled to a handful of requests an hour.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from hashlib import sha256

from django.db import connection, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import Throttled

from apps.audit.services import AuditAction, AuditResult, record
from apps.common.models import BaseModel

from .emails import send_otp_code_email

CODE_DIGITS = 6
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_USER_PER_HOUR = 5
MAX_SENDS_PER_IP_PER_HOUR = 20
_SALT_BYTES = 16  # secrets.token_hex(16) -> 32 hex characters


class OtpPurpose(models.TextChoices):
    """What the code is proving control of an inbox *for*.

    Only ``STEP_UP`` has a caller today. ``LOGIN`` and ``ENROL`` are named now
    so Phase 5 (pending-MFA sign-in) and a later enrolment-verification flow
    do not need to touch this enum's shape — they need only start passing it.
    """

    STEP_UP = "step_up", _("Step-up authentication")
    LOGIN = "login", _("Sign-in second factor")
    ENROL = "enrol", _("Enrolment verification")


class OneTimeCode(BaseModel):
    """A short-lived security artifact.

    Not soft-deletable on purpose: a consumed or expired code is not a record
    anyone recovers, edits or reports on — it is scratch state with a 10-minute
    shelf life, so it takes the plain :class:`~apps.common.models.BaseModel`
    rather than :class:`~apps.common.models.SoftDeleteBaseModel`.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="one_time_codes"
    )
    purpose = models.CharField(max_length=20, choices=OtpPurpose.choices, db_index=True)
    code_hash = models.CharField(max_length=64, editable=False)
    salt = models.CharField(max_length=32, editable=False)
    sent_to = models.EmailField(max_length=254)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = _("one-time code")
        verbose_name_plural = _("one-time codes")
        indexes = [
            models.Index(
                fields=["user", "purpose", "created_at"], name="otc_user_purpose_time_idx"
            ),
        ]

    def __str__(self) -> str:
        # Deliberately never renders the hash, the salt or anything derived
        # from the code.
        return f"{self.get_purpose_display()} code for {self.user_id} ({self.created_at:%Y-%m-%d})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_void(self) -> bool:
        """Attempts exhausted: the code is dead even if the next guess is right."""
        return self.attempts >= MAX_ATTEMPTS


def _hash_code(*, salt: str, code: str) -> str:
    return sha256(f"{salt}{code}".encode()).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def _advisory_lock_key(*parts: str) -> int:
    """A deterministic signed 64-bit key for ``pg_advisory_xact_lock``.

    Never derived from the code — only from identifiers (``user``, ``purpose``,
    an IP) that are already fine to compute on and are not secrets.
    """
    digest = sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _lock_for_send(key: int) -> None:
    """Block until ``key`` is free, then hold it for the rest of this
    transaction (released automatically on commit or rollback)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _throttled(*, user, purpose: str, reason: str, wait: float) -> None:
    """Audit the refusal and raise the same ``Throttled`` shape DRF's own
    throttle classes answer with (see ``api_exception_handler``), so a
    service-level limit and a view-level one look identical to a client."""
    record(
        action=AuditAction.OTP_THROTTLED,
        actor=user,
        resource_type="one_time_code",
        result=AuditResult.DENIED,
        context={"purpose": purpose, "reason": reason},
    )
    raise Throttled(wait=wait)


@transaction.atomic
def send_email_code(*, user, purpose: str, request_ip: str | None = None) -> OneTimeCode:
    """Create and email a 6-digit one-time code of ``purpose`` for ``user``.

    Opens by taking a Postgres advisory lock scoped to ``(user, purpose)``
    — and, when ``request_ip`` is given, a second one scoped to that IP —
    so that the resend cooldown and the per-user/per-IP hourly caps that
    follow are checked and acted on as one serialised section per key
    instead of a check-then-act race between concurrent callers. Enforces,
    in order, the resend cooldown and the per-user and per-IP hourly caps,
    raising :class:`rest_framework.exceptions.Throttled` (mapped by the
    shared exception handler to ``429 rate_limited``) the first time one is
    exceeded — nothing is created or sent when a limit refuses the call.
    """
    _lock_for_send(_advisory_lock_key("otp:send:user", str(user.pk), purpose))
    if request_ip:
        _lock_for_send(_advisory_lock_key("otp:send:ip", request_ip))

    now = timezone.now()
    window_start = now - timedelta(hours=1)

    last = OneTimeCode.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if last is not None:
        elapsed = (now - last.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            _throttled(
                user=user,
                purpose=purpose,
                reason="resend_too_soon",
                wait=RESEND_COOLDOWN_SECONDS - elapsed,
            )

    sent_this_hour = OneTimeCode.objects.filter(
        user=user, purpose=purpose, created_at__gte=window_start
    ).count()
    if sent_this_hour >= MAX_SENDS_PER_USER_PER_HOUR:
        _throttled(user=user, purpose=purpose, reason="user_hourly_cap", wait=3600)

    if request_ip:
        sent_from_ip = OneTimeCode.objects.filter(
            request_ip=request_ip, created_at__gte=window_start
        ).count()
        if sent_from_ip >= MAX_SENDS_PER_IP_PER_HOUR:
            _throttled(user=user, purpose=purpose, reason="ip_hourly_cap", wait=3600)

    code = _generate_code()
    salt = secrets.token_hex(_SALT_BYTES)
    row = OneTimeCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=_hash_code(salt=salt, code=code),
        salt=salt,
        sent_to=user.email,
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
        request_ip=request_ip,
    )

    # Inline, never through the outbox — see the module docstring.
    send_otp_code_email(user=user, code=code, minutes=CODE_TTL_MINUTES)
    del code  # out of scope the moment it is no longer needed

    record(
        action=AuditAction.OTP_SENT,
        actor=user,
        resource_type="one_time_code",
        resource_id=row.pk,
        context={"purpose": purpose},
        durable=False,
    )
    return row


@transaction.atomic
def verify_email_code(*, user, purpose: str, code: str, request_ip: str | None = None) -> bool:
    """Check ``code`` against the newest unconsumed code of ``purpose`` for
    ``user``, returning whether it matched.

    Runs under ``select_for_update()`` on that one row: a second concurrent
    call blocks until the first commits, then sees the first's ``consumed_at``
    or its exhausted ``attempts`` — so two simultaneous verifications of the
    same code cannot both return ``True``.
    """
    row = (
        OneTimeCode.objects.select_for_update()
        .filter(user=user, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if row is None or row.is_expired or row.is_void:
        record(
            action=AuditAction.OTP_FAILED,
            actor=user,
            resource_type="one_time_code",
            resource_id=getattr(row, "pk", ""),
            result=AuditResult.FAILURE,
            context={"purpose": purpose, "reason": "no_valid_code"},
        )
        return False

    submitted = (code or "").strip()
    matches = hmac.compare_digest(row.code_hash, _hash_code(salt=row.salt, code=submitted))

    if not matches:
        row.attempts += 1
        row.save(update_fields=["attempts", "updated_at"])
        record(
            action=AuditAction.OTP_FAILED,
            actor=user,
            resource_type="one_time_code",
            resource_id=row.pk,
            result=AuditResult.FAILURE,
            context={"purpose": purpose, "reason": "wrong_code"},
        )
        return False

    row.consumed_at = timezone.now()
    row.save(update_fields=["consumed_at", "updated_at"])
    record(
        action=AuditAction.OTP_VERIFIED,
        actor=user,
        resource_type="one_time_code",
        resource_id=row.pk,
        context={"purpose": purpose},
        durable=False,
    )
    return True


__all__ = [
    "CODE_TTL_MINUTES",
    "MAX_ATTEMPTS",
    "MAX_SENDS_PER_IP_PER_HOUR",
    "MAX_SENDS_PER_USER_PER_HOUR",
    "RESEND_COOLDOWN_SECONDS",
    "OneTimeCode",
    "OtpPurpose",
    "send_email_code",
    "verify_email_code",
]
