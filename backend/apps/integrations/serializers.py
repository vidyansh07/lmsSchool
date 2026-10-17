from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import ApiKey, IntakeStatus, LeadIntake, Preset, Webhook, WebhookDelivery


class ApiKeySerializer(serializers.ModelSerializer):
    display = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None
    )
    is_active = serializers.BooleanField(read_only=True)
    intake_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ApiKey
        fields = (
            "id",
            "name",
            "preset",
            "display",
            "branch",
            "branch_name",
            "default_source",
            "field_map",
            "is_active",
            "last_used_at",
            "revoked_at",
            "created_by_name",
            "created_at",
            "intake_count",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_display(self, obj: ApiKey) -> str:
        return f"grk_{obj.prefix}_…"


class ApiKeyCreatedSerializer(ApiKeySerializer):
    """The one response that carries the key itself."""

    key = serializers.CharField(read_only=True)

    class Meta(ApiKeySerializer.Meta):
        fields = (*ApiKeySerializer.Meta.fields, "key")
        read_only_fields = fields


class ApiKeyWriteSerializer(StrictSerializer):
    name = SafeCharField(max_length=80, required=False)
    preset = serializers.ChoiceField(choices=Preset.choices, required=False)
    branch = serializers.UUIDField(required=False, allow_null=True)
    default_source = SafeCharField(max_length=40, required=False)
    field_map = serializers.DictField(child=serializers.CharField(max_length=60), required=False)


class LeadIntakeSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=IntakeStatus.choices, read_only=True)
    enquiry_name = serializers.CharField(source="enquiry.full_name", read_only=True, default=None)

    class Meta:
        model = LeadIntake
        fields = (
            "id",
            "status",
            "enquiry",
            "enquiry_name",
            "external_id",
            "payload",
            "errors",
            "created_at",
        )
        read_only_fields = fields


class LeadResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=IntakeStatus.choices)
    enquiry_id = serializers.UUIDField(allow_null=True)
    errors = serializers.DictField(required=False)


class WebhookSerializer(serializers.ModelSerializer):
    has_secret = serializers.SerializerMethodField()
    last_delivery = serializers.SerializerMethodField()

    class Meta:
        model = Webhook
        fields = (
            "id",
            "name",
            "preset",
            "url",
            "header_names",
            "has_secret",
            "is_active",
            "created_at",
            "updated_at",
            "last_delivery",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_has_secret(self, obj: Webhook) -> bool:
        return bool(obj.secret_encrypted)

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_last_delivery(self, obj: Webhook) -> dict | None:
        row = obj.deliveries.order_by("-created_at").first()
        if row is None:
            return None
        return {"ok": row.ok, "status_code": row.status_code, "created_at": row.created_at}


class WebhookSavedSerializer(WebhookSerializer):
    """Carries the signing secret, only when it was just made."""

    secret = serializers.CharField(read_only=True, allow_blank=True)

    class Meta(WebhookSerializer.Meta):
        fields = (*WebhookSerializer.Meta.fields, "secret")
        read_only_fields = fields


class WebhookWriteSerializer(StrictSerializer):
    name = SafeCharField(max_length=80, required=False)
    preset = serializers.ChoiceField(choices=Preset.choices, required=False)
    url = serializers.URLField(max_length=500, required=False)
    # Sent: these are the headers now (values encrypted; an empty object clears them).
    headers = serializers.DictField(
        child=serializers.CharField(max_length=500, allow_blank=True), required=False
    )
    is_active = serializers.BooleanField(required=False)
    rotate_secret = serializers.BooleanField(required=False, default=False)


class WebhookDeliverySerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)

    class Meta:
        model = WebhookDelivery
        fields = (
            "id",
            "event",
            "rule",
            "rule_name",
            "ok",
            "status_code",
            "error",
            "response_excerpt",
            "duration_ms",
            "created_at",
        )
        read_only_fields = fields
