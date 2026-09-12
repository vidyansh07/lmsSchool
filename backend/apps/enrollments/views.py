"""Enrolment and progress API.

The security rule that matters most here: a student may only ever see and act on
their *own* enrolment. That is enforced by resolving every record inside
``access.visible_enrollments``, which for a student is filtered to their own
profile — so another student's enrolment id is simply not found.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.batches import access
from apps.batches.models import Batch
from apps.common.permissions import IsActiveUser
from apps.courses.models import Lesson
from apps.fees.queries import annotate_enrollment_fee
from apps.students.models import StudentProfile

from . import services
from .models import Enrollment
from .serializers import (
    AdminEnrollmentSerializer,
    CourseProgressSerializer,
    EnrollmentSerializer,
    EnrollmentStatusSerializer,
    EnrolStudentSerializer,
    LessonCompletionSerializer,
    LessonProgressSerializer,
)

ENROLLMENTS_TAG = ["enrollments"]
PROGRESS_TAG = ["progress"]


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


class EnrollmentFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    batch = django_filters.UUIDFilter(field_name="batch_id")
    course = django_filters.CharFilter(field_name="course__slug", lookup_expr="iexact")

    class Meta:
        model = Enrollment
        fields = ("status", "batch", "course")


class EnrollmentListCreateView(ListCreateAPIView):
    """List enrolments, or enrol a student.

    A student sees only their own rows; a trainer sees the enrolments on the
    batches they teach; an administrator sees everything. The queryset decides.
    """

    permission_classes = (IsActiveUser,)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = EnrollmentFilterSet
    search_fields = ("code", "student__student_id", "student__user__email", "batch__code")
    ordering_fields = ("enrolled_at", "status", "code")
    ordering = ("-enrolled_at",)

    def get_queryset(self):
        queryset = access.visible_enrollments(self.request.user)
        if has_capability(self.request.user, Capability.FEE_VIEW_ANY):
            queryset = annotate_enrollment_fee(queryset)
        return queryset

    def get_serializer_class(self):
        # A student never receives the administrative status note.
        if has_capability(self.request.user, Capability.ENROLMENT_VIEW_ANY):
            return AdminEnrollmentSerializer
        if access.trainer_profile(self.request.user) is not None:
            return AdminEnrollmentSerializer
        return EnrollmentSerializer

    @extend_schema(summary="List enrolments", tags=ENROLLMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Enrol a student on a batch",
        request=EnrolStudentSerializer,
        responses={
            201: AdminEnrollmentSerializer,
            409: OpenApiResponse(description="Batch full, or the student is already enrolled."),
        },
        tags=ENROLLMENTS_TAG,
    )
    def post(self, request, *args, **kwargs):
        # Enrolling is an institutional act. A student cannot enrol themselves,
        # and — more importantly — cannot enrol anybody else.
        if not has_capability(request.user, Capability.ENROLMENT_CREATE):
            return _forbidden(request, "You do not have permission to enrol students.")

        serializer = EnrolStudentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        student = get_object_or_404(
            StudentProfile.objects.select_related("user"), pk=data.pop("student_id")
        )
        batch = get_object_or_404(Batch.objects.select_related("course"), pk=data.pop("batch_id"))

        enrollment = services.enrol_student(
            student=student, batch=batch, actor=request.user, **data
        )
        return Response(
            AdminEnrollmentSerializer(enrollment).data, status=http_status.HTTP_201_CREATED
        )


def _enrollment_for(request, enrollment_id) -> Enrollment:
    return get_object_or_404(access.visible_enrollments(request.user), pk=enrollment_id)


class EnrollmentDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Retrieve an enrolment", responses={200: EnrollmentSerializer}, tags=ENROLLMENTS_TAG
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        serializer = (
            AdminEnrollmentSerializer
            if access.can_manage_enrollment(request.user, enrollment)
            or access.trainer_profile(request.user) is not None
            else EnrollmentSerializer
        )
        return Response(serializer(enrollment).data)


class EnrollmentStatusView(APIView):
    """Suspend, reactivate, complete or cancel an enrolment.

    Administrators only. A trainer may see their students but not change their
    standing, and a student may not change their own — both are institutional
    decisions, and both are audited.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Change an enrolment's status",
        request=EnrollmentStatusSerializer,
        responses={
            200: AdminEnrollmentSerializer,
            400: OpenApiResponse(description="Invalid transition."),
        },
        tags=ENROLLMENTS_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        if not access.can_manage_enrollment(request.user, enrollment):
            return _forbidden(request, "You do not have permission to change this enrolment.")

        serializer = EnrollmentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_enrollment_status(
            enrollment=enrollment,
            target=serializer.validated_data["status"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(AdminEnrollmentSerializer(updated).data)


class MyEnrollmentsView(APIView):
    """The signed-in student's own enrolments.

    No identifier in the URL, so there is nothing to tamper with.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My enrolments", responses={200: EnrollmentSerializer}, tags=ENROLLMENTS_TAG
    )
    def get(self, request):
        student = access.student_profile(request.user)
        if student is None:
            return Response([])
        enrollments = (
            Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        )
        return Response(EnrollmentSerializer(enrollments, many=True).data)


class EnrollmentProgressView(APIView):
    """Course progress for one enrolment."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Progress on an enrolment",
        responses={200: CourseProgressSerializer},
        tags=PROGRESS_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        summary = services.course_progress(enrollment)
        records = enrollment.lesson_progress.select_related("lesson").all()
        return Response({**summary, "lessons": LessonProgressSerializer(records, many=True).data})


class LessonCompletionView(APIView):
    """Mark a lesson complete, or reopen it.

    Progress is keyed on the enrolment, so this only works for a student with a
    live enrolment — which is also what stops a browsing visitor generating
    progress rows from preview lessons.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Set lesson completion",
        request=LessonCompletionSerializer,
        responses={
            200: LessonProgressSerializer,
            400: OpenApiResponse(description="Not enrolled."),
        },
        tags=PROGRESS_TAG,
    )
    def post(self, request, lesson_id):
        student = access.student_profile(request.user)
        if student is None:
            return _forbidden(request, "Only students track lesson progress.")

        lesson = get_object_or_404(Lesson.objects.select_related("module__course"), pk=lesson_id)
        serializer = LessonCompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        progress = services.set_lesson_completion(
            student=student, lesson=lesson, completed=serializer.validated_data["completed"]
        )
        return Response(LessonProgressSerializer(progress).data)
