"""Fee serializers.

Money travels as the API's decimal strings ("12500.00"), never as floats, and
every derived figure — payable, paid, balance, status, overdue — is computed
by the model so that no screen ever does its own arithmetic.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import (
    MAX_INSTALLMENTS,
    FeePayment,
    FeePlan,
    InstallmentStatus,
    PaymentKind,
    PaymentMethod,
    installment_rows,
)

MONEY = {"max_digits": 10, "decimal_places": 2}


class FeePaymentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.SerializerMethodField()
    voided_by = serializers.SerializerMethodField()
    refunded_by = serializers.SerializerMethodField()
    is_voided = serializers.BooleanField(read_only=True)
    is_refunded = serializers.BooleanField(read_only=True)

    class Meta:
        model = FeePayment
        fields = (
            "id",
            "receipt_number",
            "amount",
            "paid_on",
            "method",
            "reference",
            "reference_name",
            "note",
            "recorded_by",
            "created_at",
            "is_voided",
            "voided_at",
            "voided_by",
            "void_reason",
            "kind",
            "is_refundable",
            "is_refunded",
            "refunded_at",
            "refunded_by",
            "refund_reason",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_recorded_by(self, obj: FeePayment) -> str | None:
        return obj.recorded_by.full_name or obj.recorded_by.email if obj.recorded_by else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_voided_by(self, obj: FeePayment) -> str | None:
        return obj.voided_by.full_name or obj.voided_by.email if obj.voided_by else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_refunded_by(self, obj: FeePayment) -> str | None:
        return obj.refunded_by.full_name or obj.refunded_by.email if obj.refunded_by else None


class FeeInstallmentSerializer(serializers.Serializer):
    """One row of a schedule, with its derived state."""

    id = serializers.UUIDField(read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    amount = serializers.DecimalField(read_only=True, **MONEY)
    due_on = serializers.DateField(read_only=True)
    paid_amount = serializers.DecimalField(read_only=True, **MONEY)
    balance = serializers.DecimalField(read_only=True, **MONEY)
    status = serializers.ChoiceField(choices=InstallmentStatus.choices, read_only=True)


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
    installments = serializers.SerializerMethodField()

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
            "discount_percent",
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
            "installments",
            "payments",
        )
        read_only_fields = fields

    @extend_schema_field(FeeInstallmentSerializer(many=True))
    def get_installments(self, obj: FeePlan) -> list[dict]:
        return FeeInstallmentSerializer(installment_rows(obj), many=True).data

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


class InstallmentInputSerializer(StrictSerializer):
    amount = serializers.DecimalField(min_value=0, **MONEY)
    due_on = serializers.DateField()


class SetInstallmentsSerializer(StrictSerializer):
    """The schedule, as the counsellor shaped it. Empty means ad hoc."""

    installments = InstallmentInputSerializer(many=True, max_length=MAX_INSTALLMENTS)


class SetFeePlanSerializer(StrictSerializer):
    agreed_amount = serializers.DecimalField(min_value=0, **MONEY)
    discount_amount = serializers.DecimalField(min_value=0, required=False, default=0, **MONEY)
    # Sent instead of `discount_amount` when the discount was agreed as a
    # percentage. No default: left out means "no percentage was offered", which
    # is a different answer from zero.
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )
    discount_reason = SafeCharField(max_length=200, required=False, allow_blank=True, default="")
    notes = SafeCharField(max_length=1000, required=False, allow_blank=True)
    # Left out: a new fee gets the default schedule, an existing one keeps its
    # dates. Sent (even empty): this is the schedule.
    installments = InstallmentInputSerializer(
        many=True, required=False, max_length=MAX_INSTALLMENTS
    )
    installment_count = serializers.IntegerField(
        required=False, min_value=0, max_value=MAX_INSTALLMENTS
    )


class SetNextDueSerializer(StrictSerializer):
    next_due_amount = serializers.DecimalField(required=False, allow_null=True, **MONEY)
    next_due_on = serializers.DateField(required=False, allow_null=True)


class RecordPaymentSerializer(StrictSerializer):
    amount = serializers.DecimalField(min_value=0, **MONEY)
    paid_on = serializers.DateField(required=False)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    reference = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    reference_name = SafeCharField(max_length=120, required=False, allow_blank=True, default="")
    note = SafeCharField(max_length=300, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=PaymentKind.choices, default=PaymentKind.INSTALMENT)
    is_refundable = serializers.BooleanField(default=False)


class VoidPaymentSerializer(StrictSerializer):
    reason = SafeCharField(max_length=300)


class RefundPaymentSerializer(StrictSerializer):
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


class FeeCollectionsTrendPointSerializer(serializers.Serializer):
    """One week's takings. `amount` is money, so it stays a decimal all the
    way to the client rather than becoming a float on the way."""

    week = serializers.DateField()
    amount = serializers.DecimalField(**MONEY)
    receipts = serializers.IntegerField()


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
