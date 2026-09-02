"""Attendance serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import AttendanceRecord, AttendanceStatus


class RegisterEntrySerializer(serializers.Serializer):
    """One row of a class register, as the trainer's screen needs it.

    Carries the student's current mark (or `null` if unmarked) so the screen can
    be rendered from one request rather than joining two on the client.
    """

    enrollment_id = serializers.UUIDField(read_only=True)
    student_code = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    enrollment_status = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True, allow_null=True)
    note = serializers.CharField(read_only=True)
    was_corrected = serializers.BooleanField(read_only=True)


class RegisterSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(read_only=True)
    session_date = serializers.DateField(read_only=True)
    batch_code = serializers.CharField(read_only=True)
    can_mark = serializers.BooleanField(read_only=True)
    attendance_taken_at = serializers.DateTimeField(read_only=True, allow_null=True)
    entries = RegisterEntrySerializer(many=True, read_only=True)


class MarkEntrySerializer(StrictSerializer):
    enrollment_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=AttendanceStatus.choices)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class MarkAttendanceSerializer(StrictSerializer):
    """A whole register in one request.

    Bulk by design: a trainer marks the room in one action, so the API takes it
    in one action too — one transaction, and no half-saved register.
    """

    entries = MarkEntrySerializer(many=True, allow_empty=False)


class MarkResultSerializer(serializers.Serializer):
    created = serializers.IntegerField(read_only=True)
    updated = serializers.IntegerField(read_only=True)
    corrections = serializers.IntegerField(read_only=True)


class CorrectAttendanceSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=AttendanceStatus.choices)
    reason = SafeCharField(max_length=255)


class AttendanceRecordSerializer(serializers.ModelSerializer):
    session_date = serializers.DateField(source="session.session_date", read_only=True)
    start_time = serializers.TimeField(source="session.start_time", read_only=True)
    topic = serializers.CharField(source="session.topic", read_only=True)
    batch_code = serializers.CharField(source="session.batch.code", read_only=True)
    was_corrected = serializers.BooleanField(read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "session_id",
            "session_date",
            "start_time",
            "topic",
            "batch_code",
            "status",
            "note",
            "was_corrected",
            "marked_at",
        )
        read_only_fields = fields


class AdminAttendanceRecordSerializer(AttendanceRecordSerializer):
    """Adds who marked and corrected it — staff only."""

    student_code = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    student_name = serializers.CharField(source="enrollment.student.user.full_name", read_only=True)
    marked_by_email = serializers.SerializerMethodField()

    class Meta(AttendanceRecordSerializer.Meta):
        fields = (
            *AttendanceRecordSerializer.Meta.fields,
            "student_code",
            "student_name",
            "previous_status",
            "correction_reason",
            "corrected_at",
            "marked_by_email",
        )
        read_only_fields = fields

    def get_marked_by_email(self, obj: AttendanceRecord) -> str:
        return obj.marked_by.email if obj.marked_by else ""


class AttendanceSummarySerializer(serializers.Serializer):
    """Counts, plus the requirement they are judged against.

    The threshold comes from the academic configuration (§4.7), so a student
    reading this sees both where they stand and what is being asked of them —
    and a change of policy is visible here on the next request.
    """

    total_sessions = serializers.IntegerField(read_only=True)
    present = serializers.IntegerField(read_only=True)
    late = serializers.IntegerField(read_only=True)
    absent = serializers.IntegerField(read_only=True)
    excused = serializers.IntegerField(read_only=True)
    attended = serializers.IntegerField(read_only=True)
    percentage = serializers.IntegerField(read_only=True, allow_null=True)
    required = serializers.BooleanField(read_only=True)
    minimum_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    met = serializers.BooleanField(read_only=True, allow_null=True)
