"""Academic configuration serializers.

Every writable field is optional and nullable: ``null`` is how a course says
"inherit this one", which is a different statement from omitting it.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import POLICY_FIELDS, AcademicEvent, AcademicEventKind, AcademicPolicy


def _percent(**kwargs):
    return serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=Decimal(100),
        required=False,
        allow_null=True,
        **kwargs,
    )


class PolicySerializer(StrictModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)

    class Meta:
        model = AcademicPolicy
        fields = ("id", "scope", "course", "course_title", *POLICY_FIELDS, "updated_at")
        read_only_fields = fields


class PolicyWriteSerializer(StrictSerializer):
    minimum_attendance_percent = _percent()
    attendance_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    passing_percent = _percent()
    assignment_default_max_marks = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )
    assignment_allow_late = serializers.BooleanField(required=False, allow_null=True)
    assignment_default_max_attempts = serializers.IntegerField(
        min_value=1, max_value=20, required=False, allow_null=True
    )
    assignment_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    minimum_assignment_completion_percent = _percent()
    test_default_max_marks = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )
    tests_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    minimum_test_average_percent = _percent()
    minimum_test_completion_percent = _percent()
    lessons_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    minimum_lesson_completion_percent = _percent()
    projects_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    final_exam_required_for_completion = serializers.BooleanField(required=False, allow_null=True)
    batch_directory_visible = serializers.BooleanField(required=False, allow_null=True)
    grade_bands = serializers.ListField(child=serializers.DictField(), required=False)


class EffectivePolicySerializer(StrictSerializer):
    """The rules actually in force, after course → institution → default."""

    minimum_attendance_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    attendance_required_for_completion = serializers.BooleanField()
    passing_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    assignment_default_max_marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    assignment_allow_late = serializers.BooleanField()
    assignment_default_max_attempts = serializers.IntegerField()
    assignment_required_for_completion = serializers.BooleanField()
    minimum_assignment_completion_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    test_default_max_marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    tests_required_for_completion = serializers.BooleanField()
    minimum_test_average_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    minimum_test_completion_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    lessons_required_for_completion = serializers.BooleanField()
    minimum_lesson_completion_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    projects_required_for_completion = serializers.BooleanField()
    final_exam_required_for_completion = serializers.BooleanField()
    batch_directory_visible = serializers.BooleanField()
    grade_bands = serializers.ListField(child=serializers.DictField())


class AttendanceRequirementSerializer(StrictSerializer):
    """Whether a student has attended enough, and against what threshold."""

    required = serializers.BooleanField()
    minimum_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    met = serializers.BooleanField(allow_null=True)
    total_sessions = serializers.IntegerField()
    present = serializers.IntegerField()
    late = serializers.IntegerField()
    absent = serializers.IntegerField()
    excused = serializers.IntegerField()
    attended = serializers.IntegerField()
    percentage = serializers.IntegerField(allow_null=True)


class AcademicEventSerializer(StrictModelSerializer):
    """§8.1's academic calendar."""

    class Meta:
        model = AcademicEvent
        fields = ("id", "name", "kind", "start_date", "end_date", "note", "created_at")
        read_only_fields = fields


class AcademicEventWriteSerializer(StrictSerializer):
    name = SafeCharField(max_length=160)
    kind = serializers.ChoiceField(choices=AcademicEventKind.choices, required=False)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    note = SafeCharField(required=False, allow_blank=True, max_length=300)
