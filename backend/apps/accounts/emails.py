"""Transactional email for credential flows.

Plain text only. HTML mail would add a template surface and an escaping
responsibility for no benefit on links this short.

Two rules govern everything here:

* The raw token appears in exactly one place — the link in the message body.
  It is never logged, never audited and never returned in an API response.
* Sending failures never propagate. A user must not learn that an address is
  undeliverable from a different HTTP status, and a mail outage must not turn
  a password-reset request into a 500.

Every send is still *recorded*: an audit row says which kind of email went to
which account and whether the mail service took it — never the link or the
code. Without that, an administrator who created a trainer had no way to know
the invitation never left (the staging mail service refused every message for
days and nothing in the product said so). Whether the service *accepted* a
message says nothing about the recipient's mailbox — bounces arrive later and
elsewhere — so this reveals the institution's own mail set-up, not anyone's
address.

Why these are the one kind of email that is *not* queued
--------------------------------------------------------
Phase 9 moved notification email onto a Celery worker, and deliberately left
these behind. Both halves of the queue would store the message: the outbox row
keeps the body in a database table, and the task payload keeps it in Redis. The
body of a reset email *is* the credential — anyone who reads either one can take
the account. §14.5 forbids exactly that, and an operations engineer with
read access to the outbox table is precisely the reader it forbids.

So credential mail is sent inline, and the cost is accepted rather than hidden:
one SMTP round trip on an endpoint that is rate-limited to a handful of requests
a minute, whose failure is already swallowed. A slow request on a rare endpoint
is a smaller problem than a reset link with a shelf life.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("grras.security")

#: Why the last send in this request (or task) failed, for the screen that
#: asked for it. The audit row of a failure is written only after the request
#: ends, so it cannot be read back in time.
_LAST_FAILURE: ContextVar[str] = ContextVar("credential_email_failure", default="")


def last_failure() -> str:
    return _LAST_FAILURE.get()


def _build_link(path: str, token: str, email: str) -> str:
    query = urlencode({"token": token, "email": email}, quote_via=quote)
    return f"{settings.FRONTEND_BASE_URL}{path}?{query}"


#: Which email, in the words the account page uses.
KIND_LABEL = {
    "invitation": "Invitation",
    "password_reset": "Password reset",
    "email_verification": "Email verification",
    "one_time_code": "One-time code",
}


def describe_failure(exc: Exception) -> str:
    """What went wrong, in words an administrator can act on — never the raw
    provider message, which can carry account identifiers."""
    import smtplib
    import socket

    code = getattr(exc, "smtp_code", None)
    text = str(getattr(exc, "smtp_error", b"") or exc).lower()
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The mail service refused this address."
    if code == 554 or "access denied" in text or "not authorized" in text:
        return (
            "The mail service refused to send it: this environment is not allowed to "
            "email this address yet."
        )
    if "not verified" in text or "unverified" in text:
        return "The mail service refused it: the address is not verified with the mail service."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "The mail service rejected the sign-in details this system uses."
    if isinstance(exc, (smtplib.SMTPConnectError, socket.timeout, ConnectionError, OSError)):
        return "The mail service could not be reached."
    return "The mail service reported an error."


def _send(*, subject: str, body: str, user, kind: str) -> bool:
    from apps.audit.models import AuditResult
    from apps.audit.services import AuditAction, record

    recipient = user.email
    error = ""
    try:
        send_mail(
            subject=f"{settings.EMAIL_SUBJECT_PREFIX}{subject}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as exc:
        # The exception detail is logged; the caller learns only that it failed,
        # and the API response to the person asking for a reset is identical
        # either way.
        logger.exception("Failed to send %s email", kind)
        error = describe_failure(exc)
    _LAST_FAILURE.set(error)
    record(
        action=AuditAction.CREDENTIAL_EMAIL_FAILED if error else AuditAction.CREDENTIAL_EMAIL_SENT,
        actor=None,
        actor_label="system",
        resource_type="user",
        resource_id=user.pk,
        result=AuditResult.FAILURE if error else AuditResult.SUCCESS,
        context={"kind": kind, "to": recipient, **({"error": error} if error else {})},
    )
    return not error


def send_password_reset_email(*, user, raw_token: str) -> bool:
    link = _build_link(settings.FRONTEND_PASSWORD_RESET_PATH, raw_token, user.email)
    hours = int(settings.AUTH_TOKEN_RESET_TTL_HOURS)
    body = (
        f"Hello {user.first_name or 'there'},\n\n"
        "We received a request to reset the password for your Grras LMS account.\n\n"
        f"Reset your password:\n{link}\n\n"
        f"This link can be used once and expires in {hours} hour(s).\n\n"
        "If you did not request this, you can ignore this email. Your password "
        "will not change until the link above is used.\n"
    )
    return _send(subject="Reset your password", body=body, user=user, kind="password_reset")


def send_email_verification_email(*, user, raw_token: str) -> bool:
    link = _build_link(settings.FRONTEND_EMAIL_VERIFY_PATH, raw_token, user.email)
    days = int(settings.AUTH_TOKEN_VERIFICATION_TTL_DAYS)
    body = (
        f"Hello {user.first_name or 'there'},\n\n"
        "Confirm this email address for your Grras LMS account.\n\n"
        f"Verify your email:\n{link}\n\n"
        f"This link can be used once and expires in {days} day(s).\n\n"
        "If you did not expect this email, you can ignore it.\n"
    )
    return _send(
        subject="Verify your email address", body=body, user=user, kind="email_verification"
    )


def send_otp_code_email(*, user, code: str, minutes: int) -> bool:
    """One-time code mail (ADR-05, Phase 4).

    Sent inline for the same reason ``send_password_reset_email`` is (see the
    module docstring): the code *is* the credential, and both halves of the
    notification outbox — the ``EmailMessage`` row and the Celery payload —
    would put it somewhere an operator with read access could take the
    account. Worded generically ("confirm it's you") rather than naming
    step-up specifically, since Phase 5 reuses the same code path to deliver
    a sign-in code.
    """
    body = (
        f"Hello {user.first_name or 'there'},\n\n"
        f"Your one-time code is: {code}\n\n"
        f"Use it to confirm it's you. It expires in {minutes} minute(s) and "
        "works once.\n\n"
        "If you did not request this, you can ignore this email — nobody can "
        "do anything with your account without it.\n"
    )
    return _send(subject="Your one-time code", body=body, user=user, kind="one_time_code")


def send_account_created_email(*, user, raw_token: str) -> bool:
    """The invitation: welcome mail for an account somebody else created.

    It carries a set-your-password link rather than a password: an
    administrator never learns, sets or transmits another person's password.
    Opening it and choosing a password also confirms the email address.
    """
    link = _build_link(settings.FRONTEND_PASSWORD_RESET_PATH, raw_token, user.email) + "&invite=1"
    days = int(settings.AUTH_TOKEN_INVITATION_TTL_DAYS)
    body = (
        f"Hello {user.first_name or 'there'},\n\n"
        "An account has been created for you on Grras LMS.\n\n"
        f"Set your password to get started:\n{link}\n\n"
        f"This link works once and expires in {days} day(s). If it has expired, use "
        f"'Forgot password' at {settings.FRONTEND_BASE_URL}/login and a new one is sent.\n"
    )
    return _send(subject="Your Grras LMS account", body=body, user=user, kind="invitation")
