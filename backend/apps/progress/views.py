"""Progress and completion API.

One endpoint answers "how is this student doing?" and it is the same endpoint
whether a student, a trainer or an administrator asks — §6.3's rule that nothing
computes progress independently applies to the API surface too, not only to the
Python.
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

from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.enrollments.models import Enrollment

from . import access, services
from .models import CourseCompletion
from .serializers import (
    ApproveCompletionSerializer,
    CompletionSerializer,
    DecisionNoteSerializer,
    EvaluationSerializer,
    ProgressReportSerializer,
    StudentEvaluationSerializer,
)

PROGRESS_TAG = ["progress and completion"]


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


def _enrollment_for(request, enrollment_id) -> Enrollment:
    return get_object_or_404(access.visible_enrollments(request.user), pk=enrollment_id)


def _evaluation_payload(request, enrollment: Enrollment) -> dict:
    result = services.evaluate_enrollment(enrollment)
    completion = CourseCompletion.objects.filter(enrollment=enrollment).first()
    return {**result, "completion": completion}


class MyProgressView(APIView):
    """A student's own progress and completion standing, per enrolment."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My progress",
        responses={200: StudentEvaluationSerializer(many=True)},
        tags=PROGRESS_TAG,
    )
    def get(self, request):
        student = batch_access.student_profile(request.user)
        if student is None:
            return Response([])

        payload = []
        rows = Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        for enrollment in rows:
            # Recomputed on read, so a rule change moves the answer at once.
            services.refresh_completion(enrollment=enrollment, actor=request.user)
            payload.append(
                StudentEvaluationSerializer(_evaluation_payload(request, enrollment)).data
            )
        return Response(payload)


class EnrollmentProgressView(APIView):
    """One enrolment's progress. The owner, their trainer, or staff."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Progress for one enrolment",
        responses={200: EvaluationSerializer},
        tags=PROGRESS_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        services.refresh_completion(enrollment=enrollment, actor=request.user)

        payload = _evaluation_payload(request, enrollment)
        if access.can_decide_completion(request.user) or batch_access.trainer_profile(request.user):
            return Response(EvaluationSerializer(payload).data)
        return Response(StudentEvaluationSerializer(payload).data)


class ProgressReportView(APIView):
    """Just the numbers, without the rules. Used by dashboards."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Progress numbers for one enrolment",
        responses={200: ProgressReportSerializer},
        tags=PROGRESS_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        from .reports import progress_report

        return Response(ProgressReportSerializer(progress_report(enrollment)).data)


class CompletionFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    batch = django_filters.UUIDFilter(field_name="enrollment__batch_id")
    course = django_filters.UUIDFilter(field_name="enrollment__course_id")

    class Meta:
        model = CourseCompletion
        fields = ("status", "batch", "course")


class CompletionListView(ListAPIView):
    """The approval queue."""

    permission_classes = (IsActiveUser,)
    serializer_class = CompletionSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = CompletionFilterSet
    ordering_fields = ("became_eligible_at", "updated_at", "completed_on")
    ordering = ("-became_eligible_at",)

    def get_queryset(self):
        return access.visible_completions(self.request.user)

    @extend_schema(summary="Course completions", tags=PROGRESS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RefreshCompletionsView(APIView):
    """Re-evaluate a batch's cohort in one go.

    Eligibility is derived on read anyway; this exists so an administrator can
    populate the approval queue after changing a rule, rather than waiting for
    each student to load their own dashboard.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Re-evaluate a batch's completions",
        request=None,
        responses={200: CompletionSerializer(many=True)},
        tags=PROGRESS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not access.can_decide_completion(request.user):
            return _forbidden(request, "You cannot evaluate completions.")

        rows = []
        for enrollment in Enrollment.objects.with_related().filter(batch=batch):
            rows.append(services.refresh_completion(enrollment=enrollment, actor=request.user))
        return Response(CompletionSerializer(rows, many=True).data)


class ApproveCompletionView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Approve a course completion",
        request=ApproveCompletionSerializer,
        responses={200: CompletionSerializer},
        tags=PROGRESS_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        if not access.can_decide_completion(request.user):
            return _forbidden(request, "You cannot approve completions.")

        serializer = ApproveCompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        completion = services.approve_completion(
            enrollment=enrollment,
            actor=request.user,
            completed_on=data.get("completed_on"),
            note=data.get("note", ""),
            override=data.get("override", False),
        )
        return Response(CompletionSerializer(completion).data)


class RejectCompletionView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Decline a course completion",
        request=DecisionNoteSerializer,
        responses={200: CompletionSerializer},
        tags=PROGRESS_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        if not access.can_decide_completion(request.user):
            return _forbidden(request, "You cannot decide completions.")

        serializer = DecisionNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        completion = services.reject_completion(
            enrollment=enrollment, actor=request.user, note=serializer.validated_data["note"]
        )
        return Response(CompletionSerializer(completion).data)


class ReopenCompletionView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reopen a decided completion",
        request=DecisionNoteSerializer,
        responses={200: CompletionSerializer},
        tags=PROGRESS_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        if not access.can_decide_completion(request.user):
            return _forbidden(request, "You cannot decide completions.")

        serializer = DecisionNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        completion = services.reopen_completion(
            enrollment=enrollment, actor=request.user, note=serializer.validated_data["note"]
        )
        return Response(CompletionSerializer(completion).data)
