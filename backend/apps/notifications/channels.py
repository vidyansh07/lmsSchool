"""Delivery channels — §7.1's "provider-agnostic" requirement, concretely.

A notification is written to the database first and delivered afterwards. Each
channel is a small class with one method, and the registry is a list. Adding SMS
or a push service later is one class and one line; no service, view or caller
changes.

Two rules every channel obeys:

* **Delivery never breaks the notification.** A channel that raises is logged
  and skipped. A mail outage must not turn "grade this assignment" into a 500.
* **Nothing sensitive is logged.** Failures go through `apps.common.logging`'s
  scrubber before they are stored or logged, because a provider's error message
  can echo the headers it was given.
"""

from __future__ import annotations

import logging
from typing import Protocol

from django.utils import timezone

from .models import (
    EmailMessage,
    EmailStatus,
    Notification,
    NotificationKind,
    NotificationPreference,
)
from .templates import render

#: Which template each kind uses. Anything unlisted falls back to `generic`,
#: which is why a new notification kind never fails to send.
TEMPLATE_FOR_KIND: dict[str, str] = {
    NotificationKind.ASSIGNMENT_DUE: "assignment_due",
    NotificationKind.RESULT_PUBLISHED: "result_published",
    NotificationKind.CERTIFICATE_ISSUED: "certificate_issued",
    NotificationKind.ATTENDANCE_WARNING: "attendance_warning",
}

logger = logging.getLogger("grras.notifications")

#: How many times a failed message is retried before it is given up on. Small,
#: because there is no worker yet: retries happen when `send_pending_email` is
#: run, and a message that has failed four times is not going to succeed.
MAX_ATTEMPTS = 4

#: Errors are truncated as well as scrubbed. A provider that returns a whole
#: SMTP transcript should not fill a column.
ERROR_MAX = 500


class Channel(Protocol):
    name: str

    def deliver(self, notification: Notification) -> bool: ...


def _wants_email(notification: Notification) -> bool:
    """Whether this person wants this category by email.

    A missing preference row means the defaults, so nobody has to be
    back-filled. An address that cannot receive mail is skipped rather than
    queued and failed repeatedly.
    """
    recipient = notification.recipient
    if not recipient.email or not recipient.is_active:
        return False

    preference = NotificationPreference.objects.filter(user=recipient).first()
    if preference is None:
        return True
    return preference.wants_email(notification.category)


class EmailChannel:
    """Writes to the outbox and attempts one immediate send."""

    name = "email"

    def deliver(self, notification: Notification) -> bool:
        if not _wants_email(notification):
            return False

        subject, body = render(
            TEMPLATE_FOR_KIND.get(notification.kind, "generic"),
            {
                "first_name": notification.recipient.first_name,
                "title": notification.title,
                "body": notification.body,
                "link_path": notification.link_path,
            },
        )

        message = EmailMessage.objects.create(
            to_email=notification.recipient.email,
            subject=subject[:255],
            body=body,
            template=TEMPLATE_FOR_KIND.get(notification.kind, "generic"),
            notification=notification,
        )
        # The row is written inside the request; the SMTP conversation is not.
        # See `apps.notifications.tasks` for why that order matters.
        enqueue_email(message)
        return True


#: The registry. In-app delivery is the `Notification` row itself, so it is not
#: a channel — writing the row *is* the notification.
CHANNELS: list[Channel] = [EmailChannel()]


def deliver(notification: Notification) -> None:
    """Push one notification through every channel, surviving any of them."""
    for channel in CHANNELS:
        try:
            channel.deliver(notification)
        except Exception:
            logger.exception(
                "Notification channel failed",
                extra={"context": {"channel": channel.name, "notification": str(notification.pk)}},
            )


def enqueue_email(message: EmailMessage) -> bool:
    """Hand one outbox row to the worker, surviving a broker that is down.

    Returns whether the task was queued. A `False` is not a failure to deliver:
    the row is PENDING with `next_attempt_at` already in the past, so the
    scheduled sweep collects it. Raising here instead would turn a Redis blip
    into a failed grading request.
    """
    from apps.notifications.tasks import send_queued_email

    try:
        send_queued_email.delay(str(message.pk))
    except Exception:
        logger.warning(
            "Could not queue an email; it stays in the outbox for the retry sweep",
            extra={"context": {"message": str(message.pk)}},
        )
        return False
    return True


def send_email_message(message: EmailMessage) -> bool:
    """Attempt one delivery, recording the outcome either way."""
    from django.conf import settings
    from django.core.mail import send_mail

    from apps.common.logging import scrub

    message.attempts += 1
    try:
        send_mail(
            subject=f"{settings.EMAIL_SUBJECT_PREFIX}{message.subject}",
            message=message.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[message.to_email],
            fail_silently=False,
        )
    except Exception as exc:
        # Scrubbed before it is stored *or* logged: a provider error can echo
        # the credentials it was handed.
        detail = str(scrub({"error": str(exc)}).get("error", ""))[:ERROR_MAX]
        message.last_error = detail
        message.status = (
            EmailStatus.ABANDONED if message.attempts >= MAX_ATTEMPTS else EmailStatus.FAILED
        )
        message.next_attempt_at = timezone.now() + _backoff(message.attempts)
        message.save(
            update_fields=["attempts", "last_error", "status", "next_attempt_at", "updated_at"]
        )
        logger.warning(
            "Email delivery failed",
            extra={
                "context": {
                    "message": str(message.pk),
                    "attempts": message.attempts,
                    "status": message.status,
                }
            },
        )
        return False

    message.status = EmailStatus.SENT
    message.sent_at = timezone.now()
    message.last_error = ""
    message.save(update_fields=["attempts", "status", "sent_at", "last_error", "updated_at"])
    return True


def _backoff(attempts: int):
    """Exponential, capped. Bounded because there is no worker to spread load."""
    from datetime import timedelta

    return timedelta(minutes=min(60, 5 * (2 ** (attempts - 1))))
