"""Admission endpoints (`/api/v1/admissions/`).

Reading is the student's own rule, reused: you see an admission exactly when
you see the student (`access.visible_admissions`). Writing is
`enrolment.create`, checked here and again in the service, so a view wired
wrong cannot grant it.

Every id a write names — the student, the academic year, each course — is
resolved out of the caller's own scoped queryset rather than the table. A
write is a read as well: a 201 against an id the caller cannot see would both
confirm the record exists and file money against it.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import IsActiveUser
from apps.courses.models import Course
from apps.organisation.models import AcademicYear
from apps.students import access as students_access

from . import access, services
from .models import Admission, AdmissionStatus, LineKind
from .serializers import (
    AdmissionCancelSerializer,
    AdmissionSerializer,
    AdmissionWriteSerializer,
)

TAG = ["Admissions"]


class AdmissionFilterSet(django_filters.FilterSet):
    student = django_filters.UUIDFilter(field_name="student_id")
    status = django_filters.ChoiceFilter(choices=AdmissionStatus.choices)
    academic_year = django_filters.UUIDFilter(field_name="academic_year_id")
    course = django_filters.UUIDFilter(field_name="lines__course_id", distinct=True)
    admitted_after = django_filters.DateFilter(field_name="admission_date", lookup_expr="gte")
    admitted_before = django_filters.DateFilter(field_name="admission_date", lookup_expr="lte")

    class Meta:
        model = Admission
        fields = ("student", "status", "academic_year", "course")


class AdmissionListView(ListAPIView):
    """Every admission the caller may see, newest first."""

    permission_classes = (IsActiveUser,)
    serializer_class = AdmissionSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = AdmissionFilterSet
    ordering_fields = ("admission_date", "created_at")
    ordering = ("-admission_date",)

    def get_queryset(self):
        return access.visible_admissions(self.request.user)

    @extend_schema(summary="Admissions", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Record an admission",
        request=AdmissionWriteSerializer,
        responses={201: AdmissionSerializer},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        if not access.can_manage_admissions(request.user):
            raise AuthorityError("You do not have authority to admit a student.")
        serializer = AdmissionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        student = get_object_or_404(
            students_access.visible_students(request.user), pk=data.pop("student")
        )
        year_id = data.pop("academic_year", None)
        year = (
            get_object_or_404(AcademicYear.objects.all(), pk=year_id)
            if year_id
            else AcademicYear.objects.current()
        )

        lines = []
        for row in data.pop("lines"):
            line = dict(row)
            course_id = line.pop("course", None)
            if line.get("kind", LineKind.COURSE) == LineKind.COURSE:
                if not course_id:
                    raise ApplicationError({"course": ["Choose the course."]})
                line["course"] = get_object_or_404(Course.objects.all(), pk=course_id)
            lines.append(line)

        admission = services.create_admission(
            actor=request.user, student=student, academic_year=year, lines=lines, **data
        )
        return Response(
            AdmissionSerializer(self._reload(request, admission.pk)).data,
            status=http_status.HTTP_201_CREATED,
        )

    def _reload(self, request, admission_id) -> Admission:
        return get_object_or_404(access.visible_admissions(request.user), pk=admission_id)


class AdmissionDetailView(APIView):
    """One admission."""

    permission_classes = (IsActiveUser,)
    serializer_class = AdmissionSerializer

    def _get(self, request, admission_id) -> Admission:
        return get_object_or_404(access.visible_admissions(request.user), pk=admission_id)

    @extend_schema(summary="One admission", responses={200: AdmissionSerializer}, tags=TAG)
    def get(self, request, admission_id):
        return Response(AdmissionSerializer(self._get(request, admission_id)).data)


class AdmissionCancelView(APIView):
    """End an admission, settling each course's money through the fee ledger."""

    permission_classes = (IsActiveUser,)
    serializer_class = AdmissionCancelSerializer

    @extend_schema(
        summary="Cancel an admission",
        request=AdmissionCancelSerializer,
        responses={200: AdmissionSerializer},
        tags=TAG,
    )
    def post(self, request, admission_id):
        admission = get_object_or_404(access.visible_admissions(request.user), pk=admission_id)
        if not access.can_manage_admissions(request.user):
            raise AuthorityError("You do not have authority to cancel an admission.")
        serializer = AdmissionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_admission(
            actor=request.user, admission=admission, reason=serializer.validated_data["reason"]
        )
        return Response(
            AdmissionSerializer(
                get_object_or_404(access.visible_admissions(request.user), pk=admission_id)
            ).data
        )
