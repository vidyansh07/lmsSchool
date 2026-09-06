"""Resolving academic rules, and applying them.

Everything that needs to know a rule asks :func:`policy_for`. Nothing reads the
``AcademicPolicy`` table directly, so the inheritance order — course, then
institution, then code default — exists in exactly one place.

The resolved object is a plain frozen dataclass rather than a model instance,
which makes two things true: a caller cannot accidentally save through it, and
a rule can be resolved for a course that has no override row at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.common.request_context import clear_scope, scoped

from .models import DEFAULT_POLICY, POLICY_FIELDS, AcademicPolicy, PolicyScope


@dataclass(frozen=True)
class EffectivePolicy:
    """The rules that actually apply, after inheritance."""

    minimum_attendance_percent: Decimal
    attendance_required_for_completion: bool
    passing_percent: Decimal
    assignment_default_max_marks: Decimal
    assignment_allow_late: bool
    assignment_default_max_attempts: int
    assignment_required_for_completion: bool
    minimum_assignment_completion_percent: Decimal
    test_default_max_marks: Decimal
    tests_required_for_completion: bool
    minimum_test_average_percent: Decimal
    minimum_test_completion_percent: Decimal
    lessons_required_for_completion: bool
    minimum_lesson_completion_percent: Decimal
    projects_required_for_completion: bool
    final_exam_required_for_completion: bool
    batch_directory_visible: bool
    grade_bands: list
    risk_attendance_percent: Decimal
    risk_assessment_average_percent: Decimal
    risk_missed_assignments: int
    risk_progress_variance_percent: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in POLICY_FIELDS}

    def grade_for(self, percent) -> str:
        """The letter for a percentage, under the bands in force.

        Returns an empty string when there is nothing to grade — a missing score
        is not an F, and reporting one as such would be a lie about a student.
        """
        if percent is None:
            return ""
        from .models import DEFAULT_GRADE_BANDS

        value = Decimal(str(percent))
        for band in self.grade_bands or DEFAULT_GRADE_BANDS:
            if value >= Decimal(str(band["min_percent"])):
                return str(band["label"])
        return ""

    def passing_mark_for(self, max_marks: Decimal) -> Decimal:
        """The pass threshold for a piece of work worth ``max_marks``.

        Rounded to two places, the same precision marks are stored at, so a
        borderline score cannot pass under one calculation and fail under
        another.
        """
        return (Decimal(max_marks) * self.passing_percent / Decimal(100)).quantize(Decimal("0.01"))


def forget_resolved_policies() -> None:
    """Drop the memo after a policy is written, so the same request sees it."""
    clear_scope()


def global_policy() -> AcademicPolicy | None:
    return AcademicPolicy.objects.filter(scope=PolicyScope.GLOBAL).first()


def course_policy(course_id) -> AcademicPolicy | None:
    if course_id is None:
        return None
    return AcademicPolicy.objects.filter(scope=PolicyScope.COURSE, course_id=course_id).first()


def policy_for(course=None) -> EffectivePolicy:
    """The rules in force for a course, or institution-wide when none is given.

    Accepts a ``Course`` or a course id, so callers that only hold a foreign key
    do not have to fetch the row.

    Memoised for the life of one request. Serialising a page of results asks
    this the same question once per row, and the answer cannot change
    mid-response; a shared cache would instead delay a rule change by its TTL,
    which is exactly what §4.7 is trying to avoid.
    """
    course_id = getattr(course, "pk", course)
    return scoped(f"academic-policy:{course_id or 'global'}", lambda: _resolve(course_id))


def _resolve(course_id) -> EffectivePolicy:
    layers = [layer for layer in (course_policy(course_id), global_policy()) if layer is not None]
    resolved: dict[str, Any] = {}
    for field in POLICY_FIELDS:
        value = None
        for layer in layers:
            value = getattr(layer, field)
            if value is not None:
                break
        resolved[field] = DEFAULT_POLICY[field] if value is None else value
    return EffectivePolicy(**resolved)


# ---------------------------------------------------------------------------
# Applying the rules
# ---------------------------------------------------------------------------


def passing_mark_for_assignment(assignment) -> Decimal:
    """The threshold this assignment is actually marked against.

    An assignment that sets its own ``passing_marks`` keeps it; one that does
    not inherits the course's passing percentage. This is what makes the
    configuration real rather than decorative — changing the institution's
    passing percentage moves every unset assignment at once.
    """
    if assignment.passing_marks is not None:
        return assignment.passing_marks
    return policy_for(assignment.course_id).passing_mark_for(assignment.max_marks)


def passing_mark_for_assessment(assessment) -> Decimal:
    if assessment.passing_marks is not None:
        return assessment.passing_marks
    return policy_for(assessment.course_id).passing_mark_for(assessment.max_marks)


def attendance_requirement(enrollment, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Whether this student has attended enough, under the rule in force.

    Returns the percentage, the threshold and the verdict together, because a
    bare boolean is useless to a student asking why.

    ``summary`` lets a caller that already has the counts — a cohort report
    which fetched them for every student in one query — pass them in rather than
    making this function fetch them again per student.
    """
    from apps.attendance.models import attendance_summary

    policy = policy_for(enrollment.course_id)
    if summary is None:
        summary = attendance_summary(enrollment)
    percentage = summary["percentage"]

    if not policy.attendance_required_for_completion:
        met = True
    elif percentage is None:
        # No countable classes yet. Nothing has been failed.
        met = None
    else:
        met = Decimal(str(percentage)) >= policy.minimum_attendance_percent

    return {
        **summary,
        "required": policy.attendance_required_for_completion,
        "minimum_percent": policy.minimum_attendance_percent,
        "met": met,
    }
