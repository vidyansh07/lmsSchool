"""Student serializers, scoped by who is calling.

Three write serializers exist deliberately:

* :class:`StudentCreateSerializer` — administrator creating a student
* :class:`AdminStudentUpdateSerializer` — administrator editing one
* :class:`StudentSelfUpdateSerializer` — a student editing their own record

Merging them into one class with conditional field stripping is exactly how a
student ends up able to set their own fee status.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import MIN_FEE_AMOUNT, FeeStatus, InstitutionKind, Qualification, StudentProfile

#: Fields an administrator may set or change. Identifiers, the linked account
#: and timestamps are absent: they are system-owned.
ADMIN_EDITABLE_FIELDS = (*StudentProfile.SELF_EDITABLE_FIELDS, "notes")


class StudentProfileSerializer(StrictModelSerializer):
    """Read representation for the student themselves.

    ``notes`` is absent: internal notes are administrator-only and must never
    reach the person they are about.
    """

    user = UserSerializer(read_only=True)
    completion_percent = serializers.IntegerField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            "student_id",
            "user",
            "date_of_birth",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "country",
            "postal_code",
            "qualification",
            "institution",
            "institution_kind",
            "graduation_year",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            "guardian_name",
            "guardian_phone",
            "fee_status",
            "fee_status_updated_at",
            "fee_amount",
            "fee_amount_updated_at",
            "completion_percent",
            "is_profile_complete",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AdminStudentProfileSerializer(StudentProfileSerializer):
    """Administrator read view: adds internal notes and fee attribution."""

    fee_status_updated_by = serializers.SerializerMethodField()
    fee_amount_updated_by = serializers.SerializerMethodField()

    class Meta(StudentProfileSerializer.Meta):
        fields = (
            *StudentProfileSerializer.Meta.fields,
            "notes",
            "fee_status_updated_by",
            "fee_amount_updated_by",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_fee_status_updated_by(self, obj: StudentProfile) -> str | None:
        return obj.fee_status_updated_by.email if obj.fee_status_updated_by else None

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_fee_amount_updated_by(self, obj: StudentProfile) -> str | None:
        return obj.fee_amount_updated_by.email if obj.fee_amount_updated_by else None


class StudentListSerializer(serializers.ModelSerializer):
    """Flattened row for the administrator table.

    Flat by design: a nested user object would push the table component into
    reshaping data, and the list endpoint is the one place where payload size
    across hundreds of rows actually matters.
    """

    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    is_email_verified = serializers.BooleanField(source="user.is_email_verified", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = StudentProfile
        fields = (
            "id",
            "student_id",
            "user_id",
            "email",
            "full_name",
            "city",
            "qualification",
            "fee_status",
            "fee_amount",
            "is_active",
            "is_email_verified",
            "created_at",
        )
        read_only_fields = fields


class StudentProfileFieldsSerializer(StrictModelSerializer):
    """Profile fields accepted when an administrator creates a student."""

    institution = SafeCharField(max_length=200, required=False, allow_blank=True)
    institution_kind = serializers.ChoiceField(
        choices=InstitutionKind.choices, required=False, allow_blank=True
    )
    qualification = serializers.ChoiceField(
        choices=Qualification.choices, required=False, allow_blank=True
    )

    class Meta:
        model = StudentProfile
        fields = ADMIN_EDITABLE_FIELDS


class StudentCreateSerializer(StrictSerializer):
    """Administrator creating a student account and profile together."""

    email = serializers.EmailField(max_length=254)
    first_name = SafeCharField(max_length=100)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    phone = SafeCharField(max_length=20, required=False, allow_blank=True, default="")
    profile = StudentProfileFieldsSerializer(required=False)
    # Top-level, not inside ``profile``: that sub-object is the self-editable
    # set plus notes, and the fee is neither. Keeping it out of that list is
    # what stops it becoming self-editable by accident when the list grows.
    fee_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=MIN_FEE_AMOUNT,
        required=False,
        allow_null=True,
    )

    def validate_email(self, value: str) -> str:
        from apps.accounts.models import User

        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalised


class FeeAmountUpdateSerializer(StrictSerializer):
    """Set or clear the agreed fee. ``null`` means "not decided", never zero."""

    fee_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=MIN_FEE_AMOUNT, allow_null=True
    )
    note = SafeCharField(max_length=500, required=False, allow_blank=True, default="")


class StudentSelfUpdateSerializer(StrictModelSerializer):
    """What a student may change about their own profile.

    Absent on purpose: ``student_id``, ``fee_status``, ``notes``, ``user`` and
    every timestamp. Unknown fields are rejected, so sending ``fee_status``
    returns 400 naming the field.
    """

    institution = SafeCharField(max_length=200, required=False, allow_blank=True)
    institution_kind = serializers.ChoiceField(
        choices=InstitutionKind.choices, required=False, allow_blank=True
    )

    class Meta:
        model = StudentProfile
        fields = StudentProfile.SELF_EDITABLE_FIELDS


class AdminStudentUpdateSerializer(StrictModelSerializer):
    """What an administrator may change. Fee status has its own endpoint."""

    institution = SafeCharField(max_length=200, required=False, allow_blank=True)
    institution_kind = serializers.ChoiceField(
        choices=InstitutionKind.choices, required=False, allow_blank=True
    )

    class Meta:
        model = StudentProfile
        fields = ADMIN_EDITABLE_FIELDS


class FeeStatusUpdateSerializer(StrictSerializer):
    """Fee status change. Separate endpoint so it is separately authorised."""

    fee_status = serializers.ChoiceField(choices=FeeStatus.choices)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")
