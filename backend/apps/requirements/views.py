"""Trainer requirement API.

Every record is fetched through `access.visible_requirements`, so an id from
another centre is a 404 before any permission code runs.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.trainers.models import TrainerProfile

from . import access, services
from .models import TrainerRequirement
from .serializers import (
    RequirementCloseSerializer,
    RequirementDeleteSerializer,
    RequirementReplySerializer,
    RequirementReplyWriteSerializer,
    RequirementWriteSerializer,
    TrainerRequirementSerializer,
)

TAG = ["Trainer requirements"]


class RequirementFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    batch = django_filters.UUIDFilter(field_name="batch_id")

    class Meta:
        model = TrainerRequirement
        fields = ("status", "batch")


def _readable(request) -> None:
    if not access.can_read_requirements(request.user):
        raise PermissionDenied(
            "Trainer requirements are for the teaching staff and their managers."
        )


def _manageable(request) -> None:
    _readable(request)
    if not access.can_manage_requirements(request.user):
        raise PermissionDenied("Only a manager raises or closes a requirement.")


def _requirement_for(request, requirement_id) -> TrainerRequirement:
    return get_object_or_404(access.visible_requirements(request.user), pk=requirement_id)


class RequirementListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = TrainerRequirementSerializer
    queryset = TrainerRequirement.objects.none()  # the schema generator's view; see below
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filterset_class = RequirementFilterSet
    search_fields = ("title", "details", "batch__code")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TrainerRequirement.objects.none()
        _readable(self.request)
        return access.visible_requirements(self.request.user)

    @extend_schema(summary="Requirements I can see, newest first", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Raise a requirement to the trainers of my centre",
        request=RequirementWriteSerializer,
        responses={
            201: TrainerRequirementSerializer,
            403: OpenApiResponse(description="Not a manager"),
        },
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        _manageable(request)
        serializer = RequirementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        batch_id = fields.pop("batch", None)
        batch = (
            get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
            if batch_id
            else None
        )
        requirement = services.raise_requirement(actor=request.user, batch=batch, **fields)
        requirement = access.visible_requirements(request.user).get(pk=requirement.pk)
        return Response(
            TrainerRequirementSerializer(requirement).data, status=http_status.HTTP_201_CREATED
        )


class RequirementDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="One requirement with its replies",
        responses={200: TrainerRequirementSerializer},
        tags=TAG,
    )
    def get(self, request, requirement_id):
        _readable(request)
        requirement = _requirement_for(request, requirement_id)
        return Response(TrainerRequirementSerializer(requirement).data)

    @extend_schema(
        summary="Remove a requirement (reversible)",
        request=RequirementDeleteSerializer,
        responses={204: None},
        tags=TAG,
    )
    def delete(self, request, requirement_id):
        _manageable(request)
        requirement = _requirement_for(request, requirement_id)
        serializer = RequirementDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_requirement(
            requirement=requirement, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class RequirementReplyView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reply on an open requirement",
        request=RequirementReplyWriteSerializer,
        responses={201: RequirementReplySerializer},
        tags=TAG,
    )
    def post(self, request, requirement_id):
        _readable(request)
        requirement = _requirement_for(request, requirement_id)
        serializer = RequirementReplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = services.reply_to_requirement(
            requirement=requirement, actor=request.user, **serializer.validated_data
        )
        return Response(RequirementReplySerializer(reply).data, status=http_status.HTTP_201_CREATED)


class RequirementCloseView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Close a requirement, naming who fulfilled it if anyone did",
        request=RequirementCloseSerializer,
        responses={200: TrainerRequirementSerializer},
        tags=TAG,
    )
    def post(self, request, requirement_id):
        _manageable(request)
        requirement = _requirement_for(request, requirement_id)
        serializer = RequirementCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trainer_id = serializer.validated_data["fulfilled_by"]
        trainer = None
        if trainer_id:
            # Through the caller's reach, like every other id a client sends.
            trainer = get_object_or_404(_trainers_in_reach(request.user), pk=trainer_id)
        requirement = services.close_requirement(
            requirement=requirement,
            actor=request.user,
            fulfilled_by=trainer,
            note=serializer.validated_data["note"],
        )
        requirement = access.visible_requirements(request.user).get(pk=requirement.pk)
        return Response(TrainerRequirementSerializer(requirement).data)


def _trainers_in_reach(user):
    from apps.organisation.scoping import scope_to_branch

    return scope_to_branch(TrainerProfile.objects.select_related("user"), user, path="user__branch")
