"""Enrolment and the progress foundation.

An enrolment connects a student to a batch, and through the batch to a course.
It is the record that grants course access, and it is what every later phase —
attendance, assignments, results, certificates — will hang off.

Relationships, not copies
-------------------------
``course`` is a real foreign key rather than a denormalised copy, but it is
*derived*: the service layer sets it from ``batch.course`` and a database
constraint would not be able to keep the two in step on its own, so
:meth:`Enrollment.clean` enforces the match. Nothing else about the student,
course or batch is duplicated here — a name or a title is read through the
relation, so it cannot go stale.

Duplicate prevention
--------------------
A student may re-enrol on a batch they previously left, but must never hold two
live enrolments on the same one. That is a *partial* unique index — unique only
across the statuses that count as live — which PostgreSQL supports directly, so
it is enforced by the database rather than by a check that a race could slip
past.

History is never destroyed
--------------------------
Cancelling or suspending changes ``status`` and records why. It does not delete
the row, and it does not touch progress: a student who returns finds their
history intact, and a dispute months later can still be answered.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.batches.models import DeliveryMode
from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class EnrollmentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")


#: Statuses that occupy a seat in the batch. A cancelled enrolment frees its
#: seat; a completed one does not, because the cohort has already run.
SEAT_HOLDING_STATUSES = frozenset(
    {
        EnrollmentStatus.PENDING,
        EnrollmentStatus.ACTIVE,
        EnrollmentStatus.SUSPENDED,
        EnrollmentStatus.COMPLETED,
    }
)

#: Statuses that count as "live" for duplicate prevention. A student may
#: re-enrol after cancelling, but not hold two live enrolments on one batch.
#:
#: Ordered, not a set: this list goes into a database constraint, and a set's
#: iteration order is not stable between runs — which would make the migration
#: autodetector see a change on every invocation and generate an endless stream
#: of no-op migrations.
LIVE_STATUS_LIST = [
    EnrollmentStatus.PENDING,
    EnrollmentStatus.ACTIVE,
    EnrollmentStatus.SUSPENDED,
]
LIVE_STATUSES = frozenset(LIVE_STATUS_LIST)

#: Statuses that grant access to the course content.
#:
#: ``COMPLETED`` is included deliberately: a student who finished the course
#: keeps read access to the material they studied. ``SUSPENDED`` is not — that
#: is the whole point of suspending. ``PENDING`` is not either: the enrolment
#: has not been confirmed yet.
ACCESS_GRANTING_STATUSES = frozenset({EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED})


class EnrollmentQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        # `batch__trainer__user` is here because every serializer renders the
        # trainer's name: without it a page of twenty-five enrolments made
        # twenty-five extra queries for twenty-five names.
        return self.select_related(
            "student",
            "student__user",
            "batch",
            "batch__trainer",
            "batch__trainer__user",
            "course",
            "course__category",
        )

    def live(self):
        return self.filter(status__in=LIVE_STATUSES)

    def granting_access(self):
        return self.filter(status__in=ACCESS_GRANTING_STATUSES)


class Enrollment(SoftDeleteBaseModel):
    code = models.CharField(
        _("enrolment code"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human-readable identifier, e.g. GRS-E-00307."),
    )
    student = models.ForeignKey(
        "students.StudentProfile",
        on_delete=models.PROTECT,
        related_name="enrollments",
        help_text=_("Protected: educational history is never removed with the profile."),
    )
    batch = models.ForeignKey("batches.Batch", on_delete=models.PROTECT, related_name="enrollments")
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.PROTECT,
        related_name="enrollments",
        help_text=_("Always the batch's course. Stored so access queries need one join fewer."),
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING,
        db_index=True,
    )
    #: Null means "however the batch is taught" — the usual case. Set only for a
    #: student who attends differently from their cohort, which a hybrid batch
    #: has by definition (§6.5).
    delivery_mode = models.CharField(
        _("delivery mode"),
        max_length=10,
        choices=DeliveryMode.choices,
        blank=True,
        default="",
        help_text=_("Leave empty to follow the batch."),
    )

    enrolled_at = models.DateTimeField(_("enrolled at"), default=timezone.now)
    start_date = models.DateField(
        _("access start date"),
        null=True,
        blank=True,
        help_text=_("Defaults to the batch start date."),
    )
    access_end_date = models.DateField(
        _("access end date"),
        null=True,
        blank=True,
        help_text=_("Optional. After this date the enrolment no longer opens the course."),
    )

    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    status_changed_at = models.DateTimeField(_("status last changed at"), null=True, blank=True)
    status_note = models.CharField(
        _("status note"),
        max_length=255,
        blank=True,
        help_text=_("Why the status last changed. Shown to administrators only."),
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enrollments_created",
    )

    objects, all_objects = soft_delete_managers(EnrollmentQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("enrolment")
        verbose_name_plural = _("enrolments")
        ordering = ("-enrolled_at",)
        constraints = [
            # A partial unique index: one live enrolment per student per batch,
            # while still allowing a fresh enrolment after a cancellation.
            models.UniqueConstraint(
                fields=["student", "batch"],
                # `deleted_at` joins the condition for a reason worth stating:
                # without it, removing an enrolment would permanently bar that
                # student from that batch, because the deleted row would go on
                # holding the slot. A soft delete that cannot be undone by
                # re-enrolling is not soft.
                condition=models.Q(status__in=LIVE_STATUS_LIST, deleted_at__isnull=True),
                name="enrollment_one_live_per_student_batch",
            ),
        ]
        indexes = [
            # The access check: "does this user have a live enrolment on this
            # course?" — asked on every lesson, resource and video request.
            models.Index(fields=["student", "course", "status"], name="enrol_student_course_idx"),
            models.Index(fields=["batch", "status"], name="enrol_batch_status_idx"),
            models.Index(fields=["course", "status"], name="enrol_course_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.student_id} on {self.batch_id}"

    def clean(self) -> None:
        """Rules a column constraint cannot express."""
        from django.core.exceptions import ValidationError

        super().clean()
        errors: dict[str, str] = {}

        if self.batch_id and self.course_id and self.batch.course_id != self.course_id:
            # The derived FK must match its source, or access checks would
            # answer for a course the student never joined.
            errors["course"] = _("The course must be the batch's course.")

        if self.start_date and self.access_end_date and self.access_end_date < self.start_date:
            errors["access_end_date"] = _("Access cannot end before it starts.")

        if errors:
            raise ValidationError(errors)

    @property
    def holds_seat(self) -> bool:
        return self.status in SEAT_HOLDING_STATUSES

    @property
    def effective_delivery_mode(self) -> str:
        """How this student is actually taught.

        Their own setting when they have one, the batch's otherwise. Written
        once here so no caller has to remember the inheritance rule.
        """
        return self.delivery_mode or self.batch.delivery_mode

    def grants_access(self, *, on_date=None) -> bool:
        """Whether this enrolment opens the course right now.

        Three things must hold: the status allows it, the batch has not been
        cancelled, and today is inside any access window. This is the single
        definition — :mod:`apps.courses.access` calls it rather than
        re-implementing the rule.
        """
        if self.status not in ACCESS_GRANTING_STATUSES:
            return False
        if not self.batch.grants_access:
            return False

        today = on_date or timezone.localdate()
        if self.start_date and today < self.start_date:
            return False
        if self.access_end_date and today > self.access_end_date:
            return False
        return True


class LessonProgressStatus(models.TextChoices):
    NOT_STARTED = "not_started", _("Not started")
    IN_PROGRESS = "in_progress", _("In progress")
    COMPLETED = "completed", _("Completed")


class LessonProgress(BaseModel):
    """One student's progress through one lesson.

    Deliberately minimal — §13 asks for the *architecture*, not the full system.
    What exists is the shape later phases need: a row per (enrolment, lesson),
    a status, when it was last opened and when it was finished. Watch position,
    time-on-task, quiz scores and completion rules all attach to this row
    without reshaping it.

    Keyed on the enrolment rather than the user: the same person may take the
    same course twice in different batches, and those are different attempts
    with different progress.
    """

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="lesson_progress"
    )
    lesson = models.ForeignKey(
        "courses.Lesson", on_delete=models.CASCADE, related_name="progress_records"
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=LessonProgressStatus.choices,
        default=LessonProgressStatus.IN_PROGRESS,
        db_index=True,
    )
    first_accessed_at = models.DateTimeField(_("first opened at"), default=timezone.now)
    last_accessed_at = models.DateTimeField(_("last opened at"), default=timezone.now)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("lesson progress")
        verbose_name_plural = _("lesson progress")
        ordering = ("-last_accessed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "lesson"], name="progress_one_per_enrollment_lesson"
            ),
        ]
        indexes = [
            models.Index(fields=["enrollment", "status"], name="progress_enrol_status_idx"),
            models.Index(fields=["enrollment", "-last_accessed_at"], name="progress_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_id} / {self.lesson_id}: {self.status}"

    @property
    def is_complete(self) -> bool:
        return self.status == LessonProgressStatus.COMPLETED
