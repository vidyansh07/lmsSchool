"""Performance reviews and feedback.

Two records, deliberately different weights:

* :class:`PerformanceReview` is a scored, periodic judgement — the thing a
  manager sits down and writes once a month or once a term, with a rating and
  a frozen snapshot of the numbers that justified it.
* :class:`Feedback` is a remark — a line left after a class, with none of that
  ceremony.

Both are soft-deletable, like every other domain record here (see
:mod:`apps.common.models`): a review written in error is withdrawn, not erased,
because "somebody reviewed me and then it vanished" is exactly the kind of gap
an audit trail exists to prevent.

Exactly one subject
--------------------
A review or a piece of feedback is about a student, or about a trainer, never
both and never neither. ``subject_type`` names which, and a database
``CheckConstraint`` — not application code — enforces that the matching foreign
key is set and the other is null. Application code that got this wrong would
produce a record with no subject at all, discovered only when a screen tries
to render it.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class PerformanceSubjectType(models.TextChoices):
    STUDENT = "student", _("Student")
    TRAINER = "trainer", _("Trainer")


def _subject_matches_type(prefix: str = "") -> models.Q:
    """The constraint every subject-typed model here shares.

    A function rather than a shared abstract base: the two models differ in
    almost everything else, and duplicating four lines of `Q` is cheaper to
    read than a mixin built for just this.
    """
    return models.Q(
        **{
            "subject_type": PerformanceSubjectType.STUDENT,
            f"{prefix}student__isnull": False,
            f"{prefix}trainer__isnull": True,
        }
    ) | models.Q(
        **{
            "subject_type": PerformanceSubjectType.TRAINER,
            f"{prefix}student__isnull": True,
            f"{prefix}trainer__isnull": False,
        }
    )


class PerformanceReviewQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "student", "student__user", "trainer", "trainer__user", "reviewer"
        )


class PerformanceReview(SoftDeleteBaseModel):
    """A point-in-time, rated judgement on a student's or a trainer's performance.

    ``snapshot`` freezes :mod:`apps.performance.engine`'s output at the moment
    the review was written, and is never recalculated. A review is a record of
    what a reviewer *saw* and decided; if a later attendance correction moved
    the numbers underneath it, the review would silently appear to have judged
    data that never existed, and "what did they actually see when they wrote
    this" would have no answer. History is frozen. Only the live dashboard —
    `apps.performance.engine` called fresh — moves when the underlying records
    change.
    """

    subject_type = models.CharField(
        _("subject type"), max_length=10, choices=PerformanceSubjectType.choices
    )
    student = models.ForeignKey(
        "students.StudentProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="performance_reviews",
    )
    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="performance_reviews",
    )

    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))

    rating = models.PositiveSmallIntegerField(
        _("rating"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("1 (serious concern) to 5 (excellent)."),
    )
    summary = models.TextField(_("summary"), blank=True)
    strengths = models.TextField(_("strengths"), blank=True)
    concerns = models.TextField(_("concerns"), blank=True)
    actions = models.TextField(_("agreed actions"), blank=True)

    snapshot = models.JSONField(
        _("performance snapshot"),
        default=dict,
        blank=True,
        help_text=_(
            "The engine's output at the moment this review was written. Frozen — "
            "never recomputed, even if the underlying records change later."
        ),
    )

    reviewer = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="performance_reviews_written",
        help_text=_("Who wrote it. Null if that account has since been removed."),
    )

    objects, all_objects = soft_delete_managers(PerformanceReviewQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("performance review")
        verbose_name_plural = _("performance reviews")
        ordering = ("-period_end", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=_subject_matches_type(),
                name="performance_review_subject_matches_type",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="performance_review_period_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "-period_end"], name="perfreview_student_idx"),
            models.Index(fields=["trainer", "-period_end"], name="perfreview_trainer_idx"),
            models.Index(fields=["reviewer", "-created_at"], name="perfreview_reviewer_idx"),
        ]

    def __str__(self) -> str:
        who = self.student_id or self.trainer_id
        return f"{self.subject_type} review {who} ({self.period_start} to {self.period_end})"


class FeedbackQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "student", "student__user", "trainer", "trainer__user", "batch", "author"
        )


class Feedback(SoftDeleteBaseModel):
    """A lighter note than a review: one remark, not a scored assessment.

    No rating, no snapshot, no fixed period — a trainer leaving a line after a
    class, or a manager noting something worth recording, without the ceremony
    a formal review carries.

    ``visible_to_subject`` is what keeps this from being redundant with a
    review: most feedback is written to be read by the person it is about, but
    a manager's private note about a trainer — kept for the next formal review
    — is feedback too, just not shown to them yet.
    """

    subject_type = models.CharField(
        _("subject type"), max_length=10, choices=PerformanceSubjectType.choices
    )
    student = models.ForeignKey(
        "students.StudentProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feedback_received",
    )
    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feedback_received",
    )
    batch = models.ForeignKey(
        "batches.Batch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback",
        help_text=_("The class this feedback relates to, if any."),
    )

    body = models.TextField(_("feedback"), max_length=5000)
    visible_to_subject = models.BooleanField(_("visible to the subject"), default=True)

    author = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_written",
        help_text=_("Who wrote it. Null if that account has since been removed."),
    )

    objects, all_objects = soft_delete_managers(FeedbackQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("feedback")
        verbose_name_plural = _("feedback")
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=_subject_matches_type(),
                name="feedback_subject_matches_type",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "-created_at"], name="feedback_student_idx"),
            models.Index(fields=["trainer", "-created_at"], name="feedback_trainer_idx"),
            models.Index(fields=["batch", "-created_at"], name="feedback_batch_idx"),
        ]

    def __str__(self) -> str:
        who = self.student_id or self.trainer_id
        return f"Feedback for {self.subject_type} {who}"
