"""Admission API shapes."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import Admission, AdmissionLine, DiscountKind, LineKind

MONEY = {"max_digits": 10, "decimal_places": 2}


class AdmissionMoneySerializer(serializers.Serializer):
    """The five figures the admission list shows. `uncleared` is part of
    `paid`, not beside it — see `Admission.money`."""

    total = serializers.DecimalField(read_only=True, **MONEY)
    paid = serializers.DecimalField(read_only=True, **MONEY)
    uncleared = serializers.DecimalField(read_only=True, **MONEY)
    refund = serializers.DecimalField(read_only=True, **MONEY)
    balance = serializers.DecimalField(read_only=True, **MONEY)


class AdmissionLineSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    name = serializers.CharField(read_only=True)
    line_total = serializers.DecimalField(read_only=True, **MONEY)

    class Meta:
        model = AdmissionLine
        fields = (
            "id",
            "kind",
            "course_id",
            "course_title",
            "label",
            "name",
            "charged_on_id",
            "quantity",
            "unit_fee",
            "line_total",
            "discount_share",
            "enrollment_id",
        )
        read_only_fields = fields


class AdmissionSerializer(serializers.ModelSerializer):
    """One admission, as every screen reads it."""

    student_id = serializers.UUIDField(source="student.pk", read_only=True)
    student_name = serializers.SerializerMethodField()
    academic_year = serializers.CharField(source="academic_year.name", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    created_by = serializers.SerializerMethodField()
    lines = AdmissionLineSerializer(many=True, read_only=True)
    gross_total = serializers.DecimalField(read_only=True, **MONEY)
    total_fees = serializers.DecimalField(read_only=True, **MONEY)
    is_cancelled = serializers.BooleanField(read_only=True)
    #: Total / Paid / Uncleared / Refund / Balance, read from the fee ledger.
    money = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = (
            "id",
            "student_id",
            "student_name",
            "branch_id",
            "branch_name",
            "academic_year_id",
            "academic_year",
            "admission_date",
            "status",
            "is_cancelled",
            "discount_kind",
            "discount_amount",
            "discount_percent",
            "gross_total",
            "total_fees",
            "note",
            "money",
            "lines",
            "created_by",
            "cancelled_at",
            "cancellation_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(AdmissionMoneySerializer)
    def get_money(self, admission: Admission) -> dict:
        return {key: str(value) for key, value in admission.money().items()}

    def get_student_name(self, admission: Admission) -> str:
        user = admission.student.user if admission.student_id else None
        return (user.get_full_name() or user.email) if user is not None else ""

    def get_created_by(self, admission: Admission) -> str | None:
        author = admission.created_by
        if author is None:
            return None
        return author.get_full_name() or author.email


class AdmissionLineWriteSerializer(StrictSerializer):
    """One row of the Course Information table.

    `charged_on` is the *index* of the course line an additional fee is
    charged with — a position in this same list, not an id, because the lines
    it refers to do not exist yet when the form is submitted.
    """

    kind = serializers.ChoiceField(
        choices=LineKind.choices, required=False, default=LineKind.COURSE
    )
    course = serializers.UUIDField(required=False, allow_null=True)
    label = SafeCharField(max_length=120, required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, max_value=99, required=False, default=1)
    unit_fee = serializers.DecimalField(min_value=0, required=False, default=0, **MONEY)
    charged_on = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class AdmissionWriteSerializer(StrictSerializer):
    """Recording one. The centre is not a field: it comes from the student."""

    student = serializers.UUIDField()
    academic_year = serializers.UUIDField(required=False, allow_null=True)
    admission_date = serializers.DateField(required=False)
    discount_kind = serializers.ChoiceField(
        choices=DiscountKind.choices, required=False, default=DiscountKind.FLAT
    )
    discount_value = serializers.DecimalField(min_value=0, required=False, default=0, **MONEY)
    note = SafeCharField(max_length=2000, required=False, allow_blank=True, default="")
    lines = AdmissionLineWriteSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("An admission needs at least one course.")
        return value


class AdmissionCancelSerializer(StrictSerializer):
    """Ending one. The refund, when there is one, is recorded by the fee
    ledger's own refund flow — this says why the admission ended.

    Named `AdmissionCancel…` rather than `CancelAdmission…` because
    `apps.fees` already has a `CancelAdmissionSerializer` that means
    something else (settling one enrolment's money), and two schema
    components with one name produce a generated client where one of them
    silently wins.
    """

    reason = SafeCharField(max_length=300)
