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


class MessageRuleSerializer(serializers.Serializer):
    """One cell of the matrix."""

    event = serializers.CharField()
    recipient = serializers.CharField()
    channel = serializers.CharField()
    is_enabled = serializers.BooleanField()


class MessageMatrixSerializer(serializers.Serializer):
    """The whole screen in one answer: the tabs and their events in the order
    they are drawn, the recipients, the channels, and which cells are on.

    The *shape* is sent with the data on purpose. A screen that hardcodes the
    list of events drifts the moment one is added, and the first anybody
    knows is a row the settings page cannot turn off.
    """

    tabs = serializers.ListField(child=serializers.DictField())
    recipients = serializers.ListField(child=serializers.DictField())
    channels = serializers.ListField(child=serializers.DictField())
    rules = MessageRuleSerializer(many=True)


class SetMessageRulesSerializer(StrictSerializer):
    """Changing cells. Only the ones that moved are sent — the screen has
    thirty and a person changes one."""

    rules = MessageRuleSerializer(many=True)
