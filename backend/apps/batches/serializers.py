"""Batch and schedule serializers, scoped by audience.

Write serializers reject unknown fields, so `code`, `status` and `created_by`
cannot be set by including them — each has its own endpoint or is system-owned.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import MAX_CAPACITY, Batch, BatchSchedule, BatchStatus, Weekday


class BatchScheduleSerializer(serializers.ModelSerializer):
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)
    trainer_name = serializers.SerializerMethodField()
    duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = BatchSchedule
        fields = (
            "id",
            "weekday",
            "weekday_label",
            "start_time",
            "end_time",
            "timezone_name",
            "location",
            "trainer_name",
            "is_active",
            "note",
            "duration_minutes",
        )
        read_only_fields = fields

    def get_trainer_name(self, obj: BatchSchedule) -> str:
        """The person teaching this slot — a name only, never contact details."""
        trainer = obj.trainer or obj.batch.trainer
        return trainer.user.full_name if trainer else ""


class BatchScheduleWriteSerializer(StrictModelSerializer):
    weekday = serializers.ChoiceField(choices=Weekday.choices)
    location = SafeCharField(max_length=150, required=False, allow_blank=True)
    note = SafeCharField(max_length=200, required=False, allow_blank=True)

    class Meta:
        model = BatchSchedule
        fields = (
            "weekday",
            "start_time",
            "end_time",
            "timezone_name",
            "location",
            "trainer",
            "is_active",
            "note",
        )

    def validate(self, attrs):
        start, end = attrs.get("start_time"), attrs.get("end_time")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": ["The end time must be after the start time."]}
            )
        return attrs


class BatchListSerializer(serializers.ModelSerializer):
    """Flat row for the batch table."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    trainer_name = serializers.SerializerMethodField()
    enrolled_count = serializers.IntegerField(read_only=True, default=0)
    seats_available = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = (
            "id",
            "code",
            "name",
            "course_id",
            "course_code",
            "course_title",
            "course_slug",
            "trainer_name",
            "start_date",
            "end_date",
            "capacity",
            "enrolled_count",
            "seats_available",
            "status",
            "created_at",
        )
        read_only_fields = fields

    def get_trainer_name(self, obj: Batch) -> str:
        return obj.trainer.user.full_name if obj.trainer else ""

    def get_seats_available(self, obj: Batch) -> int:
        # Uses the annotation when the queryset provided one, so a list of 50
        # batches does not issue 50 count queries.
        taken = getattr(obj, "enrolled_count", None)
        if taken is None:
            taken = obj.seats_taken()
        return max(obj.capacity - taken, 0)


class BatchDetailSerializer(BatchListSerializer):
    schedules = BatchScheduleSerializer(many=True, read_only=True)
    trainer_code = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    can_view_roster = serializers.SerializerMethodField()

    class Meta(BatchListSerializer.Meta):
        fields = (
            *BatchListSerializer.Meta.fields,
            "description",
            "trainer_id",
            "trainer_code",
            "schedules",
            "updated_at",
            "can_manage",
            "can_view_roster",
        )
        read_only_fields = fields

    def get_trainer_code(self, obj: Batch) -> str:
        return obj.trainer.trainer_id if obj.trainer else ""

    def get_can_manage(self, obj: Batch) -> bool:
        from . import access

        return access.can_manage_batch(self.context["request"].user, obj)

    def get_can_view_roster(self, obj: Batch) -> bool:
        from . import access

        return access.can_view_roster(self.context["request"].user, obj)


class BatchWriteSerializer(StrictModelSerializer):
    """Create/update input.

    Absent on purpose: `code` (system-allocated), `status` (its own endpoint and
    transition table), `trainer` (its own endpoint, because assignment checks
    the timetable) and `created_by`.
    """

    name = SafeCharField(max_length=200)
    capacity = serializers.IntegerField(min_value=1, max_value=MAX_CAPACITY)

    class Meta:
        model = Batch
        fields = ("name", "course", "description", "start_date", "end_date", "capacity")

    def validate(self, attrs):
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": ["The end date cannot be before the start date."]}
            )
        return attrs


class BatchStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=BatchStatus.choices)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class AssignTrainerSerializer(StrictSerializer):
    """Assign or clear the batch trainer.

    ``null`` clears it, which is why this is not a plain PATCH field: clearing a
    trainer on an active batch is a decision, not a typo.
    """

    trainer_id = serializers.UUIDField(allow_null=True)
