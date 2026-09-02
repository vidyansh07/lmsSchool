"""Trainer serializers, scoped by who is calling."""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import MAX_SKILL_LENGTH, MAX_SKILLS, TrainerProfile

#: Administrators may additionally control availability for assignment.
ADMIN_EDITABLE_FIELDS = (*TrainerProfile.SELF_EDITABLE_FIELDS, "is_accepting_assignments")


class SkillsField(serializers.ListField):
    """Bounded list of short, de-duplicated skill tags."""

    def __init__(self, **kwargs):
        kwargs.setdefault("child", SafeCharField(max_length=MAX_SKILL_LENGTH, allow_blank=False))
        kwargs.setdefault("max_length", MAX_SKILLS)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        seen: dict[str, str] = {}
        for value in values:
            seen.setdefault(value.strip().lower(), value.strip())
        return list(seen.values())


class TrainerProfileSerializer(StrictModelSerializer):
    """Full read representation, used by the trainer and by administrators."""

    user = UserSerializer(read_only=True)
    completion_percent = serializers.IntegerField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = TrainerProfile
        fields = (
            "id",
            "trainer_id",
            "user",
            "professional_title",
            "bio",
            "skills",
            "expertise",
            "qualifications",
            "years_of_experience",
            "professional_links",
            "is_accepting_assignments",
            "completion_percent",
            "is_profile_complete",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TrainerPublicSerializer(serializers.ModelSerializer):
    """Reduced view for contexts where a trainer is visible but not managed.

    Contact details and account state are omitted. Nothing consumes this in
    Phase 1; it exists so that when batches expose "your trainer", the reduced
    shape already exists rather than being improvised then.
    """

    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = TrainerProfile
        fields = (
            "id",
            "trainer_id",
            "full_name",
            "professional_title",
            "skills",
            "expertise",
            "years_of_experience",
        )
        read_only_fields = fields


class TrainerListSerializer(serializers.ModelSerializer):
    """Flattened row for the administrator table."""

    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    is_email_verified = serializers.BooleanField(source="user.is_email_verified", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = TrainerProfile
        fields = (
            "id",
            "trainer_id",
            "user_id",
            "email",
            "full_name",
            "professional_title",
            "skills",
            "years_of_experience",
            "is_accepting_assignments",
            "is_active",
            "is_email_verified",
            "created_at",
        )
        read_only_fields = fields


class TrainerProfileFieldsSerializer(StrictModelSerializer):
    """Profile fields accepted when an administrator creates a trainer."""

    skills = SkillsField()
    professional_title = SafeCharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = TrainerProfile
        fields = ADMIN_EDITABLE_FIELDS


class TrainerCreateSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    first_name = SafeCharField(max_length=100)
    last_name = SafeCharField(max_length=100, required=False, allow_blank=True, default="")
    phone = SafeCharField(max_length=20, required=False, allow_blank=True, default="")
    profile = TrainerProfileFieldsSerializer(required=False)

    def validate_email(self, value: str) -> str:
        from apps.accounts.models import User

        normalised = value.strip().lower()
        if User.objects.filter(email__iexact=normalised).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalised


class TrainerSelfUpdateSerializer(StrictModelSerializer):
    """What a trainer may change about their own profile.

    ``trainer_id`` and ``is_accepting_assignments`` are absent: a trainer does
    not assign themselves work, and identifiers are system-owned.
    """

    skills = SkillsField()
    professional_title = SafeCharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = TrainerProfile
        fields = TrainerProfile.SELF_EDITABLE_FIELDS


class AdminTrainerUpdateSerializer(StrictModelSerializer):
    skills = SkillsField()
    professional_title = SafeCharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = TrainerProfile
        fields = ADMIN_EDITABLE_FIELDS
