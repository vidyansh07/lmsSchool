"""Performance review and feedback serializers.

The engine's own output (`apps.performance.engine`) is returned as-is: it is
already a plain, fully null-safe dictionary, and wrapping it in a matching
`Serializer` tree would only be a second, hand-maintained copy of its shape
that could drift from the real one.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Feedback, PerformanceReview, PerformanceSubjectType


class PerformanceReviewSerializer(StrictModelSerializer):
    student_code = serializers.CharField(source="student.student_id", read_only=True, default=None)
    student_name = serializers.CharField(
        source="student.user.get_full_name", read_only=True, default=None
    )
    trainer_code = serializers.CharField(source="trainer.trainer_id", read_only=True, default=None)
    trainer_name = serializers.CharField(
        source="trainer.user.get_full_name", read_only=True, default=None
    )
    reviewer_name = serializers.CharField(
        source="reviewer.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = PerformanceReview
        fields = (
            "id",
            "subject_type",
            "student",
            "student_code",
            "student_name",
            "trainer",
            "trainer_code",
            "trainer_name",
            "period_start",
            "period_end",
            "rating",
            "summary",
            "strengths",
            "concerns",
            "actions",
            "snapshot",
            "reviewer",
            "reviewer_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ReviewWriteSerializer(StrictSerializer):
    """Create a review. ``student`` xor ``trainer`` — enforced in the service."""

    student = serializers.UUIDField(required=False, allow_null=True)
    trainer = serializers.UUIDField(required=False, allow_null=True)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    summary = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    strengths = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    concerns = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    actions = serializers.CharField(max_length=5000, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get("period_end") and attrs.get("period_start"):
            if attrs["period_end"] < attrs["period_start"]:
                raise serializers.ValidationError(
                    {"period_end": ["The period cannot end before it starts."]}
                )
        return attrs


class ReviewUpdateSerializer(StrictSerializer):
    """Edit the judgement. The subject, reviewer and snapshot never change."""

    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    summary = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    strengths = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    concerns = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    actions = serializers.CharField(max_length=5000, required=False, allow_blank=True)


class FeedbackSerializer(StrictModelSerializer):
    student_code = serializers.CharField(source="student.student_id", read_only=True, default=None)
    student_name = serializers.CharField(
        source="student.user.get_full_name", read_only=True, default=None
    )
    trainer_code = serializers.CharField(source="trainer.trainer_id", read_only=True, default=None)
    trainer_name = serializers.CharField(
        source="trainer.user.get_full_name", read_only=True, default=None
    )
    batch_code = serializers.CharField(source="batch.code", read_only=True, default=None)
    author_name = serializers.CharField(source="author.get_full_name", read_only=True, default=None)

    class Meta:
        model = Feedback
        fields = (
            "id",
            "subject_type",
            "student",
            "student_code",
            "student_name",
            "trainer",
            "trainer_code",
            "trainer_name",
            "batch",
            "batch_code",
            "body",
            "visible_to_subject",
            "author",
            "author_name",
            "created_at",
        )
        read_only_fields = fields


class FeedbackWriteSerializer(StrictSerializer):
    student = serializers.UUIDField(required=False, allow_null=True)
    trainer = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    body = SafeCharField(max_length=5000)
    visible_to_subject = serializers.BooleanField(required=False, default=True)


class RiskThresholdsSerializer(StrictSerializer):
    """A partial update of the four numbers `apps.performance.risk` reads."""

    risk_attendance_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )
    risk_assessment_average_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )
    risk_missed_assignments = serializers.IntegerField(min_value=1, required=False)
    risk_progress_variance_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one threshold to change.")
        return attrs


class DeleteReasonSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255)


__all__ = [
    "DeleteReasonSerializer",
    "FeedbackSerializer",
    "FeedbackWriteSerializer",
    "PerformanceReviewSerializer",
    "PerformanceSubjectType",
    "ReviewUpdateSerializer",
    "ReviewWriteSerializer",
    "RiskThresholdsSerializer",
]
