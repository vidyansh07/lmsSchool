"""Placement API shapes."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import Placement, PlacementStatus

#: Annual packages. Twelve digits because a lakh-denominated figure typed in
#: full is eight, and an institute that places somebody on a crore package
#: should not meet a validation error on the day it happens.
PACKAGE = {"max_digits": 12, "decimal_places": 2}


class PlacementSerializer(serializers.ModelSerializer):
    """One offer, as every screen reads it."""

    student_id = serializers.UUIDField(source="student.pk", read_only=True)
    student_name = serializers.SerializerMethodField()
    student_code = serializers.CharField(source="student.student_id", read_only=True, default=None)
    course_title = serializers.CharField(
        source="enrollment.course.title", read_only=True, default=None
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    recorded_by = serializers.SerializerMethodField()
    is_placed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Placement
        fields = (
            "id",
            "student_id",
            "student_name",
            "student_code",
            "enrollment_id",
            "course_title",
            "branch_id",
            "branch_name",
            "company",
            "role_title",
            "location",
            "status",
            "is_placed",
            "annual_package",
            "offered_on",
            "joined_on",
            "notes",
            "recorded_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_student_name(self, placement: Placement) -> str:
        user = placement.student.user if placement.student_id else None
        return (user.get_full_name() or user.email) if user is not None else ""

    def get_recorded_by(self, placement: Placement) -> str | None:
        author = placement.created_by
        if author is None:
            return None
        return author.get_full_name() or author.email


class PlacementWriteSerializer(StrictSerializer):
    """Recording an offer. The centre is not a field: it comes from the
    student (`services.record_placement`), so nothing can be filed into a
    centre the caller cannot read."""

    student = serializers.UUIDField()
    enrollment = serializers.UUIDField(required=False, allow_null=True)
    company = SafeCharField(max_length=120)
    role_title = SafeCharField(max_length=120)
    location = SafeCharField(max_length=80, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=PlacementStatus.choices, required=False, default=PlacementStatus.OFFERED
    )
    annual_package = serializers.DecimalField(
        min_value=0, required=False, allow_null=True, **PACKAGE
    )
    offered_on = serializers.DateField()
    joined_on = serializers.DateField(required=False, allow_null=True)
    notes = SafeCharField(max_length=2000, required=False, allow_blank=True, default="")


class PlacementUpdateSerializer(StrictSerializer):
    """Changing one. Every field optional; `student` is absent on purpose —
    see `services.EDITABLE_FIELDS`."""

    enrollment = serializers.UUIDField(required=False, allow_null=True)
    company = SafeCharField(max_length=120, required=False)
    role_title = SafeCharField(max_length=120, required=False)
    location = SafeCharField(max_length=80, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=PlacementStatus.choices, required=False)
    annual_package = serializers.DecimalField(
        min_value=0, required=False, allow_null=True, **PACKAGE
    )
    offered_on = serializers.DateField(required=False)
    joined_on = serializers.DateField(required=False, allow_null=True)
    notes = SafeCharField(max_length=2000, required=False, allow_blank=True)


class PlacementSummarySerializer(serializers.Serializer):
    """The workspace's opening numbers. `placed_students` counts people, every
    other figure counts offers — see `services.summary`."""

    offers = serializers.IntegerField()
    open_offers = serializers.IntegerField()
    closed_offers = serializers.IntegerField()
    placed_students = serializers.IntegerField()
    offers_this_month = serializers.IntegerField()
