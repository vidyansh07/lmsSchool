"""Roles and the permission catalog (``/api/v1/roles/``, ``/api/v1/permissions/``)."""

from __future__ import annotations

from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.accounts.stepup import StepUpRequired, is_fresh
from apps.common.exceptions import AuthorityError
from apps.common.permissions import HasCapability

from . import services
from .models import Permission, Role, ScopeGrant
from .serializers import (
    PermissionSerializer,
    RoleDeleteSerializer,
    RoleMatrixSerializer,
    RoleSerializer,
    RoleSummarySerializer,
    RoleUpdateSerializer,
    RoleWriteSerializer,
    ScopeGrantSerializer,
    ScopeGrantWriteSerializer,
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


class LockPermissionView(APIView):
    """Freeze or unfree a role's grant (ADR-03). Superadmin only, and only
    with a fresh step-up: locking is one of the acts §72 marks destructive
    to the *configuration*, not to a record, so it gets the same treatment."""

    permission_classes = (HasCapability,)
    required_capability = Capability.PERMISSION_LOCK
    serializer_class = RoleSerializer

    def _apply(self, request, slug, code, locked):
        if not is_fresh(request):
            raise StepUpRequired()
        role = get_object_or_404(Role.objects.all(), slug=slug)
        services.set_grant_lock(actor=request.user, role=role, code=code, locked=locked)
        return Response(RoleSerializer(_role_for(slug)).data)

    @extend_schema(
        summary="Lock a role's permission grant",
        responses={
            200: RoleSerializer,
            403: OpenApiResponse(description="Not a superadmin, or step-up required"),
        },
        tags=TAG,
    )
    def post(self, request, slug, code):
        return self._apply(request, slug, code, True)


class UnlockPermissionView(LockPermissionView):
    @extend_schema(
        summary="Unlock a role's permission grant",
        responses={
            200: RoleSerializer,
            403: OpenApiResponse(description="Not a superadmin, or step-up required"),
        },
        tags=TAG,
    )
    def post(self, request, slug, code):
        return self._apply(request, slug, code, False)


class ScopeGrantListView(APIView):
    """A user's batch/course grants under the `assigned` scope (ADR-02)."""

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_UPDATE_ANY

    def _user_for(self, user_id):
        from apps.accounts.access import visible_accounts

        return get_object_or_404(visible_accounts(self.request.user), pk=user_id)

    @extend_schema(
        summary="A user's scope grants",
        responses={200: ScopeGrantSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, user_id):
        target = self._user_for(user_id)
        rows = ScopeGrant.objects.filter(user=target).select_related("batch", "course")
        return Response(ScopeGrantSerializer(rows, many=True).data)

    @extend_schema(
        summary="Grant a batch or course scope",
        request=ScopeGrantWriteSerializer,
        responses={201: ScopeGrantSerializer},
        tags=TAG,
    )
    def post(self, request, user_id):
        target = self._user_for(user_id)
        serializer = ScopeGrantWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        batch_id = data.pop("batch", None)
        course_id = data.pop("course", None)
        batch = course = None
        if batch_id:
            from apps.batches.access import visible_batches

            batch = get_object_or_404(visible_batches(request.user), pk=batch_id)
        if course_id:
            from apps.courses.access import visible_courses

            course = get_object_or_404(visible_courses(request.user), pk=course_id)
        grant = services.grant_scope(actor=request.user, user=target, batch=batch, course=course)
        return Response(ScopeGrantSerializer(grant).data, status=http_status.HTTP_201_CREATED)


class ScopeGrantDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.USER_UPDATE_ANY

    @extend_schema(summary="Revoke a scope grant", responses={204: None}, tags=TAG)
    def delete(self, request, user_id, grant_id):
        from apps.accounts.access import visible_accounts

        target = get_object_or_404(visible_accounts(request.user), pk=user_id)
        grant = get_object_or_404(ScopeGrant.objects.filter(user=target), pk=grant_id)
        services.revoke_scope(actor=request.user, grant=grant)
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
