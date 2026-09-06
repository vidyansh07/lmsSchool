"""Progress and completion serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import CourseCompletion


class LessonProgressSummarySerializer(StrictSerializer):
    total = serializers.IntegerField()
    started = serializers.IntegerField()
    completed = serializers.IntegerField()
    percent = serializers.IntegerField()
    last_lesson_id = serializers.CharField(allow_null=True)
    last_lesson_title = serializers.CharField(allow_null=True)
    last_accessed_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)


class ModuleProgressSerializer(StrictSerializer):
    id = serializers.CharField()
    title = serializers.CharField()
    position = serializers.IntegerField()
    total_lessons = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    percent = serializers.IntegerField()
    is_complete = serializers.BooleanField()


class AttendanceProgressSerializer(StrictSerializer):
    total = serializers.IntegerField()
    attended = serializers.IntegerField()
    percent = serializers.IntegerField()
    has_records = serializers.BooleanField()
    present = serializers.IntegerField()
    late = serializers.IntegerField()
    absent = serializers.IntegerField()
    excused = serializers.IntegerField()


class AssignmentProgressSerializer(StrictSerializer):
    total = serializers.IntegerField()
    submitted = serializers.IntegerField()
    graded = serializers.IntegerField()
    passed = serializers.IntegerField()
    percent = serializers.IntegerField()


class TestProgressSerializer(StrictSerializer):
    total = serializers.IntegerField()
    recorded = serializers.IntegerField()
    percent = serializers.IntegerField()
    average_percent = serializers.FloatField(allow_null=True)
    passed = serializers.IntegerField()


class OutstandingSerializer(StrictSerializer):
    id = serializers.CharField()
    code = serializers.CharField()
    title = serializers.CharField()


class ProjectProgressSerializer(StrictSerializer):
    required = serializers.IntegerField()
    finished = serializers.IntegerField()
    percent = serializers.IntegerField()
    outstanding = OutstandingSerializer(many=True)


class ExamProgressSerializer(StrictSerializer):
    exists = serializers.BooleanField()
    sat = serializers.BooleanField()
    passed = serializers.BooleanField(allow_null=True)
    best_percent = serializers.FloatField(allow_null=True)


class ProgressReportSerializer(StrictSerializer):
    """The one progress shape. Every screen reads this; none computes its own."""

    enrollment_id = serializers.CharField()
    course_title = serializers.CharField()
    batch_code = serializers.CharField()
    delivery_mode = serializers.CharField()
    lessons = LessonProgressSummarySerializer()
    modules = ModuleProgressSerializer(many=True)
    attendance = AttendanceProgressSerializer()
    assignments = AssignmentProgressSerializer()
    tests = TestProgressSerializer()
    projects = ProjectProgressSerializer()
    exam = ExamProgressSerializer()


class RuleOutcomeSerializer(StrictSerializer):
    key = serializers.CharField()
    label = serializers.CharField()
    required = serializers.BooleanField()
    met = serializers.BooleanField()
    detail = serializers.CharField()
    numbers = serializers.DictField()


class CompletionSerializer(StrictModelSerializer):
    student_name = serializers.CharField(
        source="enrollment.student.user.get_full_name", read_only=True
    )
    student_code = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    course_title = serializers.CharField(source="enrollment.course.title", read_only=True)
    batch_code = serializers.CharField(source="enrollment.batch.code", read_only=True)
    decided_by_name = serializers.CharField(
        source="decided_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = CourseCompletion
        fields = (
            "id",
            "enrollment",
            "student_name",
            "student_code",
            "course_title",
            "batch_code",
            "status",
            "became_eligible_at",
            "completed_on",
            "decision_note",
            "decided_at",
            "decided_by_name",
            "rule_snapshot",
            "updated_at",
        )
        read_only_fields = fields


class StudentCompletionSerializer(CompletionSerializer):
    """A student's own view. Who decided, and the note, are staff information."""

    class Meta(CompletionSerializer.Meta):
        fields = (
            "id",
            "enrollment",
            "course_title",
            "batch_code",
            "status",
            "became_eligible_at",
            "completed_on",
        )
        read_only_fields = fields


class EvaluationSerializer(StrictSerializer):
    """Progress, the rules, and the verdict — the completion screen in one call."""

    progress = ProgressReportSerializer()
    eligible = serializers.BooleanField()
    rules = RuleOutcomeSerializer(many=True)
    unmet = serializers.ListField(child=serializers.CharField())
    required_count = serializers.IntegerField()
    met_count = serializers.IntegerField()
    completion = CompletionSerializer(allow_null=True)


class StudentEvaluationSerializer(EvaluationSerializer):
    completion = StudentCompletionSerializer(allow_null=True)


class ApproveCompletionSerializer(StrictSerializer):
    completed_on = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    #: An override is recorded in the snapshot, so it stays explainable later.
    override = serializers.BooleanField(required=False, default=False)


class DecisionNoteSerializer(StrictSerializer):
    note = serializers.CharField(max_length=500)


class TimelineNextLessonSerializer(StrictSerializer):
    id = serializers.CharField()
    title = serializers.CharField()


class TimelineProgressSerializer(StrictSerializer):
    """`apps.progress.reports.timeline_progress`'s shape, unchanged.

    Percentages are ``allow_null``: a course with no published lessons, a
    batch with no classes, or one that has not started yet all report `None`
    rather than a `0` that would misstate what is actually known.
    """

    as_of = serializers.DateField()
    sessions_total = serializers.IntegerField()
    sessions_completed = serializers.IntegerField()
    course_lessons_total = serializers.IntegerField()
    lessons_planned = serializers.IntegerField()
    lessons_covered = serializers.IntegerField()
    next_lesson = TimelineNextLessonSerializer(allow_null=True)
    percent_complete = serializers.IntegerField(allow_null=True)
    percent_expected = serializers.IntegerField(allow_null=True)
    variance_percent = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
