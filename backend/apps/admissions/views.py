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
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches import access as batch_access
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.courses.models import Course
from apps.organisation.models import AcademicYear
from apps.students import access as students_access

from . import access, reports, services
from .models import Admission, AdmissionStatus, LineKind
from .serializers import (
    AdmissionCancelSerializer,
    AdmissionLineEnrolSerializer,
    AdmissionReportSerializer,
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


class AdmissionLineEnrolView(APIView):
    """Put this course line's student on a batch, and record that the line
    became that enrolment.

    The last step of the desk's registration flow. Until it runs the student
    is registered and billed but on no batch, which is a student the timetable
    does not know about.

    `enrolment.create`, not the admission's own right: this creates an
    enrolment, and the capability that governs enrolments is the one that
    should answer for it.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.ENROLMENT_CREATE
    serializer_class = AdmissionLineEnrolSerializer

    @extend_schema(
        summary="Enrol a course line onto a batch",
        request=AdmissionLineEnrolSerializer,
        responses={200: AdmissionSerializer},
        tags=TAG,
    )
    def post(self, request, admission_id, line_id):
        admission = get_object_or_404(access.visible_admissions(request.user), pk=admission_id)
        line = get_object_or_404(admission.lines, pk=line_id)
        serializer = AdmissionLineEnrolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = get_object_or_404(
            batch_access.visible_batches(request.user), pk=serializer.validated_data["batch"]
        )
        services.enrol_line(actor=request.user, line=line, batch=batch)
        return Response(
            AdmissionSerializer(
                get_object_or_404(access.visible_admissions(request.user), pk=admission_id)
            ).data
        )


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


class AdmissionReportView(APIView):
    """One of the five admissions reports.

    `/api/v1/admissions/reports/{tab}/` where `tab` is one of
    `overall`, `discount`, `expiry`, `additional-fees`, `coursewise`.

    Gated on reading fees, not on reading admissions: every tab is mostly
    money, and somebody who may see that a student was admitted does not
    thereby get to read what the centre took this month.

    The filters are the screen's own, and each narrows an already-scoped
    queryset — none of them can widen it.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY
    serializer_class = AdmissionReportSerializer

    @extend_schema(
        summary="An admissions report",
        parameters=[
            OpenApiParameter("academic_year", str),
            OpenApiParameter("status", str, description="active or cancelled"),
            OpenApiParameter("course", str),
            OpenApiParameter("batch", str),
            OpenApiParameter("user", str, description="Who recorded the admission."),
            OpenApiParameter("school", str, description="The student's college."),
            OpenApiParameter("start_date", str),
            OpenApiParameter("end_date", str),
        ],
        responses={200: AdmissionReportSerializer},
        tags=TAG,
    )
    def get(self, request, tab):
        if tab not in reports.BUILDERS:
            raise ApplicationError({"tab": ["No such report."]})

        rows = access.visible_admissions(request.user)
        params = request.query_params
        if params.get("academic_year"):
            rows = rows.filter(academic_year_id=params["academic_year"])
        if params.get("status"):
            rows = rows.filter(status=params["status"])
        if params.get("course"):
            rows = rows.filter(lines__course_id=params["course"]).distinct()
        if params.get("batch"):
            rows = rows.filter(lines__enrollment__batch_id=params["batch"]).distinct()
        if params.get("user"):
            rows = rows.filter(created_by_id=params["user"])
        if params.get("school"):
            rows = rows.filter(student__college_id=params["school"])
        if params.get("start_date"):
            rows = rows.filter(admission_date__gte=params["start_date"])
        if params.get("end_date"):
            rows = rows.filter(admission_date__lte=params["end_date"])

        try:
            built = reports.BUILDERS[tab](list(rows))
        except (ValueError, ValidationError) as exc:
            # A malformed uuid or date in a filter is a bad request, not a
            # 500 and not a silently unfiltered report — which would show
            # more than was asked for.
            raise ApplicationError({"detail": ["One of the filters is not valid."]}) from exc
        return Response(built)
