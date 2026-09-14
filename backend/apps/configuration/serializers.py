"""Institution settings at the boundary.

Two audiences, two classes. What an operator reads and writes is every setting;
what everybody else reads is the institution's name and how to contact it, and
that is a *separate serializer* rather than a filtered response — a field a
caller must not see is absent from their shape, so a setting added to the model
later cannot leak by being added to one list and forgotten in another.

Both read shapes describe *resolved* values rather than a stored row, which is
why neither is a model serializer.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer


class SystemSettingSerializer(serializers.Serializer):
    """The settings actually in force, as the administrator's form shows them.

    A read-only output shape rather than a model serializer, because the
    question this answers is not "what is in the row" but "what is in force".
    They differ on a fresh install, which has no row at all, and on any column
    an operator has cleared, which falls back to the code default. Serving the
    row itself put an empty institution name in the form while every outbound
    email and the profile card said "Grras Solutions" — two screens disagreeing
    about the same string, from a difference the operator has no way to see.

    The last two fields are provenance rather than settings, and both are null
    until somebody has saved the form once.
    """

    institution_name = serializers.CharField(read_only=True)
    support_email = serializers.CharField(read_only=True, allow_blank=True)
    support_phone = serializers.CharField(read_only=True, allow_blank=True)
    notification_email_enabled = serializers.BooleanField(read_only=True)
    export_retention_days = serializers.IntegerField(read_only=True)
    resource_upload_max_mb = serializers.IntegerField(read_only=True)
    updated_by_name = serializers.CharField(read_only=True, allow_null=True)
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)


class SystemSettingWriteSerializer(StrictSerializer):
    """A partial change. Every field is optional; the caller sends what moved.

    The two numeric ranges are declared here as well as in the model's
    ``clean()`` so the refusal names the field at the edge, where a form can
    put the message under the input the operator typed into.
    """

    institution_name = SafeCharField(max_length=160, required=False, allow_blank=True)
    support_email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    support_phone = SafeCharField(max_length=32, required=False, allow_blank=True)
    notification_email_enabled = serializers.BooleanField(required=False)
    export_retention_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    resource_upload_max_mb = serializers.IntegerField(min_value=1, max_value=100, required=False)


class PublicSettingsSerializer(StrictSerializer):
    """What anybody signed in may read: who the institution is, and where to write.

    Nothing operational. A student reading their own product's name and its
    support address is not a disclosure; the retention window and the upload
    ceiling are decisions about how the institution runs, and they stay behind
    ``settings.manage``.
    """

    institution_name = serializers.CharField()
    support_email = serializers.CharField(allow_blank=True)
    support_phone = serializers.CharField(allow_blank=True)
