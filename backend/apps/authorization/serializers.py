from __future__ import annotations

from rest_framework import serializers

from apps.accounts.roles import UserRole
from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Permission, PermissionScope, Role, RolePermission, RoleStatus


class PermissionSerializer(StrictModelSerializer):
    class Meta:
        model = Permission
        fields = (
            "code",
            "resource",
            "action",
            "category",
            "description",
            "is_lockable",
            "is_active",
        )
        read_only_fields = fields


class GrantSerializer(StrictModelSerializer):
    code = serializers.CharField(source="permission.code", read_only=True)

    class Meta:
        model = RolePermission
        fields = ("code", "scope", "is_locked")
        read_only_fields = fields


class RoleSerializer(StrictModelSerializer):
    permissions = GrantSerializer(source="grants", many=True, read_only=True)
    user_count = serializers.IntegerField(read_only=True)
    updated_by_name = serializers.CharField(
        source="updated_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Role
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "kind",
            "status",
            "is_system",
            "is_locked",
            "user_count",
            "permissions",
            "updated_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RoleSummarySerializer(StrictModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    permission_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "slug",
            "name",
            "description",
            "kind",
            "status",
            "is_system",
            "is_locked",
            "user_count",
            "permission_count",
            "updated_at",
        )
        read_only_fields = fields


class GrantWriteSerializer(StrictSerializer):
    code = serializers.CharField(max_length=60)
    scope = serializers.ChoiceField(
        choices=PermissionScope.choices, required=False, allow_null=True, default=None
    )


class RoleWriteSerializer(StrictSerializer):
    slug = serializers.SlugField(max_length=60)
    name = SafeCharField(max_length=80)
    description = SafeCharField(max_length=300, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=UserRole.choices)
    permissions = GrantWriteSerializer(many=True, required=False, default=list)


class RoleUpdateSerializer(StrictSerializer):
    name = SafeCharField(max_length=80, required=False)
    description = SafeCharField(max_length=300, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=RoleStatus.choices, required=False)
    permissions = GrantWriteSerializer(many=True, required=False)


class RoleDeleteSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255)


class RoleMatrixSerializer(serializers.Serializer):
    roles = RoleSummarySerializer(many=True, read_only=True)
    permissions = PermissionSerializer(many=True, read_only=True)
    cells = serializers.DictField(child=serializers.DictField(child=serializers.CharField()))
