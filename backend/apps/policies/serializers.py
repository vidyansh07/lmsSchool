"""Policy API shapes (ERP Phase 3).

Read shapes describe *resolved* values — value in force, its default,
whether the row is a real override or the default answer — the same reason
`configuration.serializers.SystemSettingSerializer` is a plain serializer
rather than a model one: the question is "what applies", not "what is in
the row".
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import PolicyVersion


class PolicyEntrySerializer(serializers.Serializer):
    category = serializers.CharField(read_only=True)
    key = serializers.CharField(read_only=True)
    value = serializers.JSONField(read_only=True)
    default = serializers.JSONField(read_only=True)
    is_default = serializers.BooleanField(read_only=True)
    scope = serializers.CharField(read_only=True)
    branch = serializers.UUIDField(read_only=True, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    critical = serializers.BooleanField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    updated_by_name = serializers.CharField(read_only=True, allow_null=True)


class PolicyWriteSerializer(StrictSerializer):
    value = serializers.JSONField()
    branch = serializers.UUIDField(required=False, allow_null=True, default=None)
    reason = SafeCharField(max_length=300)
    confirm = SafeCharField(
        max_length=60, required=False, allow_blank=True, allow_null=True, default=None
    )


class PolicyVersionSerializer(StrictModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = PolicyVersion
        fields = ("id", "version", "value", "changed_by_name", "reason", "created_at")
        read_only_fields = fields


__all__ = ["PolicyEntrySerializer", "PolicyVersionSerializer", "PolicyWriteSerializer"]
