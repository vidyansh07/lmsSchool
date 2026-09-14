"""A manager's ask of the teaching staff.

"We need somebody for the evening Python batch from Monday", "who can cover
Linux next week?" — the owner's answer to the question of how a manager
reaches the trainers (14 September 2026, D-132): a plain announcement to the
trainers of the centre exists too (`Audience.TRAINERS`), but a *requirement*
is a record with a life of its own. It is raised, trainers reply on it, and
the manager closes it — fulfilled by somebody, or not — so the question
"what did we ask for and who answered" has one place to look.

Soft-deleted like everything else a person can remove (D-131). Replies are
not deleted on their own: they are the conversation, and go with the record.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class RequirementStatus(models.TextChoices):
    OPEN = "open", _("Open")
    FULFILLED = "fulfilled", _("Fulfilled")
    CLOSED = "closed", _("Closed")


class TrainerRequirementQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "branch", "raised_by", "batch", "fulfilled_by__user", "closed_by"
        ).prefetch_related("replies__author")

    def open(self):
        return self.filter(status=RequirementStatus.OPEN)


class TrainerRequirement(SoftDeleteBaseModel):
    branch = models.ForeignKey(
        "organisation.Branch",
        on_delete=models.PROTECT,
        related_name="trainer_requirements",
        verbose_name=_("centre"),
    )
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requirements_raised",
        verbose_name=_("raised by"),
    )
    title = models.CharField(_("title"), max_length=160)
    details = models.TextField(_("details"), blank=True)
    batch = models.ForeignKey(
        "batches.Batch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trainer_requirements",
        verbose_name=_("batch"),
        help_text=_("The batch this is about, if there is one."),
    )
    needed_by = models.DateField(_("needed by"), null=True, blank=True)
    status = models.CharField(
        _("status"),
        max_length=12,
        choices=RequirementStatus.choices,
        default=RequirementStatus.OPEN,
    )
    fulfilled_by = models.ForeignKey(
        "trainers.TrainerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirements_fulfilled",
        verbose_name=_("fulfilled by"),
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("closed by"),
    )
    closing_note = models.CharField(_("closing note"), max_length=300, blank=True)

    objects, all_objects = soft_delete_managers(TrainerRequirementQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("trainer requirement")
        verbose_name_plural = _("trainer requirements")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["branch", "status", "-created_at"], name="requirement_branch_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status == RequirementStatus.OPEN


class RequirementReply(BaseModel):
    requirement = models.ForeignKey(
        TrainerRequirement, on_delete=models.CASCADE, related_name="replies"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    message = models.TextField(_("message"))

    class Meta:
        verbose_name = _("requirement reply")
        verbose_name_plural = _("requirement replies")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.author_id} on {self.requirement_id}"
