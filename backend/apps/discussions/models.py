"""Course and batch discussions — §7.6.

    "Build lightweight course/batch discussions where useful. Do not build a
    general social network."

So: a thread belongs to a **batch**, has replies, and that is the whole shape.
No following, no profiles, no direct messages, no reactions, no cross-batch
feed. A student talks to the people in the room with them, and to their trainer.

Moderation is a state, not a delete
-----------------------------------
Hiding a reply keeps the row and records who hid it. A deleted reply leaves a
conversation that no longer makes sense, and leaves nothing to appeal to if the
moderation was wrong.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class ThreadQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("batch", "batch__course", "author", "closed_by")

    def open(self):
        return self.filter(is_closed=False)


class Thread(BaseModel):
    """A question or a discussion on one batch."""

    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="threads")
    author = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="threads"
    )

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    body = models.TextField(_("body"))

    is_pinned = models.BooleanField(_("pinned"), default=False)
    is_closed = models.BooleanField(
        _("closed"), default=False, help_text=_("Closed threads are readable but take no replies.")
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="threads_closed",
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)

    #: Denormalised so a list of thirty threads does not cost thirty counts.
    #: Maintained by the service, which is the only thing that creates replies.
    reply_count = models.PositiveIntegerField(_("replies"), default=0)
    last_reply_at = models.DateTimeField(_("last reply"), null=True, blank=True)
    has_trainer_reply = models.BooleanField(_("answered by a trainer"), default=False)

    objects = ThreadQuerySet.as_manager()

    class Meta:
        verbose_name = _("discussion thread")
        verbose_name_plural = _("discussion threads")
        ordering = ("-is_pinned", "-last_reply_at", "-created_at")
        indexes = [
            models.Index(fields=["batch", "-created_at"], name="thread_batch_recent_idx"),
            models.Index(fields=["batch", "is_pinned"], name="thread_pinned_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class ReplyQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("thread", "author", "hidden_by")

    def visible(self):
        return self.filter(is_hidden=False)


class Reply(BaseModel):
    """One message in a thread."""

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="replies"
    )
    body = models.TextField(_("body"))

    #: Recorded at the time rather than derived from the author's current role:
    #: a trainer who later becomes an administrator still answered as a trainer.
    is_trainer_response = models.BooleanField(_("from a trainer"), default=False)

    is_hidden = models.BooleanField(_("hidden"), default=False)
    hidden_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies_hidden",
    )
    hidden_reason = models.CharField(_("reason"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("discussion reply")
        verbose_name_plural = _("discussion replies")
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["thread", "created_at"], name="reply_thread_order_idx"),
        ]

    objects = ReplyQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.thread_id}: {self.body[:40]}"
