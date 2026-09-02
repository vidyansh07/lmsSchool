"""Assignment serializers.

Scoped by caller, as everywhere else in this codebase: a student's view of a
submission carries their marks and feedback, a trainer's additionally carries
who the student is. Nothing decides *permission* here — that is
``access.py``'s job — but a field a caller must not see is simply absent from
their serializer rather than filtered out downstream.
"""

from __future__ import annotations

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionFile,
    SubmissionKind,
)

ASSIGNMENT_STATUS_CHOICES = [(value, label) for value, label in AssignmentStatus.choices]


class AttachmentSerializer(StrictModelSerializer):
    class Meta:
        model = AssignmentAttachment
        fields = ("id", "title", "original_filename", "content_type", "size_bytes", "created_at")
        read_only_fields = fields


class AttachmentUploadSerializer(StrictSerializer):
    title = SafeCharField(max_length=200)
    file = serializers.FileField()


class AssignmentSerializer(StrictModelSerializer):
    """The staff view of a brief."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    batch_code = serializers.CharField(source="batch.code", read_only=True, default=None)
    module_title = serializers.CharField(source="module.title", read_only=True, default=None)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True, default=None)
    attachments = AttachmentSerializer(many=True, read_only=True)
    submission_count = serializers.IntegerField(read_only=True, default=0)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = (
            "id",
            "code",
            "course",
            "course_title",
            "module",
            "module_title",
            "lesson",
            "lesson_title",
            "batch",
            "batch_code",
            "title",
            "instructions",
            "submission_kind",
            "max_marks",
            "passing_marks",
            "due_at",
            "allow_late",
            "late_cutoff_at",
            "allow_resubmission",
            "max_attempts",
            "status",
            "published_at",
            "is_open",
            "attachments",
            "submission_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AssignmentWriteSerializer(StrictSerializer):
    """Create and edit. ``status`` is absent on purpose — it moves through
    :func:`services.set_assignment_status`, which enforces the lifecycle."""

    module = serializers.UUIDField(required=False, allow_null=True)
    lesson = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    title = SafeCharField(max_length=200)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    submission_kind = serializers.ChoiceField(
        choices=SubmissionKind.choices, required=False, default=SubmissionKind.FILE
    )
    max_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    passing_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    allow_late = serializers.BooleanField(required=False)
    late_cutoff_at = serializers.DateTimeField(required=False, allow_null=True)
    allow_resubmission = serializers.BooleanField(required=False)
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=20)


class AssignmentStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=ASSIGNMENT_STATUS_CHOICES)


class SubmissionFileSerializer(StrictModelSerializer):
    class Meta:
        model = SubmissionFile
        fields = ("id", "original_filename", "extension", "size_bytes", "checksum", "created_at")
        read_only_fields = fields


class SubmissionSerializer(StrictModelSerializer):
    """What the submitting student sees of their own attempt."""

    files = SubmissionFileSerializer(many=True, read_only=True)
    assignment_code = serializers.CharField(source="assignment.code", read_only=True)
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    max_marks = serializers.DecimalField(
        source="assignment.max_marks", max_digits=6, decimal_places=2, read_only=True
    )
    is_passing = serializers.BooleanField(read_only=True, allow_null=True)

    class Meta:
        model = AssignmentSubmission
        fields = (
            "id",
            "assignment",
            "assignment_code",
            "assignment_title",
            "attempt",
            "status",
            "text_answer",
            "link_url",
            "submitted_at",
            "is_late",
            "marks_awarded",
            "max_marks",
            "is_passing",
            "feedback",
            "graded_at",
            "files",
            "created_at",
        )
        read_only_fields = fields


class StaffSubmissionSerializer(SubmissionSerializer):
    """The marking view. Adds who handed it in.

    A student's own serializer deliberately does not carry ``graded_by``: who
    marked a piece of work is staff information, and surfacing it invites the
    argument rather than the improvement.
    """

    student_id = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="enrollment.student.user.get_full_name", read_only=True
    )
    batch_code = serializers.CharField(source="enrollment.batch.code", read_only=True)
    graded_by_name = serializers.CharField(
        source="graded_by.get_full_name", read_only=True, default=None
    )

    class Meta(SubmissionSerializer.Meta):
        fields = (
            *SubmissionSerializer.Meta.fields,
            "enrollment",
            "student_id",
            "student_name",
            "batch_code",
            "graded_by_name",
        )
        read_only_fields = fields


class SubmitSerializer(StrictSerializer):
    """A hand-in. Files arrive as repeated ``files`` parts in a multipart body."""

    text_answer = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    link_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    files = serializers.ListField(child=serializers.FileField(), required=False, allow_empty=True)


class GradeSerializer(StrictSerializer):
    """One raw mark for one attempt.

    There is no ``percentage``, no ``total`` and no ``passed`` field, and that
    is the point: the server derives all three from ``marks`` and the
    assignment's own maximum.
    """

    marks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal(0))
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=10000)


class ReturnSerializer(StrictSerializer):
    feedback = serializers.CharField(max_length=10000)


class StudentAssignmentSerializer(StrictModelSerializer):
    """A student's view of a brief: what to do, by when, and where they stand.

    ``my_submission`` is attached by the view from a single prefetch, so a list
    of twenty assignments does not become twenty-one queries.
    """

    course_title = serializers.CharField(source="course.title", read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    my_submission = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assignment
        fields = (
            "id",
            "code",
            "course",
            "course_title",
            "module",
            "lesson",
            "title",
            "instructions",
            "submission_kind",
            "max_marks",
            "passing_marks",
            "due_at",
            "allow_late",
            "late_cutoff_at",
            "allow_resubmission",
            "max_attempts",
            "status",
            "is_open",
            "attachments",
            "my_submission",
        )
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(SubmissionSerializer(allow_null=True))
    def get_my_submission(obj):
        submission = getattr(obj, "my_latest_submission", None)
        if submission is None:
            return None
        return SubmissionSerializer(submission).data
