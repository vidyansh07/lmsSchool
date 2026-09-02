"""Assessment, result and import API.

The import endpoints are the interesting ones. They are two separate requests
on purpose — §4.6 asks for preview → validate → confirm — and the first of them
writes nothing to the results table. A trainer who uploads the wrong file
discovers it from a report, not from a class's marks.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.courses.models import Module

from . import access, importers, services
from .models import Assessment, AssessmentResult, ImportStatus, ResultImport
from .serializers import (
    AssessmentSerializer,
    AssessmentStatusSerializer,
    AssessmentWriteSerializer,
    ImportSerializer,
    ImportUploadSerializer,
    MarksSheetSerializer,
    RecordResultSerializer,
    ResultSerializer,
    StaffResultSerializer,
    StudentAssessmentSerializer,
)

ASSESSMENTS_TAG = ["assessments"]
RESULTS_TAG = ["results"]


def _forbidden(request, message: str) -> Response:
    return Response(
        {
            "error": {
                "code": "permission_denied",
                "message": message,
                "request_id": getattr(request, "request_id", "-"),
            }
        },
        status=http_status.HTTP_403_FORBIDDEN,
    )


class AssessmentFilterSet(django_filters.FilterSet):
    batch = django_filters.UUIDFilter(field_name="batch_id")
    course = django_filters.UUIDFilter(field_name="course_id")
    category = django_filters.CharFilter(field_name="category", lookup_expr="exact")
    delivery = django_filters.CharFilter(field_name="delivery", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")

    class Meta:
        model = Assessment
        fields = ("batch", "course", "category", "delivery", "status")


class AssessmentListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = AssessmentSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AssessmentFilterSet
    search_fields = ("title", "code")
    ordering_fields = ("scheduled_for", "created_at", "title")
    ordering = ("-scheduled_for",)

    def get_queryset(self):
        return access.visible_assessments(self.request.user)

    @extend_schema(summary="List assessments", tags=ASSESSMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BatchAssessmentsView(APIView):
    """Set a test on a batch."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Create an assessment",
        request=AssessmentWriteSerializer,
        responses={201: AssessmentSerializer},
        tags=ASSESSMENTS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not access.can_set_assessments_on(request.user, batch):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="batch",
                resource_id=batch.pk,
                result="failure",
                context={"attempted": "assessment.create"},
            )
            return _forbidden(request, "You cannot set assessments on this batch.")

        serializer = AssessmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)

        module_id = fields.pop("module", None)
        if module_id:
            fields["module"] = get_object_or_404(
                Module.objects.filter(course=batch.course), pk=module_id
            )

        assessment = services.create_assessment(actor=request.user, batch=batch, **fields)
        return Response(AssessmentSerializer(assessment).data, status=http_status.HTTP_201_CREATED)


def _assessment_for(request, assessment_id, *, manage: bool = False) -> Assessment:
    source = (
        access.manageable_assessments(request.user)
        if manage
        else access.visible_assessments(request.user)
    )
    return get_object_or_404(source, pk=assessment_id)


class AssessmentDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Assessment detail", responses={200: AssessmentSerializer}, tags=ASSESSMENTS_TAG
    )
    def get(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id)
        if access.can_manage_assessment(request.user, assessment):
            return Response(AssessmentSerializer(assessment).data)

        assessment.my_result_row = (
            access.visible_results(request.user).filter(assessment=assessment).first()
        )
        return Response(StudentAssessmentSerializer(assessment).data)

    @extend_schema(
        summary="Edit an assessment",
        request=AssessmentWriteSerializer,
        responses={200: AssessmentSerializer},
        tags=ASSESSMENTS_TAG,
    )
    def patch(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        serializer = AssessmentWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)

        module_id = fields.pop("module", None)
        if module_id:
            fields["module"] = get_object_or_404(
                Module.objects.filter(course=assessment.course), pk=module_id
            )

        assessment = services.update_assessment(assessment=assessment, actor=request.user, **fields)
        return Response(AssessmentSerializer(assessment).data)

    @extend_schema(
        summary="Delete an assessment",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=ASSESSMENTS_TAG,
    )
    def delete(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        services.delete_assessment(assessment=assessment, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class AssessmentStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish, close or archive an assessment",
        request=AssessmentStatusSerializer,
        responses={200: AssessmentSerializer},
        tags=ASSESSMENTS_TAG,
    )
    def post(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        serializer = AssessmentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assessment = services.set_assessment_status(
            assessment=assessment,
            actor=request.user,
            status=serializer.validated_data["status"],
        )
        return Response(AssessmentSerializer(assessment).data)


class MyAssessmentsView(ListAPIView):
    """A student's tests, each with their own result attached."""

    permission_classes = (IsActiveUser,)
    serializer_class = StudentAssessmentSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = AssessmentFilterSet
    ordering_fields = ("scheduled_for", "created_at")
    ordering = ("-scheduled_for",)

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return Assessment.objects.none()
        return access.visible_assessments(self.request.user)

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        if rows:
            results = {
                row.assessment_id: row
                for row in access.visible_results(self.request.user).filter(
                    assessment_id__in=[item.pk for item in rows]
                )
            }
            for item in rows:
                item.my_result_row = results.get(item.pk)
        return page

    @extend_schema(summary="My assessments", tags=ASSESSMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class MarksSheetView(APIView):
    """The whole cohort with their marks, prefilled — the marking screen.

    Shaped like the attendance register for the same reason: a trainer works
    through a class in one pass, not one student per request.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Marks sheet for an assessment",
        responses={200: MarksSheetSerializer},
        tags=RESULTS_TAG,
    )
    def get(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        existing = {
            row.enrollment_id: row for row in assessment.results.select_related("enrollment")
        }

        entries = []
        for enrollment in services.cohort_for(assessment):
            result = existing.get(enrollment.pk)
            entries.append(
                {
                    "enrollment_id": enrollment.pk,
                    "student_code": enrollment.student.student_id,
                    "student_name": enrollment.student.user.get_full_name(),
                    "marks_obtained": result.marks_obtained if result else None,
                    "is_absent": bool(result and result.is_absent),
                    "remarks": result.remarks if result else "",
                    "source": result.source if result else "",
                }
            )

        return Response(
            MarksSheetSerializer(
                {
                    "assessment": assessment,
                    "entries": entries,
                    "can_record": access.can_record_results(request.user, assessment),
                }
            ).data
        )

    @extend_schema(
        summary="Record one student's result",
        request=RecordResultSerializer,
        responses={200: StaffResultSerializer},
        tags=RESULTS_TAG,
    )
    def post(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        if not access.can_record_results(request.user, assessment):
            return _forbidden(request, "You cannot record results for this assessment.")

        serializer = RecordResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        enrollment = get_object_or_404(services.cohort_for(assessment), pk=data["enrollment_id"])
        result, _created = services.record_result(
            assessment=assessment,
            enrollment=enrollment,
            actor=request.user,
            marks=data.get("marks"),
            is_absent=data.get("is_absent", False),
            remarks=data.get("remarks", ""),
        )
        return Response(StaffResultSerializer(result).data)


class ResultFilterSet(django_filters.FilterSet):
    assessment = django_filters.UUIDFilter(field_name="assessment_id")
    batch = django_filters.UUIDFilter(field_name="assessment__batch_id")
    is_absent = django_filters.BooleanFilter(field_name="is_absent")
    source = django_filters.CharFilter(field_name="source", lookup_expr="exact")

    class Meta:
        model = AssessmentResult
        fields = ("assessment", "batch", "is_absent", "source")


class MyResultsView(ListAPIView):
    """A student's own marks across every assessment they can see."""

    permission_classes = (IsActiveUser,)
    serializer_class = ResultSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ResultFilterSet
    ordering_fields = ("recorded_at",)
    ordering = ("-recorded_at",)

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return AssessmentResult.objects.none()
        return access.visible_results(self.request.user)

    @extend_schema(summary="My results", tags=RESULTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Import — preview, then confirm
# ---------------------------------------------------------------------------


class ResultImportPreviewView(APIView):
    """Step one. Reads the file, validates it, writes **no** results."""

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(
        summary="Preview a result import",
        request=ImportUploadSerializer,
        responses={201: ImportSerializer},
        tags=RESULTS_TAG,
    )
    def post(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        if not access.can_record_results(request.user, assessment):
            return _forbidden(request, "You cannot import results for this assessment.")

        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = importers.preview_import(
            assessment=assessment,
            actor=request.user,
            uploaded_file=serializer.validated_data["file"],
        )
        return Response(ImportSerializer(run).data, status=http_status.HTTP_201_CREATED)

    @extend_schema(
        summary="Imports for an assessment",
        responses={200: ImportSerializer(many=True)},
        tags=RESULTS_TAG,
    )
    def get(self, request, assessment_id):
        assessment = _assessment_for(request, assessment_id, manage=True)
        runs = assessment.imports.all()[:50]
        return Response(ImportSerializer(runs, many=True).data)


def _import_for(request, import_id) -> ResultImport:
    return get_object_or_404(
        ResultImport.objects.filter(
            assessment__in=access.manageable_assessments(request.user)
        ).select_related("assessment"),
        pk=import_id,
    )


class ResultImportDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Import preview detail", responses={200: ImportSerializer}, tags=RESULTS_TAG
    )
    def get(self, request, import_id):
        return Response(ImportSerializer(_import_for(request, import_id)).data)


class ResultImportConfirmView(APIView):
    """Step two. Applies the previewed rows in one transaction."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Confirm a result import",
        request=None,
        responses={200: ImportSerializer},
        tags=RESULTS_TAG,
    )
    def post(self, request, import_id):
        run = _import_for(request, import_id)
        if not access.can_record_results(request.user, run.assessment):
            return _forbidden(request, "You cannot import results for this assessment.")
        run = importers.confirm_import(run=run, actor=request.user)
        return Response(ImportSerializer(run).data)


class ResultImportRejectView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Discard a result import",
        request=None,
        responses={200: ImportSerializer},
        tags=RESULTS_TAG,
    )
    def post(self, request, import_id):
        run = _import_for(request, import_id)
        run = importers.reject_import(run=run, actor=request.user)
        return Response(ImportSerializer(run).data)


# Referenced by the admin listing so the status vocabulary has one home.
IMPORT_STATUSES = ImportStatus
