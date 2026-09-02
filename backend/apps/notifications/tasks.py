"""Background tasks for notification delivery.

Two tasks, and the split between them is the whole retry design.

``send_queued_email`` is the fast path. The outbox row is written inside the
request — one insert, cheap, and durable — and only the SMTP conversation is
queued. That ordering is the point: if the broker is unreachable when the
request runs, the row still exists and still says PENDING, so the message is
late rather than lost. Queue first and a broker outage would silently discard
every password reset sent during it.

``retry_pending_email`` is the slow path, run on a schedule. It picks up
messages whose delivery failed and whose backoff has elapsed, and it is the
only reason a message queued during a provider outage ever arrives. It is also
the net under the fast path: a task lost to a worker dying leaves a PENDING row
that the next sweep collects.

Task arguments are primary keys, never objects. A serialized model in a broker
is a copy of student data sitting in Redis, and it is stale by the time it is
consumed.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("grras.notifications")

#: Bound so one sweep cannot monopolise a worker after a long outage.
RETRY_BATCH = 100


@shared_task(name="notifications.send_queued_email", ignore_result=True)
def send_queued_email(message_id: str) -> bool:
    """Attempt delivery of one outbox row.

    Re-reads the row and checks its status before sending, because
    ``task_acks_late`` makes redelivery possible: a worker killed after the SMTP
    call but before the acknowledgement leaves a task that will run again. The
    status check is what turns that into a no-op instead of a second copy of the
    same email.
    """
    from apps.notifications.channels import send_email_message
    from apps.notifications.models import EmailMessage, EmailStatus

    message = EmailMessage.objects.filter(pk=message_id).first()
    if message is None:
        # The transaction that wrote it rolled back, or it was purged. Neither
        # is an error worth waking anybody for.
        return False
    if message.status not in (EmailStatus.PENDING, EmailStatus.FAILED):
        return False
    return send_email_message(message)


@shared_task(name="notifications.retry_pending_email", ignore_result=True)
def retry_pending_email(limit: int = RETRY_BATCH) -> dict[str, int]:
    """Attempt every queued or failed message whose next attempt is due."""
    from apps.notifications.channels import send_email_message
    from apps.notifications.models import EmailMessage, EmailStatus

    limit = max(1, min(1000, limit))
    due = EmailMessage.objects.filter(
        status__in=(EmailStatus.PENDING, EmailStatus.FAILED),
        next_attempt_at__lte=timezone.now(),
    ).order_by("next_attempt_at")[:limit]

    sent = failed = 0
    for message in due:
        if send_email_message(message):
            sent += 1
        else:
            failed += 1
    if sent or failed:
        logger.info("Email outbox swept", extra={"context": {"sent": sent, "failed": failed}})
    return {"sent": sent, "failed": failed}
