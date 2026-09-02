"""Assessment serializers, scoped by caller."""

from __future__ import annotations

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultImport,
)

ASSESSMENT_STATUS_CHOICES = list(AssessmentStatus.choices)


class AssessmentSerializer(StrictModelSerializer):
    """The staff view."""

    batch_code = serializers.CharField(source="batch.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    result_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Assessment
        fields = (
            "id",
            "code",
            "batch",
            "batch_code",
            "course",
            "course_title",
            "module",
            "title",
            "description",
            "category",
            "delivery",
            "external_url",
            "external_provider",
            "backing_assignment",
            "scheduled_for",
            "duration_minutes",
            "opens_at",
            "closes_at",
            "max_marks",
            "passing_marks",
            "status",
            "published_at",
            "is_open",
            "result_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AssessmentWriteSerializer(StrictSerializer):
    """Create and edit.

    ``status`` and ``backing_assignment`` are absent on purpose: the first moves
    through the lifecycle service, the second is created by it.
    """

    module = serializers.UUIDField(required=False, allow_null=True)
    title = SafeCharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    category = serializers.ChoiceField(choices=AssessmentCategory.choices, required=False)
    delivery = serializers.ChoiceField(choices=AssessmentDelivery.choices, required=False)
    external_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    external_provider = SafeCharField(required=False, allow_blank=True, max_length=60)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=1440
    )
    opens_at = serializers.DateTimeField(required=False, allow_null=True)
    closes_at = serializers.DateTimeField(required=False, allow_null=True)
    max_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    passing_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )


class AssessmentStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=ASSESSMENT_STATUS_CHOICES)


class StudentAssessmentSerializer(StrictModelSerializer):
    """A student's view: what the test is, when, and what they scored."""

    batch_code = serializers.CharField(source="batch.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    my_result = serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = (
            "id",
            "code",
            "batch",
            "batch_code",
            "course",
            "course_title",
            "title",
            "description",
            "category",
            "delivery",
            "external_url",
            "external_provider",
            "backing_assignment",
            "scheduled_for",
            "duration_minutes",
            "opens_at",
            "closes_at",
            "max_marks",
            "passing_marks",
            "status",
            "is_open",
            "my_result",
        )
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_my_result(obj):
        result = getattr(obj, "my_result_row", None)
        if result is None:
            return None
        return ResultSerializer(result).data


class ResultSerializer(StrictModelSerializer):
    """What a student sees of their own result."""

    assessment_code = serializers.CharField(source="assessment.code", read_only=True)
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    max_marks = serializers.DecimalField(
        source="assessment.max_marks", max_digits=6, decimal_places=2, read_only=True
    )
    is_passing = serializers.BooleanField(read_only=True, allow_null=True)
    percentage = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = AssessmentResult
        fields = (
            "id",
            "assessment",
            "assessment_code",
            "assessment_title",
            "marks_obtained",
            "max_marks",
            "is_absent",
            "is_passing",
            "percentage",
            "remarks",
            "recorded_at",
        )
        read_only_fields = fields


class StaffResultSerializer(ResultSerializer):
    """The marks-sheet view. Adds who the mark belongs to and where it came from."""

    student_id = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="enrollment.student.user.get_full_name", read_only=True
    )

    class Meta(ResultSerializer.Meta):
        fields = (
            *ResultSerializer.Meta.fields,
            "enrollment",
            "student_id",
            "student_name",
            "source",
            "import_run",
        )
        read_only_fields = fields


class RecordResultSerializer(StrictSerializer):
    """One mark for one student. Bounded server-side against ``max_marks``."""

    enrollment_id = serializers.UUIDField()
    marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    is_absent = serializers.BooleanField(required=False, default=False)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)


class MarksSheetEntrySerializer(StrictSerializer):
    enrollment_id = serializers.UUIDField()
    student_code = serializers.CharField()
    student_name = serializers.CharField()
    marks_obtained = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    is_absent = serializers.BooleanField()
    remarks = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)


class MarksSheetSerializer(StrictSerializer):
    assessment = AssessmentSerializer()
    entries = MarksSheetEntrySerializer(many=True)
    can_record = serializers.BooleanField()


class ImportUploadSerializer(StrictSerializer):
    file = serializers.FileField()


class ImportSerializer(StrictModelSerializer):
    """The preview a trainer confirms or rejects."""

    class Meta:
        model = ResultImport
        fields = (
            "id",
            "assessment",
            "original_filename",
            "checksum",
            "row_count",
            "valid_count",
            "error_count",
            "created_count",
            "updated_count",
            "status",
            "report",
            "confirmed_at",
            "created_at",
        )
        read_only_fields = fields
