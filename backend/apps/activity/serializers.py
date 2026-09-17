from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import UserRole
from apps.common.serializers import StrictSerializer

from .services import KIND_LABELS


class FeedQuerySerializer(StrictSerializer):
    since = serializers.DateField(required=False)
    until = serializers.DateField(required=False)
    actor = serializers.UUIDField(required=False)
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)
    kind = serializers.ChoiceField(choices=list(KIND_LABELS.keys()), required=False)
    branch = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate(self, attrs):
        since, until = attrs.get("since"), attrs.get("until")
        if since and until and since > until:
            raise serializers.ValidationError(
                {"until": ["The end of the range is before its start."]}
            )
        return attrs


class FeedEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    action = serializers.CharField()
    action_label = serializers.CharField()
    kind = serializers.CharField()
    actor_id = serializers.UUIDField(allow_null=True)
    actor_label = serializers.CharField()
    actor_role = serializers.CharField(allow_null=True)
    actor_branch = serializers.CharField(allow_null=True)
    resource_type = serializers.CharField()
    resource_id = serializers.CharField()
    summary = serializers.CharField()
    href = serializers.CharField(allow_null=True)
    context = serializers.JSONField()


class ScorecardQuerySerializer(StrictSerializer):
    period = serializers.ChoiceField(choices=["today", "week", "month", "custom"], default="today")
    since = serializers.DateField(required=False)
    until = serializers.DateField(required=False)
    branch = serializers.UUIDField(required=False)
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)

    def validate(self, attrs):
        if attrs["period"] == "custom":
            if not attrs.get("since") or not attrs.get("until"):
                raise serializers.ValidationError({"since": ["A custom period needs both dates."]})
            if attrs["since"] > attrs["until"]:
                raise serializers.ValidationError(
                    {"until": ["The end of the range is before its start."]}
                )
        return attrs


class FigureSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()


class ScorecardSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    branch_name = serializers.CharField(allow_null=True)
    total_actions = serializers.IntegerField()
    fees_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_active_at = serializers.DateTimeField(allow_null=True)
    figures = FigureSerializer(many=True)


class ScorecardsResponseSerializer(serializers.Serializer):
    since = serializers.DateField()
    until = serializers.DateField()
    cards = ScorecardSerializer(many=True)
