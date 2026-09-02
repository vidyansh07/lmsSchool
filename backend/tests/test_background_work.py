"""§14.10 — what the queue does when things go wrong.

Eager mode makes the happy path indistinguishable from synchronous code, which
is exactly why it is not what these tests exercise. Every test here is about a
failure the queue introduces and must survive: a broker that is down when a
message is written, a task redelivered after a worker died, a scheduled sweep
that has to be the net under both.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.notifications import channels
from apps.notifications.models import EmailMessage, EmailStatus
from apps.notifications.tasks import RETRY_BATCH, retry_pending_email, send_queued_email


@pytest.fixture
def outbox_row(db):
    return EmailMessage.objects.create(
        to_email="student@demo.grras.invalid",
        subject="Your result is available",
        body="Signed in to see it.",
        template="generic",
    )


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------


def test_the_outbox_row_exists_before_anything_is_queued(outbox_row, monkeypatch):
    """The durability claim: the row is written first, the send is queued after.

    Asserted by making the queue explode. If the ordering were reversed, a
    broker outage would leave nothing to retry.
    """
    monkeypatch.setattr(
        channels, "enqueue_email", lambda message: (_ for _ in ()).throw(AssertionError)
    )
    assert EmailMessage.objects.filter(pk=outbox_row.pk).exists()
    assert outbox_row.status == EmailStatus.PENDING


def test_a_broker_outage_leaves_the_message_for_the_sweep(outbox_row, monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    from apps.notifications import tasks

    monkeypatch.setattr(tasks.send_queued_email, "delay", refuse)

    assert channels.enqueue_email(outbox_row) is False

    outbox_row.refresh_from_db()
    assert outbox_row.status == EmailStatus.PENDING
    assert outbox_row.next_attempt_at <= timezone.now()
    # Which means the scheduled sweep will find it.
    assert retry_pending_email()["sent"] == 1


def test_a_broker_error_does_not_reach_the_caller(outbox_row, monkeypatch):
    """Grading must not fail because Redis is unreachable."""
    from apps.notifications import tasks

    def refuse(*args, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(tasks.send_queued_email, "delay", refuse)
    channels.enqueue_email(outbox_row)  # does not raise


# ---------------------------------------------------------------------------
# Redelivery
# ---------------------------------------------------------------------------


def test_a_redelivered_task_does_not_send_the_message_twice(outbox_row, mailoutbox):
    assert send_queued_email(str(outbox_row.pk)) is True
    assert len(mailoutbox) == 1

    # acks_late means a worker that died after sending gets the task again.
    assert send_queued_email(str(outbox_row.pk)) is False
    assert len(mailoutbox) == 1


def test_a_task_for_a_vanished_row_is_a_no_op(db, mailoutbox):
    import uuid

    assert send_queued_email(str(uuid.uuid4())) is False
    assert mailoutbox == []


def test_an_abandoned_message_is_never_retried(outbox_row, mailoutbox):
    outbox_row.status = EmailStatus.ABANDONED
    outbox_row.save(update_fields=["status"])

    assert send_queued_email(str(outbox_row.pk)) is False
    assert retry_pending_email()["sent"] == 0
    assert mailoutbox == []


# ---------------------------------------------------------------------------
# The scheduled sweep
# ---------------------------------------------------------------------------


def test_the_sweep_ignores_messages_that_are_not_due_yet(outbox_row, mailoutbox):
    outbox_row.status = EmailStatus.FAILED
    outbox_row.next_attempt_at = timezone.now() + timezone.timedelta(minutes=10)
    outbox_row.save(update_fields=["status", "next_attempt_at"])

    assert retry_pending_email() == {"sent": 0, "failed": 0}
    assert mailoutbox == []


def test_the_sweep_is_bounded(db, mailoutbox):
    EmailMessage.objects.bulk_create(
        EmailMessage(
            to_email=f"student{index}@demo.grras.invalid",
            subject="Bulk",
            body="body",
            template="generic",
        )
        for index in range(5)
    )

    assert retry_pending_email(limit=2)["sent"] == 2
    assert len(mailoutbox) == 2
    # An absurd limit is clamped rather than trusted.
    assert retry_pending_email(limit=10_000)["sent"] == 3


def test_the_sweep_takes_the_oldest_due_message_first(db, mailoutbox):
    now = timezone.now()
    for offset, address in ((30, "oldest"), (10, "newest")):
        EmailMessage.objects.create(
            to_email=f"{address}@demo.grras.invalid",
            subject="Ordered",
            body="body",
            template="generic",
            next_attempt_at=now - timezone.timedelta(minutes=offset),
        )

    retry_pending_email(limit=1)
    assert mailoutbox[0].to == ["oldest@demo.grras.invalid"]


def test_the_default_batch_is_bounded():
    assert RETRY_BATCH <= 1000


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_no_task_result_is_stored(settings):
    """Task results would keep recipient addresses in Redis for no reader."""
    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert settings.CELERY_RESULT_BACKEND is None


def test_the_worker_acknowledges_late_and_prefetches_one(settings):
    assert settings.CELERY_TASK_ACKS_LATE is True
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1


def test_the_outbox_sweep_is_scheduled(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["retry-pending-email"]
    assert entry["task"] == "notifications.retry_pending_email"
    # Expiry shorter than the interval: a sweep queued during an outage must not
    # pile up behind the next one.
    assert entry["options"]["expires"] < entry["schedule"]


# The two remaining configuration guarantees — that a deployed environment
# requires a broker and refuses eager mode — are asserted in
# `tests/test_security_config.py`, which loads settings in a subprocess. Loading
# a failing settings module in-process leaves it half-initialised in
# `sys.modules` and makes the result depend on test order.


# ---------------------------------------------------------------------------
# What is deliberately not queued
# ---------------------------------------------------------------------------


def test_a_password_reset_link_never_reaches_the_outbox_or_the_broker(db, mailoutbox):
    """§14.5 — the body of a credential email is the credential.

    Queueing it would store it twice: in the outbox table and in the broker
    payload. This asserts the reset path sends directly and leaves no copy.
    """
    from apps.accounts.emails import send_password_reset_email
    from apps.accounts.models import User

    user = User.objects.create_user(
        email="reset@demo.grras.invalid", password="Str0ng-Passphrase!42", first_name="Reset"
    )
    assert send_password_reset_email(user=user, raw_token="a-secret-token") is True

    assert len(mailoutbox) == 1
    assert "a-secret-token" in mailoutbox[0].body
    # Nothing durable holds it.
    assert not EmailMessage.objects.filter(to_email=user.email).exists()
    assert not EmailMessage.objects.filter(body__contains="a-secret-token").exists()
