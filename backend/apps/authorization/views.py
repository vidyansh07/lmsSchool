"""Roles and the permission catalog (``/api/v1/roles/``, ``/api/v1/permissions/``)."""

from __future__ import annotations

from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.common.exceptions import AuthorityError
from apps.common.permissions import HasCapability

from . import services
from .models import Permission, Role
from .serializers import (
    PermissionSerializer,
    RoleDeleteSerializer,
    RoleMatrixSerializer,
    RoleSerializer,
    RoleSummarySerializer,
    RoleUpdateSerializer,
    RoleWriteSerializer,
)

TAG = ["Roles"]


def _annotated():
    return Role.objects.with_related().annotate(
        user_count=Count("users", filter=Q(users__is_active=True), distinct=True),
        permission_count=Count("grants", distinct=True),
    )


def _role_for(slug: str) -> Role:
    return get_object_or_404(_annotated(), slug=slug)


class RoleListCreateView(ListAPIView):
    permission_classes = (HasCapability,)
    capability_map = {"GET": Capability.ROLE_VIEW, "POST": Capability.ROLE_MANAGE}
    serializer_class = RoleSummarySerializer
    queryset = Role.objects.none()
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Role.objects.none()
        return _annotated()

    @extend_schema(summary="Every role, system roles first", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a custom role",
        request=RoleWriteSerializer,
        responses={201: RoleSerializer, 403: OpenApiResponse(description="Wider than the caller")},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("permissions") and not has_capability(
            request.user, Capability.PERMISSION_ASSIGN
        ):
            raise AuthorityError("You may create roles but not assign permissions to them.")
        role = services.create_role(actor=request.user, **data)
        return Response(
            RoleSerializer(_role_for(role.slug)).data, status=http_status.HTTP_201_CREATED
        )


class RoleDetailView(APIView):
    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.ROLE_VIEW,
        "PATCH": Capability.ROLE_MANAGE,
        "DELETE": Capability.ROLE_MANAGE,
    }

    @extend_schema(summary="One role with its grants", responses={200: RoleSerializer}, tags=TAG)
    def get(self, request, slug):
        return Response(RoleSerializer(_role_for(slug)).data)

    @extend_schema(
        summary="Edit a role",
        request=RoleUpdateSerializer,
        responses={200: RoleSerializer},
        tags=TAG,
    )
    def patch(self, request, slug):
        role = _role_for(slug)
        serializer = RoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "permissions" in data and not has_capability(request.user, Capability.PERMISSION_ASSIGN):
            raise AuthorityError("You may edit roles but not assign permissions to them.")
        services.update_role(actor=request.user, role=role, **data)
        return Response(RoleSerializer(_role_for(slug)).data)

    @extend_schema(
        summary="Remove a custom role (reversible)",
        request=RoleDeleteSerializer,
        responses={204: None},
        tags=TAG,
    )
    def delete(self, request, slug):
        role = _role_for(slug)
        serializer = RoleDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_role(
            actor=request.user, role=role, reason=serializer.validated_data["reason"]
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class PermissionListView(ListAPIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.ROLE_VIEW
    serializer_class = PermissionSerializer
    queryset = Permission.objects.filter(is_active=True)
    pagination_class = None

    @extend_schema(summary="The permission catalog", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RoleMatrixView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.ROLE_VIEW

    @extend_schema(
        summary="Every role by every permission, as five states",
        responses={200: RoleMatrixSerializer},
        tags=TAG,
    )
    def get(self, request):
        data = services.matrix()
        return Response(
            {
                "roles": RoleSummarySerializer(
                    _annotated().order_by("-is_system", "kind", "name"), many=True
                ).data,
                "permissions": PermissionSerializer(data["permissions"], many=True).data,
                "cells": data["cells"],
            }
        )
