"""Project API.

Same authorization shape as everywhere else: the record is resolved inside a
queryset the caller is entitled to, so an id from another course 404s before
any permission code runs.
"""

from __future__ import annotations

import django_filters
from django.http import FileResponse, Http404
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
from apps.common.uploads import SUBMISSION_CONTENT_TYPE, safe_download_name
from apps.courses import access as course_access
from apps.courses.models import Module
from apps.trainers.models import TrainerProfile

from . import access, services
from .models import Project, ProjectFile, StudentProject
from .serializers import (
    AssignResultSerializer,
    ProjectSerializer,
    ProjectStatusSerializer,
    ProjectWorkWriteSerializer,
    ProjectWriteSerializer,
    RequiredProjectProgressSerializer,
    ReviewerProjectSerializer,
    ReviewSerializer,
    StudentProjectListSerializer,
    StudentProjectSerializer,
)

PROJECTS_TAG = ["projects"]


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


def _resolve_relations(request, course, data: dict) -> dict:
    fields = dict(data)
    module_id = fields.pop("module", None)
    batch_id = fields.pop("batch", None)
    reviewer_id = fields.pop("reviewer", None)

    if module_id:
        fields["module"] = get_object_or_404(Module.objects.filter(course=course), pk=module_id)
    if batch_id:
        fields["batch"] = get_object_or_404(
            batch_access.visible_batches(request.user).filter(course=course), pk=batch_id
        )
    if reviewer_id:
        fields["reviewer"] = get_object_or_404(TrainerProfile.objects.all(), pk=reviewer_id)
    return fields


class ProjectFilterSet(django_filters.FilterSet):
    course = django_filters.UUIDFilter(field_name="course_id")
    batch = django_filters.UUIDFilter(field_name="batch_id")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    kind = django_filters.CharFilter(field_name="kind", lookup_expr="exact")
    is_required = django_filters.BooleanFilter(field_name="is_required")

    class Meta:
        model = Project
        fields = ("course", "batch", "status", "kind", "is_required")


class ProjectListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ProjectSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ProjectFilterSet
    search_fields = ("title", "code")
    ordering_fields = ("end_date", "created_at", "title")
    ordering = ("-created_at",)

    def get_queryset(self):
        return access.visible_projects(self.request.user)

    @extend_schema(summary="List projects", tags=PROJECTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CourseProjectsView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Create a project",
        request=ProjectWriteSerializer,
        responses={201: ProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)
        serializer = ProjectWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = _resolve_relations(request, course, serializer.validated_data)

        if not access.can_set_projects_on(request.user, course, fields.get("batch")):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="course",
                resource_id=course.pk,
                result="failure",
                context={"attempted": "project.create"},
            )
            return _forbidden(request, "You cannot set projects on this course.")

        project = services.create_project(actor=request.user, course=course, **fields)
        return Response(ProjectSerializer(project).data, status=http_status.HTTP_201_CREATED)


def _project_for(request, project_id, *, manage: bool = False) -> Project:
    source = (
        access.manageable_projects(request.user)
        if manage
        else access.visible_projects(request.user)
    )
    return get_object_or_404(source, pk=project_id)


class ProjectDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(summary="Project detail", responses={200: ProjectSerializer}, tags=PROJECTS_TAG)
    def get(self, request, project_id):
        project = _project_for(request, project_id)
        if access.can_manage_project(request.user, project):
            return Response(ProjectSerializer(project).data)

        student = batch_access.student_profile(request.user)
        project.my_work_row = (
            services.student_project_for(project=project, student=student)
            if student is not None
            else None
        )
        return Response(StudentProjectListSerializer(project).data)

    @extend_schema(
        summary="Edit a project",
        request=ProjectWriteSerializer,
        responses={200: ProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def patch(self, request, project_id):
        project = _project_for(request, project_id, manage=True)
        serializer = ProjectWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = _resolve_relations(request, project.course, serializer.validated_data)
        project = services.update_project(project=project, actor=request.user, **fields)
        return Response(ProjectSerializer(project).data)

    @extend_schema(
        summary="Delete a project",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=PROJECTS_TAG,
    )
    def delete(self, request, project_id):
        project = _project_for(request, project_id, manage=True)
        services.delete_project(project=project, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class ProjectStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish, close or archive a project",
        request=ProjectStatusSerializer,
        responses={200: ProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def post(self, request, project_id):
        project = _project_for(request, project_id, manage=True)
        serializer = ProjectStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = services.set_project_status(
            project=project, actor=request.user, status=serializer.validated_data["status"]
        )
        return Response(ProjectSerializer(project).data)


class ProjectAssignView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Assign a project to its cohort",
        request=None,
        responses={200: AssignResultSerializer},
        tags=PROJECTS_TAG,
    )
    def post(self, request, project_id):
        project = _project_for(request, project_id, manage=True)
        result = services.assign_project(project=project, actor=request.user)
        return Response(AssignResultSerializer(result).data)


class ProjectWorkListView(ListAPIView):
    """Every student's work on one project — the review queue."""

    permission_classes = (IsActiveUser,)
    serializer_class = ReviewerProjectSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering_fields = ("submitted_at", "status", "marks_awarded")
    ordering = ("-submitted_at",)
    queryset = StudentProject.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StudentProject.objects.none()
        project = _project_for(self.request, self.kwargs["project_id"], manage=True)
        return access.visible_student_projects(self.request.user).filter(project=project)

    @extend_schema(summary="Work submitted on a project", tags=PROJECTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MyProjectsView(ListAPIView):
    """A student's projects, each with their own row attached."""

    permission_classes = (IsActiveUser,)
    serializer_class = StudentProjectListSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ProjectFilterSet
    ordering_fields = ("end_date", "created_at")
    # Soonest due first, then most recently set. The second key matters: most
    # projects carry no due date, and without it a student's newest work sorts
    # arbitrarily among every undated brief on the course.
    ordering = ("end_date", "-created_at")

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return Project.objects.none()
        return access.visible_projects(self.request.user)

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        if not rows:
            return page

        student = batch_access.student_profile(self.request.user)
        # Rows created here, in one batch, rather than left to a follow-up
        # request per project: a student's project list is one call, not one
        # plus one for every project on the course.
        existing = (
            services.ensure_student_projects(projects=list(rows), student=student)
            if student is not None
            else {}
        )
        for item in rows:
            item.my_work_row = existing.get(item.pk)
        return page

    @extend_schema(summary="My projects", tags=PROJECTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _work_for(request, work_id, *, review: bool = False) -> StudentProject:
    work = get_object_or_404(access.visible_student_projects(request.user), pk=work_id)
    if review and not access.can_review(request.user, work.project):
        raise Http404
    return work


class ProjectWorkView(APIView):
    """A student's own project row: read it, save progress, hand it in."""

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(
        summary="My work on a project",
        responses={200: StudentProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def get(self, request, project_id):
        project = _project_for(request, project_id)
        student = batch_access.student_profile(request.user)
        if student is None:
            return _forbidden(request, "Only enrolled students have project work.")
        work = services.student_project_for(project=project, student=student)
        if work is None:
            return _forbidden(
                request, "You are not enrolled on the course this project belongs to."
            )
        return Response(StudentProjectSerializer(work).data)

    @extend_schema(
        summary="Save progress on my project",
        request=ProjectWorkWriteSerializer,
        responses={200: StudentProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def patch(self, request, project_id):
        work, error = self._own_work(request, project_id)
        if error is not None:
            return error
        data, files = self._payload(request)
        work = services.save_progress(work=work, actor=request.user, files=files, **data)
        return Response(StudentProjectSerializer(work).data)

    @extend_schema(
        summary="Hand in my project",
        request=ProjectWorkWriteSerializer,
        responses={200: StudentProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def post(self, request, project_id):
        work, error = self._own_work(request, project_id)
        if error is not None:
            return error
        data, files = self._payload(request)
        work = services.submit_project(work=work, actor=request.user, files=files, **data)
        return Response(StudentProjectSerializer(work).data)

    def _own_work(self, request, project_id):
        project = _project_for(request, project_id)
        student = batch_access.student_profile(request.user)
        if student is None:
            return None, _forbidden(request, "Only enrolled students submit projects.")
        work = services.student_project_for(project=project, student=student)
        if work is None:
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="project",
                resource_id=project.pk,
                result="failure",
                context={"attempted": "project.submit"},
            )
            return None, _forbidden(
                request, "You are not enrolled on the course this project belongs to."
            )
        return work, None

    @staticmethod
    def _payload(request):
        serializer = ProjectWorkWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        files = data.pop("files", None) or []
        if not files and hasattr(request.data, "getlist"):
            files = request.data.getlist("files")
        return data, files


class ProjectReviewView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Review a student's project",
        request=ReviewSerializer,
        responses={200: ReviewerProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def post(self, request, work_id):
        work = _work_for(request, work_id, review=True)
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        work = services.review_project(
            work=work,
            actor=request.user,
            outcome=data["outcome"],
            feedback=data.get("feedback", ""),
            marks=data.get("marks"),
            rubric_scores=data.get("rubric_scores"),
        )
        return Response(ReviewerProjectSerializer(work).data)


class ProjectWorkDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="One student's project work",
        responses={200: ReviewerProjectSerializer},
        tags=PROJECTS_TAG,
    )
    def get(self, request, work_id):
        work = _work_for(request, work_id)
        if access.can_review(request.user, work.project):
            return Response(ReviewerProjectSerializer(work).data)
        return Response(StudentProjectSerializer(work).data)


class ProjectFileView(APIView):
    """Serve or remove a deliverable file.

    Identical response rules to an assignment submission: opaque content type,
    attachment disposition, ``nosniff`` and a sandbox CSP, so a submitted
    ``.html`` deliverable is never rendered for the reviewer opening it.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a project file",
        responses={200: OpenApiResponse(description="The file, as an attachment.")},
        tags=PROJECTS_TAG,
    )
    def get(self, request, file_id):
        stored = get_object_or_404(
            ProjectFile.objects.filter(
                student_project__in=access.visible_student_projects(request.user)
            ).select_related("student_project", "student_project__project"),
            pk=file_id,
        )
        if not stored.file:
            raise Http404

        work = stored.student_project
        record(
            action=AuditAction.PROJECT_FILE_DOWNLOADED,
            actor=request.user,
            resource_type="project_file",
            resource_id=stored.pk,
            context={"project": work.project.code},
            durable=False,
        )

        name = safe_download_name(f"{work.project.code}-{work.enrollment_id}", stored.extension)
        response = FileResponse(stored.file.open("rb"), content_type=SUBMISSION_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Remove a file from my project",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=PROJECTS_TAG,
    )
    def delete(self, request, file_id):
        student = batch_access.student_profile(request.user)
        if student is None:
            return _forbidden(request, "Only the student who uploaded it may remove it.")
        stored = get_object_or_404(
            ProjectFile.objects.filter(
                student_project__in=access.visible_student_projects(request.user),
                student_project__enrollment__student=student,
            ),
            pk=file_id,
        )
        services.remove_file(stored=stored, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class MyRequiredProjectsView(APIView):
    """§5.2: whether every required project is finished, and which are not."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My required-project progress",
        responses={200: RequiredProjectProgressSerializer(many=True)},
        tags=PROJECTS_TAG,
    )
    def get(self, request):
        from apps.enrollments.models import Enrollment

        student = batch_access.student_profile(request.user)
        if student is None:
            return Response([])

        payload = []
        rows = Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        for enrollment in rows:
            progress = services.required_project_progress(enrollment)
            payload.append(
                {
                    "enrollment_id": str(enrollment.pk),
                    "course_title": enrollment.course.title,
                    "batch_code": enrollment.batch.code,
                    **RequiredProjectProgressSerializer(progress).data,
                }
            )
        return Response(payload)
