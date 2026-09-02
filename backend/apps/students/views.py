"""Student endpoints (``/api/v1/students/``).

Two access paths, deliberately separate:

* ``/students/me/`` — a student's own record. No identifier in the URL, so
  there is nothing to tamper with.
* ``/students/<id>/`` — administrator access, gated on a capability, plus an
  object-level check so a student who guesses another student's id gets 403
  rather than someone else's data.
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
from .models import StudentProfile
from .serializers import (
    AdminStudentProfileSerializer,
    AdminStudentUpdateSerializer,
    FeeStatusUpdateSerializer,
    StudentCreateSerializer,
    StudentListSerializer,
    StudentProfileSerializer,
    StudentSelfUpdateSerializer,
)

STUDENTS_TAG = ["students"]


class StudentFilterSet(django_filters.FilterSet):
    fee_status = django_filters.CharFilter(field_name="fee_status", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="user__is_active")
    qualification = django_filters.CharFilter(field_name="qualification", lookup_expr="exact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")

    class Meta:
        model = StudentProfile
        fields = ("fee_status", "qualification", "city")


def _base_queryset():
    return StudentProfile.objects.select_related("user", "fee_status_updated_by")


class StudentListCreateView(ListCreateAPIView):
    """Administrator listing and creation."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.STUDENT_VIEW_ANY,
        "POST": Capability.STUDENT_CREATE,
    }
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = StudentFilterSet
    search_fields = (
        "student_id",
        "user__email",
        "user__first_name",
        "user__last_name",
        "institution",
    )
    ordering_fields = ("student_id", "created_at", "fee_status", "user__email")
    ordering = ("-created_at",)
    serializer_class = StudentListSerializer

    def get_queryset(self):
        return _base_queryset()

    @extend_schema(
        summary="List students", responses={200: StudentListSerializer}, tags=STUDENTS_TAG
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a student",
        request=StudentCreateSerializer,
        responses={
            201: AdminStudentProfileSerializer,
            409: OpenApiResponse(description="Email already in use."),
        },
        tags=STUDENTS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        profile_fields = data.pop("profile", None) or {}
        profile = services.create_student(actor=request.user, profile_fields=profile_fields, **data)
        return Response(AdminStudentProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class StudentDetailView(RetrieveUpdateAPIView):
    """Retrieve or update one student record.

    Object-level ownership is checked on every request. A student may read and
    edit their own record here; anyone else needs the administrator capability.
    """

    permission_classes = (IsOwnerOrHasCapability,)
    object_capability = Capability.STUDENT_VIEW_ANY
    lookup_url_kwarg = "student_id"

    def get_queryset(self):
        return _base_queryset()

    def get_object(self):
        profile = get_object_or_404(self.get_queryset(), pk=self.kwargs["student_id"])
        self.check_object_permissions(self.request, profile)
        return profile

    def _is_admin(self) -> bool:
        return has_capability(self.request.user, Capability.STUDENT_VIEW_ANY)

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AdminStudentProfileSerializer if self._is_admin() else StudentProfileSerializer
        return AdminStudentUpdateSerializer if self._is_admin() else StudentSelfUpdateSerializer

    @extend_schema(summary="Retrieve a student", tags=STUDENTS_TAG)
    def get(self, request, *args, **kwargs):
        profile = self.get_object()
        return Response(self.get_serializer_class()(profile).data)

    @extend_schema(summary="Update a student", tags=STUDENTS_TAG)
    def patch(self, request, *args, **kwargs):
        profile = self.get_object()
        # Editing someone else's record needs the update capability, not just
        # the read capability that got the caller this far.
        is_admin_edit = has_capability(request.user, Capability.STUDENT_UPDATE_ANY)
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
            AdminStudentUpdateSerializer if is_admin_edit else StudentSelfUpdateSerializer
        )
        allowed = (
            serializer_class.Meta.fields if is_admin_edit else StudentProfile.SELF_EDITABLE_FIELDS
        )
        serializer = serializer_class(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_student_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=tuple(allowed),
            **serializer.validated_data,
        )
        read_class = AdminStudentProfileSerializer if is_admin_edit else StudentProfileSerializer
        return Response(read_class(updated).data)


class StudentMeView(APIView):
    """The signed-in student's own profile.

    No identifier in the URL: the record is resolved from the session, so there
    is nothing for a caller to tamper with.
    """

    permission_classes = (IsActiveUser,)

    def _profile(self, request) -> StudentProfile:
        if request.user.role != UserRole.STUDENT:
            raise PermissionDenied("This endpoint is only available to student accounts.")
        return services.get_or_create_profile_for(request.user)

    @extend_schema(
        summary="Own student profile", responses={200: StudentProfileSerializer}, tags=STUDENTS_TAG
    )
    def get(self, request):
        return Response(StudentProfileSerializer(self._profile(request)).data)

    @extend_schema(
        summary="Update own student profile",
        request=StudentSelfUpdateSerializer,
        responses={200: StudentProfileSerializer},
        tags=STUDENTS_TAG,
    )
    def patch(self, request):
        profile = self._profile(request)
        serializer = StudentSelfUpdateSerializer(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_student_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=StudentProfile.SELF_EDITABLE_FIELDS,
            **serializer.validated_data,
        )
        return Response(StudentProfileSerializer(updated).data)


class StudentFeeStatusView(APIView):
    """Change a student's fee status. Administrator-only and always audited."""

    permission_classes = (HasCapability,)
    required_capability = Capability.STUDENT_SET_FEE_STATUS

    @extend_schema(
        summary="Set a student's fee status",
        request=FeeStatusUpdateSerializer,
        responses={200: AdminStudentProfileSerializer},
        tags=STUDENTS_TAG,
    )
    def post(self, request, student_id):
        profile = get_object_or_404(_base_queryset(), pk=student_id)
        serializer = FeeStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_fee_status(
            profile=profile,
            fee_status=serializer.validated_data["fee_status"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(AdminStudentProfileSerializer(updated).data)
