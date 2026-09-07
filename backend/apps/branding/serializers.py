"""Branding serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer

from .models import HEX_COLOR, BrandingSetting


class BrandingSerializer(serializers.ModelSerializer):
    """What every signed-in caller reads.

    Deliberately tiny. This is fetched on the first paint of every page, by
    everyone, so it carries what the interface needs to draw itself and nothing
    else — no timestamps, no editor, nothing that would make it a second way to
    learn who administers the system.
    """

    class Meta:
        model = BrandingSetting
        fields = ("brand_color", "display_name")
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Empty means "no choice made", and the interface reads that as "use the
        # built-in palette". `null` says that plainly; `""` makes every caller
        # write the same falsy check.
        data["brand_color"] = data["brand_color"] or None
        data["display_name"] = data["display_name"] or None
        return data


class BrandingUpdateSerializer(StrictModelSerializer):
    """What a superadmin may change."""

    brand_color = SafeCharField(
        max_length=7, required=False, allow_blank=True, validators=[HEX_COLOR]
    )
    display_name = SafeCharField(max_length=120, required=False, allow_blank=True)

    class Meta:
        model = BrandingSetting
        fields = ("brand_color", "display_name")
