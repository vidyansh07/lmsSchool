"""Batches and their class schedules.

A **batch** is one cohort running one course between two dates, taught by one
trainer, with a capacity. A **schedule** is a recurring weekly slot within that
batch's date range.

Why this is a separate app from ``enrollments``
-----------------------------------------------
Batch and schedule are the *delivery* side: they exist whether or not anyone
signs up, and they are owned by the institution. Enrolment is the *participation*
side: a student's relationship with a batch, which grows its own concerns
(progress, later attendance, certificates, payments). The dependency runs one
way — enrollments → batches → courses — and keeping the boundary means adding a
progress field never touches the timetable.

Capacity and conflicts
----------------------
Neither is enforceable by a column alone:

* Capacity is a count of *other* rows, so it is checked under a row lock in
  ``enrollments.services`` — a plain check would let two concurrent enrolments
  both see the last seat.
* Overlap is a relationship between rows, so it is checked in
  ``apps.batches.conflicts`` before a schedule is written.

Both are backed by tests that exercise the concurrent and adjacent cases, since
neither can be delegated to a constraint.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers
from apps.common.validators import validate_no_control_characters

MAX_CAPACITY = 1000


class DeliveryMode(models.TextChoices):
    """How teaching reaches a student — §6.5.

    A field, not a second product. Online and offline students share the same
    courses, batches, sessions, attendance, assignments and certificates; what
    changes is which completion rules an institution turns on for them, which is
    configuration (`apps.academics`) rather than architecture.
    """

    OFFLINE = "offline", _("In the classroom")
    ONLINE = "online", _("Online")
    HYBRID = "hybrid", _("Both")


class BatchKind(models.TextChoices):
    """What shape of training this batch runs.

    A field rather than three products, for the same reason `DeliveryMode` is:
    all three kinds share courses, sessions, attendance, assessments and
    certificates. What differs is how the institution talks about them and, in
    time, which completion rules apply — configuration, not architecture.

    Added because the client names internship and modular cohorts alongside
    regular ones and moves students between them. Nothing in the model said a
    batch had a kind, so screens were inferring it from the name.

    ``MODULAR`` is recorded but nothing yet branches on it. Whether a modular
    student is enrolled on the whole course and taking it in pieces, or on only
    some of its modules, is an open question with the client — and the two give
    different answers for progress and completion. The field is safe to store
    now; guessing the semantics would not be.
    """

    REGULAR = "regular", _("Regular")
    INTERNSHIP = "internship", _("Internship")
    MODULAR = "modular", _("Modular")


class BatchStatus(models.TextChoices):
    """Where a batch is in its life.

    ``CANCELLED`` and ``ARCHIVED`` differ on purpose: cancelled means it was
    called off and its students lose access; archived means it ran, finished
    and is being kept out of the way. Educational history survives both.
    """

    UPCOMING = "upcoming", _("Upcoming")
    ACTIVE = "active", _("Active")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    ARCHIVED = "archived", _("Archived")


#: Batches that may take new students. A completed or cancelled batch cannot.
ENROLLABLE_STATUSES = frozenset({BatchStatus.UPCOMING, BatchStatus.ACTIVE})

#: Batches whose enrolments still grant course access.
ACCESS_GRANTING_STATUSES = frozenset(
    {BatchStatus.UPCOMING, BatchStatus.ACTIVE, BatchStatus.COMPLETED}
)


class Weekday(models.IntegerChoices):
    """Matches ``date.weekday()`` so no conversion is ever needed."""

    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class BatchQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("course", "course__category", "trainer", "trainer__user")

    def with_counts(self):
        """Annotate the seat count.

        Filtered so cancelled and completed enrolments do not hold a seat —
        which is what makes "seats left" mean what a reader expects.
        """
        from apps.enrollments.models import SEAT_HOLDING_STATUSES

        return self.annotate(
            enrolled_count=models.Count(
                "enrollments",
                filter=models.Q(enrollments__status__in=SEAT_HOLDING_STATUSES),
                distinct=True,
            )
        )

    def enrollable(self):
        return self.filter(status__in=ENROLLABLE_STATUSES)


class Batch(SoftDeleteBaseModel):
    code = models.CharField(
        _("batch code"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human-readable identifier, e.g. GRS-B-00021. Allocated by the system."),
    )
    name = models.CharField(
        _("name"),
        max_length=200,
        validators=[validate_no_control_characters],
        help_text=_("For example: Linux Foundations — Morning, Jan 2026."),
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.PROTECT,
        related_name="batches",
        help_text=_("Protected: deleting a course with batches would orphan its students."),
    )
    description = models.TextField(_("description"), max_length=2000, blank=True)
    delivery_mode = models.CharField(
        _("delivery mode"),
        max_length=10,
        choices=DeliveryMode.choices,
        default=DeliveryMode.OFFLINE,
        help_text=_("How this cohort is taught. A student may differ; see Enrollment."),
    )
    kind = models.CharField(
        _("kind"),
        max_length=12,
        choices=BatchKind.choices,
        default=BatchKind.REGULAR,
        db_index=True,
        help_text=_("Regular, internship or modular. Descriptive today; see BatchKind."),
    )

    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="batches",
        help_text=_("The trainer who teaches this batch. Set before the batch goes active."),
    )

    start_date = models.DateField(_("start date"), db_index=True)
    end_date = models.DateField(_("end date"))
    capacity = models.PositiveIntegerField(
        _("capacity"),
        validators=[MinValueValidator(1), MaxValueValidator(MAX_CAPACITY)],
        help_text=_("Maximum number of students holding a seat."),
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=BatchStatus.choices,
        default=BatchStatus.UPCOMING,
        db_index=True,
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batches_created",
    )

    objects, all_objects = soft_delete_managers(BatchQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("batch")
        verbose_name_plural = _("batches")
        ordering = ("-start_date", "code")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="batch_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(capacity__gt=0), name="batch_capacity_positive"
            ),
        ]
        indexes = [
            # The two questions asked most: "which batches is this course
            # running?" and "what is this trainer teaching?".
            models.Index(fields=["course", "status"], name="batch_course_status_idx"),
            models.Index(fields=["trainer", "status"], name="batch_trainer_status_idx"),
            models.Index(fields=["status", "start_date"], name="batch_status_start_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"

    def clean(self) -> None:
        """Validate what a column constraint cannot express."""
        from django.core.exceptions import ValidationError

        super().clean()
        errors: dict[str, str] = {}

        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")

        if self.trainer_id and self.trainer and not self.trainer.user.is_active:
            # A deactivated trainer cannot be given a class to teach.
            errors["trainer"] = _("That trainer's account is not active.")

        if self.course_id and self.course:
            from apps.courses.models import PublishStatus

            if self.course.status not in (PublishStatus.PUBLISHED, PublishStatus.IN_REVIEW):
                errors["course"] = _("A batch can only run a published course, or one in review.")

        if errors:
            raise ValidationError(errors)

    @property
    def is_enrollable(self) -> bool:
        return self.status in ENROLLABLE_STATUSES

    @property
    def grants_access(self) -> bool:
        """Whether an active enrolment on this batch still opens the course."""
        return self.status in ACCESS_GRANTING_STATUSES

    @property
    def is_running(self) -> bool:
        today = timezone.localdate()
        return self.status == BatchStatus.ACTIVE and self.start_date <= today <= self.end_date

    def seats_taken(self) -> int:
        from apps.enrollments.models import SEAT_HOLDING_STATUSES

        return self.enrollments.filter(status__in=SEAT_HOLDING_STATUSES).count()

    def seats_available(self) -> int:
        return max(self.capacity - self.seats_taken(), 0)


class BatchSchedule(SoftDeleteBaseModel):
    """One recurring weekly class slot inside a batch's date range.

    Times are stored as wall-clock times plus an IANA time-zone name rather than
    as UTC instants. A class that meets at 09:00 local should still meet at
    09:00 after a daylight-saving change — converting to UTC at write time would
    silently move it by an hour.
    """

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.IntegerField(_("day"), choices=Weekday.choices, db_index=True)
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    timezone_name = models.CharField(
        _("time zone"),
        max_length=64,
        default="Asia/Kolkata",
        help_text=_("IANA name, e.g. Asia/Kolkata."),
    )
    location = models.CharField(
        _("location"),
        max_length=150,
        blank=True,
        help_text=_("Classroom, lab or meeting link label. A placeholder for now."),
    )
    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedules",
        help_text=_("Defaults to the batch trainer. Set to cover a single slot."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_("Turn off to suspend a slot without losing its history."),
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("batch schedule")
        verbose_name_plural = _("batch schedules")
        ordering = ("weekday", "start_time")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="schedule_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "weekday"], name="schedule_batch_day_idx"),
            models.Index(fields=["trainer", "weekday"], name="schedule_trainer_day_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": _("The end time must be after the start time.")})
        if self.timezone_name:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(self.timezone_name)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValidationError({"timezone_name": _("Unknown time zone.")}) from exc

    @property
    def effective_trainer_id(self):
        """The trainer actually teaching this slot."""
        return self.trainer_id or self.batch.trainer_id

    @property
    def duration_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return end - start
