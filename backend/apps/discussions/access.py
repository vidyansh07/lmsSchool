"""Discussion access.

A thread belongs to a batch, so the rule is the batch rule: the students
enrolled on it, the trainer who teaches it, and staff who can already see it.
That is deliberately the *same* answer as everywhere else — a discussion is not
a separate permission universe.

Moderation is narrower: the batch's trainer and capability holders. A student
cannot hide another student's reply, and a trainer cannot moderate a batch they
do not teach.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access

from .models import Reply, Thread


def visible_threads(user) -> QuerySet[Thread]:
    """Threads on batches the caller can already reach."""
    return Thread.objects.with_related().filter(batch__in=batch_access.visible_batches(user))


def can_post_in(user, batch) -> bool:
    """May the caller start a thread or reply on this batch?

    Enrolment must be *live*: a cancelled student keeps their history but stops
    taking part.

    The capability branch answers through `visible_batches`, not through the
    capability alone. Every caller today resolves the batch out of that same
    queryset first, so the short-circuit was unreachable — but it was also an
    assertion that a moderator may moderate every centre's discussions, which
    stopped being true the day batches were bounded to a centre. CONVENTIONS
    §3.5: the boolean and the queryset are two halves of one rule and must not
    be able to disagree.
    """
    if has_capability(user, Capability.DISCUSSION_MODERATE_ANY):
        return batch_access.visible_batches(user).filter(pk=batch.pk).exists()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return batch.trainer_id == trainer.pk

    student = batch_access.student_profile(user)
    if student is None:
        return False

    from apps.enrollments.models import Enrollment

    rows = Enrollment.objects.granting_access().filter(student=student, batch=batch)
    return any(row.grants_access() for row in rows)


def can_moderate(user, batch) -> bool:
    """Pin, close, and hide replies. Through the queryset, as `can_post_in` is."""
    if has_capability(user, Capability.DISCUSSION_MODERATE_ANY):
        return batch_access.visible_batches(user).filter(pk=batch.pk).exists()
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and batch.trainer_id == trainer.pk


def can_edit_reply(user, reply: Reply) -> bool:
    """A person may edit their own words; a moderator may hide anybody's."""
    return reply.author_id == getattr(user, "pk", None)


def visible_replies(user, thread: Thread):
    """Replies in a thread.

    A hidden reply stays visible to its author and to moderators — the author so
    they can see what happened to their message, the moderator so the decision
    is reviewable. Everybody else sees the conversation without it.
    """
    rows = thread.replies.with_related()
    if can_moderate(user, thread.batch):
        return rows
    from django.db.models import Q

    return rows.filter(Q(is_hidden=False) | Q(author_id=getattr(user, "pk", None)))
