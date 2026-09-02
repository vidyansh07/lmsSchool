"""Projects — §5.1 to §5.3.

A project is longer-lived than an assignment and is *reviewed* rather than
simply marked: it goes back and forth between student and mentor before it is
approved. That difference is why this is its own app rather than a flag on
``Assignment``.

Two tables carry it, and the split matters:

``Project``
    The brief. Belongs to a course, optionally narrowed to a module or a single
    batch — the same shape as an assignment, for the same reasons (D-025).
    ``is_required`` is what Phase 6's completion rules will read.

``StudentProject``
    One student's work on it, and the only place the workflow lives. Created
    when the project is assigned, then walked through
    ASSIGNED → IN_PROGRESS → SUBMITTED → UNDER_REVIEW → REWORK → APPROVED →
    COMPLETED. Rework loops back to IN_PROGRESS, which is the whole point of
    modelling a project differently from an assignment.

Files
-----
``ProjectFile`` reuses the assignment upload pipeline exactly — §5.3 asks for
"the same secure upload controls", and having one implementation is the only way
that stays true. Archives are stored and **never unpacked**; code is never read,
parsed or executed anywhere in this codebase.

Rubrics
-------
``Project.rubric`` is a list of criteria; ``StudentProject.rubric_scores`` is a
map from criterion key to score. The total is computed by the server from those
scores and checked against ``max_marks`` — a browser never sends a total.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.uploads import submission_upload_to
from apps.common.validators import validate_no_control_characters


class ProjectKind(models.TextChoices):
    SMALL = "small", _("Small project")
    MAJOR = "major", _("Major project")
    CAPSTONE = "capstone", _("Capstone project")


class ProjectStatus(models.TextChoices):
    """The lifecycle of the *brief*, not of anybody's work on it."""

    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    CLOSED = "closed", _("Closed")
    ARCHIVED = "archived", _("Archived")


STUDENT_VISIBLE_STATUSES = frozenset({ProjectStatus.PUBLISHED, ProjectStatus.CLOSED})


class WorkStatus(models.TextChoices):
    """One student's progress through their project."""

    ASSIGNED = "assigned", _("Assigned")
    IN_PROGRESS = "in_progress", _("In progress")
    SUBMITTED = "submitted", _("Submitted")
    UNDER_REVIEW = "under_review", _("Under review")
    REWORK = "rework", _("Rework requested")
    APPROVED = "approved", _("Approved")
    COMPLETED = "completed", _("Completed")


#: Work that counts as finished for completion purposes (§5.2, Phase 6).
FINISHED_STATUSES = frozenset({WorkStatus.APPROVED, WorkStatus.COMPLETED})

#: States in which a student may still edit and submit.
OPEN_TO_STUDENT = frozenset({WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS, WorkStatus.REWORK})


class ProjectQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("course", "module", "batch", "reviewer", "created_by")

    def student_visible(self):
        return self.filter(status__in=list(STUDENT_VISIBLE_STATUSES))


class Project(BaseModel):
    """A project set on a course."""

    code = models.CharField(_("code"), max_length=20, unique=True, editable=False)
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="projects")
    module = models.ForeignKey(
        "courses.Module", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    batch = models.ForeignKey(
        "batches.Batch",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="projects",
        help_text=_("Leave empty to set this for every batch running the course."),
    )

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    description = models.TextField(_("description"), blank=True)
    instructions = models.TextField(_("instructions"), blank=True)
    deliverables = models.TextField(
        _("deliverables"), blank=True, help_text=_("What the student must hand in.")
    )

    kind = models.CharField(
        _("kind"), max_length=10, choices=ProjectKind.choices, default=ProjectKind.SMALL
    )
    is_required = models.BooleanField(
        _("required"),
        default=True,
        help_text=_("Required projects must be finished before a course can be completed."),
    )
    #: Reserved for the configuration §5.1 anticipates. Team allocation is not
    #: built: the field records intent so a later phase has somewhere to hang
    #: it, and the API refuses to set it until then.
    allow_team = models.BooleanField(_("team project"), default=False, editable=False)

    start_date = models.DateField(_("starts"), null=True, blank=True)
    end_date = models.DateField(_("due"), null=True, blank=True)

    requires_repository_url = models.BooleanField(_("repository URL required"), default=False)
    requires_deployment_url = models.BooleanField(_("deployment URL required"), default=False)

    max_marks = models.DecimalField(
        _("maximum marks"), max_digits=6, decimal_places=2, default=Decimal("100.00")
    )
    passing_marks = models.DecimalField(
        _("passing marks"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    #: ``[{"key": "code_quality", "label": "Code quality", "max_marks": "20.00"}, …]``
    rubric = models.JSONField(_("rubric"), default=list, blank=True)

    reviewer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects_mentored",
        help_text=_("Default mentor. A batch's own trainer may review regardless."),
    )

    status = models.CharField(
        _("status"), max_length=12, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects_created",
    )

    objects = ProjectQuerySet.as_manager()

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["course", "status"], name="project_course_status_idx"),
            models.Index(fields=["batch", "status"], name="project_batch_status_idx"),
            models.Index(fields=["end_date"], name="project_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_marks__gt=0), name="project_max_marks_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(passing_marks__isnull=True)
                    | models.Q(passing_marks__lte=models.F("max_marks"))
                ),
                name="project_passing_within_max",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(end_date__isnull=True)
                    | models.Q(start_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="project_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.module_id and self.module.course_id != self.course_id:
            errors["module"] = "That module belongs to a different course."
        if self.batch_id and self.batch.course_id != self.course_id:
            errors["batch"] = "That batch does not run this course."
        errors.update(self._rubric_errors())
        if errors:
            raise ValidationError(errors)

    def _rubric_errors(self) -> dict[str, str]:
        """A rubric is data the API accepts, so it is validated like input."""
        if not self.rubric:
            return {}
        if not isinstance(self.rubric, list):
            return {"rubric": "A rubric must be a list of criteria."}

        seen: set[str] = set()
        total = Decimal("0")
        for criterion in self.rubric:
            if not isinstance(criterion, dict):
                return {"rubric": "Each criterion must be an object."}
            key = str(criterion.get("key", "")).strip()
            label = str(criterion.get("label", "")).strip()
            if not key or not label:
                return {"rubric": "Each criterion needs a key and a label."}
            if key in seen:
                return {"rubric": f"Duplicate criterion '{key}'."}
            seen.add(key)
            try:
                marks = Decimal(str(criterion.get("max_marks", "0")))
            except (ArithmeticError, ValueError, TypeError):
                return {"rubric": f"'{key}' has a non-numeric maximum."}
            if marks <= 0:
                return {"rubric": f"'{key}' must be worth more than zero."}
            total += marks

        if total != self.max_marks:
            # Otherwise a perfect score on every criterion would not equal the
            # marks the project is advertised as being out of.
            return {
                "rubric": (
                    f"The criteria add up to {total}, but the project is out of {self.max_marks}."
                )
            }
        return {}

    @property
    def rubric_keys(self) -> list[str]:
        return [str(criterion.get("key")) for criterion in (self.rubric or [])]

    @property
    def is_open(self) -> bool:
        return self.status == ProjectStatus.PUBLISHED

    def applies_to_batch(self, batch_id) -> bool:
        return self.batch_id is None or self.batch_id == batch_id


class StudentProjectQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "project",
            "project__course",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
            "enrollment__batch",
            "reviewer",
        ).prefetch_related("files")

    def finished(self):
        return self.filter(status__in=list(FINISHED_STATUSES))


class StudentProject(BaseModel):
    """One student's work on one project, and the whole review workflow."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="student_projects")
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="student_projects"
    )

    status = models.CharField(
        _("status"), max_length=14, choices=WorkStatus.choices, default=WorkStatus.ASSIGNED
    )
    repository_url = models.URLField(_("repository URL"), max_length=500, blank=True)
    deployment_url = models.URLField(_("deployment URL"), max_length=500, blank=True)
    notes = models.TextField(_("student notes"), blank=True)

    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    submission_count = models.PositiveSmallIntegerField(
        _("times submitted"),
        default=0,
        help_text=_("Rework sends a project back, so a student may submit more than once."),
    )
    is_late = models.BooleanField(_("late"), default=False)

    reviewer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_projects_reviewed",
    )
    #: ``{"code_quality": "18.00", …}`` — the server sums these; a client never
    #: sends a total.
    rubric_scores = models.JSONField(_("rubric scores"), default=dict, blank=True)
    marks_awarded = models.DecimalField(
        _("marks awarded"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    feedback = models.TextField(_("feedback"), blank=True)
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)

    objects = StudentProjectQuerySet.as_manager()

    class Meta:
        verbose_name = _("student project")
        verbose_name_plural = _("student projects")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["project", "status"], name="studentproject_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "enrollment"], name="studentproject_one_per_student"
            ),
            models.CheckConstraint(
                condition=models.Q(marks_awarded__isnull=True) | models.Q(marks_awarded__gte=0),
                name="studentproject_marks_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project_id} · {self.enrollment_id}"

    @property
    def is_open_to_student(self) -> bool:
        return self.status in OPEN_TO_STUDENT

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES

    @property
    def is_passing(self) -> bool | None:
        """Derived on read from the project's threshold, or the academic rules."""
        if self.marks_awarded is None:
            return None

        from apps.academics.policies import policy_for

        threshold = self.project.passing_marks
        if threshold is None:
            threshold = policy_for(self.project.course_id).passing_mark_for(self.project.max_marks)
        return self.marks_awarded >= threshold

    def due_at_end_of(self):
        return self.project.end_date

    def mark_late(self) -> bool:
        end = self.project.end_date
        return bool(end and timezone.localdate() > end)


class ProjectFile(BaseModel):
    """A deliverable file.

    Stored by exactly the same rules as an assignment submission: a
    server-generated inert path, no client bytes anywhere in the filename, and
    served only as an opaque attachment by an authorising view.
    """

    student_project = models.ForeignKey(
        StudentProject, on_delete=models.CASCADE, related_name="files"
    )
    file = models.FileField(_("file"), upload_to=submission_upload_to, max_length=255)
    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    extension = models.CharField(_("extension"), max_length=20, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"), default=0)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True)

    class Meta:
        verbose_name = _("project file")
        verbose_name_plural = _("project files")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.original_filename or str(self.pk)
