"""Notification serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import Notification, NotificationPreference


class NotificationSerializer(StrictModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "category",
            "title",
            "body",
            "link_path",
            "resource_type",
            "resource_id",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class UnreadCountSerializer(StrictSerializer):
    unread = serializers.IntegerField()


class PreferenceSerializer(StrictModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = (
            "email_academic",
            "email_schedule",
            "email_announcements",
            "email_administrative",
            "updated_at",
        )
        read_only_fields = fields


class PreferenceWriteSerializer(StrictSerializer):
    email_academic = serializers.BooleanField(required=False)
    email_schedule = serializers.BooleanField(required=False)
    email_announcements = serializers.BooleanField(required=False)
    email_administrative = serializers.BooleanField(required=False)
