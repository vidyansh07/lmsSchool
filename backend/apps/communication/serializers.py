"""Communication centre serializers (ERP Phase 19)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Delivery, MessageChannel, MessageTemplate, TemplateVersion


class TemplateVersionSerializer(StrictModelSerializer):
    class Meta:
        model = TemplateVersion
        fields = (
            "id",
            "template",
            "number",
            "subject",
            "body_html",
            "body_text",
            "variables",
            "provider_template_id",
            "approved_by",
            "approved_at",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MessageTemplateSerializer(StrictModelSerializer):
    current_version = TemplateVersionSerializer(read_only=True)
    draft_version = serializers.SerializerMethodField()

    class Meta:
        model = MessageTemplate
        fields = (
            "id",
            "key",
            "name",
            "channel",
            "kind",
            "language",
            "status",
            "current_version",
            "draft_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(TemplateVersionSerializer(allow_null=True))
    def get_draft_version(self, template: MessageTemplate):
        draft = template.versions.filter(published_at__isnull=True).order_by("-number").first()
        return TemplateVersionSerializer(draft).data if draft else None


class TemplateCreateSerializer(StrictSerializer):
    key = SafeCharField(max_length=60)
    name = SafeCharField(max_length=200)
    channel = serializers.ChoiceField(choices=MessageChannel.choices)
    kind = SafeCharField(max_length=60)
    language = SafeCharField(max_length=8, required=False)


class TemplateVersionWriteSerializer(StrictSerializer):
    """`POST .../versions/` (body ignored — a draft clones the published
    content) and `PUT .../versions/{n}/` (every field optional; only what is
    sent is changed)."""

    subject = serializers.CharField(max_length=255, required=False, allow_blank=True)
    body_html = serializers.CharField(required=False, allow_blank=True)
    body_text = serializers.CharField(required=False, allow_blank=True)
    variables = serializers.ListField(child=serializers.CharField(max_length=200), required=False)
    provider_template_id = serializers.CharField(max_length=120, required=False, allow_blank=True)


class TemplateRenderRequestSerializer(StrictSerializer):
    variables = serializers.JSONField(required=False)

    def validate_variables(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("variables must be an object.")
        return value


class RenderResultSerializer(StrictSerializer):
    subject = serializers.CharField()
    html = serializers.CharField()
    text = serializers.CharField()
    warnings = serializers.ListField(child=serializers.CharField())


class DeliverySerializer(StrictModelSerializer):
    recipient_name = serializers.CharField(
        source="recipient.get_full_name", read_only=True, default=None
    )
    template_key = serializers.CharField(
        source="template_version.template.key", read_only=True, default=None
    )
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Delivery
        fields = (
            "id",
            "channel",
            "recipient",
            "recipient_name",
            "address",
            "template_version",
            "template_key",
            "variables",
            "state",
            "attempts",
            "next_attempt_at",
            "provider_message_id",
            "error",
            "requested_by",
            "requested_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ManualSendRecipientsSerializer(StrictSerializer):
    students = serializers.ListField(child=serializers.UUIDField(), required=False)
    batch = serializers.UUIDField(required=False)
    role = serializers.CharField(required=False)


class ManualSendSerializer(StrictSerializer):
    channel = serializers.ChoiceField(choices=MessageChannel.choices)
    template = serializers.CharField(max_length=60)
    recipients = ManualSendRecipientsSerializer()
    variables = serializers.JSONField(required=False)
    confirm_count = serializers.IntegerField(min_value=0)

    def validate_variables(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("variables must be an object.")
        return value
