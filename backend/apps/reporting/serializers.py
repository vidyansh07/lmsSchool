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


# ---------------------------------------------------------------------------
# The manager hubs — a landing summary, and the batch and trainer drill-downs
# beneath it. Every numeric field below is a real number or `None`, never an
# absent key: a brand-new batch or a trainer with no history yet still
# serialises the full shape, just with zeroes and nulls in it.
# ---------------------------------------------------------------------------


class AttentionItemSerializer(StrictSerializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    href = serializers.CharField()
    severity = serializers.ChoiceField(choices=("low", "medium", "high"))


class ManagerDashboardBatchesSerializer(StrictSerializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    behind_schedule = serializers.IntegerField()
    at_risk = serializers.IntegerField()


class ManagerDashboardStudentsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    at_risk = serializers.IntegerField()


class ManagerDashboardTrainersSerializer(StrictSerializer):
    total = serializers.IntegerField()
    with_overdue_dsr = serializers.IntegerField()


class ManagerDashboardSerializer(StrictSerializer):
    """The two hubs' landing summary — a KPI strip that summarises the
    drill-down screens beneath it, and the manager's attention queue."""

    batches = ManagerDashboardBatchesSerializer()
    students = ManagerDashboardStudentsSerializer()
    trainers = ManagerDashboardTrainersSerializer()
    attention = AttentionItemSerializer(many=True)
    as_of = serializers.CharField()


class BatchOverviewBatchSerializer(StrictSerializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    status = serializers.CharField()
    delivery_mode = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    capacity = serializers.IntegerField()
    seats_taken = serializers.IntegerField()


class BatchOverviewCourseSerializer(StrictSerializer):
    id = serializers.CharField()
    title = serializers.CharField()
    code = serializers.CharField()


class BatchOverviewTrainerSerializer(StrictSerializer):
    id = serializers.CharField()
    name = serializers.CharField()
    trainer_id = serializers.CharField()


class BatchOverviewAttendanceSerializer(StrictSerializer):
    percentage = serializers.IntegerField(allow_null=True)
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    total_sessions = serializers.IntegerField()


class BatchOverviewTimelineSerializer(StrictSerializer):
    """Whatever `apps.progress.reports.timeline_progress` returns, verbatim."""

    as_of = serializers.CharField()
    sessions_total = serializers.IntegerField()
    sessions_completed = serializers.IntegerField()
    course_lessons_total = serializers.IntegerField()
    lessons_planned = serializers.IntegerField()
    lessons_covered = serializers.IntegerField()
    next_lesson = serializers.DictField(allow_null=True)
    percent_complete = serializers.IntegerField(allow_null=True)
    percent_expected = serializers.IntegerField(allow_null=True)
    variance_percent = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()


class BatchOverviewSessionsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    upcoming = serializers.IntegerField()


class BatchOverviewDsrSerializer(StrictSerializer):
    expected = serializers.IntegerField()
    submitted = serializers.IntegerField()
    approved = serializers.IntegerField()
    pending_review = serializers.IntegerField()
    overdue = serializers.IntegerField()


class BatchOverviewAssessmentsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    average_percent = serializers.FloatField(allow_null=True)


class BatchOverviewAssignmentsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    graded = serializers.IntegerField()


class BatchOverviewProjectsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    reviewed = serializers.IntegerField()


class BatchOverviewStudentsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    at_risk = serializers.IntegerField()


class BatchOverviewSerializer(StrictSerializer):
    """Everything about one batch, in the one request the batch hub asks for."""

    batch = BatchOverviewBatchSerializer()
    course = BatchOverviewCourseSerializer()
    trainer = BatchOverviewTrainerSerializer(allow_null=True)
    attendance = BatchOverviewAttendanceSerializer()
    timeline = BatchOverviewTimelineSerializer()
    sessions = BatchOverviewSessionsSerializer()
    dsr = BatchOverviewDsrSerializer()
    assessments = BatchOverviewAssessmentsSerializer()
    assignments = BatchOverviewAssignmentsSerializer()
    projects = BatchOverviewProjectsSerializer()
    students = BatchOverviewStudentsSerializer()
    as_of = serializers.CharField()


class BatchRosterRowSerializer(StrictSerializer):
    """One student's rollup on a batch roster — the batch hub's next drill-down."""

    enrollment_id = serializers.CharField()
    student_id = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    attendance_percent = serializers.IntegerField(allow_null=True)
    assessment_average = serializers.FloatField(allow_null=True)
    assignments_submitted = serializers.IntegerField()
    assignments_total = serializers.IntegerField()
    projects_submitted = serializers.IntegerField()
    projects_total = serializers.IntegerField()
    progress_percent = serializers.IntegerField(allow_null=True)
    risk_flags = serializers.ListField(child=serializers.CharField())
    transferred_in = serializers.BooleanField()


class TrainerOverviewTrainerSerializer(StrictSerializer):
    id = serializers.CharField()
    name = serializers.CharField()
    trainer_id = serializers.CharField()
    email = serializers.CharField()


class TrainerOverviewBatchesSerializer(StrictSerializer):
    total = serializers.IntegerField()
    active = serializers.IntegerField()


class TrainerOverviewStudentsSerializer(StrictSerializer):
    total = serializers.IntegerField()
    at_risk = serializers.IntegerField()


class TrainerOverviewSubmissionSerializer(StrictSerializer):
    attendance_rate = serializers.FloatField(allow_null=True)
    dsr_rate = serializers.FloatField(allow_null=True)
    dsr_approval_rate = serializers.FloatField(allow_null=True)


class TrainerOverviewCompletionSerializer(StrictSerializer):
    assessments = serializers.FloatField(allow_null=True)
    assignments = serializers.FloatField(allow_null=True)
    projects = serializers.FloatField(allow_null=True)


class TrainerOverviewOutcomesSerializer(StrictSerializer):
    student_average_score = serializers.FloatField(allow_null=True)
    student_attendance_percent = serializers.IntegerField(allow_null=True)


class TrainerOverviewPendingSerializer(StrictSerializer):
    dsr_to_submit = serializers.IntegerField()
    assignments_to_grade = serializers.IntegerField()
    projects_to_review = serializers.IntegerField()
    overdue = serializers.IntegerField()


class TrainerOverviewReviewSerializer(StrictSerializer):
    id = serializers.CharField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    rating = serializers.IntegerField()
    summary = serializers.CharField(allow_blank=True)
    reviewer = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class TrainerOverviewFeedbackSerializer(StrictSerializer):
    id = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()
    batch_code = serializers.CharField(allow_null=True)


class TrainerOverviewSerializer(StrictSerializer):
    """Everything about one trainer — their load, their record, what is
    waiting on them — for the trainer hub's drill-down."""

    trainer = TrainerOverviewTrainerSerializer()
    batches = TrainerOverviewBatchesSerializer()
    students = TrainerOverviewStudentsSerializer()
    submission = TrainerOverviewSubmissionSerializer()
    completion = TrainerOverviewCompletionSerializer()
    outcomes = TrainerOverviewOutcomesSerializer()
    pending = TrainerOverviewPendingSerializer()
    reviews = TrainerOverviewReviewSerializer(many=True)
    student_feedback = TrainerOverviewFeedbackSerializer(many=True)
    as_of = serializers.CharField()


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
