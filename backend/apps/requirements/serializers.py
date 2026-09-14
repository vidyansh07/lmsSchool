from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import RequirementReply, TrainerRequirement


class RequirementReplySerializer(StrictModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    author_role = serializers.CharField(source="author.role", read_only=True)

    class Meta:
        model = RequirementReply
        fields = ("id", "author", "author_name", "author_role", "message", "created_at")
        read_only_fields = fields


class TrainerRequirementSerializer(StrictModelSerializer):
    branch_code = serializers.CharField(source="branch.code", read_only=True)
    raised_by_name = serializers.CharField(source="raised_by.get_full_name", read_only=True)
    batch_code = serializers.CharField(source="batch.code", read_only=True, default=None)
    batch_name = serializers.CharField(source="batch.name", read_only=True, default=None)
    fulfilled_by_name = serializers.CharField(
        source="fulfilled_by.user.get_full_name", read_only=True, default=None
    )
    closed_by_name = serializers.CharField(
        source="closed_by.get_full_name", read_only=True, default=None
    )
    replies = RequirementReplySerializer(many=True, read_only=True)
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = TrainerRequirement
        fields = (
            "id",
            "title",
            "details",
            "status",
            "branch",
            "branch_code",
            "raised_by",
            "raised_by_name",
            "batch",
            "batch_code",
            "batch_name",
            "needed_by",
            "fulfilled_by",
            "fulfilled_by_name",
            "closed_at",
            "closed_by_name",
            "closing_note",
            "reply_count",
            "replies",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_reply_count(self, obj) -> int:
        return len(obj.replies.all())


class RequirementWriteSerializer(StrictSerializer):
    title = SafeCharField(max_length=160)
    details = SafeCharField(max_length=4000, required=False, allow_blank=True, default="")
    batch = serializers.UUIDField(required=False, allow_null=True, default=None)
    needed_by = serializers.DateField(required=False, allow_null=True, default=None)


class RequirementReplyWriteSerializer(StrictSerializer):
    message = SafeCharField(max_length=2000)


class RequirementCloseSerializer(StrictSerializer):
    fulfilled_by = serializers.UUIDField(required=False, allow_null=True, default=None)
    note = SafeCharField(max_length=300, required=False, allow_blank=True, default="")


class RequirementDeleteSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255)
