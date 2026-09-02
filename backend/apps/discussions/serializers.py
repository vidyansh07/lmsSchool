"""Discussion serializers.

Names, never contact details: a classmate's email is not part of a conversation
(§7.7's rule applies here too).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Reply, Thread


class ReplySerializer(StrictModelSerializer):
    author_name = serializers.CharField(
        source="author.get_full_name", read_only=True, default="Removed"
    )
    hidden_by_name = serializers.CharField(
        source="hidden_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Reply
        fields = (
            "id",
            "thread",
            "author_name",
            "body",
            "is_trainer_response",
            "is_hidden",
            "hidden_reason",
            "hidden_by_name",
            "created_at",
        )
        read_only_fields = fields


class ThreadSerializer(StrictModelSerializer):
    author_name = serializers.CharField(
        source="author.get_full_name", read_only=True, default="Removed"
    )
    batch_code = serializers.CharField(source="batch.code", read_only=True)
    course_title = serializers.CharField(source="batch.course.title", read_only=True)

    class Meta:
        model = Thread
        fields = (
            "id",
            "batch",
            "batch_code",
            "course_title",
            "title",
            "body",
            "author_name",
            "is_pinned",
            "is_closed",
            "reply_count",
            "last_reply_at",
            "has_trainer_reply",
            "created_at",
        )
        read_only_fields = fields


class ThreadDetailSerializer(ThreadSerializer):
    replies = ReplySerializer(many=True, read_only=True)
    can_reply = serializers.BooleanField(read_only=True)
    can_moderate = serializers.BooleanField(read_only=True)

    class Meta(ThreadSerializer.Meta):
        fields = (*ThreadSerializer.Meta.fields, "replies", "can_reply", "can_moderate")
        read_only_fields = fields


class ThreadWriteSerializer(StrictSerializer):
    title = SafeCharField(max_length=200)
    body = serializers.CharField(max_length=20000)


class ReplyWriteSerializer(StrictSerializer):
    body = serializers.CharField(max_length=20000)


class ModerationSerializer(StrictSerializer):
    pinned = serializers.BooleanField(required=False)
    closed = serializers.BooleanField(required=False)


class HideSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=300)
