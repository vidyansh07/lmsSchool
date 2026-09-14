"""Branch shapes at the boundary."""

from __future__ import annotations

from apps.common.serializers import SafeCharField, StrictModelSerializer

from .models import Branch


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
