"""Branch shapes at the boundary."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import AcademicYear, Bank, Branch, College


class BranchSerializer(StrictModelSerializer):
    """One centre, as a screen reads it."""

    class Meta:
        model = Branch
        fields = ("id", "code", "name", "city", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class BranchWriteSerializer(StrictModelSerializer):
    """Creating or renaming a centre.

    ``is_active`` is absent on purpose: closing a centre changes what a whole
    set of accounts can see, and it belongs to
    :func:`apps.organisation.services.set_branch_active` rather than to a field
    somebody could flip while correcting a spelling.
    """

    code = SafeCharField(max_length=20)
    name = SafeCharField(max_length=120)
    city = SafeCharField(max_length=80, required=False, allow_blank=True)

    class Meta:
        model = Branch
        fields = ("code", "name", "city")


class CollegeSerializer(serializers.ModelSerializer):
    class Meta:
        model = College
        fields = ("id", "name", "city", "is_active")
        read_only_fields = ("id", "is_active")


class AddCollegeSerializer(StrictSerializer):
    """Adding a college from inside the flow that needed it.

    Strict, like every other serializer that parses client input: a request
    naming a field this never listed is refused rather than silently dropped,
    which is also how somebody finds out whether a field exists at all
    (`tests/test_erp_security_sweep.py`).
    """

    name = SafeCharField(max_length=200)
    city = SafeCharField(max_length=80, required=False, allow_blank=True, default="")


class AcademicYearSerializer(serializers.ModelSerializer):
    """A year, as every screen that files something under one reads it."""

    class Meta:
        model = AcademicYear
        fields = ("id", "name", "starts_on", "ends_on", "is_current", "is_closed")
        read_only_fields = fields


class AcademicYearWriteSerializer(StrictSerializer):
    """Adding or changing one. `is_current` is not here: moving it is its own
    act (exactly one year holds it) and has its own endpoint, so a careless
    PATCH cannot leave the institute with two current years or none."""

    name = SafeCharField(max_length=20)
    starts_on = serializers.DateField(required=False, allow_null=True)
    ends_on = serializers.DateField(required=False, allow_null=True)
    is_closed = serializers.BooleanField(required=False, default=False)


class AcademicYearPatchSerializer(StrictSerializer):
    """Changing one, including which year is current.

    `is_current` *is* here, unlike on the create form, because moving it is
    the common act on this screen — a switch per row — and the service makes
    it exclusive in the same transaction. Setting it to false is refused
    rather than leaving the institute with no current year: the way to move
    it is to set it on another year."""

    name = SafeCharField(max_length=20, required=False)
    starts_on = serializers.DateField(required=False, allow_null=True)
    ends_on = serializers.DateField(required=False, allow_null=True)
    is_closed = serializers.BooleanField(required=False)
    is_current = serializers.BooleanField(required=False)

    def validate_is_current(self, value: bool) -> bool:
        if value is False:
            raise serializers.ValidationError(
                "Make another year current instead; the institute always has one."
            )
        return value


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ("id", "name", "is_active")
        read_only_fields = fields


class BankWriteSerializer(StrictSerializer):
    name = SafeCharField(max_length=120)
    is_active = serializers.BooleanField(required=False, default=True)


class BankPatchSerializer(StrictSerializer):
    name = SafeCharField(max_length=120, required=False)
    is_active = serializers.BooleanField(required=False)
