"""Discussion services.

The denormalised counters on ``Thread`` are maintained here, and only here —
nothing else creates a reply, so they cannot drift.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify

from .models import Reply, Thread


def _is_trainer_of(user, batch) -> bool:
    from apps.batches import access as batch_access

    trainer = batch_access.trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


@transaction.atomic
def create_thread(*, batch, actor: User, title: str, body: str) -> Thread:
    if not body.strip():
        raise ApplicationError({"body": ["Say something."]})

    thread = Thread.objects.create(batch=batch, author=actor, title=title[:200], body=body)

    record(
        action=AuditAction.THREAD_CREATED,
        actor=actor,
        resource_type="thread",
        resource_id=thread.pk,
        context={"batch": batch.code, "title": thread.title},
        durable=False,
    )

    # The trainer is told, because an unanswered question is the failure mode
    # this feature exists to avoid. Students are not: a notification per thread
    # per classmate is how a noticeboard becomes noise.
    if batch.trainer_id and batch.trainer.user_id != getattr(actor, "pk", None):
        notify(
            recipient=batch.trainer.user,
            kind=NotificationKind.BATCH_UPDATED,
            title=f"New question on {batch.code}",
            body=thread.title,
            link_path=f"/discussions/{thread.pk}",
            resource_type="thread",
            resource_id=thread.pk,
        )
    return thread


@transaction.atomic
def reply(*, thread: Thread, actor: User, body: str) -> Reply:
    if thread.is_closed:
        raise ConflictError({"thread": ["This thread is closed."]})
    if not body.strip():
        raise ApplicationError({"body": ["Say something."]})

    from_trainer = _is_trainer_of(actor, thread.batch)
    row = Reply.objects.create(
        thread=thread, author=actor, body=body, is_trainer_response=from_trainer
    )

    Thread.objects.filter(pk=thread.pk).update(
        reply_count=thread.replies.count(),
        last_reply_at=timezone.now(),
        has_trainer_reply=thread.has_trainer_reply or from_trainer,
    )
    thread.refresh_from_db()

    record(
        action=AuditAction.REPLY_CREATED,
        actor=actor,
        resource_type="reply",
        resource_id=row.pk,
        context={"thread": str(thread.pk), "from_trainer": from_trainer},
        durable=False,
    )

    # The person who asked is told when somebody answers, and nobody else.
    if thread.author_id and thread.author_id != getattr(actor, "pk", None):
        notify(
            recipient=thread.author,
            kind=NotificationKind.BATCH_UPDATED,
            title=f"Reply on: {thread.title}",
            body=body[:300],
            link_path=f"/discussions/{thread.pk}",
            resource_type="thread",
            resource_id=thread.pk,
        )
    return row


@transaction.atomic
def set_pinned(*, thread: Thread, actor: User, pinned: bool) -> Thread:
    thread.is_pinned = pinned
    thread.save(update_fields=["is_pinned", "updated_at"])
    record(
        action=AuditAction.THREAD_MODERATED,
        actor=actor,
        resource_type="thread",
        resource_id=thread.pk,
        context={"action": "pinned" if pinned else "unpinned"},
        durable=False,
    )
    return thread


@transaction.atomic
def set_closed(*, thread: Thread, actor: User, closed: bool) -> Thread:
    thread.is_closed = closed
    thread.closed_by = actor if closed and getattr(actor, "pk", None) else None
    thread.closed_at = timezone.now() if closed else None
    thread.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])
    record(
        action=AuditAction.THREAD_MODERATED,
        actor=actor,
        resource_type="thread",
        resource_id=thread.pk,
        context={"action": "closed" if closed else "reopened"},
        durable=False,
    )
    return thread


@transaction.atomic
def hide_reply(*, row: Reply, actor: User, reason: str) -> Reply:
    """Moderate a message. The row stays, and so does the reason."""
    if not reason.strip():
        raise ApplicationError({"reason": ["Say why the message was hidden."]})

    row.is_hidden = True
    row.hidden_by = actor if getattr(actor, "pk", None) else None
    row.hidden_reason = reason[:300]
    row.save(update_fields=["is_hidden", "hidden_by", "hidden_reason", "updated_at"])

    record(
        action=AuditAction.REPLY_HIDDEN,
        actor=actor,
        resource_type="reply",
        resource_id=row.pk,
        context={"thread": str(row.thread_id), "reason": row.hidden_reason},
        durable=False,
    )
    return row


@transaction.atomic
def unhide_reply(*, row: Reply, actor: User) -> Reply:
    row.is_hidden = False
    row.hidden_by = None
    row.hidden_reason = ""
    row.save(update_fields=["is_hidden", "hidden_by", "hidden_reason", "updated_at"])
    record(
        action=AuditAction.REPLY_HIDDEN,
        actor=actor,
        resource_type="reply",
        resource_id=row.pk,
        context={"thread": str(row.thread_id), "action": "restored"},
        durable=False,
    )
    return row
