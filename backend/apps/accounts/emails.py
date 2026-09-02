"""Transactional email for credential flows.

Plain text only. HTML mail would add a template surface and an escaping
responsibility for no benefit on links this short.

Two rules govern everything here:

* The raw token appears in exactly one place — the link in the message body.
  It is never logged, never audited and never returned in an API response.
* Sending failures never propagate. A user must not learn that an address is
  undeliverable from a different HTTP status, and a mail outage must not turn
  a password-reset request into a 500.

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
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("grras.security")


def _build_link(path: str, token: str, email: str) -> str:
    query = urlencode({"token": token, "email": email}, quote_via=quote)
    return f"{settings.FRONTEND_BASE_URL}{path}?{query}"


def _send(*, subject: str, body: str, recipient: str, context: str) -> bool:
    try:
        send_mail(
            subject=f"{settings.EMAIL_SUBJECT_PREFIX}{subject}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        # The exception detail is logged; the caller learns only that it failed,
        # and the API response is identical either way.
        logger.exception("Failed to send %s email", context)
        return False
    return True


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
    return _send(
        subject="Reset your password",
        body=body,
        recipient=user.email,
        context="password reset",
    )


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
        subject="Verify your email address",
        body=body,
        recipient=user.email,
        context="email verification",
    )


def send_account_created_email(*, user, raw_token: str) -> bool:
    """Welcome mail for an administrator-created account.

    It carries a password-reset token rather than a password: an administrator
    never learns, sets or transmits another person's password.
    """
    link = _build_link(settings.FRONTEND_PASSWORD_RESET_PATH, raw_token, user.email)
    body = (
        f"Hello {user.first_name or 'there'},\n\n"
        "An account has been created for you on Grras LMS.\n\n"
        f"Set your password to get started:\n{link}\n\n"
        "This link can be used once. If it has expired, use the "
        f"'Forgot password' link at {settings.FRONTEND_BASE_URL}/login to request a new one.\n"
    )
    return _send(
        subject="Your Grras LMS account",
        body=body,
        recipient=user.email,
        context="account created",
    )
