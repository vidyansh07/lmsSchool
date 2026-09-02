"""Class session serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import ClassSession, SessionStatus


class ClassSessionSerializer(serializers.ModelSerializer):
    batch_code = serializers.CharField(source="batch.code", read_only=True)
    batch_name = serializers.CharField(source="batch.name", read_only=True)
    course_title = serializers.CharField(source="batch.course.title", read_only=True)
    trainer_name = serializers.SerializerMethodField()
    starts_at = serializers.DateTimeField(read_only=True)
    ends_at = serializers.DateTimeField(read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)
    can_take_attendance = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClassSession
        fields = (
            "id",
            "batch_id",
            "batch_code",
            "batch_name",
            "course_title",
            "session_date",
            "start_time",
            "end_time",
            "timezone_name",
            "starts_at",
            "ends_at",
            "duration_minutes",
            "trainer_name",
            "topic",
            "location",
            "status",
            "cancellation_reason",
            "attendance_taken_at",
            "can_take_attendance",
            "duration_minutes",
        )
        read_only_fields = fields

    def get_trainer_name(self, obj: ClassSession) -> str:
        """A name, never contact details."""
        return obj.trainer.user.full_name if obj.trainer else ""


class ClassSessionWriteSerializer(StrictModelSerializer):
    """Create or edit a one-off class.

    Absent on purpose: `status` (its own endpoint and transition table),
    `batch`, `schedule`, `trainer` and every attendance field.
    """

    topic = SafeCharField(max_length=250, required=False, allow_blank=True)
    location = SafeCharField(max_length=150, required=False, allow_blank=True)
    notes = SafeCharField(max_length=2000, required=False, allow_blank=True)

    class Meta:
        model = ClassSession
        fields = (
            "session_date",
            "start_time",
            "end_time",
            "timezone_name",
            "topic",
            "location",
            "notes",
        )

    def validate(self, attrs):
        start = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": ["The end time must be after the start time."]}
            )
        return attrs


class SessionStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=SessionStatus.choices)
    reason = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class GenerateSessionsSerializer(StrictSerializer):
    """Materialise classes from the batch timetable.

    The window defaults to the batch's own dates, which is what an operator
    almost always wants.
    """

    start = serializers.DateField(required=False, allow_null=True)
    end = serializers.DateField(required=False, allow_null=True)


class GenerationResultSerializer(serializers.Serializer):
    created = serializers.IntegerField(read_only=True)
    skipped = serializers.IntegerField(read_only=True)
    start = serializers.DateField(read_only=True)
    end = serializers.DateField(read_only=True)


class RescheduleSerializer(StrictSerializer):
    session_date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    reason = SafeCharField(max_length=255, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": ["The end time must be after the start time."]}
            )
        return attrs


class TrainerHistorySerializer(serializers.Serializer):
    """Who taught a batch, and when."""

    id = serializers.UUIDField(read_only=True)
    trainer_name = serializers.CharField(read_only=True)
    trainer_code = serializers.CharField(read_only=True)
    assigned_at = serializers.DateTimeField(read_only=True)
    ended_at = serializers.DateTimeField(read_only=True, allow_null=True)
    is_current = serializers.BooleanField(read_only=True)
    note = serializers.CharField(read_only=True)
