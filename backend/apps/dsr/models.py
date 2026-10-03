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

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)
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

#: Statuses in which the class has its report. Submitted is enough; a
#: manager's approval, when one is given, is a courtesy rather than a step.
DONE_STATUSES = frozenset({DSRStatus.SUBMITTED, DSRStatus.UNDER_REVIEW, DSRStatus.APPROVED})

#: Statuses nothing further can happen to.
#:
#: Only `APPROVED`. `REJECTED` was here too, and that was a trap: a rejected
#: report could not be revised and — because one report per class is enforced
#: against every row including soft-deleted ones — no replacement could be
#: written either. The class permanently had no acceptable report and nobody,
#: at any level, could fix it.
#:
#: The class happened, so a report about it has to be possible. Rejecting one
#: sends it back to the trainer as a draft to rewrite; see `TRANSITIONS`.
TERMINAL_STATUSES = frozenset({DSRStatus.APPROVED})


def _lesson_model():
    from django.apps import apps

    return apps.get_model("courses", "Lesson")


class DSRQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "session",
            "session__planned_lesson__module",
            "batch",
            "trainer",
            "trainer__user",
            "module",
            "reviewed_by",
            "homework_assignment",
            "form_version",
        ).prefetch_related(
            # One query each, joined rather than chained, so a list of
            # reports costs the same however many lessons, notes or files
            # each one has.
            models.Prefetch(
                "lessons_covered",
                queryset=_lesson_model().objects.select_related("module"),
            ),
            models.Prefetch(
                "student_notes",
                queryset=DSRStudentNote.objects.select_related("enrollment__student__user"),
            ),
            models.Prefetch("attachments", queryset=DSRAttachment.objects.select_related("upload")),
            "form_version__fields",
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

    # --- What was covered, against the course ----------------------------
    #: The lessons this class actually got through — more than one when a
    #: trainer covered two short lessons, none when the class was revision.
    #: On submit the first one becomes the session's `actual_lesson`, which
    #: is what the batch's timeline progress already counts.
    lessons_covered = models.ManyToManyField(
        "courses.Lesson", blank=True, related_name="dsr_reports"
    )
    #: Whether the planned lesson was finished: `completed`, `in_progress`
    #: (carried over to the next class) or `skipped`; blank until the trainer
    #: says. Copied onto the session's `topic_status` on submit.
    topic_status = models.CharField(_("topic status"), max_length=20, blank=True)

    # --- Homework, shown to students ---------------------------------------
    homework = models.TextField(_("homework"), max_length=2000, blank=True)
    homework_due_on = models.DateField(_("homework due"), null=True, blank=True)
    homework_assignment = models.ForeignKey(
        "assignments.Assignment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dsr_reports",
    )

    # --- The institution's own questions (the `dsr-extra` form) ------------
    form_version = models.ForeignKey(
        "forms.FormVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="dsr_reports",
    )
    extra_answers = models.JSONField(_("extra answers"), default=dict, blank=True)

    # --- When it is due, and who has been told -----------------------------
    #: The class's end plus `notification.dsr_due_hours`. Past this, a report
    #: still not submitted is overdue and the centre's managers are told once.
    due_at = models.DateTimeField(_("due at"), null=True, blank=True, db_index=True)
    reminded_at = models.DateTimeField(_("reminder sent at"), null=True, blank=True)
    overdue_notified_at = models.DateTimeField(_("overdue notice sent at"), null=True, blank=True)

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

    @property
    def is_done(self) -> bool:
        """Submitted counts as done: no manager approval is needed (the
        owner's call, 3 October 2026). A manager may still ask for changes,
        which puts it back in the trainer's hands."""
        return self.status in DONE_STATUSES

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


class StudentFlag(models.TextChoices):
    """What a trainer noted about one student in one class."""

    DOUBT = "doubt", _("Had a doubt")
    NEEDS_ATTENTION = "needs_attention", _("Needs attention")
    DID_WELL = "did_well", _("Did well")
    ABSENT_REASON = "absent_reason", _("Reason for absence")
    OTHER = "other", _("Other")


class DSRStudentNote(BaseModel):
    """One note about one student in one class report. Shown on the
    student's timeline; a `needs_attention` note is also an automation
    occurrence (`DSR_STUDENT_FLAGGED`), so a rule can book counselling."""

    dsr = models.ForeignKey(DSR, on_delete=models.CASCADE, related_name="student_notes")
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="dsr_notes"
    )
    flag = models.CharField(_("flag"), max_length=20, choices=StudentFlag.choices)
    note = models.TextField(_("note"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("class report student note")
        verbose_name_plural = _("class report student notes")
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["dsr", "enrollment", "flag"], name="dsr_student_note_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.dsr_id}:{self.enrollment_id}:{self.flag}"


class DSRAttachment(BaseModel):
    """A file attached to a class report — class notes, a whiteboard photo.
    The file itself is a `FormUpload`, made by whoever attached it."""

    dsr = models.ForeignKey(DSR, on_delete=models.CASCADE, related_name="attachments")
    upload = models.ForeignKey(
        "forms.FormUpload", on_delete=models.PROTECT, related_name="dsr_attachments"
    )
    caption = models.CharField(_("caption"), max_length=150, blank=True)

    class Meta:
        verbose_name = _("class report attachment")
        verbose_name_plural = _("class report attachments")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.caption or str(self.upload_id)
