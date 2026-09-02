"""Assignments, submissions and the files that go with them.

An assignment is a piece of work a trainer sets and a student hands in. Four
tables carry it, and the split is deliberate.

``Assignment``
    The brief. It belongs to a **course**, because that is what the work is
    about, and may be narrowed to a module, a lesson or a single batch. A batch
    of ``None`` means "every batch running this course" — the common case, and
    the reason a trainer does not have to re-create the same task each intake.

``AssignmentAttachment``
    Starter files, a specification, a dataset. Trainer-supplied, so it reuses
    the course-resource upload rules.

``AssignmentSubmission``
    One **attempt**. A resubmission is a new row, never an overwrite: the first
    attempt, its marks and the feedback that prompted the rework all survive.
    Marks are stored on the attempt, so "what did they score first time?" is
    answerable a year later.

``SubmissionFile``
    The bytes a student handed in, one row per file. Stored under a
    server-generated inert path and served only by an authorising view — see
    ``apps.common.uploads`` for the rules and why each one exists.

Marks
-----
``max_marks`` lives on the assignment and the server checks every award against
it. The client never sends a total, a percentage or a pass/fail flag; it sends
the raw mark for one attempt and the server derives everything else. §5.5's rule
— "never calculate final scores from browser-submitted totals" — starts here.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.uploads import assignment_attachment_upload_to, submission_upload_to
from apps.common.validators import validate_no_control_characters


class AssignmentStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    CLOSED = "closed", _("Closed")
    ARCHIVED = "archived", _("Archived")


#: Statuses in which a student may see the assignment at all. A draft is the
#: trainer's workspace and must not appear anywhere a student can reach.
STUDENT_VISIBLE_STATUSES = frozenset({AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED})


class SubmissionKind(models.TextChoices):
    """What the student is expected to hand in."""

    FILE = "file", _("File upload")
    TEXT = "text", _("Written answer")
    LINK = "link", _("Link")
    ANY = "any", _("Any of the above")


class SubmissionStatus(models.TextChoices):
    SUBMITTED = "submitted", _("Submitted")
    GRADED = "graded", _("Graded")
    RETURNED = "returned", _("Returned for rework")


class AssignmentQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("course", "module", "lesson", "batch", "created_by")

    def student_visible(self):
        return self.filter(status__in=list(STUDENT_VISIBLE_STATUSES))


class Assignment(BaseModel):
    """A piece of work set on a course."""

    code = models.CharField(_("code"), max_length=20, unique=True, editable=False)
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        # `course.assignments` was already taken in Phase 2 by
        # `courses.CourseAssignment`, which assigns *authors* to a course.
        # Renaming that would touch working code for cosmetic reasons, so the
        # academic work reverses as `course.coursework`.
        related_name="coursework",
    )
    module = models.ForeignKey(
        "courses.Module",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    lesson = models.ForeignKey(
        "courses.Lesson",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    batch = models.ForeignKey(
        "batches.Batch",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text=_("Leave empty to set this work for every batch running the course."),
    )

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    instructions = models.TextField(_("instructions"), blank=True)

    submission_kind = models.CharField(
        _("submission kind"),
        max_length=10,
        choices=SubmissionKind.choices,
        default=SubmissionKind.FILE,
    )
    max_marks = models.DecimalField(
        _("maximum marks"), max_digits=6, decimal_places=2, default=Decimal("100.00")
    )
    passing_marks = models.DecimalField(
        _("passing marks"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave empty to take the passing rule from the academic configuration."),
    )

    due_at = models.DateTimeField(_("due at"), null=True, blank=True)
    allow_late = models.BooleanField(
        _("allow late submission"),
        default=True,
        help_text=_("Late work is accepted and flagged, rather than refused."),
    )
    late_cutoff_at = models.DateTimeField(
        _("late cutoff"),
        null=True,
        blank=True,
        help_text=_("Nothing is accepted after this moment, late or not."),
    )

    allow_resubmission = models.BooleanField(_("allow resubmission"), default=False)
    max_attempts = models.PositiveSmallIntegerField(_("maximum attempts"), default=1)

    status = models.CharField(
        _("status"), max_length=12, choices=AssignmentStatus.choices, default=AssignmentStatus.DRAFT
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments_created",
    )

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("assignment")
        verbose_name_plural = _("assignments")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["course", "status"], name="assignment_course_status_idx"),
            models.Index(fields=["batch", "status"], name="assignment_batch_status_idx"),
            models.Index(fields=["due_at"], name="assignment_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_marks__gt=0), name="assignment_max_marks_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(passing_marks__isnull=True)
                    | models.Q(passing_marks__lte=models.F("max_marks"))
                ),
                name="assignment_passing_within_max",
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1), name="assignment_attempts_at_least_one"
            ),
            # A late cutoff without a due date is meaningless, and a cutoff
            # before the due date would refuse work that is not yet late.
            models.CheckConstraint(
                condition=(
                    models.Q(late_cutoff_at__isnull=True)
                    | (
                        models.Q(due_at__isnull=False)
                        & models.Q(late_cutoff_at__gte=models.F("due_at"))
                    )
                ),
                name="assignment_late_cutoff_after_due",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    def clean(self) -> None:
        """Keep the course/module/lesson/batch chain consistent.

        A module from another course would silently mis-file the work and break
        every later progress calculation, so it is refused here rather than
        discovered in a report.
        """
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.module_id and self.module.course_id != self.course_id:
            errors["module"] = "That module belongs to a different course."
        if self.lesson_id:
            lesson_course_id = self.lesson.module.course_id
            if lesson_course_id != self.course_id:
                errors["lesson"] = "That lesson belongs to a different course."
            if self.module_id and self.lesson.module_id != self.module_id:
                errors["lesson"] = "That lesson is not in the selected module."
        if self.batch_id and self.batch.course_id != self.course_id:
            errors["batch"] = "That batch does not run this course."
        if errors:
            raise ValidationError(errors)

    # -- Windows -----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Whether a submission would be accepted right now."""
        if self.status != AssignmentStatus.PUBLISHED:
            return False
        now = timezone.now()
        if self.late_cutoff_at and now > self.late_cutoff_at:
            return False
        if self.due_at and now > self.due_at and not self.allow_late:
            return False
        return True

    def is_late_at(self, moment=None) -> bool:
        moment = moment or timezone.now()
        return bool(self.due_at and moment > self.due_at)

    def applies_to_batch(self, batch_id) -> bool:
        """A course-wide assignment applies to every batch; a scoped one to its own."""
        return self.batch_id is None or self.batch_id == batch_id


class AssignmentAttachment(BaseModel):
    """A file the trainer attaches to the brief."""

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="attachments")
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    file = models.FileField(_("file"), upload_to=assignment_attachment_upload_to, max_length=255)
    original_filename = models.CharField(
        _("original filename"),
        max_length=255,
        blank=True,
        help_text=_("Display only — never used to build a path."),
    )
    content_type = models.CharField(_("content type"), max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignment_attachments_uploaded",
    )

    class Meta:
        verbose_name = _("assignment attachment")
        verbose_name_plural = _("assignment attachments")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.title


class SubmissionQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "assignment",
            "assignment__course",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
            "graded_by",
        ).prefetch_related("files")


class AssignmentSubmission(BaseModel):
    """One attempt at an assignment.

    Keyed by ``(assignment, enrollment, attempt)`` rather than by student, so
    the row is tied to the enrolment that produced it. A student who repeats a
    course on a later batch starts a fresh set of attempts, and their first
    run's marks are not overwritten by their second.
    """

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="assignment_submissions"
    )
    attempt = models.PositiveSmallIntegerField(_("attempt"), default=1)

    status = models.CharField(
        _("status"),
        max_length=12,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED,
    )
    text_answer = models.TextField(_("written answer"), blank=True)
    link_url = models.URLField(_("link"), max_length=500, blank=True)

    submitted_at = models.DateTimeField(_("submitted at"), default=timezone.now)
    is_late = models.BooleanField(_("late"), default=False)

    marks_awarded = models.DecimalField(
        _("marks awarded"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    feedback = models.TextField(_("feedback"), blank=True)
    graded_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submissions_graded",
    )
    graded_at = models.DateTimeField(_("graded at"), null=True, blank=True)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        verbose_name = _("assignment submission")
        verbose_name_plural = _("assignment submissions")
        ordering = ("-submitted_at",)
        indexes = [
            models.Index(fields=["assignment", "status"], name="submission_assign_status_idx"),
            models.Index(fields=["enrollment", "assignment"], name="submission_enrol_assign_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "enrollment", "attempt"],
                name="submission_one_row_per_attempt",
            ),
            models.CheckConstraint(
                condition=models.Q(marks_awarded__isnull=True) | models.Q(marks_awarded__gte=0),
                name="submission_marks_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt__gte=1), name="submission_attempt_at_least_one"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assignment.code} attempt {self.attempt}"

    @property
    def is_graded(self) -> bool:
        return self.status == SubmissionStatus.GRADED and self.marks_awarded is not None

    @property
    def is_passing(self) -> bool | None:
        """Pass/fail for this attempt, or None when it has not been graded.

        Derived on read, never stored. The threshold is the assignment's own
        ``passing_marks`` when it sets one, and otherwise the passing percentage
        from the academic configuration (§4.7) — so raising the institution's
        pass mark moves every assignment that has no opinion of its own, without
        a deployment and without rewriting a single stored mark.
        """
        if not self.is_graded:
            return None

        from apps.academics.policies import passing_mark_for_assignment

        return self.marks_awarded >= passing_mark_for_assignment(self.assignment)

    @property
    def passing_mark(self):
        """The threshold this attempt is judged against, after inheritance."""
        from apps.academics.policies import passing_mark_for_assignment

        return passing_mark_for_assignment(self.assignment)


class SubmissionFile(BaseModel):
    """One file inside a submission.

    ``file.name`` is always ``…/<uuid>.bin``. ``original_filename`` and
    ``extension`` are display metadata: they are shown to the trainer and used
    to build a download name, and neither ever reaches the filesystem.
    """

    submission = models.ForeignKey(
        AssignmentSubmission, on_delete=models.CASCADE, related_name="files"
    )
    file = models.FileField(_("file"), upload_to=submission_upload_to, max_length=255)
    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    extension = models.CharField(_("extension"), max_length=20, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    checksum = models.CharField(
        _("SHA-256"),
        max_length=64,
        blank=True,
        help_text=_("Of the bytes as received, so integrity can be proven later."),
    )

    class Meta:
        verbose_name = _("submission file")
        verbose_name_plural = _("submission files")
        ordering = ("created_at",)
        indexes = []

    def __str__(self) -> str:
        return self.original_filename or str(self.pk)
