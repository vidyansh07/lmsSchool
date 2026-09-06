"""Reporting serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import BulkImport, ExportFormat, ExportStatus


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


# ---------------------------------------------------------------------------
# Background export jobs
# ---------------------------------------------------------------------------


class ExportJobRequestSerializer(StrictSerializer):
    """What it takes to queue an export. Everything else is derived server-side."""

    report_key = serializers.CharField()
    format = serializers.ChoiceField(choices=ExportFormat.choices)
    batch = serializers.UUIDField(required=False, allow_null=True)
    course = serializers.UUIDField(required=False, allow_null=True)


class ExportJobSerializer(StrictSerializer):
    """An export job's status. Not a `ModelSerializer`.

    Deliberately does not expose the underlying `FileField`: DRF's default
    rendering of a `FileField` is the storage URL, and for a job backed by S3
    that is a *signed* URL — a bearer credential that would otherwise leave the
    API response and land in browser history. `download_url` points at this
    app's own download view instead, which re-checks ownership and expiry on
    every request. See `apps.common.storage` for why that indirection exists at
    all.

    Every field that can be empty is a real, typed value here rather than
    conditionally present, so a job that has not started yet serialises with
    `started_at: null`, not a missing key.
    """

    id = serializers.UUIDField(read_only=True)
    report_key = serializers.CharField()
    format = serializers.ChoiceField(choices=ExportFormat.choices)
    filters = serializers.JSONField()
    status = serializers.ChoiceField(choices=ExportStatus.choices)
    requested_by_email = serializers.SerializerMethodField()
    queued_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    row_count = serializers.IntegerField()
    original_filename = serializers.CharField()
    checksum = serializers.CharField()
    size_bytes = serializers.IntegerField()
    error = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)
    download_url = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_requested_by_email(self, obj) -> str | None:
        return obj.requested_by.email if obj.requested_by_id else None

    def get_download_url(self, obj) -> str | None:
        if obj.status != ExportStatus.COMPLETED or not obj.file:
            return None
        path = f"/api/v1/reports/exports/{obj.pk}/download/"
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request is not None else path
