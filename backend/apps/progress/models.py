"""Course completion — §6.6.

One row per enrolment, recording where a student stands against the completion
rules and what a human decided about it.

Why a stored row when the rules are evaluated on read
-----------------------------------------------------
The *evaluation* is derived and recomputed on demand, so a rule change takes
effect immediately (§6.4). The *decision* is not: an administrator approving a
completion is an act, with a person and a moment attached, and a certificate
will later point at it. Those two things have different lifetimes, so they are
different columns — ``rule_snapshot`` holds what the rules said at the moment of
approval, and it is never recomputed afterwards.

That is also the honest answer to "why did this student get a certificate when
they only have 62% attendance?": the snapshot says what the rule was on the day.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class CompletionStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("In progress")
    ELIGIBLE = "eligible", _("Eligible, awaiting approval")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Not approved")


#: A completion an administrator has settled one way or the other.
DECIDED_STATUSES = frozenset({CompletionStatus.APPROVED, CompletionStatus.REJECTED})


class CourseCompletionQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
            "enrollment__course",
            "decided_by",
        )

    def approved(self):
        return self.filter(status=CompletionStatus.APPROVED)


class CourseCompletion(BaseModel):
    """Where one enrolment stands, and what was decided about it."""

    enrollment = models.OneToOneField(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="completion"
    )

    status = models.CharField(
        _("status"),
        max_length=12,
        choices=CompletionStatus.choices,
        default=CompletionStatus.IN_PROGRESS,
    )
    became_eligible_at = models.DateTimeField(_("became eligible at"), null=True, blank=True)

    #: What the rules said when the decision was taken. Never recomputed.
    rule_snapshot = models.JSONField(_("rules at decision"), default=dict, blank=True)

    decided_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completions_decided",
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)
    decision_note = models.CharField(_("note"), max_length=500, blank=True)

    completed_on = models.DateField(
        _("completion date"),
        null=True,
        blank=True,
        help_text=_("The date the course is recorded as finished. Appears on the certificate."),
    )

    objects = CourseCompletionQuerySet.as_manager()

    class Meta:
        verbose_name = _("course completion")
        verbose_name_plural = _("course completions")
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["status"], name="completion_status_idx"),
        ]
        constraints = [
            # An approval must say when the course was finished; a certificate
            # with no completion date is not a certificate.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=CompletionStatus.APPROVED)
                    | models.Q(completed_on__isnull=False)
                ),
                name="completion_approved_has_a_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_id}: {self.status}"

    @property
    def is_approved(self) -> bool:
        return self.status == CompletionStatus.APPROVED

    @property
    def is_decided(self) -> bool:
        return self.status in DECIDED_STATUSES
