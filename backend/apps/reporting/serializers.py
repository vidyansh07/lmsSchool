"""Reporting serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import BulkImport


class ColumnSerializer(StrictSerializer):
    key = serializers.CharField()
    label = serializers.CharField()


class ReportDefinitionSerializer(StrictSerializer):
    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    source = serializers.CharField()
    columns = ColumnSerializer(many=True)


class ReportPageSerializer(StrictSerializer):
    """A report, its columns and one page of rows."""

    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    columns = ColumnSerializer(many=True)
    rows = serializers.ListField(child=serializers.DictField())
    row_count = serializers.IntegerField()
    truncated = serializers.BooleanField()


class MetricSerializer(StrictSerializer):
    """A number, and the definition §8.6 requires it to carry."""

    key = serializers.CharField()
    label = serializers.CharField()
    definition = serializers.CharField()
    unit = serializers.CharField()
    value = serializers.FloatField(allow_null=True)
    numerator = serializers.FloatField(required=False, allow_null=True)
    denominator = serializers.FloatField(required=False, allow_null=True)


class TrendPointSerializer(StrictSerializer):
    week = serializers.DateField()
    counted = serializers.IntegerField()
    attended = serializers.IntegerField()
    percent = serializers.FloatField(allow_null=True)


class AdminDashboardSerializer(StrictSerializer):
    active_students = serializers.IntegerField()
    active_trainers = serializers.IntegerField()
    published_courses = serializers.IntegerField()
    active_batches = serializers.IntegerField()
    awaiting_completion_approval = serializers.IntegerField()
    certificates_issued = serializers.IntegerField()
    metrics = MetricSerializer(many=True)


class TrainerWorkloadSerializer(StrictSerializer):
    batches = serializers.IntegerField()
    sessions_today = serializers.IntegerField()
    registers_outstanding = serializers.IntegerField()
    submissions_to_mark = serializers.IntegerField()
    exam_answers_to_mark = serializers.IntegerField()
    projects_to_review = serializers.IntegerField()
    upcoming_tests = serializers.IntegerField()
    upcoming_exams = serializers.IntegerField()


class BatchSummarySerializer(StrictSerializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    course_title = serializers.CharField()
    status = serializers.CharField()
    students = serializers.IntegerField()
    attendance_percent = serializers.FloatField(allow_null=True)


class BulkImportSerializer(StrictModelSerializer):
    class Meta:
        model = BulkImport
        fields = (
            "id",
            "kind",
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


class UploadSerializer(StrictSerializer):
    file = serializers.FileField()
    #: Students only: enrol everybody in the file on this batch as well.
    batch = serializers.UUIDField(required=False, allow_null=True)
