"""Assessments and results.

§4.5 describes today's reality — a trainer sets a weekly test, often as a Google
Form, sometimes as a file hand-in, sometimes on paper in the lab — and one
requirement about tomorrow: *the LMS must not depend on Google Forms being the
permanent assessment engine*.

So the model is an abstraction with the delivery mechanism as a field, not a
Google Form table with extra columns:

``EXTERNAL_LINK``
    The test lives somewhere else. The LMS holds the link, the schedule and the
    marks; the results arrive by import (§4.6) or manual entry.

``FILE_UPLOAD``
    Students hand work in through the LMS. Rather than build a second upload
    pipeline, the assessment is **backed by an Assignment** — so the file
    security of §4.4, the attempt rules and the grading path are reused rather
    than reimplemented. Grading the backing assignment writes the result.

``OFFLINE``
    A paper test. The LMS holds the schedule and the marks and nothing else.

A native quiz engine is Phase 5's job. It is deliberately *not* listed here:
adding it means one new delivery value and one new result source, and nothing
above this layer has to change. Listing it now would mean shipping a choice
that does nothing.

Results
-------
``AssessmentResult`` is one row per student per assessment, whatever the
delivery. Reporting, progress and completion in later phases read this one
table and never have to know how the test was taken.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class AssessmentCategory(models.TextChoices):
    """What kind of academic event this is, for reporting."""

    WEEKLY_TEST = "weekly_test", _("Weekly test")
    PRACTICE = "practice", _("Practice test")
    MOCK = "mock", _("Mock test")
    OTHER = "other", _("Other assessment")


class AssessmentDelivery(models.TextChoices):
    """How the test is actually taken. See the module docstring."""

    EXTERNAL_LINK = "external_link", _("External link")
    FILE_UPLOAD = "file_upload", _("File upload")
    OFFLINE = "offline", _("Offline / in class")


class AssessmentStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    CLOSED = "closed", _("Closed")
    ARCHIVED = "archived", _("Archived")


STUDENT_VISIBLE_STATUSES = frozenset({AssessmentStatus.PUBLISHED, AssessmentStatus.CLOSED})


class ResultSource(models.TextChoices):
    """Where a mark came from. Kept because it changes how much to trust it.

    An imported mark can be re-imported and overwritten; a graded one is the
    product of the LMS's own grading path and is not touched by an import.
    """

    MANUAL = "manual", _("Entered by staff")
    IMPORT = "import", _("Imported from a file")
    GRADED = "graded", _("Graded in the LMS")


class AssessmentQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("course", "batch", "module", "created_by", "backing_assignment")

    def student_visible(self):
        return self.filter(status__in=list(STUDENT_VISIBLE_STATUSES))


class Assessment(BaseModel):
    """A test set for one batch."""

    code = models.CharField(_("code"), max_length=20, unique=True, editable=False)
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="assessments")
    #: Derived from ``batch.course`` by the service and checked in ``clean``.
    #: Stored so course-level reporting does not have to join through batches.
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="assessments"
    )
    module = models.ForeignKey(
        "courses.Module",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
    )

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    description = models.TextField(_("description"), blank=True)
    category = models.CharField(
        _("category"),
        max_length=20,
        choices=AssessmentCategory.choices,
        default=AssessmentCategory.WEEKLY_TEST,
    )
    delivery = models.CharField(
        _("delivery"),
        max_length=20,
        choices=AssessmentDelivery.choices,
        default=AssessmentDelivery.EXTERNAL_LINK,
    )

    external_url = models.URLField(
        _("external URL"),
        max_length=500,
        blank=True,
        help_text=_("Where the test is taken, for an externally delivered assessment."),
    )
    external_provider = models.CharField(
        _("provider"),
        max_length=60,
        blank=True,
        help_text=_("Free-text label, e.g. 'Google Forms'. Nothing is integrated with it."),
    )
    backing_assignment = models.OneToOneField(
        "assignments.Assignment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backed_assessment",
        help_text=_("Created automatically for a file-upload assessment."),
    )

    scheduled_for = models.DateTimeField(_("scheduled for"), null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        _("duration in minutes"), null=True, blank=True
    )
    opens_at = models.DateTimeField(_("opens at"), null=True, blank=True)
    closes_at = models.DateTimeField(_("closes at"), null=True, blank=True)

    max_marks = models.DecimalField(
        _("maximum marks"), max_digits=6, decimal_places=2, default=Decimal("100.00")
    )
    passing_marks = models.DecimalField(
        _("passing marks"), max_digits=6, decimal_places=2, null=True, blank=True
    )

    status = models.CharField(
        _("status"), max_length=12, choices=AssessmentStatus.choices, default=AssessmentStatus.DRAFT
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments_created",
    )

    objects = AssessmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("assessment")
        verbose_name_plural = _("assessments")
        ordering = ("-scheduled_for", "-created_at")
        indexes = [
            models.Index(fields=["batch", "status"], name="assessment_batch_status_idx"),
            models.Index(fields=["course", "category"], name="assessment_course_cat_idx"),
            models.Index(fields=["scheduled_for"], name="assessment_scheduled_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_marks__gt=0), name="assessment_max_marks_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(passing_marks__isnull=True)
                    | models.Q(passing_marks__lte=models.F("max_marks"))
                ),
                name="assessment_passing_within_max",
            ),
            # An externally delivered test without a link is a dead end for the
            # student, so the database refuses one.
            models.CheckConstraint(
                condition=(
                    ~models.Q(delivery=AssessmentDelivery.EXTERNAL_LINK)
                    | ~models.Q(external_url="")
                ),
                name="assessment_external_needs_url",
            ),
            # Only a file-upload assessment may carry a backing assignment.
            models.CheckConstraint(
                condition=(
                    models.Q(delivery=AssessmentDelivery.FILE_UPLOAD)
                    | models.Q(backing_assignment__isnull=True)
                ),
                name="assessment_backing_only_for_upload",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closes_at__isnull=True)
                    | models.Q(opens_at__isnull=True)
                    | models.Q(closes_at__gte=models.F("opens_at"))
                ),
                name="assessment_window_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.batch_id and self.course_id and self.batch.course_id != self.course_id:
            errors["course"] = "The course must be the one the batch runs."
        if self.module_id and self.module.course_id != self.course_id:
            errors["module"] = "That module belongs to a different course."
        if self.delivery == AssessmentDelivery.EXTERNAL_LINK:
            if not self.external_url:
                errors["external_url"] = "An externally delivered test needs a link."
            elif not self.external_url.startswith("https://"):
                # An http:// link would downgrade a student mid-assessment.
                errors["external_url"] = "The link must be an https:// URL."
        elif self.external_url:
            errors["external_url"] = "Only an externally delivered test carries a link."
        if errors:
            raise ValidationError(errors)

    @property
    def is_open(self) -> bool:
        """Whether a student may take it right now."""
        from django.utils import timezone

        if self.status != AssessmentStatus.PUBLISHED:
            return False
        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        return not (self.closes_at and now > self.closes_at)


class ResultQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "assessment",
            "assessment__batch",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "recorded_by",
        )


class AssessmentResult(BaseModel):
    """One student's outcome on one assessment.

    ``marks_obtained`` is null when the student was absent, which is different
    from zero: a zero is a mark that was earned, an absence is a mark that was
    never attempted. Reporting has to be able to tell them apart.
    """

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="results")
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="assessment_results"
    )

    marks_obtained = models.DecimalField(
        _("marks obtained"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    is_absent = models.BooleanField(_("absent"), default=False)
    remarks = models.CharField(_("remarks"), max_length=500, blank=True)

    source = models.CharField(
        _("source"), max_length=10, choices=ResultSource.choices, default=ResultSource.MANUAL
    )
    import_run = models.ForeignKey(
        "assessments.ResultImport",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="results",
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="results_recorded",
    )
    recorded_at = models.DateTimeField(_("recorded at"), auto_now=True)

    objects = ResultQuerySet.as_manager()

    class Meta:
        verbose_name = _("assessment result")
        verbose_name_plural = _("assessment results")
        ordering = ("-recorded_at",)
        indexes = [
            models.Index(fields=["assessment", "is_absent"], name="result_assessment_abs_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "enrollment"], name="result_one_per_student_per_assessment"
            ),
            models.CheckConstraint(
                condition=models.Q(marks_obtained__isnull=True) | models.Q(marks_obtained__gte=0),
                name="result_marks_not_negative",
            ),
            # An absence has no mark, and a mark means they were not absent.
            models.CheckConstraint(
                condition=(
                    models.Q(is_absent=True, marks_obtained__isnull=True)
                    | models.Q(is_absent=False)
                ),
                name="result_absent_has_no_marks",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.assessment.code} · {self.enrollment_id}"

    @property
    def is_passing(self) -> bool | None:
        """Derived on read, so changing the threshold leaves no stale flag.

        Falls back to the passing percentage in the academic configuration when
        the assessment does not set its own — see §4.7 and
        ``apps.academics.policies``.
        """
        if self.is_absent:
            return False
        if self.marks_obtained is None:
            return None

        from apps.academics.policies import passing_mark_for_assessment

        return self.marks_obtained >= passing_mark_for_assessment(self.assessment)

    @property
    def percentage(self) -> float | None:
        if self.marks_obtained is None or not self.assessment.max_marks:
            return None
        return round(float(self.marks_obtained) / float(self.assessment.max_marks) * 100, 2)


class ImportStatus(models.TextChoices):
    PREVIEW = "preview", _("Awaiting confirmation")
    CONFIRMED = "confirmed", _("Applied")
    REJECTED = "rejected", _("Rejected")
    FAILED = "failed", _("Failed validation")


class ResultImport(BaseModel):
    """The audit record for one attempt to import results — §4.6.

    A row exists from the moment a file is uploaded, before anything is
    written to the results table. That is what makes the workflow
    *preview → validate → confirm* rather than "upload and hope": the parsed
    rows and every problem found are stored here, the trainer sees exactly what
    would happen, and only an explicit confirmation applies it.

    ``report`` holds the parsed rows and the errors. It is written once at
    preview and never trusted again on confirm: confirmation re-validates
    against the live database, because enrolments can change between the two
    requests.
    """

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="imports")
    uploaded_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="result_imports"
    )

    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True)
    row_count = models.PositiveIntegerField(_("rows read"), default=0)
    valid_count = models.PositiveIntegerField(_("rows that would apply"), default=0)
    error_count = models.PositiveIntegerField(_("rows with problems"), default=0)
    created_count = models.PositiveIntegerField(_("results created"), default=0)
    updated_count = models.PositiveIntegerField(_("results updated"), default=0)

    status = models.CharField(
        _("status"), max_length=12, choices=ImportStatus.choices, default=ImportStatus.PREVIEW
    )
    report = models.JSONField(_("report"), default=dict, blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("result import")
        verbose_name_plural = _("result imports")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["assessment", "status"], name="import_assessment_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.assessment_id} · {self.original_filename or self.pk}"
