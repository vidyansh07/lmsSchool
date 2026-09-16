"""Form builder API shapes (ERP Phase 8)."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import FormDefinition, FormEntity, FormField, FormFieldType, FormVersion


class FormFieldSerializer(StrictModelSerializer):
    class Meta:
        model = FormField
        fields = (
            "id",
            "key",
            "label",
            "help",
            "type",
            "required",
            "order",
            "group",
            "options",
            "validation",
            "visible_to_student",
            "performance_key",
        )
        read_only_fields = ("id",)


class FormFieldWriteSerializer(StrictSerializer):
    key = SafeCharField(max_length=60)
    label = SafeCharField(max_length=150)
    help = SafeCharField(max_length=500, required=False, allow_blank=True, default="")
    type = serializers.ChoiceField(choices=FormFieldType.choices)
    required = serializers.BooleanField(default=False)
    order = serializers.IntegerField(default=0)
    group = SafeCharField(max_length=60, required=False, allow_blank=True, default="")
    options = serializers.JSONField(default=list)
    validation = serializers.JSONField(default=dict)
    visible_to_student = serializers.BooleanField(default=False)
    performance_key = SafeCharField(max_length=30, required=False, allow_blank=True, default="")


class FormFieldsWriteSerializer(StrictSerializer):
    fields = FormFieldWriteSerializer(many=True)


class FormVersionSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    number = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    schema_hash = serializers.CharField(read_only=True)
    field_count = serializers.SerializerMethodField()

    def get_field_count(self, version: FormVersion) -> int:
        count = getattr(version, "field_count", None)
        return count if count is not None else version.fields.count()


class FormVersionDetailSerializer(FormVersionSummarySerializer):
    definition_slug = serializers.CharField(source="definition.slug", read_only=True)
    cloned_from = serializers.IntegerField(
        source="cloned_from.number", read_only=True, allow_null=True
    )
    published_at = serializers.DateTimeField(read_only=True, allow_null=True)
    published_by_name = serializers.CharField(
        source="published_by.get_full_name", read_only=True, default=None
    )
    fields = FormFieldSerializer(many=True, read_only=True)


def _version_summary(version: FormVersion | None) -> dict | None:
    if version is None:
        return None
    return FormVersionSummarySerializer(version).data


class FormDefinitionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    entity = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    published_version = serializers.SerializerMethodField()
    draft_version = serializers.SerializerMethodField()

    def get_published_version(self, definition: FormDefinition) -> dict | None:
        versions = getattr(definition, "_prefetched_versions", None)
        if versions is not None:
            found = next((v for v in versions if v.status == "published"), None)
        else:
            found = definition.versions.filter(status="published").first()
        return _version_summary(found)

    def get_draft_version(self, definition: FormDefinition) -> dict | None:
        versions = getattr(definition, "_prefetched_versions", None)
        if versions is not None:
            found = next((v for v in versions if v.status == "draft"), None)
        else:
            found = definition.versions.filter(status="draft").first()
        return _version_summary(found)


class FormDefinitionDetailSerializer(FormDefinitionSerializer):
    versions = serializers.SerializerMethodField()

    def get_versions(self, definition: FormDefinition) -> list[dict]:
        versions = getattr(definition, "_prefetched_versions", None)
        if versions is None:
            versions = list(definition.versions.order_by("-number"))
        return FormVersionSummarySerializer(versions, many=True).data


class FormDefinitionCreateSerializer(StrictSerializer):
    slug = SafeCharField(max_length=60)
    name = SafeCharField(max_length=150)
    entity = serializers.ChoiceField(choices=FormEntity.choices)


class FormVersionCreateSerializer(StrictSerializer):
    cloned_from = serializers.IntegerField(required=False, allow_null=True, default=None)


class FormPreviewSerializer(StrictSerializer):
    values = serializers.JSONField(default=dict)


__all__ = [
    "FormDefinitionCreateSerializer",
    "FormDefinitionDetailSerializer",
    "FormDefinitionSerializer",
    "FormFieldSerializer",
    "FormFieldWriteSerializer",
    "FormFieldsWriteSerializer",
    "FormPreviewSerializer",
    "FormVersionCreateSerializer",
    "FormVersionDetailSerializer",
    "FormVersionSummarySerializer",
]
