from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserRole
from apps.common.permissions import IsActiveUser

from . import services


class WarningItemSerializer(serializers.Serializer):
    label = serializers.CharField()
    href = serializers.CharField(allow_null=True)


class WarningSerializer(serializers.Serializer):
    kind = serializers.CharField()
    severity = serializers.ChoiceField(choices=["error", "warning", "info"])
    label = serializers.CharField()
    count = serializers.IntegerField()
    href = serializers.CharField(allow_null=True)
    items = WarningItemSerializer(many=True)


class WarningsView(APIView):
    """What needs doing, for the caller's own reach.

    A student is refused rather than handed an empty list (D-121): an endpoint
    that is permanently empty for a role should say so.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Warnings for the signed-in staff member, most urgent first",
        responses={200: WarningSerializer(many=True)},
        tags=["Warnings"],
    )
    def get(self, request):
        if request.user.role == UserRole.STUDENT:
            raise PermissionDenied("Warnings are for staff.")
        return Response(
            WarningSerializer(services.cached_warnings_for(request.user), many=True).data
        )
