"""Serializers for the automation builder (ERP Phase 14, ADR-13).

Structural validation of ``conditions``/``actions`` (allowed operators,
allowed paths per trigger, known action types) and the save-time permission
check both live in ``services.py`` — not here — the same split the rest of
this codebase draws between "what shape can this field hold" and "what
value is actually allowed right now".
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import AutomationRule, AutomationRun


class AutomationRuleSerializer(StrictModelSerializer):
    branch = serializers.UUIDField(source="branch_id", read_only=True, allow_null=True)
    created_by = serializers.UUIDField(source="created_by_id", read_only=True, allow_null=True)
    updated_by = serializers.UUIDField(source="updated_by_id", read_only=True, allow_null=True)
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AutomationRule
        fields = (
            "id",
            "name",
            "description",
            "trigger",
            "conditions",
            "actions",
            "status",
            "version",
            "branch",
            "is_system",
            "created_by",
            "updated_by",
            "created_by_name",
            "updated_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_created_by_name(self, rule: AutomationRule) -> str:
        return self._who(rule.created_by, rule.is_system)

    @extend_schema_field(serializers.CharField())
    def get_updated_by_name(self, rule: AutomationRule) -> str:
        return self._who(rule.updated_by, rule.is_system)

    @staticmethod
    def _who(user, is_system: bool) -> str:
        """The name, never the address. A seeded rule says it was seeded
        rather than naming whoever ran the migration."""
        if user is not None:
            return user.get_full_name() or user.email.split("@")[0]
        return "Seeded with the catalog" if is_system else ""


class AutomationRuleSummarySerializer(serializers.Serializer):
    """How many rules sit in each status, for the cards above the list.

    Counted on the server rather than from the page in front of the person:
    a count worked out from twenty visible rows is wrong the moment there
    are twenty-one.
    """

    total = serializers.IntegerField(read_only=True)
    active = serializers.IntegerField(read_only=True)
    draft = serializers.IntegerField(read_only=True)
    paused = serializers.IntegerField(read_only=True)


class AutomationRuleWriteSerializer(StrictSerializer):
    """``PATCH``: every field is optional — ``services.update_rule`` only
    touches whatever key actually made it into ``validated_data``."""

    name = SafeCharField(max_length=150, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    trigger = serializers.CharField(required=False)
    conditions = serializers.ListField(child=serializers.DictField(), required=False)
    actions = serializers.ListField(child=serializers.DictField(), required=False)
    branch = serializers.UUIDField(required=False, allow_null=True)


class AutomationRuleCreateSerializer(AutomationRuleWriteSerializer):
    """``POST``: ``name`` and ``trigger`` are the two fields a rule cannot
    exist without."""

    name = SafeCharField(max_length=150)
    trigger = serializers.CharField()
    status = serializers.CharField(required=False)


class DeleteReasonSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255)


class PauseReasonSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class AutomationRunSerializer(StrictModelSerializer):
    rule = serializers.UUIDField(source="rule_id", read_only=True)
    object_id = serializers.CharField(read_only=True)

    class Meta:
        model = AutomationRun
        fields = (
            "id",
            "rule",
            "trigger",
            "object_id",
            "occurrence_key",
            "depth",
            "status",
            "result",
            "error",
            "rule_version",
            "created_at",
        )
        read_only_fields = fields


class DryRunResultSerializer(StrictSerializer):
    object_id = serializers.CharField()
    would_fire = serializers.BooleanField()
    context = serializers.DictField()
