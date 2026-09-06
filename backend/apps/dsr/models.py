"""Daily status reports.

One row per class, the way attendance is one row per `(session, enrolment)`.
The report and the register describe the same hour from two directions —
"who was there" and "what actually happened" — and neither can stand in for
the other, so a session gets at most one of each (`session` is a
`OneToOneField`, mirroring `AttendanceRecord.session` without the second
dimension attendance needs).

Why counts live on the report as well as on attendance
--------------------------------------------------------
`student_count`, `present_count` and `absent_count` are prefilled from
`AttendanceRecord` when the report is started (see `services.start_dsr`), so a
trainer is not asked to recount a room they just marked. They are copied
rather than computed on read because a report is a point-in-time account: a
correction made to the register next week should not silently rewrite what a
manager already approved. `online_count` and `offline_count` have no
attendance equivalent — attendance does not record how a student joined — and
exist purely for the trainer to state, defaulting to zero rather than null so
a report always renders a number.

Why a workflow at all
----------------------
A register is taken and is simply true. A status report is an account of a
class, and an account is worth a second pair of eyes: a manager reading it may
ask a question, and the trainer may need to say more before it stands as the
record. `DSRStatus` encodes that back-and-forth explicitly rather than as a
free-text field a report might or might not have been "reviewed" — see
`services.TRANSITIONS` for the moves this allows.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers
from apps.common.validators import validate_no_control_characters


class DSRStatus(models.TextChoices):
    """Where a report sits between being written and being acted on.

    ``UNDER_REVIEW`` exists separately from a straight submitted-to-decided
    move because a manager may want to say "I have this" before they have an
    answer — the same reason `AssignmentSubmission` and `StudentProject` both
    carry an in-review state of their own. Nothing requires passing through
    it: a reviewer may decide straight from ``SUBMITTED``.
    """

    DRAFT = "draft", _("Draft")
    SUBMITTED = "submitted", _("Submitted")
    UNDER_REVIEW = "under_review", _("Under review")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    REVISION_REQUIRED = "revision_required", _("Revision required")


#: Statuses in which the trainer's own copy is still theirs to change.
#:
#: Once a report is submitted it becomes the record a manager reads and acts
#: on; a trainer editing it under a reviewer's feet would make "what did they
#: actually write" unanswerable. Read access is unaffected — only the write
#: path checks this.
EDITABLE_STATUSES = frozenset({DSRStatus.DRAFT, DSRStatus.REVISION_REQUIRED})

#: Statuses nothing further can happen to.
TERMINAL_STATUSES = frozenset({DSRStatus.APPROVED, DSRStatus.REJECTED})


class DSRQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "session", "batch", "trainer", "trainer__user", "module", "reviewed_by"
        )


class DSR(SoftDeleteBaseModel):
    session = models.OneToOneField(
        "class_sessions.ClassSession",
        on_delete=models.CASCADE,
        related_name="dsr",
        help_text=_("The class this report is about. One report per class."),
    )
    #: Denormalised from `session.batch` at creation, so a list can be filtered
    #: and ordered by batch without joining through the session on every row —
    #: the same reasoning `AttendanceRecord` would use if a batch-wide report
    #: were common enough to ask for it directly.
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="dsr_reports")
    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        on_delete=models.PROTECT,
        related_name="dsr_reports",
        help_text=_("Who wrote this report."),
    )

    report_date = models.DateField(_("date"), db_index=True)
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))

    module = models.ForeignKey(
        "courses.Module",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dsr_reports",
    )
    planned_topic = models.CharField(
        _("planned topic"), max_length=250, blank=True, validators=[validate_no_control_characters]
    )
    actual_topic = models.CharField(
        _("actual topic"), max_length=250, blank=True, validators=[validate_no_control_characters]
    )

    student_count = models.PositiveIntegerField(_("students on roster"), default=0)
    present_count = models.PositiveIntegerField(_("present"), default=0)
    absent_count = models.PositiveIntegerField(_("absent"), default=0)
    online_count = models.PositiveIntegerField(_("joined online"), default=0)
    offline_count = models.PositiveIntegerField(_("joined in person"), default=0)

    teaching_notes = models.TextField(_("teaching notes"), max_length=2000, blank=True)
    issues = models.TextField(_("issues"), max_length=2000, blank=True)
    student_concerns = models.TextField(_("student concerns"), max_length=2000, blank=True)

    assignment_given = models.BooleanField(_("assignment given"), default=False)
    assessment_conducted = models.BooleanField(_("assessment conducted"), default=False)

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=DSRStatus.choices,
        default=DSRStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dsr_reports_reviewed",
    )
    manager_comments = models.TextField(_("manager comments"), max_length=2000, blank=True)

    objects, all_objects = soft_delete_managers(DSRQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("daily status report")
        verbose_name_plural = _("daily status reports")
        ordering = ("-report_date", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="dsr_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "-report_date"], name="dsr_batch_date_idx"),
            models.Index(fields=["trainer", "-report_date"], name="dsr_trainer_date_idx"),
            models.Index(fields=["status", "-report_date"], name="dsr_status_date_idx"),
        ]

    def __str__(self) -> str:
        return f"DSR {self.session_id} ({self.status})"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": _("The end time must be after the start time.")})

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
