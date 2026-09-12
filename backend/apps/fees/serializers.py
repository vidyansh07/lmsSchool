"""Fee serializers.

Money travels as the API's decimal strings ("12500.00"), never as floats, and
every derived figure — payable, paid, balance, status, overdue — is computed
by the model so that no screen ever does its own arithmetic.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import FeePayment, FeePlan, PaymentMethod

MONEY = {"max_digits": 10, "decimal_places": 2}


class FeePaymentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.SerializerMethodField()
    voided_by = serializers.SerializerMethodField()
    is_voided = serializers.BooleanField(read_only=True)

    class Meta:
        model = FeePayment
        fields = (
            "id",
            "receipt_number",
            "amount",
            "paid_on",
            "method",
            "reference",
            "note",
            "recorded_by",
            "created_at",
            "is_voided",
            "voided_at",
            "voided_by",
            "void_reason",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_recorded_by(self, obj: FeePayment) -> str | None:
        return obj.recorded_by.full_name or obj.recorded_by.email if obj.recorded_by else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_voided_by(self, obj: FeePayment) -> str | None:
        return obj.voided_by.full_name or obj.voided_by.email if obj.voided_by else None


class FeePlanSerializer(serializers.ModelSerializer):
    enrollment_id = serializers.UUIDField(source="enrollment.pk", read_only=True)
    enrollment_code = serializers.CharField(source="enrollment.code", read_only=True)
    course_title = serializers.CharField(source="enrollment.course.title", read_only=True)
    batch_code = serializers.CharField(source="enrollment.batch.code", read_only=True)
    batch_name = serializers.CharField(source="enrollment.batch.name", read_only=True)
    enrollment_status = serializers.CharField(source="enrollment.status", read_only=True)
    payable = serializers.DecimalField(read_only=True, **MONEY)
    paid = serializers.DecimalField(read_only=True, **MONEY)
    balance = serializers.DecimalField(read_only=True, **MONEY)
    status = serializers.CharField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    payments = FeePaymentSerializer(many=True, read_only=True)

    class Meta:
        model = FeePlan
        fields = (
            "id",
            "enrollment_id",
            "enrollment_code",
            "enrollment_status",
            "course_title",
            "batch_code",
            "batch_name",
            "agreed_amount",
            "discount_amount",
            "discount_reason",
            "payable",
            "paid",
            "balance",
            "status",
            "next_due_amount",
            "next_due_on",
            "is_overdue",
            "notes",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "payments",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_created_by(self, obj: FeePlan) -> str | None:
        return obj.created_by.full_name or obj.created_by.email if obj.created_by else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_updated_by(self, obj: FeePlan) -> str | None:
        return obj.updated_by.full_name or obj.updated_by.email if obj.updated_by else None


class FeePlanBriefSerializer(FeePlanSerializer):
    """A plan without its payments, for lists."""

    class Meta(FeePlanSerializer.Meta):
        fields = tuple(field for field in FeePlanSerializer.Meta.fields if field != "payments")
        read_only_fields = fields


class SetFeePlanSerializer(StrictSerializer):
    agreed_amount = serializers.DecimalField(min_value=0, **MONEY)
    discount_amount = serializers.DecimalField(min_value=0, required=False, default=0, **MONEY)
    discount_reason = SafeCharField(max_length=200, required=False, allow_blank=True, default="")
    notes = SafeCharField(max_length=1000, required=False, allow_blank=True)


class SetNextDueSerializer(StrictSerializer):
    next_due_amount = serializers.DecimalField(required=False, allow_null=True, **MONEY)
    next_due_on = serializers.DateField(required=False, allow_null=True)


class RecordPaymentSerializer(StrictSerializer):
    amount = serializers.DecimalField(min_value=0, **MONEY)
    paid_on = serializers.DateField(required=False)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    reference = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    note = SafeCharField(max_length=300, required=False, allow_blank=True, default="")


class VoidPaymentSerializer(StrictSerializer):
    reason = SafeCharField(max_length=300)


class FeeHistoryEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField()
    action_label = serializers.CharField()
    actor_label = serializers.CharField()
    created_at = serializers.DateTimeField()
    context = serializers.JSONField()


class StudentFeeSummarySerializer(serializers.Serializer):
    payable_total = serializers.DecimalField(**MONEY)
    paid_total = serializers.DecimalField(**MONEY)
    balance_total = serializers.DecimalField(**MONEY)
    next_due_amount = serializers.DecimalField(allow_null=True, **MONEY)
    next_due_on = serializers.DateField(allow_null=True)
    is_overdue = serializers.BooleanField()
    enrollments_without_plan = serializers.IntegerField()
    plans = FeePlanSerializer(many=True)


class FeesOverviewSerializer(serializers.Serializer):
    collected_today = serializers.DecimalField(**MONEY)
    collected_this_week = serializers.DecimalField(**MONEY)
    collected_this_month = serializers.DecimalField(**MONEY)
    outstanding_total = serializers.DecimalField(**MONEY)
    overdue_count = serializers.IntegerField()
    unpaid_count = serializers.IntegerField()
    enrollments_without_plan = serializers.IntegerField()
    overdue = serializers.ListField(child=serializers.DictField())
    due_soon = serializers.ListField(child=serializers.DictField())
