"""Project serializers, scoped by caller."""

from __future__ import annotations

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Project, ProjectFile, ProjectKind, ProjectStatus, StudentProject, WorkStatus

PROJECT_STATUS_CHOICES = list(ProjectStatus.choices)

#: The outcomes a reviewer may choose. Deliberately not the whole workflow: a
#: reviewer cannot put a project back to "assigned".
REVIEW_OUTCOMES = [
    (WorkStatus.UNDER_REVIEW, WorkStatus.UNDER_REVIEW.label),
    (WorkStatus.REWORK, WorkStatus.REWORK.label),
    (WorkStatus.APPROVED, WorkStatus.APPROVED.label),
    (WorkStatus.COMPLETED, WorkStatus.COMPLETED.label),
]


class ProjectFileSerializer(StrictModelSerializer):
    class Meta:
        model = ProjectFile
        fields = ("id", "original_filename", "extension", "size_bytes", "checksum", "created_at")
        read_only_fields = fields


class ProjectSerializer(StrictModelSerializer):
    """The staff view of a brief."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    batch_code = serializers.CharField(source="batch.code", read_only=True, default=None)
    module_title = serializers.CharField(source="module.title", read_only=True, default=None)
    reviewer_name = serializers.CharField(
        source="reviewer.user.get_full_name", read_only=True, default=None
    )
    assigned_count = serializers.IntegerField(read_only=True, default=0)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Project
        fields = (
            "id",
            "code",
            "course",
            "course_title",
            "module",
            "module_title",
            "batch",
            "batch_code",
            "title",
            "description",
            "instructions",
            "deliverables",
            "kind",
            "is_required",
            "start_date",
            "end_date",
            "requires_repository_url",
            "requires_deployment_url",
            "max_marks",
            "passing_marks",
            "rubric",
            "reviewer",
            "reviewer_name",
            "status",
            "published_at",
            "is_open",
            "assigned_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProjectWriteSerializer(StrictSerializer):
    """Create and edit. ``status`` moves through its own endpoint."""

    module = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    reviewer = serializers.UUIDField(required=False, allow_null=True)
    title = SafeCharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    deliverables = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    kind = serializers.ChoiceField(choices=ProjectKind.choices, required=False)
    is_required = serializers.BooleanField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    requires_repository_url = serializers.BooleanField(required=False)
    requires_deployment_url = serializers.BooleanField(required=False)
    max_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    passing_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    rubric = serializers.ListField(child=serializers.DictField(), required=False)


class ProjectStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=PROJECT_STATUS_CHOICES)


class StudentProjectSerializer(StrictModelSerializer):
    """What the student sees of their own project."""

    files = ProjectFileSerializer(many=True, read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    max_marks = serializers.DecimalField(
        source="project.max_marks", max_digits=6, decimal_places=2, read_only=True
    )
    is_passing = serializers.BooleanField(read_only=True, allow_null=True)
    is_open_to_student = serializers.BooleanField(read_only=True)

    class Meta:
        model = StudentProject
        fields = (
            "id",
            "project",
            "project_code",
            "project_title",
            "status",
            "repository_url",
            "deployment_url",
            "notes",
            "submitted_at",
            "submission_count",
            "is_late",
            "marks_awarded",
            "max_marks",
            "rubric_scores",
            "is_passing",
            "is_open_to_student",
            "feedback",
            "reviewed_at",
            "files",
            "created_at",
        )
        read_only_fields = fields


class ReviewerProjectSerializer(StudentProjectSerializer):
    """The reviewer's view. Adds whose work it is."""

    student_id = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="enrollment.student.user.get_full_name", read_only=True
    )
    batch_code = serializers.CharField(source="enrollment.batch.code", read_only=True)
    reviewer_name = serializers.CharField(
        source="reviewer.user.get_full_name", read_only=True, default=None
    )

    class Meta(StudentProjectSerializer.Meta):
        fields = (
            *StudentProjectSerializer.Meta.fields,
            "enrollment",
            "student_id",
            "student_name",
            "batch_code",
            "reviewer_name",
        )
        read_only_fields = fields


class ProjectWorkWriteSerializer(StrictSerializer):
    """A student's save or hand-in. Files arrive as repeated ``files`` parts."""

    repository_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    deployment_url = serializers.URLField(required=False, allow_blank=True, max_length=500)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    files = serializers.ListField(child=serializers.FileField(), required=False, allow_empty=True)


class ReviewSerializer(StrictSerializer):
    """A review decision.

    There is no ``total`` and no ``percentage`` field: the server sums the
    rubric, or bounds the single mark, and derives pass or fail on read.
    """

    outcome = serializers.ChoiceField(choices=REVIEW_OUTCOMES)
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    rubric_scores = serializers.DictField(required=False)


class AssignResultSerializer(StrictSerializer):
    assigned = serializers.IntegerField()
    already_had = serializers.IntegerField()


class OutstandingProjectSerializer(StrictSerializer):
    id = serializers.CharField()
    code = serializers.CharField()
    title = serializers.CharField()


class RequiredProjectProgressSerializer(StrictSerializer):
    """§5.2: whether every required project is finished."""

    required = serializers.IntegerField()
    finished = serializers.IntegerField()
    met = serializers.BooleanField()
    outstanding = OutstandingProjectSerializer(many=True)


class StudentProjectListSerializer(ProjectSerializer):
    """A student's list: the brief plus their own row on it."""

    my_work = serializers.SerializerMethodField()

    class Meta(ProjectSerializer.Meta):
        fields = (*ProjectSerializer.Meta.fields, "my_work")
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(StudentProjectSerializer(allow_null=True))
    def get_my_work(obj):
        work = getattr(obj, "my_work_row", None)
        return None if work is None else StudentProjectSerializer(work).data
