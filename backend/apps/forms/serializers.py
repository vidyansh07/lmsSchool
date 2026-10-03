"""Form builder API shapes (ERP Phase 8)."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import (
    FormAssignment,
    FormAssignmentStatus,
    FormDefinition,
    FormEntity,
    FormField,
    FormFieldType,
    FormVersion,
)


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
            "show_if",
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
    show_if = serializers.JSONField(required=False, default=dict)


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


def _person(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "name": user.get_full_name() or user.email, "role": user.role}


class FormUploadSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    filename = serializers.CharField(source="original_name", read_only=True)
    content_type = serializers.CharField(read_only=True)
    size_bytes = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class FormAssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    form = serializers.SerializerMethodField()
    version = serializers.IntegerField(source="version.number", read_only=True)
    title = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    assigned_to = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    student = serializers.SerializerMethodField()
    enquiry = serializers.SerializerMethodField()
    due_at = serializers.DateTimeField(read_only=True, allow_null=True)
    submitted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    cancelled_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    is_overdue = serializers.SerializerMethodField()
    from_automation = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    def get_form(self, assignment: FormAssignment) -> dict:
        return {
            "slug": assignment.definition.slug,
            "name": assignment.definition.name,
            "entity": assignment.definition.entity,
        }

    def get_assigned_to(self, assignment: FormAssignment) -> dict | None:
        return _person(assignment.assigned_to)

    def get_requested_by(self, assignment: FormAssignment) -> dict | None:
        return _person(assignment.requested_by)

    def get_enquiry(self, assignment: FormAssignment) -> dict | None:
        enquiry = assignment.enquiry
        if enquiry is None:
            return None
        return {"id": str(enquiry.pk), "name": enquiry.full_name, "stage": enquiry.stage}

    def get_student(self, assignment: FormAssignment) -> dict | None:
        student = assignment.student
        if student is None:
            return None
        name = student.user.get_full_name() if student.user_id else ""
        return {"id": str(student.pk), "name": name}

    def get_is_overdue(self, assignment: FormAssignment) -> bool:
        return bool(
            assignment.status == FormAssignmentStatus.PENDING
            and assignment.due_at is not None
            and assignment.due_at < timezone.now()
        )

    def get_from_automation(self, assignment: FormAssignment) -> bool:
        return assignment.automation_run_id is not None

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_can_submit(self, assignment: FormAssignment) -> bool:
        user = self._user()
        return bool(
            user is not None
            and assignment.status == FormAssignmentStatus.PENDING
            and assignment.assigned_to_id == user.pk
        )

    def get_can_cancel(self, assignment: FormAssignment) -> bool:
        from .access import can_cancel_assignment

        user = self._user()
        return bool(
            user is not None
            and assignment.status == FormAssignmentStatus.PENDING
            and can_cancel_assignment(user, assignment)
        )


class FormAssignmentDetailSerializer(FormAssignmentSerializer):
    # `method_name` because `get_fields` is DRF's own Serializer method.
    fields = serializers.SerializerMethodField(method_name="get_version_fields")
    values = serializers.SerializerMethodField()

    def get_version_fields(self, assignment: FormAssignment) -> list[dict]:
        return FormFieldSerializer(assignment.version.fields.order_by("order"), many=True).data

    def get_values(self, assignment: FormAssignment) -> dict | None:
        return assignment.response.values if assignment.response_id else None


class FormAssignmentCreateSerializer(StrictSerializer):
    form = SafeCharField(max_length=60)
    assigned_to = serializers.UUIDField()
    student = serializers.UUIDField(required=False, allow_null=True, default=None)
    enquiry = serializers.UUIDField(required=False, allow_null=True, default=None)
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    title = SafeCharField(max_length=200, required=False, allow_blank=True, default="")
    message = SafeCharField(max_length=2000, required=False, allow_blank=True, default="")


class FormValuesSerializer(StrictSerializer):
    values = serializers.JSONField(default=dict)


class FormFillSerializer(StrictSerializer):
    values = serializers.JSONField(default=dict)
    student = serializers.UUIDField(required=False, allow_null=True, default=None)


class FormAssignmentCancelSerializer(StrictSerializer):
    reason = SafeCharField(max_length=500, required=False, allow_blank=True, default="")


__all__ = [
    "FormAssignmentCancelSerializer",
    "FormAssignmentCreateSerializer",
    "FormAssignmentDetailSerializer",
    "FormAssignmentSerializer",
    "FormDefinitionCreateSerializer",
    "FormDefinitionDetailSerializer",
    "FormDefinitionSerializer",
    "FormFieldSerializer",
    "FormFieldWriteSerializer",
    "FormFieldsWriteSerializer",
    "FormFillSerializer",
    "FormPreviewSerializer",
    "FormUploadSerializer",
    "FormValuesSerializer",
    "FormVersionCreateSerializer",
    "FormVersionDetailSerializer",
    "FormVersionSummarySerializer",
]
