"""Response shapes for the calendar and dashboards.

These exist so the OpenAPI document describes real objects rather than "any
JSON". The views build plain dictionaries — a dashboard is an assembled view,
not a model — so these serializers are declarative documentation of that shape.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.warnings.views import WarningSerializer


class CalendarEventSerializer(serializers.Serializer):
    kind = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    start = serializers.CharField(read_only=True)
    end = serializers.CharField(read_only=True, allow_null=True)
    all_day = serializers.BooleanField(read_only=True)
    location = serializers.CharField(read_only=True)
    batch_id = serializers.CharField(read_only=True, allow_null=True)
    batch_code = serializers.CharField(read_only=True)
    course_id = serializers.CharField(read_only=True, allow_null=True)
    course_title = serializers.CharField(read_only=True)
    trainer_name = serializers.CharField(read_only=True)
    metadata = serializers.DictField(read_only=True)


class CalendarResponseSerializer(serializers.Serializer):
    start = serializers.CharField(read_only=True)
    end = serializers.CharField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    events = CalendarEventSerializer(many=True, read_only=True)


class DashboardCourseSerializer(serializers.Serializer):
    enrollment_id = serializers.CharField(read_only=True)
    course_id = serializers.CharField(read_only=True)
    course_title = serializers.CharField(read_only=True)
    course_slug = serializers.CharField(read_only=True)
    batch_code = serializers.CharField(read_only=True)
    batch_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    grants_access = serializers.BooleanField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    completed_lessons = serializers.IntegerField(read_only=True)
    total_lessons = serializers.IntegerField(read_only=True)
    last_lesson_id = serializers.CharField(read_only=True, allow_null=True)
    last_lesson_title = serializers.CharField(read_only=True, allow_null=True)


class DashboardBatchSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    course_title = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    enrollment_status = serializers.CharField(read_only=True, required=False)
    start_date = serializers.CharField(read_only=True)
    end_date = serializers.CharField(read_only=True)


class StudentDashboardSerializer(serializers.Serializer):
    is_student = serializers.BooleanField(read_only=True)
    courses = DashboardCourseSerializer(many=True, read_only=True)
    batches = DashboardBatchSerializer(many=True, read_only=True)
    upcoming_classes = CalendarEventSerializer(many=True, read_only=True)
    continue_learning = DashboardCourseSerializer(read_only=True, allow_null=True)
    recent_activity = serializers.ListField(child=serializers.DictField(), read_only=True)
    notifications = serializers.ListField(child=serializers.DictField(), read_only=True)


class TrainerBatchSerializer(DashboardBatchSerializer):
    capacity = serializers.IntegerField(read_only=True)
    enrolled_count = serializers.IntegerField(read_only=True)


class TrainerCourseSerializer(serializers.Serializer):
    course_id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    batch_count = serializers.IntegerField(read_only=True)


class TrainerWorkSerializer(serializers.Serializer):
    """§Phase 9 work-queue counts, scoped to the calling trainer's own
    activities (`apps.work.access.visible_activities`, never a raw
    `Activity.objects.count()`) — always a real, measured number, never
    `null`, even when it is zero."""

    pending = serializers.IntegerField(read_only=True)
    overdue = serializers.IntegerField(read_only=True)


class TrainerDashboardSerializer(serializers.Serializer):
    is_trainer = serializers.BooleanField(read_only=True)
    batches = TrainerBatchSerializer(many=True, read_only=True)
    today_classes = CalendarEventSerializer(many=True, read_only=True)
    upcoming_classes = CalendarEventSerializer(many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    courses = TrainerCourseSerializer(many=True, read_only=True)
    #: Phase 15: `{pending, overdue}` — always measured, never `null`.
    work = TrainerWorkSerializer(read_only=True)


class CounsellorDashboardSerializer(serializers.Serializer):
    """ERP Phase 17 (`API_CONTRACTS.md`, verbatim field names) — every count
    scoped to the calling counsellor's own reach, never `null`."""

    new_students_today = serializers.IntegerField(read_only=True)
    pending_registrations = serializers.IntegerField(read_only=True)
    follow_ups_due = serializers.IntegerField(read_only=True)
    follow_ups_overdue = serializers.IntegerField(read_only=True)
    unassigned_batch = serializers.IntegerField(read_only=True)
    unassigned_trainer = serializers.IntegerField(read_only=True)
    #: The same shape `GET /warnings/` returns, reused rather than
    #: redeclared — `apps.warnings.services.cached_warnings_for` is the one
    #: source for both.
    warnings = WarningSerializer(many=True, read_only=True)
