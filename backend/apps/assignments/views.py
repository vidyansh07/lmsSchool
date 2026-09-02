"""Assignment API.

The authorization shape is the one used everywhere in this codebase: the record
is fetched from a queryset the caller is already entitled to, so an id from
somebody else's course produces 404 before any permission code runs. There is
no "load it, then check it" path here for an attacker to race.
"""

from __future__ import annotations

import django_filters
from django.http import FileResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.common.uploads import SUBMISSION_CONTENT_TYPE, safe_download_name
from apps.courses import access as course_access
from apps.courses.models import Course, Lesson, Module

from . import access, services
from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentSubmission,
    SubmissionFile,
)
from .serializers import (
    AssignmentSerializer,
    AssignmentStatusSerializer,
    AssignmentWriteSerializer,
    AttachmentSerializer,
    AttachmentUploadSerializer,
    GradeSerializer,
    ReturnSerializer,
    StaffSubmissionSerializer,
    StudentAssignmentSerializer,
    SubmissionSerializer,
    SubmitSerializer,
)

ASSIGNMENTS_TAG = ["assignments"]
SUBMISSIONS_TAG = ["submissions"]


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


def _resolve_relations(request, course: Course, data: dict) -> dict:
    """Turn the submitted ids into objects, inside the caller's own visibility.

    A module id the caller cannot see must not become a 400 that confirms the
    module exists, so every lookup runs against a scoped queryset.
    """
    fields = dict(data)
    module_id = fields.pop("module", None)
    lesson_id = fields.pop("lesson", None)
    batch_id = fields.pop("batch", None)

    if module_id:
        fields["module"] = get_object_or_404(Module.objects.filter(course=course), pk=module_id)
    if lesson_id:
        fields["lesson"] = get_object_or_404(
            Lesson.objects.filter(module__course=course), pk=lesson_id
        )
    if batch_id:
        fields["batch"] = get_object_or_404(
            batch_access.visible_batches(request.user).filter(course=course), pk=batch_id
        )
    return fields


class AssignmentFilterSet(django_filters.FilterSet):
    course = django_filters.UUIDFilter(field_name="course_id")
    batch = django_filters.UUIDFilter(field_name="batch_id")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    due_before = django_filters.IsoDateTimeFilter(field_name="due_at", lookup_expr="lte")
    due_after = django_filters.IsoDateTimeFilter(field_name="due_at", lookup_expr="gte")

    class Meta:
        model = Assignment
        fields = ("course", "batch", "status")


class AssignmentListView(ListAPIView):
    """Assignments the caller may see."""

    permission_classes = (IsActiveUser,)
    serializer_class = AssignmentSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AssignmentFilterSet
    search_fields = ("title", "code")
    ordering_fields = ("due_at", "created_at", "title")
    ordering = ("-created_at",)

    def get_queryset(self):
        return access.visible_assignments(self.request.user).prefetch_related("attachments")

    @extend_schema(summary="List assignments", tags=ASSIGNMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CourseAssignmentsView(APIView):
    """Create work on a course."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Create an assignment",
        request=AssignmentWriteSerializer,
        responses={201: AssignmentSerializer},
        tags=ASSIGNMENTS_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)

        serializer = AssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = _resolve_relations(request, course, serializer.validated_data)

        if not access.can_set_assignments_on(request.user, course, fields.get("batch")):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="course",
                resource_id=course.pk,
                result="failure",
                context={"attempted": "assignment.create"},
            )
            return _forbidden(request, "You cannot set assignments on this course.")

        assignment = services.create_assignment(actor=request.user, course=course, **fields)
        return Response(AssignmentSerializer(assignment).data, status=http_status.HTTP_201_CREATED)


def _assignment_for(request, assignment_id, *, manage: bool = False) -> Assignment:
    """Fetch an assignment the caller may see, or may manage."""
    source = (
        access.manageable_assignments(request.user)
        if manage
        else access.visible_assignments(request.user)
    )
    return get_object_or_404(source.prefetch_related("attachments"), pk=assignment_id)


class AssignmentDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Assignment detail", responses={200: AssignmentSerializer}, tags=ASSIGNMENTS_TAG
    )
    def get(self, request, assignment_id):
        assignment = _assignment_for(request, assignment_id)
        if access.can_manage_assignment(request.user, assignment):
            return Response(AssignmentSerializer(assignment).data)

        # A student gets the student shape, with their own latest attempt
        # attached — never anybody else's.
        assignment.my_latest_submission = (
            access.visible_submissions(request.user)
            .filter(assignment=assignment)
            .order_by("-attempt")
            .first()
        )
        return Response(StudentAssignmentSerializer(assignment).data)

    @extend_schema(
        summary="Edit an assignment",
        request=AssignmentWriteSerializer,
        responses={200: AssignmentSerializer},
        tags=ASSIGNMENTS_TAG,
    )
    def patch(self, request, assignment_id):
        assignment = _assignment_for(request, assignment_id, manage=True)
        serializer = AssignmentWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = _resolve_relations(request, assignment.course, serializer.validated_data)
        assignment = services.update_assignment(assignment=assignment, actor=request.user, **fields)
        return Response(AssignmentSerializer(assignment).data)

    @extend_schema(
        summary="Delete an assignment",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=ASSIGNMENTS_TAG,
    )
    def delete(self, request, assignment_id):
        assignment = _assignment_for(request, assignment_id, manage=True)
        services.delete_assignment(assignment=assignment, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class AssignmentStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish, close or archive an assignment",
        request=AssignmentStatusSerializer,
        responses={200: AssignmentSerializer},
        tags=ASSIGNMENTS_TAG,
    )
    def post(self, request, assignment_id):
        assignment = _assignment_for(request, assignment_id, manage=True)
        serializer = AssignmentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.set_assignment_status(
            assignment=assignment, actor=request.user, status=serializer.validated_data["status"]
        )
        return Response(AssignmentSerializer(assignment).data)


class AssignmentAttachmentsView(APIView):
    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        summary="Attach a file to an assignment",
        request=AttachmentUploadSerializer,
        responses={201: AttachmentSerializer},
        tags=ASSIGNMENTS_TAG,
    )
    def post(self, request, assignment_id):
        assignment = _assignment_for(request, assignment_id, manage=True)
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attachment = services.add_attachment(
            assignment=assignment,
            actor=request.user,
            uploaded_file=serializer.validated_data["file"],
            title=serializer.validated_data["title"],
        )
        return Response(AttachmentSerializer(attachment).data, status=http_status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download an assignment attachment",
        responses={200: OpenApiResponse(description="The file, as an attachment.")},
        tags=ASSIGNMENTS_TAG,
    )
    def get(self, request, attachment_id):
        attachment = get_object_or_404(
            AssignmentAttachment.objects.filter(
                assignment__in=access.visible_assignments(request.user)
            ).select_related("assignment"),
            pk=attachment_id,
        )
        if not attachment.file:
            raise Http404
        response = FileResponse(attachment.file.open("rb"), content_type=attachment.content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{safe_download_name(attachment.title, "")}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Remove an assignment attachment",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=ASSIGNMENTS_TAG,
    )
    def delete(self, request, attachment_id):
        attachment = get_object_or_404(
            AssignmentAttachment.objects.filter(
                assignment__in=access.manageable_assignments(request.user)
            ).select_related("assignment"),
            pk=attachment_id,
        )
        services.remove_attachment(attachment=attachment, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Submitting and marking
# ---------------------------------------------------------------------------


class SubmitView(APIView):
    """A student hands in one attempt."""

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(
        summary="Submit an assignment",
        request=SubmitSerializer,
        responses={201: SubmissionSerializer},
        tags=SUBMISSIONS_TAG,
    )
    def post(self, request, assignment_id):
        assignment = get_object_or_404(access.visible_assignments(request.user), pk=assignment_id)
        student = batch_access.student_profile(request.user)
        if student is None:
            return _forbidden(request, "Only enrolled students submit assignments.")

        enrollment = services.enrollment_for(assignment=assignment, student=student)
        if enrollment is None:
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="assignment",
                resource_id=assignment.pk,
                result="failure",
                context={"attempted": "assignment.submit"},
            )
            return _forbidden(request, "You are not enrolled on the course this work belongs to.")

        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # `request.data.getlist` is what a real multipart client sends; the
        # serializer's ListField covers JSON and test clients.
        files = data.get("files") or []
        if not files and hasattr(request.data, "getlist"):
            files = request.data.getlist("files")

        submission = services.submit_assignment(
            assignment=assignment,
            enrollment=enrollment,
            actor=request.user,
            files=files,
            text_answer=data.get("text_answer", ""),
            link_url=data.get("link_url", ""),
        )
        return Response(SubmissionSerializer(submission).data, status=http_status.HTTP_201_CREATED)


class SubmissionFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    assignment = django_filters.UUIDFilter(field_name="assignment_id")
    batch = django_filters.UUIDFilter(field_name="enrollment__batch_id")
    is_late = django_filters.BooleanFilter(field_name="is_late")

    class Meta:
        model = AssignmentSubmission
        fields = ("status", "assignment", "batch", "is_late")


class AssignmentSubmissionsView(ListAPIView):
    """Every attempt on one assignment — the marking queue."""

    permission_classes = (IsActiveUser,)
    serializer_class = StaffSubmissionSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = SubmissionFilterSet
    ordering_fields = ("submitted_at", "attempt", "marks_awarded")
    ordering = ("-submitted_at",)
    # Declared so schema generation can find the model without a request; the
    # real queryset is built per request below.
    queryset = AssignmentSubmission.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AssignmentSubmission.objects.none()
        assignment = _assignment_for(self.request, self.kwargs["assignment_id"], manage=True)
        return access.visible_submissions(self.request.user).filter(assignment=assignment)

    @extend_schema(
        summary="Submissions on an assignment",
        parameters=[OpenApiParameter("status", str), OpenApiParameter("is_late", bool)],
        tags=SUBMISSIONS_TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MySubmissionsView(ListAPIView):
    """A student's own attempts, newest first."""

    permission_classes = (IsActiveUser,)
    serializer_class = SubmissionSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = SubmissionFilterSet
    ordering_fields = ("submitted_at", "attempt")
    ordering = ("-submitted_at",)

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return AssignmentSubmission.objects.none()
        return access.visible_submissions(self.request.user)

    @extend_schema(summary="My submissions", tags=SUBMISSIONS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MyAssignmentsView(ListAPIView):
    """A student's work list, each with their own latest attempt attached."""

    permission_classes = (IsActiveUser,)
    serializer_class = StudentAssignmentSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = AssignmentFilterSet
    ordering_fields = ("due_at", "created_at")
    # Soonest due first, then most recently set. The second key matters: most
    # assignments carry no due date, and without it a student's newest work
    # sorts arbitrarily among every undated one on the course.
    ordering = ("due_at", "-created_at")

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return Assignment.objects.none()
        return access.visible_assignments(self.request.user).prefetch_related("attachments")

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        self._attach_submissions(rows)
        return page

    def _attach_submissions(self, rows) -> None:
        """One extra query for the whole page, not one per assignment."""
        if not rows:
            return
        latest: dict = {}
        submissions = (
            access.visible_submissions(self.request.user)
            .filter(assignment_id__in=[row.pk for row in rows])
            .order_by("assignment_id", "attempt")
        )
        for submission in submissions:
            latest[submission.assignment_id] = submission
        for row in rows:
            row.my_latest_submission = latest.get(row.pk)

    @extend_schema(summary="My assignments", tags=ASSIGNMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _submission_for(request, submission_id, *, grade: bool = False) -> AssignmentSubmission:
    submission = get_object_or_404(access.visible_submissions(request.user), pk=submission_id)
    if grade and not access.can_grade(request.user, submission.assignment):
        raise Http404
    return submission


class SubmissionDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Submission detail",
        responses={200: StaffSubmissionSerializer},
        tags=SUBMISSIONS_TAG,
    )
    def get(self, request, submission_id):
        submission = _submission_for(request, submission_id)
        if access.can_grade(request.user, submission.assignment):
            return Response(StaffSubmissionSerializer(submission).data)
        return Response(SubmissionSerializer(submission).data)


class GradeSubmissionView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Grade a submission",
        request=GradeSerializer,
        responses={200: StaffSubmissionSerializer},
        tags=SUBMISSIONS_TAG,
    )
    def post(self, request, submission_id):
        submission = _submission_for(request, submission_id, grade=True)
        serializer = GradeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = services.grade_submission(
            submission=submission,
            actor=request.user,
            marks=serializer.validated_data["marks"],
            feedback=serializer.validated_data.get("feedback", ""),
        )
        return Response(StaffSubmissionSerializer(submission).data)


class ReturnSubmissionView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Return a submission for rework",
        request=ReturnSerializer,
        responses={200: StaffSubmissionSerializer},
        tags=SUBMISSIONS_TAG,
    )
    def post(self, request, submission_id):
        submission = _submission_for(request, submission_id, grade=True)
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = services.return_submission(
            submission=submission,
            actor=request.user,
            feedback=serializer.validated_data["feedback"],
        )
        return Response(StaffSubmissionSerializer(submission).data)


class SubmissionFileDownloadView(APIView):
    """Serve a submitted file.

    Everything about this response is deliberate. The bytes are found through
    ``visible_submissions`` so a classmate's file id 404s. The content type is
    always ``application/octet-stream`` and the disposition always
    ``attachment`` — submitted code is never rendered in a browser, which is
    what stops an ``.html`` hand-in from becoming stored XSS against the
    trainer marking it. The download name is rebuilt from the assignment code
    and the validated extension, never echoed from the uploaded string.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a submitted file",
        responses={200: OpenApiResponse(description="The file, as an attachment.")},
        tags=SUBMISSIONS_TAG,
    )
    def get(self, request, file_id):
        stored = get_object_or_404(
            SubmissionFile.objects.filter(
                submission__in=access.visible_submissions(request.user)
            ).select_related("submission", "submission__assignment"),
            pk=file_id,
        )
        if not stored.file:
            raise Http404

        submission = stored.submission
        record(
            action=AuditAction.SUBMISSION_FILE_DOWNLOADED,
            actor=request.user,
            resource_type="submission_file",
            resource_id=stored.pk,
            context={
                "assignment": submission.assignment.code,
                "attempt": submission.attempt,
            },
            durable=False,
        )

        name = safe_download_name(
            f"{submission.assignment.code}-attempt-{submission.attempt}", stored.extension
        )
        response = FileResponse(stored.file.open("rb"), content_type=SUBMISSION_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-store"
        return response
