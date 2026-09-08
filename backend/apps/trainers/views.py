"""Trainer endpoints (``/api/v1/trainers/``).

Same two access paths as students: ``/trainers/me/`` resolves the record from
the session, and ``/trainers/<id>/`` is capability-gated with an object-level
ownership check behind it.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import UserRole, has_capability
from apps.common.permissions import Capability, HasCapability, IsActiveUser, IsOwnerOrHasCapability

from . import services
from .models import TrainerProfile
from .serializers import (
    AdminTrainerUpdateSerializer,
    TrainerCreateSerializer,
    TrainerListSerializer,
    TrainerProfileSerializer,
    TrainerSelfUpdateSerializer,
)

TRAINERS_TAG = ["trainers"]


class TrainerFilterSet(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter(field_name="user__is_active")
    is_accepting_assignments = django_filters.BooleanFilter(field_name="is_accepting_assignments")
    #: Case-insensitive containment against the skills array. Bounded by the
    #: field's own length limit, so it cannot become an expensive scan.
    skill = django_filters.CharFilter(method="filter_skill")
    min_experience = django_filters.NumberFilter(
        field_name="years_of_experience", lookup_expr="gte"
    )
    # The manager's attention strip links here: `?attention=review_missing`
    # narrows to the trainers it counted, by the same test that counted them.
    attention = django_filters.ChoiceFilter(
        choices=(("review_missing", "No performance review on file"),),
        method="filter_attention",
    )

    class Meta:
        model = TrainerProfile
        fields = ("is_accepting_assignments",)

    def filter_attention(self, queryset, name, value):
        from apps.reporting.dashboards import trainers_without_review_ids

        return queryset.filter(pk__in=trainers_without_review_ids())

    def filter_skill(self, queryset, name, value):
        return queryset.filter(skills__icontains=value)


def _base_queryset():
    return TrainerProfile.objects.select_related("user")


class TrainerListCreateView(ListCreateAPIView):
    """Administrator listing and creation."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.TRAINER_VIEW_ANY,
        "POST": Capability.TRAINER_CREATE,
    }
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = TrainerFilterSet
    search_fields = (
        "trainer_id",
        "user__email",
        "user__first_name",
        "user__last_name",
        "professional_title",
    )
    ordering_fields = ("trainer_id", "created_at", "years_of_experience", "user__email")
    ordering = ("-created_at",)
    serializer_class = TrainerListSerializer

    def get_queryset(self):
        return _base_queryset()

    @extend_schema(
        summary="List trainers", responses={200: TrainerListSerializer}, tags=TRAINERS_TAG
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a trainer",
        request=TrainerCreateSerializer,
        responses={
            201: TrainerProfileSerializer,
            409: OpenApiResponse(description="Email already in use."),
        },
        tags=TRAINERS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = TrainerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        profile_fields = data.pop("profile", None) or {}
        profile = services.create_trainer(actor=request.user, profile_fields=profile_fields, **data)
        return Response(TrainerProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class TrainerDetailView(RetrieveUpdateAPIView):
    """Retrieve or update one trainer record."""

    permission_classes = (IsOwnerOrHasCapability,)
    object_capability = Capability.TRAINER_VIEW_ANY
    lookup_url_kwarg = "trainer_id"
    serializer_class = TrainerProfileSerializer

    def get_queryset(self):
        return _base_queryset()

    def get_object(self):
        profile = get_object_or_404(self.get_queryset(), pk=self.kwargs["trainer_id"])
        self.check_object_permissions(self.request, profile)
        return profile

    @extend_schema(
        summary="Retrieve a trainer", responses={200: TrainerProfileSerializer}, tags=TRAINERS_TAG
    )
    def get(self, request, *args, **kwargs):
        return Response(TrainerProfileSerializer(self.get_object()).data)

    @extend_schema(summary="Update a trainer", tags=TRAINERS_TAG)
    def patch(self, request, *args, **kwargs):
        profile = self.get_object()
        is_admin_edit = has_capability(request.user, Capability.TRAINER_UPDATE_ANY)
        if profile.user_id != request.user.pk and not is_admin_edit:
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "You may only edit your own profile.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer_class = (
            AdminTrainerUpdateSerializer if is_admin_edit else TrainerSelfUpdateSerializer
        )
        allowed = (
            serializer_class.Meta.fields if is_admin_edit else TrainerProfile.SELF_EDITABLE_FIELDS
        )
        serializer = serializer_class(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_trainer_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=tuple(allowed),
            **serializer.validated_data,
        )
        return Response(TrainerProfileSerializer(updated).data)


class TrainerMeView(APIView):
    """The signed-in trainer's own profile."""

    permission_classes = (IsActiveUser,)

    def _profile(self, request) -> TrainerProfile:
        if request.user.role != UserRole.TRAINER:
            raise PermissionDenied("This endpoint is only available to trainer accounts.")
        return services.get_or_create_profile_for(request.user)

    @extend_schema(
        summary="Own trainer profile", responses={200: TrainerProfileSerializer}, tags=TRAINERS_TAG
    )
    def get(self, request):
        return Response(TrainerProfileSerializer(self._profile(request)).data)

    @extend_schema(
        summary="Update own trainer profile",
        request=TrainerSelfUpdateSerializer,
        responses={200: TrainerProfileSerializer},
        tags=TRAINERS_TAG,
    )
    def patch(self, request):
        profile = self._profile(request)
        serializer = TrainerSelfUpdateSerializer(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_trainer_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=TrainerProfile.SELF_EDITABLE_FIELDS,
            **serializer.validated_data,
        )
        return Response(TrainerProfileSerializer(updated).data)
