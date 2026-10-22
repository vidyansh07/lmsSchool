"""Branch shapes at the boundary."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Branch, College


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
