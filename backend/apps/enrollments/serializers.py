"""Enrolment and progress serializers, scoped by audience.

A student sees their own enrolment without the administrative note attached to
it; an administrator sees everything. That is a serializer boundary rather than
a conditional field, because a conditional is where the leak eventually appears.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import Enrollment, EnrollmentStatus, LessonProgress


class EnrollmentSerializer(serializers.ModelSerializer):
    """What a student sees about their own enrolment."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    batch_name = serializers.CharField(source="batch.name", read_only=True)
    batch_code = serializers.CharField(source="batch.code", read_only=True)
    batch_status = serializers.CharField(source="batch.status", read_only=True)
    trainer_name = serializers.SerializerMethodField()
    grants_access = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "code",
            "course_id",
            "course_code",
            "course_title",
            "course_slug",
            "batch_id",
            "batch_code",
            "batch_name",
            "batch_status",
            "trainer_name",
            "status",
            "enrolled_at",
            "start_date",
            "access_end_date",
            "completed_at",
            "grants_access",
        )
        read_only_fields = fields

    def get_trainer_name(self, obj: Enrollment) -> str:
        return obj.batch.trainer.user.full_name if obj.batch.trainer else ""

    def get_grants_access(self, obj: Enrollment) -> bool:
        """Whether this enrolment opens the course right now."""
        return obj.grants_access()


class AdminEnrollmentSerializer(EnrollmentSerializer):
    """Administrator and trainer view: adds the student and the status note."""

    student_code = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_email = serializers.EmailField(source="student.user.email", read_only=True)
    # Fee figures are annotated by ``apps.fees.queries.annotate_enrollment_fee``
    # on the list; a detail fetched without them reports null, never a guess.
    fee_payable = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True, default=None
    )
    fee_paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True, default=None
    )
    fee_balance = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True, default=None
    )
    fee_next_due_on = serializers.DateField(read_only=True, allow_null=True, default=None)

    class Meta(EnrollmentSerializer.Meta):
        fields = (
            *EnrollmentSerializer.Meta.fields,
            "student_id",
            "student_code",
            "student_name",
            "student_email",
            "status_note",
            "status_changed_at",
            "fee_payable",
            "fee_paid",
            "fee_balance",
            "fee_next_due_on",
        )
        read_only_fields = fields


class RosterEntrySerializer(serializers.ModelSerializer):
    """A batch roster row.

    Names and enrolment state only. A trainer needs to know who is in the room
    and whether they are suspended, not the student's address or fee status.
    """

    student_code = serializers.CharField(source="student.student_id", read_only=True)
    full_name = serializers.CharField(source="student.user.full_name", read_only=True)
    email = serializers.EmailField(source="student.user.email", read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "code",
            "student_id",
            "student_code",
            "full_name",
            "email",
            "status",
            "enrolled_at",
        )
        read_only_fields = fields


class EnrolStudentSerializer(StrictSerializer):
    """Enrol one student on one batch.

    The course is absent by design: it is whatever the batch runs, so accepting
    it from the client would create a way for the two to disagree.
    """

    student_id = serializers.UUIDField()
    batch_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=[
            (EnrollmentStatus.PENDING, "Pending"),
            (EnrollmentStatus.ACTIVE, "Active"),
        ],
        default=EnrollmentStatus.ACTIVE,
    )
    start_date = serializers.DateField(required=False, allow_null=True)
    access_end_date = serializers.DateField(required=False, allow_null=True)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class EnrollmentStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=EnrollmentStatus.choices)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class LessonProgressSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)

    class Meta:
        model = LessonProgress
        fields = (
            "id",
            "lesson_id",
            "lesson_title",
            "status",
            "first_accessed_at",
            "last_accessed_at",
            "completed_at",
        )
        read_only_fields = fields


class CourseProgressSerializer(serializers.Serializer):
    """Summary of how far a student has got on one course."""

    total_lessons = serializers.IntegerField(read_only=True)
    completed_lessons = serializers.IntegerField(read_only=True)
    percent = serializers.IntegerField(read_only=True)
    last_lesson_id = serializers.CharField(read_only=True, allow_null=True)
    last_lesson_title = serializers.CharField(read_only=True, allow_null=True)
    last_accessed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class LessonCompletionSerializer(StrictSerializer):
    completed = serializers.BooleanField()
