"""Class sessions — the actual classes a schedule predicts.

Why these are stored rows rather than derived occurrences
---------------------------------------------------------
Phase 3's calendar expands ``BatchSchedule`` into occurrences on the fly, which
is right for *showing* a timetable: a weekly slot is a rule, and materialising a
row per week would mean rewriting history whenever the rule changed.

Attendance cannot work that way. A register attaches to one specific class, and
that class has to survive the schedule being edited afterwards — otherwise last
month's attendance would silently re-point at a different time, or vanish. A
derived occurrence also cannot be cancelled on its own, moved to a different
room, or given a topic.

So the schedule stays the rule and the session becomes the event: sessions are
materialised from the schedule by an explicit generation step, and from then on
they are independent records. Editing a schedule does not rewrite sessions that
already happened.

Reassignment history
--------------------
``Batch.trainer`` is the current teacher. Each session records the trainer who
actually took it, so reassigning a batch does not retroactively claim the new
trainer taught classes they never saw. ``TrainerAssignmentHistory`` keeps the
batch-level record of who taught when, which is what a report needs.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class SessionStatus(models.TextChoices):
    """Where a class is in its life.

    ``SCHEDULED`` and ``COMPLETED`` differ by whether it has happened;
    ``CANCELLED`` and ``RESCHEDULED`` both mean it did not, but for different
    reasons and with different consequences for attendance.
    """

    SCHEDULED = "scheduled", _("Scheduled")
    IN_PROGRESS = "in_progress", _("In progress")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    RESCHEDULED = "rescheduled", _("Rescheduled")


#: Sessions a register may be taken for. A cancelled class has no attendance,
#: because nobody could have attended it.
ATTENDABLE_STATUSES = frozenset({SessionStatus.IN_PROGRESS, SessionStatus.COMPLETED})


class ClassSessionQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("batch", "batch__course", "trainer", "trainer__user", "schedule")

    def upcoming(self):
        return self.filter(session_date__gte=timezone.localdate(), status=SessionStatus.SCHEDULED)

    def attendable(self):
        return self.filter(status__in=ATTENDABLE_STATUSES)


class ClassSession(BaseModel):
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="sessions")
    schedule = models.ForeignKey(
        "batches.BatchSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions",
        help_text=_(
            "The weekly slot this was generated from. Cleared if the slot is "
            "deleted — the session itself is history and stays."
        ),
    )

    session_date = models.DateField(_("date"), db_index=True)
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    timezone_name = models.CharField(_("time zone"), max_length=64, default="Asia/Kolkata")

    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sessions",
        help_text=_("Who actually took this class. Frozen at generation time."),
    )

    topic = models.CharField(
        _("topic"),
        max_length=250,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("What was covered. Filled in by the trainer."),
    )
    notes = models.TextField(_("notes"), max_length=2000, blank=True)
    location = models.CharField(_("location"), max_length=150, blank=True)

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.SCHEDULED,
        db_index=True,
    )
    cancellation_reason = models.CharField(_("reason"), max_length=255, blank=True)
    rescheduled_to = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rescheduled_from",
        help_text=_("The replacement class, when this one was moved."),
    )

    attendance_taken_at = models.DateTimeField(_("attendance taken at"), null=True, blank=True)
    attendance_taken_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_registers_taken",
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions_created",
    )

    objects = ClassSessionQuerySet.as_manager()

    class Meta:
        verbose_name = _("class session")
        verbose_name_plural = _("class sessions")
        ordering = ("-session_date", "start_time")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="session_end_after_start",
            ),
            # Regenerating a batch's timetable must never duplicate a class that
            # already exists — the generator is safe to re-run.
            models.UniqueConstraint(
                fields=["batch", "session_date", "start_time"],
                name="session_unique_per_batch_slot",
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "-session_date"], name="session_batch_date_idx"),
            models.Index(fields=["trainer", "-session_date"], name="session_trainer_date_idx"),
            models.Index(fields=["status", "session_date"], name="session_status_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.batch_id} on {self.session_date} at {self.start_time:%H:%M}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": _("The end time must be after the start time.")})
        if self.batch_id and self.session_date:
            if self.session_date < self.batch.start_date or self.session_date > self.batch.end_date:
                raise ValidationError(
                    {"session_date": _("The class must fall inside the batch's dates.")}
                )

    @property
    def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone_name or "UTC")
        except Exception:
            return ZoneInfo("UTC")

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.session_date, self.start_time, tzinfo=self.zone)

    @property
    def ends_at(self) -> datetime:
        return datetime.combine(self.session_date, self.end_time, tzinfo=self.zone)

    @property
    def has_ended(self) -> bool:
        return timezone.now() >= self.ends_at

    @property
    def is_today(self) -> bool:
        return self.session_date == timezone.localdate()

    @property
    def can_take_attendance(self) -> bool:
        """A register may be taken once the class has started, not before.

        Marking a class register in advance records something that has not
        happened, so it is refused until the class is under way.
        """
        return self.status in ATTENDABLE_STATUSES or (
            self.status == SessionStatus.SCHEDULED and timezone.now() >= self.starts_at
        )

    @property
    def duration_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return end - start


class TrainerAssignmentHistory(BaseModel):
    """Who taught a batch, and when.

    ``Batch.trainer`` answers "who teaches this now?". This answers "who taught
    it in March?", which is what a trainer-activity report needs and what a
    single mutable field cannot say.
    """

    batch = models.ForeignKey(
        "batches.Batch", on_delete=models.CASCADE, related_name="trainer_history"
    )
    trainer = models.ForeignKey(
        "trainers.TrainerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batch_history",
        help_text=_("Null records the batch being left without a trainer."),
    )
    assigned_at = models.DateTimeField(_("assigned at"), default=timezone.now)
    ended_at = models.DateTimeField(
        _("ended at"), null=True, blank=True, help_text=_("Set when the next trainer takes over.")
    )
    assigned_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trainer_assignments_made",
    )
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("trainer assignment")
        verbose_name_plural = _("trainer assignment history")
        ordering = ("-assigned_at",)
        indexes = [
            models.Index(fields=["batch", "-assigned_at"], name="trainerhist_batch_idx"),
            models.Index(fields=["trainer", "-assigned_at"], name="trainerhist_trainer_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.trainer_id} on {self.batch_id} from {self.assigned_at:%Y-%m-%d}"

    @property
    def is_current(self) -> bool:
        return self.ended_at is None


def default_session_end(start: time, minutes: int) -> time:
    """Add minutes to a wall-clock time, clamped to the end of the day."""
    total = start.hour * 60 + start.minute + minutes
    total = min(total, 23 * 60 + 59)
    return time(total // 60, total % 60)
