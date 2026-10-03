"""Enquiry API shapes."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer

from .models import Enquiry, EnquiryStage


def _person(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "name": user.get_full_name() or user.email}


class EnquirySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    mobile = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    whatsapp_number = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    course = serializers.CharField(read_only=True)
    track = serializers.CharField(read_only=True)
    preferred_centre = serializers.CharField(read_only=True)
    mode = serializers.CharField(read_only=True)
    batch_timing = serializers.CharField(read_only=True)
    qualification = serializers.CharField(read_only=True)
    source = serializers.CharField(read_only=True)
    utm_source = serializers.CharField(read_only=True)
    utm_medium = serializers.CharField(read_only=True)
    utm_campaign = serializers.CharField(read_only=True)
    remarks = serializers.CharField(read_only=True)
    stage = serializers.CharField(read_only=True)
    stage_changed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    lost_reason = serializers.CharField(read_only=True)
    lead_quality = serializers.IntegerField(read_only=True, allow_null=True)
    next_follow_up_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_contacted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    owner = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    student = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    can_manage = serializers.SerializerMethodField()

    def get_owner(self, enquiry: Enquiry) -> dict | None:
        return _person(enquiry.owner)

    def get_created_by(self, enquiry: Enquiry) -> dict | None:
        return _person(enquiry.created_by)

    def get_branch(self, enquiry: Enquiry) -> dict | None:
        branch = enquiry.branch
        return {"id": str(branch.pk), "name": branch.name} if branch is not None else None

    def get_student(self, enquiry: Enquiry) -> dict | None:
        student = enquiry.student
        if student is None:
            return None
        return {
            "id": str(student.pk),
            "name": student.user.get_full_name() if student.user_id else "",
        }

    def get_can_manage(self, enquiry: Enquiry) -> bool:
        from .access import can_manage_enquiry

        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user is not None and can_manage_enquiry(user, enquiry))


class EnquiryHistorySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    action = serializers.CharField(read_only=True)
    actor = serializers.SerializerMethodField()
    context = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_actor(self, row) -> str:
        if row.actor_id and row.actor is not None:
            return row.actor.get_full_name() or row.actor.email
        return row.actor_label or "Automation"


class EnquiryDetailSerializer(EnquirySerializer):
    history = serializers.SerializerMethodField()

    def get_history(self, enquiry: Enquiry) -> list[dict]:
        from apps.audit.models import AuditLog

        rows = (
            AuditLog.objects.filter(resource_type="enquiry", resource_id=str(enquiry.pk))
            .select_related("actor")
            .order_by("-created_at")[:50]
        )
        return EnquiryHistorySerializer(rows, many=True).data


class EnquiryUpdateSerializer(StrictSerializer):
    full_name = SafeCharField(max_length=120, required=False)
    mobile = SafeCharField(max_length=20, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    whatsapp_number = SafeCharField(max_length=20, required=False, allow_blank=True)
    state = SafeCharField(max_length=60, required=False, allow_blank=True)
    city = SafeCharField(max_length=60, required=False, allow_blank=True)
    course = SafeCharField(max_length=60, required=False, allow_blank=True)
    track = SafeCharField(max_length=60, required=False, allow_blank=True)
    preferred_centre = SafeCharField(max_length=30, required=False, allow_blank=True)
    mode = SafeCharField(max_length=20, required=False, allow_blank=True)
    batch_timing = SafeCharField(max_length=20, required=False, allow_blank=True)
    qualification = SafeCharField(max_length=40, required=False, allow_blank=True)
    source = SafeCharField(max_length=40, required=False, allow_blank=True)
    remarks = SafeCharField(max_length=4000, required=False, allow_blank=True)
    stage = serializers.ChoiceField(choices=EnquiryStage.choices, required=False)
    lost_reason = SafeCharField(max_length=40, required=False, allow_blank=True)
    lead_quality = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=5
    )
    next_follow_up_at = serializers.DateTimeField(required=False, allow_null=True)
    owner = serializers.UUIDField(required=False, allow_null=True)
