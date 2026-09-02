"""User administration endpoints (``/api/v1/users/``).

Every view here requires an explicit capability. Nothing falls back to "is the
caller staff" or an inline role comparison.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import has_capability
from apps.common.permissions import Capability, HasCapability

from . import services
from .models import User
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserDetailSerializer,
    AdminUserUpdateSerializer,
    SetActiveSerializer,
)

USERS_TAG = ["users"]


class UserFilterSet(django_filters.FilterSet):
    """Server-side filtering for the administrator table.

    Every filter maps to an indexed column or a small enumeration; there is no
    free-form field lookup, so a client cannot craft an expensive query.
    """

    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    is_email_verified = django_filters.BooleanFilter(field_name="is_email_verified")
    joined_after = django_filters.DateFilter(field_name="date_joined", lookup_expr="date__gte")
    joined_before = django_filters.DateFilter(field_name="date_joined", lookup_expr="date__lte")

    class Meta:
        model = User
        fields = ("role", "is_active", "is_email_verified")


class UserListCreateView(ListCreateAPIView):
    """List users, or create one.

    Listing supports search, filtering, ordering and pagination — all executed
    by the database. The page size is capped by ``DefaultPagination``, so no
    request can pull the whole table into a browser.
    """

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.USER_VIEW_ANY,
        "POST": Capability.USER_CREATE,
    }
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = UserFilterSet
    #: Matches name, email, and the student/trainer identifiers through the
    #: reverse one-to-one relations.
    search_fields = (
        "email",
        "first_name",
        "last_name",
        "student_profile__student_id",
        "trainer_profile__trainer_id",
    )
    ordering_fields = ("email", "first_name", "last_name", "role", "date_joined", "created_at")
    ordering = ("-created_at",)

    def get_queryset(self):
        return User.objects.select_related("student_profile", "trainer_profile").all()

    def get_serializer_class(self):
        return (
            AdminUserCreateSerializer
            if self.request.method == "POST"
            else AdminUserDetailSerializer
        )

    @extend_schema(summary="List users", tags=USERS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a user",
        request=AdminUserCreateSerializer,
        responses={
            201: AdminUserDetailSerializer,
            409: OpenApiResponse(description="Email in use."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.create_user(actor=request.user, **serializer.validated_data)
        return Response(AdminUserDetailSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(RetrieveUpdateAPIView):
    """Retrieve or update one user."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.USER_VIEW_ANY,
        "PATCH": Capability.USER_UPDATE_ANY,
        "PUT": Capability.USER_UPDATE_ANY,
    }
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        return User.objects.select_related("student_profile", "trainer_profile").all()

    def get_serializer_class(self):
        return (
            AdminUserDetailSerializer if self.request.method == "GET" else AdminUserUpdateSerializer
        )

    @extend_schema(
        summary="Retrieve a user", responses={200: AdminUserDetailSerializer}, tags=USERS_TAG
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update a user",
        request=AdminUserUpdateSerializer,
        responses={200: AdminUserDetailSerializer},
        tags=USERS_TAG,
    )
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = AdminUserUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Changing a role is a privilege change and needs its own capability,
        # so an operator with plain edit rights cannot promote anyone.
        if "role" in serializer.validated_data and serializer.validated_data["role"] != user.role:
            if not has_capability(request.user, Capability.USER_CHANGE_ROLE):
                return Response(
                    {
                        "error": {
                            "code": "permission_denied",
                            "message": "You do not have permission to change a user's role.",
                            "request_id": getattr(request, "request_id", "-"),
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        updated = services.update_user(user=user, actor=request.user, **serializer.validated_data)
        return Response(AdminUserDetailSerializer(updated).data)


class UserSetActiveView(APIView):
    """Activate or deactivate an account.

    A separate, separately-authorised endpoint rather than a field on the patch
    body: account status is a security control, and it should not be possible to
    flip it as a side effect of editing a phone number.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_SET_ACTIVE

    @extend_schema(
        summary="Activate or deactivate a user",
        request=SetActiveSerializer,
        responses={
            200: AdminUserDetailSerializer,
            409: OpenApiResponse(description="Not permitted."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        serializer = SetActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Deactivating yourself would lock you out with no way back in.
        if user.pk == request.user.pk and not serializer.validated_data["is_active"]:
            return Response(
                {
                    "error": {
                        "code": "conflict",
                        "message": "You cannot deactivate your own account.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        updated = services.set_user_active(
            user=user,
            is_active=serializer.validated_data["is_active"],
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(AdminUserDetailSerializer(updated).data)
