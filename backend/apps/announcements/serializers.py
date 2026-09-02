"""Announcement serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Announcement, AnnouncementStatus, Audience


class AnnouncementSerializer(StrictModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    batch_code = serializers.CharField(source="batch.code", read_only=True, default=None)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True, default=None
    )
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Announcement
        fields = (
            "id",
            "title",
            "body",
            "audience",
            "course",
            "course_title",
            "batch",
            "batch_code",
            "is_pinned",
            "status",
            "published_at",
            "expires_at",
            "is_live",
            "created_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class StudentAnnouncementSerializer(AnnouncementSerializer):
    """A reader's view: who wrote it, not the editorial state."""

    class Meta(AnnouncementSerializer.Meta):
        fields = (
            "id",
            "title",
            "body",
            "course_title",
            "batch_code",
            "is_pinned",
            "published_at",
            "expires_at",
            "created_by_name",
        )
        read_only_fields = fields


class AnnouncementWriteSerializer(StrictSerializer):
    """Create and edit. ``status`` moves through publish and archive."""

    title = SafeCharField(max_length=200)
    body = serializers.CharField(max_length=20000)
    audience = serializers.ChoiceField(choices=Audience.choices, required=False)
    course = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    recipients = serializers.ListField(child=serializers.UUIDField(), required=False)
    is_pinned = serializers.BooleanField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


ANNOUNCEMENT_STATUS_CHOICES = list(AnnouncementStatus.choices)
