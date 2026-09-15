"""Session inventory and revocation (ERP Phase 6, ADR-06).

ADR-06: "sessions get an index, not a new engine." Django's own session table
(``django.contrib.sessions.models.Session``) stays the single source of truth
for whether a session is actually live — this module never duplicates its
data, it only *indexes* it by user so "which sessions does this person have"
and "sign out this one" are no longer a full-table decode (see
:func:`apps.accounts.services.revoke_sessions`'s docstring on why that was
necessary before this phase).

Security properties, matching the precedent :mod:`apps.accounts.otp` and
:mod:`apps.accounts.mfa` already set:

* **Only a hash of the session key is ever stored** (rule §13) — never the key
  itself, the same discipline ``OneTimeCode.code_hash`` uses. Revoking a
  specific ``UserSession`` therefore means finding the one row in Django's own
  session table whose key hashes to that value (there is no reverse lookup;
  hashing is one-way by design), which is the same linear scan
  ``revoke_sessions`` already does for "sign out everywhere" — acceptable at
  this scale, called out again below.
* **Not soft-deletable.** Like ``OneTimeCode`` and ``MfaDevice``, a revoked
  session is not a record anyone edits or restores; ``revoked_at`` is a plain
  timestamp and the row stays for audit history (rule §7).
* **Written only after a session key is stable.** A row is created in
  :func:`record_login`, called by the views immediately after
  ``django.contrib.auth.login()`` *and* the defensive ``cycle_key()`` call
  that follows it in both ``LoginView`` and ``MfaVerifyView`` — hashing before
  that point would record a key that is about to be thrown away.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.sessions.models import Session as DjangoSession
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ConflictError
from apps.common.models import BaseModel

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from .models import User

#: last_seen_at is touched at most this often per row (SECURITY_DECISIONS
#: "Sessions (Phase 6)"), so an active user does not write on every request.
TOUCH_INTERVAL = timedelta(minutes=5)

_UA_MAX_LENGTH = 512


class CurrentSessionRevokeRefused(ConflictError):
    """Refusing to revoke the session the caller is using right now.

    409, not 400: the request is well-formed and names a real session — it is
    simply the wrong tool for ending *this* one. ``LogoutView`` is.
    """

    default_detail = "That is your current session. Sign out instead."
    default_code = "current_session"


class UserSession(BaseModel):
    """One row per Django session created at login, indexed by user.

    See the module docstring for why only a hash of the key is stored, and
    ``docs/erp/DATA_MODEL.md``'s Authentication section for the field shapes
    this mirrors exactly.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="sessions")
    session_key_hash = models.CharField(max_length=64, unique=True, editable=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    device_label = models.CharField(max_length=80, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("user session")
        verbose_name_plural = _("user sessions")
        indexes = [
            # No separate index on `user` alone: Django already creates one
            # for the ForeignKey column, and a second would only be overhead
            # (`tests/test_database_security.py::test_no_index_duplicates_another`).
            models.Index(fields=["user", "revoked_at"], name="usersession_user_revoked_idx"),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"Session for {self.user_id} ({state}, {self.device_label or 'unknown device'})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


# ---------------------------------------------------------------------------
# Hashing — never the raw key, matching OneTimeCode's precedent (rule §13)
# ---------------------------------------------------------------------------


def hash_session_key(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Device label — a small heuristic, never the raw user-agent string
# ---------------------------------------------------------------------------

#: Order matters: several browsers share substrings with another's user-agent
#: (Edge and Opera both include "Chrome/" and "Safari/"; Chrome includes
#: "Safari/" too), so the more specific pattern must be tried first.
_BROWSER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Edge", re.compile(r"Edg(?:A|iOS)?/")),
    ("Opera", re.compile(r"OPR/|Opera")),
    ("Chrome", re.compile(r"Chrome/")),
    ("Firefox", re.compile(r"Firefox/")),
    ("Safari", re.compile(r"Version/[\d.]+.*Safari/")),
]

#: Same ordering concern: an iPhone's user-agent also contains "Mac OS X" and
#: Android's also contains "Linux", so the mobile OS must be tried first.
_OS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Android", re.compile(r"Android")),
    ("Windows", re.compile(r"Windows NT")),
    ("macOS", re.compile(r"Mac OS X")),
    ("Linux", re.compile(r"Linux")),
]


def device_family(user_agent: str | None) -> tuple[str | None, str | None]:
    """``(browser, os)`` recognised in ``user_agent``, either of which may be
    ``None``. The pair a new-device check compares two logins by."""
    ua = user_agent or ""
    browser = next((name for name, pattern in _BROWSER_PATTERNS if pattern.search(ua)), None)
    os_name = next((name for name, pattern in _OS_PATTERNS if pattern.search(ua)), None)
    return browser, os_name


def device_label(user_agent: str | None) -> str:
    """A short, human label derived from ``user_agent`` — never the raw
    string itself, which can carry near-fingerprinting detail. Falls back to
    a generic label rather than showing something unrecognised."""
    browser, os_name = device_family(user_agent)
    if browser and os_name:
        return f"{browser} on {os_name}"
    if browser:
        return browser
    if os_name:
        return f"Unknown browser on {os_name}"
    return "Unknown device"


# ---------------------------------------------------------------------------
# New-device detection (SECURITY_DECISIONS "Sessions (Phase 6)")
# ---------------------------------------------------------------------------


def _network_key(ip: str | None) -> str | None:
    """``ip`` widened to a /24 (IPv4) or /64 (IPv6) network, as a string, or
    ``None`` when ``ip`` is missing or unparsable."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    prefix = 24 if address.version == 4 else 64
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def is_new_device(*, user, user_agent: str | None, ip: str | None) -> bool:
    """Whether this browser family from this network has never signed this
    user in before — the simple heuristic SECURITY_DECISIONS calls for.

    Looks at every prior ``UserSession`` row for the user, revoked or not: a
    device that was seen once and later signed out is still a *known* device,
    which is the property that keeps this from re-notifying somebody every
    time they sign back in on their own laptop.
    """
    family = device_family(user_agent)
    network = _network_key(ip)
    prior = UserSession.objects.filter(user=user).only("user_agent", "ip")
    for session in prior.iterator():
        if device_family(session.user_agent) == family and _network_key(session.ip) == network:
            return False
    return True


def _notify_new_device(*, user, device_label_: str, ip: str | None) -> None:
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    where = f" from {ip}" if ip else ""
    notify(
        recipient=user,
        kind=NotificationKind.NEW_DEVICE_LOGIN,
        title="New sign-in to your account",
        body=(
            f"Your account was just signed in on {device_label_}{where}. If this "
            "was not you, change your password and contact your administrator."
        ),
        send_email=True,
    )


def _notify_revoked_by_admin(*, user, device_label_: str) -> None:
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=user,
        kind=NotificationKind.SESSION_REVOKED_BY_ADMIN,
        title="A session was ended by an administrator",
        body=(
            f"An administrator signed you out of a session on {device_label_}. If "
            "you did not expect this, contact your administrator."
        ),
        send_email=True,
    )


# ---------------------------------------------------------------------------
# Written at login
# ---------------------------------------------------------------------------


@transaction.atomic
def record_login(*, request, user: User) -> UserSession:
    """Create the ``UserSession`` row for a session that just became real.

    Called by ``LoginView`` and ``MfaVerifyView`` right after
    ``django.contrib.auth.login()`` and the ``cycle_key()`` that follows it —
    never before, because the key is not stable until then (module
    docstring). Detects and, on commit, emails a new-device notice.
    """
    session_key = request.session.session_key
    if not session_key:
        # Belt and braces: every call site cycles the key first, which for the
        # database backend saves it immediately. Nothing should reach here
        # without one, but a session with no key at all is not one this
        # module can index.
        request.session.save()
        session_key = request.session.session_key

    from apps.common.middleware import client_ip

    ip = client_ip(request)
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:_UA_MAX_LENGTH]
    label = device_label(user_agent)
    new_device = is_new_device(user=user, user_agent=user_agent, ip=ip)

    row = UserSession.objects.create(
        user=user,
        session_key_hash=hash_session_key(session_key),
        ip=ip,
        user_agent=user_agent,
        device_label=label,
        last_seen_at=timezone.now(),
    )

    if new_device:
        record(
            action=AuditAction.SESSION_NEW_DEVICE_DETECTED,
            actor=user,
            resource_type="user_session",
            resource_id=row.pk,
            context={"device_label": label, "ip": ip or ""},
            durable=False,
        )
        transaction.on_commit(lambda: _notify_new_device(user=user, device_label_=label, ip=ip))
    return row


# ---------------------------------------------------------------------------
# Touched by TouchSessionActivityMiddleware, at most once per TOUCH_INTERVAL
# ---------------------------------------------------------------------------


def touch_last_seen(session_key: str | None) -> None:
    """Bump ``last_seen_at`` for the session named by ``session_key`` — a
    single guarded ``UPDATE``, not a read followed by a conditional write, so
    an ordinary request costs one indexed statement that usually matches zero
    rows rather than writing every time."""
    if not session_key:
        return
    cutoff = timezone.now() - TOUCH_INTERVAL
    UserSession.objects.filter(
        session_key_hash=hash_session_key(session_key),
        revoked_at__isnull=True,
        last_seen_at__lt=cutoff,
    ).update(last_seen_at=timezone.now())


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_active_sessions(*, user) -> QuerySet[UserSession]:
    """This user's non-revoked sessions, newest activity first."""
    return UserSession.objects.filter(user=user, revoked_at__isnull=True).order_by("-last_seen_at")


# ---------------------------------------------------------------------------
# Revocation — the Django session row is the thing that actually signs
# somebody out; the UserSession row is stamped to match.
# ---------------------------------------------------------------------------


def _live_django_sessions_by_hash() -> dict[str, DjangoSession]:
    """Every non-expired Django session, keyed by the hash of its key.

    The same linear scan ``apps.accounts.services.revoke_sessions`` already
    performs (that function's docstring explains why it is acceptable at this
    scale); this is its read-only twin, used to translate a ``UserSession``
    row back to the real session it indexes, since the raw key is never
    stored anywhere to look up directly (rule §13).
    """
    return {
        hash_session_key(entry.session_key): entry
        for entry in DjangoSession.objects.filter(expire_date__gte=timezone.now()).iterator()
    }


@transaction.atomic
def revoke_session(*, session: UserSession, actor) -> UserSession:
    """Revoke one session: delete the Django session row it indexes (signing
    that device out immediately) and stamp ``revoked_at``.

    ``actor`` may be the session's own owner (self-service) or an
    administrator acting on someone else's account — the audit action and the
    notification differ accordingly. The caller is responsible for refusing
    to revoke the caller's own *current* session through this path (see
    ``CurrentSessionRevokeRefused``) and for any step-up check an admin path
    requires; both are authorization/UX decisions the view makes, not this
    service.
    """
    session = UserSession.objects.select_for_update().get(pk=session.pk)
    if session.revoked_at is None:
        match = _live_django_sessions_by_hash().get(session.session_key_hash)
        if match is not None:
            match.delete()
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at", "updated_at"])

    is_admin_action = actor is not None and actor.pk != session.user_id
    action = (
        AuditAction.SESSION_REVOKED_BY_ADMIN if is_admin_action else AuditAction.SESSION_REVOKED
    )
    record(
        action=action,
        actor=actor,
        resource_type="user_session",
        resource_id=session.pk,
        context={"target_user": str(session.user_id)} if is_admin_action else {},
    )
    if is_admin_action:
        label = session.device_label or "an unknown device"
        transaction.on_commit(
            lambda: _notify_revoked_by_admin(user=session.user, device_label_=label)
        )
    return session


@transaction.atomic
def revoke_other_sessions(*, user, current_session_key_hash: str | None) -> int:
    """Revoke every one of ``user``'s active sessions except the current
    one. Returns how many were revoked."""
    rows = list(
        UserSession.objects.select_for_update()
        .filter(user=user, revoked_at__isnull=True)
        .exclude(session_key_hash=current_session_key_hash or "")
    )
    if not rows:
        return 0

    live = _live_django_sessions_by_hash()
    for row in rows:
        match = live.get(row.session_key_hash)
        if match is not None:
            match.delete()

    now = timezone.now()
    UserSession.objects.filter(pk__in=[row.pk for row in rows]).update(
        revoked_at=now, updated_at=now
    )
    record(
        action=AuditAction.SESSION_REVOKED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
        context={"sessions_revoked": len(rows), "reason": "revoke_others"},
    )
    return len(rows)


def mark_revoked_by_key(session_key: str | None) -> None:
    """Stamp the ``UserSession`` row matching ``session_key`` as revoked,
    without deleting the underlying Django session (the caller — ordinary
    logout — has either just deleted it or is about to).

    No audit entry here: ordinary logout is already recorded by
    ``apps.accounts.signals.on_user_logged_out``. This only keeps the
    inventory truthful so a session ended by plain logout stops showing up as
    "active" in ``GET /auth/sessions/``.
    """
    if not session_key:
        return
    UserSession.objects.filter(
        session_key_hash=hash_session_key(session_key), revoked_at__isnull=True
    ).update(revoked_at=timezone.now())


__all__ = [
    "TOUCH_INTERVAL",
    "CurrentSessionRevokeRefused",
    "UserSession",
    "device_family",
    "device_label",
    "hash_session_key",
    "is_new_device",
    "list_active_sessions",
    "mark_revoked_by_key",
    "record_login",
    "revoke_other_sessions",
    "revoke_session",
    "touch_last_seen",
]
