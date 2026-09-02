"""Academic rules, stored as data — §4.7.

    "Do not hard-code business rules into views."

The rules an institution actually argues about — what counts as enough
attendance, what a pass is, how many attempts an assignment allows — change
without warning and must not require a deployment. So they live in a table.

Two levels, and nothing else
----------------------------
``AcademicPolicy`` holds one **global** row and any number of **per-course**
overrides. A course row leaves inherited fields ``NULL``, which is what
distinguishes "this course requires 80%" from "this course has no opinion".
Resolution walks course → global → the code defaults in
:data:`DEFAULT_POLICY`, so there is always an answer and never a crash on a
missing row.

Deliberately *not* per-batch: an intake that grades differently from the one
before it is an administrative accident, not a feature, and every extra level
multiplies the number of places a rule can hide.

Nothing is retrospective
------------------------
Marks already awarded are stored numbers and are never recalculated by a policy
change. What a policy changes is *derivation* — pass or fail, met or not met —
which is computed on read. That is the same reason ``is_passing`` is a property
and not a column.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters

#: A percentage-to-grade mapping. Bands are read in order and the first whose
#: `min_percent` the score reaches wins, so they are stored high to low.
#:
#: A default is provided because a report that cannot letter a score is less
#: useful than one that letters it conventionally; an institution overrides it
#: on the academic-rules screen.
DEFAULT_GRADE_BANDS: list[dict[str, object]] = [
    {"label": "A+", "min_percent": "90.00"},
    {"label": "A", "min_percent": "80.00"},
    {"label": "B", "min_percent": "70.00"},
    {"label": "C", "min_percent": "60.00"},
    {"label": "D", "min_percent": "50.00"},
    {"label": "E", "min_percent": "40.00"},
    {"label": "F", "min_percent": "0.00"},
]

#: The answer when nothing has been configured at all. These are code defaults,
#: not policy: an institution that cares sets its own, and one that does not
#: still gets sane behaviour on day one.
DEFAULT_POLICY: dict[str, object] = {
    "minimum_attendance_percent": Decimal("75.00"),
    "attendance_required_for_completion": True,
    "passing_percent": Decimal("40.00"),
    "assignment_default_max_marks": Decimal("100.00"),
    "assignment_allow_late": True,
    "assignment_default_max_attempts": 1,
    "assignment_required_for_completion": True,
    "minimum_assignment_completion_percent": Decimal("80.00"),
    "test_default_max_marks": Decimal("100.00"),
    "tests_required_for_completion": True,
    "minimum_test_average_percent": Decimal("40.00"),
    "minimum_test_completion_percent": Decimal("80.00"),
    "lessons_required_for_completion": True,
    "minimum_lesson_completion_percent": Decimal("80.00"),
    "projects_required_for_completion": True,
    "final_exam_required_for_completion": False,
    "batch_directory_visible": True,
    "grade_bands": DEFAULT_GRADE_BANDS,
}

#: Every configurable rule, in one list, so the API, the admin and the resolver
#: cannot drift apart. Adding a rule means adding a field and a line here.
POLICY_FIELDS: tuple[str, ...] = tuple(DEFAULT_POLICY)


class PolicyScope(models.TextChoices):
    GLOBAL = "global", _("Institution-wide")
    COURSE = "course", _("Course override")


class AcademicPolicy(BaseModel):
    """One row of academic rules: the institution's, or one course's."""

    scope = models.CharField(
        _("scope"), max_length=10, choices=PolicyScope.choices, default=PolicyScope.GLOBAL
    )
    course = models.OneToOneField(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="academic_policy",
    )

    # --- Attendance
    minimum_attendance_percent = models.DecimalField(
        _("minimum attendance %"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    attendance_required_for_completion = models.BooleanField(
        _("attendance required to complete"), null=True, blank=True
    )

    # --- Marks and passing
    passing_percent = models.DecimalField(
        _("passing %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Used whenever a piece of work does not set its own passing mark."),
    )

    # --- Assignments
    assignment_default_max_marks = models.DecimalField(
        _("default assignment marks"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    assignment_allow_late = models.BooleanField(
        _("allow late submission by default"), null=True, blank=True
    )
    assignment_default_max_attempts = models.PositiveSmallIntegerField(
        _("default assignment attempts"), null=True, blank=True
    )
    assignment_required_for_completion = models.BooleanField(
        _("assignments required to complete"), null=True, blank=True
    )
    minimum_assignment_completion_percent = models.DecimalField(
        _("minimum assignments completed %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # --- Weekly tests and assessments
    test_default_max_marks = models.DecimalField(
        _("default test marks"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    tests_required_for_completion = models.BooleanField(
        _("tests required to complete"), null=True, blank=True
    )
    minimum_test_average_percent = models.DecimalField(
        _("minimum test average %"), max_digits=5, decimal_places=2, null=True, blank=True
    )

    # --- Course activity
    minimum_test_completion_percent = models.DecimalField(
        _("minimum tests taken %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("How many of the batch's tests must have been sat, as opposed to passed."),
    )

    # --- Course activity
    lessons_required_for_completion = models.BooleanField(
        _("lessons required to complete"),
        null=True,
        blank=True,
        help_text=_("Turn off for a cohort taught entirely offline (§6.5)."),
    )
    minimum_lesson_completion_percent = models.DecimalField(
        _("minimum lessons completed %"), max_digits=5, decimal_places=2, null=True, blank=True
    )

    # --- Projects and the final examination
    projects_required_for_completion = models.BooleanField(
        _("required projects must be finished"), null=True, blank=True
    )
    final_exam_required_for_completion = models.BooleanField(
        _("final examination must be passed"),
        null=True,
        blank=True,
        help_text=_("Off by default: not every course ends in an examination."),
    )

    # --- Grading
    grade_bands = models.JSONField(
        _("grade bands"),
        default=list,
        blank=True,
        help_text=_("Percentage thresholds, highest first. Empty means the built-in bands."),
    )

    # --- Privacy
    batch_directory_visible = models.BooleanField(
        _("students may see their classmates"),
        null=True,
        blank=True,
        help_text=_("Names and student ids only — never contact details (§7.7)."),
    )

    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="academic_policies_updated",
    )

    class Meta:
        verbose_name = _("academic policy")
        verbose_name_plural = _("academic policies")
        ordering = ("scope", "-created_at")
        constraints = [
            # Exactly one institution-wide row, enforced by the database rather
            # than by a convention somebody will eventually break.
            models.UniqueConstraint(
                fields=["scope"],
                condition=models.Q(scope="global"),
                name="policy_single_global_row",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(scope="global", course__isnull=True)
                    | models.Q(scope="course", course__isnull=False)
                ),
                name="policy_scope_matches_course",
            ),
        ]

    def __str__(self) -> str:
        return (
            "Institution-wide" if self.scope == PolicyScope.GLOBAL else f"Course {self.course_id}"
        )

    def _grade_band_errors(self) -> dict[str, str]:
        """Bands are data the API accepts, so they are validated like input.

        Must descend, must not repeat a threshold, and must reach zero — a score
        that falls through every band would have no grade at all, which is a
        report with a hole in it rather than an error anybody would notice.
        """
        if not self.grade_bands:
            return {}
        if not isinstance(self.grade_bands, list):
            return {"grade_bands": "Grade bands must be a list."}

        previous = None
        labels: set[str] = set()
        for band in self.grade_bands:
            if not isinstance(band, dict):
                return {"grade_bands": "Each band must be an object."}
            label = str(band.get("label", "")).strip()
            if not label:
                return {"grade_bands": "Every band needs a label."}
            if label in labels:
                return {"grade_bands": f"Duplicate band '{label}'."}
            labels.add(label)
            try:
                floor = Decimal(str(band.get("min_percent")))
            except (ArithmeticError, TypeError, ValueError):
                return {"grade_bands": f"'{label}' has a non-numeric threshold."}
            if not (Decimal(0) <= floor <= Decimal(100)):
                return {"grade_bands": f"'{label}' must sit between 0 and 100."}
            if previous is not None and floor >= previous:
                return {"grade_bands": "Bands must be listed from highest to lowest."}
            previous = floor

        if previous != Decimal(0):
            return {"grade_bands": "The lowest band must start at 0, or some scores get no grade."}
        return {}

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        for field in (
            "minimum_attendance_percent",
            "passing_percent",
            "minimum_assignment_completion_percent",
            "minimum_test_average_percent",
            "minimum_test_completion_percent",
            "minimum_lesson_completion_percent",
        ):
            value = getattr(self, field)
            if value is not None and not (Decimal(0) <= value <= Decimal(100)):
                errors[field] = "A percentage must be between 0 and 100."
        errors.update(self._grade_band_errors())
        if self.assignment_default_max_attempts is not None and (
            not 1 <= self.assignment_default_max_attempts <= 20
        ):
            errors["assignment_default_max_attempts"] = "Allow between 1 and 20 attempts."
        for field in ("assignment_default_max_marks", "test_default_max_marks"):
            value = getattr(self, field)
            if value is not None and value <= 0:
                errors[field] = "Marks out of must be greater than zero."
        if errors:
            raise ValidationError(errors)


class AcademicEventKind(models.TextChoices):
    """§8.1's academic calendar, as a small vocabulary rather than free text."""

    TERM = "term", _("Term")
    HOLIDAY = "holiday", _("Holiday")
    EXAM_WEEK = "exam_week", _("Examination week")
    OTHER = "other", _("Other")


class AcademicEvent(BaseModel):
    """A date range that means something institution-wide.

    Holidays are the one kind with behaviour attached: class generation skips
    them, so a term break does not silently create thirty classes nobody
    attends and thirty empty registers to explain afterwards. The rest are
    calendar entries.
    """

    name = models.CharField(_("name"), max_length=160, validators=[validate_no_control_characters])
    kind = models.CharField(
        _("kind"),
        max_length=10,
        choices=AcademicEventKind.choices,
        default=AcademicEventKind.HOLIDAY,
    )
    start_date = models.DateField(_("from"))
    end_date = models.DateField(_("to"))
    note = models.CharField(_("note"), max_length=300, blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="academic_events",
    )

    class Meta:
        verbose_name = _("academic calendar entry")
        verbose_name_plural = _("academic calendar")
        ordering = ("start_date", "name")
        indexes = [
            models.Index(fields=["start_date", "end_date"], name="academic_event_range_idx"),
            models.Index(fields=["kind"], name="academic_event_kind_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="academic_event_dates_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date} to {self.end_date})"

    def covers(self, day) -> bool:
        return self.start_date <= day <= self.end_date


def holiday_dates(start, end) -> set:
    """Every date in the range that falls in a holiday.

    Returned as a set because the caller — class generation — asks about one day
    at a time across a long window, and a query per day would be absurd.
    """
    from datetime import timedelta

    days: set = set()
    rows = AcademicEvent.objects.filter(
        kind=AcademicEventKind.HOLIDAY, end_date__gte=start, start_date__lte=end
    )
    for event in rows:
        day = max(event.start_date, start)
        last = min(event.end_date, end)
        while day <= last:
            days.add(day)
            day += timedelta(days=1)
    return days
