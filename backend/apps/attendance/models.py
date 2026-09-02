"""Attendance records.

One row per `(class session, enrolment)`. Keyed on the **enrolment** rather than
the student for the same reason progress is: the same person may take the same
course twice in different batches, and those are separate attendance histories.

Corrections, not rewrites
-------------------------
A register is taken quickly, at the end of a class, by a person. It will be
wrong sometimes. So a correction keeps the previous value on the row
(`previous_status`, `corrected_by`, `corrected_at`) rather than overwriting it
silently — an attendance percentage can affect course completion, and a student
disputing one deserves an answer better than "it says absent".

Why not a status on the enrolment
---------------------------------
Attendance is per class, and the questions asked of it — "what is this student's
percentage?", "who was missing on Tuesday?", "which batch has an attendance
problem?" — all need the individual rows. A running total on the enrolment would
be a second source of truth that drifts the first time a correction is made.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", _("Present")
    ABSENT = "absent", _("Absent")
    LATE = "late", _("Late")
    EXCUSED = "excused", _("Excused")


#: Statuses that count towards an attendance percentage.
#:
#: Late counts as attended — the student was in the room. Excused is neither
#: attended nor held against them, so it is removed from the denominator
#: entirely rather than counted as a miss.
COUNTS_AS_PRESENT = frozenset({AttendanceStatus.PRESENT, AttendanceStatus.LATE})
EXCLUDED_FROM_PERCENTAGE = frozenset({AttendanceStatus.EXCUSED})


class AttendanceQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "session", "session__batch", "enrollment", "enrollment__student__user"
        )

    def counted(self):
        """Rows that belong in an attendance percentage."""
        return self.exclude(status__in=EXCLUDED_FROM_PERCENTAGE)


class AttendanceRecord(BaseModel):
    session = models.ForeignKey(
        "class_sessions.ClassSession", on_delete=models.CASCADE, related_name="attendance"
    )
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="attendance"
    )
    status = models.CharField(
        _("status"), max_length=20, choices=AttendanceStatus.choices, db_index=True
    )
    note = models.CharField(
        _("note"), max_length=255, blank=True, validators=[validate_no_control_characters]
    )

    marked_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_marked",
    )
    marked_at = models.DateTimeField(_("marked at"), default=timezone.now)

    previous_status = models.CharField(
        _("previous status"),
        max_length=20,
        choices=AttendanceStatus.choices,
        blank=True,
        help_text=_("What it was before the last correction. Empty if never corrected."),
    )
    corrected_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_corrected",
    )
    corrected_at = models.DateTimeField(_("corrected at"), null=True, blank=True)
    correction_reason = models.CharField(_("correction reason"), max_length=255, blank=True)

    objects = AttendanceQuerySet.as_manager()

    class Meta:
        verbose_name = _("attendance record")
        verbose_name_plural = _("attendance records")
        ordering = ("-session__session_date", "enrollment__student__student_id")
        constraints = [
            models.UniqueConstraint(
                fields=["session", "enrollment"], name="attendance_one_per_session_enrollment"
            ),
        ]
        indexes = [
            models.Index(fields=["enrollment", "status"], name="attend_enrol_status_idx"),
            models.Index(fields=["session", "status"], name="attend_session_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.enrollment_id} / {self.session_id}: {self.status}"

    @property
    def was_corrected(self) -> bool:
        return bool(self.previous_status)

    @property
    def counts_as_present(self) -> bool:
        return self.status in COUNTS_AS_PRESENT


def _summary_from_counts(counts: dict[str, int]) -> dict[str, object]:
    """Turn a status histogram into the summary. The arithmetic lives here once.

    Excused absences leave the denominator, so a student excused for half a
    term is not punished by a percentage that treats those classes as misses.
    """
    total = sum(value for status, value in counts.items() if status not in EXCLUDED_FROM_PERCENTAGE)
    present = sum(value for status, value in counts.items() if status in COUNTS_AS_PRESENT)

    return {
        "total_sessions": total,
        "present": counts.get(AttendanceStatus.PRESENT, 0),
        "late": counts.get(AttendanceStatus.LATE, 0),
        "absent": counts.get(AttendanceStatus.ABSENT, 0),
        "excused": counts.get(AttendanceStatus.EXCUSED, 0),
        "attended": present,
        "percentage": round(present * 100 / total) if total else None,
    }


def attendance_summaries(enrollment_ids) -> dict[Any, dict[str, object]]:
    """The same summary for many enrolments, in one query.

    Exists because a cohort report asked for it per student: four hundred
    students meant two thousand round trips, and the fix cannot be a second copy
    of the percentage rule. One grouped query, one shared
    :func:`_summary_from_counts`.

    Every requested id appears in the result, including students with no
    records at all — an absent key would make every caller write the same
    "missing means zero" branch.
    """
    ids = list(enrollment_ids)
    counts: dict[Any, dict[str, int]] = {key: {} for key in ids}
    if not ids:
        return {}

    rows = (
        AttendanceRecord.objects.filter(enrollment_id__in=ids)
        .values("enrollment_id", "status")
        .annotate(total=models.Count("id"))
    )
    for row in rows:
        counts.setdefault(row["enrollment_id"], {})[row["status"]] = row["total"]

    return {key: _summary_from_counts(value) for key, value in counts.items()}


def attendance_summary(enrollment) -> dict[str, object]:
    """One student's attendance on one enrolment."""
    return attendance_summaries([enrollment.pk])[enrollment.pk]
