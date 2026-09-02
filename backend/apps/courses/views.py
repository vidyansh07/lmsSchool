"""Course API.

Authorization pattern, applied without exception:

1. Fetch the object from a queryset the caller is already entitled to
   (``access.visible_courses`` / ``access.manageable_courses``).
2. Run the object-level or capability check.
3. Only then serialise.

Step 1 is what makes a guessed identifier useless: an id the caller may not see
is not in the queryset, so it 404s before any permission code runs. Step 2
catches the narrower cases — visible but not editable, readable page but not
readable content.

A ``course_id`` in a URL is never treated as proof of anything.
"""

from __future__ import annotations

import re
import uuid as uuid_module
from pathlib import PurePosixPath

import django_filters
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.common.permissions import HasCapability, IsActiveUser

from . import access, services
from .models import (
    Category,
    Course,
    Lesson,
    LessonResource,
    Module,
    PublishStatus,
    ResourceKind,
    VideoProvider,
)
from .permissions import CanManageCourse, CanPublishCourse, CanViewCourse
from .serializers import (
    AssignAuthorSerializer,
    CategorySerializer,
    CategoryWriteSerializer,
    CourseAssignmentSerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseStatusSerializer,
    CourseThumbnailSerializer,
    CourseWriteSerializer,
    LessonContentSerializer,
    LessonResourceSerializer,
    LessonStatusSerializer,
    LessonSummarySerializer,
    LessonWriteSerializer,
    ModuleSerializer,
    ModuleStatusSerializer,
    ModuleWriteSerializer,
    PublishChecklistSerializer,
    ReorderSerializer,
    ResourceFileUploadSerializer,
    ResourceLinkSerializer,
    ResourceUpdateSerializer,
    VideoPlaybackSerializer,
)

COURSES_TAG = ["courses"]
CATEGORIES_TAG = ["categories"]
CONTENT_TAG = ["course content"]


def _forbidden(request, message: str) -> Response:
    """Permission refusal in the project's shared error envelope."""
    return Response(
        {
            "error": {
                "code": "permission_denied",
                "message": message,
                "request_id": getattr(request, "request_id", "-"),
            }
        },
        status=status.HTTP_403_FORBIDDEN,
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryListCreateView(ListCreateAPIView):
    """List categories, or create one.

    Listing is open to any signed-in user because the catalogue filter needs it.
    Creating requires the management capability.
    """

    serializer_class = CategorySerializer
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("name", "slug")
    ordering_fields = ("position", "name", "created_at")
    ordering = ("position", "name")
    required_capability = Capability.CATEGORY_MANAGE

    def get_permissions(self):
        return [HasCapability()] if self.request.method == "POST" else [IsActiveUser()]

    def get_queryset(self):
        queryset = Category.objects.annotate(
            course_count=Count("courses", filter=Q(courses__status=PublishStatus.PUBLISHED))
        )
        # Only someone who manages categories has a reason to see retired ones.
        if not has_capability(self.request.user, Capability.CATEGORY_MANAGE):
            queryset = queryset.filter(is_active=True)
        return queryset

    @extend_schema(summary="List categories", tags=CATEGORIES_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a category",
        request=CategoryWriteSerializer,
        responses={201: CategorySerializer},
        tags=CATEGORIES_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = services.create_category(actor=request.user, **serializer.validated_data)
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.CATEGORY_MANAGE

    @extend_schema(
        summary="Retrieve a category", responses={200: CategorySerializer}, tags=CATEGORIES_TAG
    )
    def get(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        return Response(CategorySerializer(category).data)

    @extend_schema(
        summary="Update a category",
        request=CategoryWriteSerializer,
        responses={200: CategorySerializer},
        tags=CATEGORIES_TAG,
    )
    def patch(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        serializer = CategoryWriteSerializer(instance=category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_category(
            category=category, actor=request.user, **serializer.validated_data
        )
        return Response(CategorySerializer(updated).data)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseFilterSet(django_filters.FilterSet):
    """Every filter maps to an indexed column or a small enumeration.

    There is no free-form field lookup, so a client cannot craft an expensive
    query — which, with pagination, is what makes §13's "no unbounded queries"
    true rather than aspirational.
    """

    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    difficulty = django_filters.CharFilter(field_name="difficulty", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    visibility = django_filters.CharFilter(field_name="visibility", lookup_expr="exact")

    class Meta:
        model = Course
        fields = ("category", "difficulty", "status", "visibility")


def _annotated(queryset):
    return queryset.annotate(
        module_count=Count("modules", distinct=True),
        lesson_count=Count("modules__lessons", distinct=True),
    )


class CourseListCreateView(ListCreateAPIView):
    """Browse courses, or create one.

    The queryset *is* the authorization: ``access.visible_courses`` returns only
    what the caller may see, so paging, filtering or sorting cannot reach past
    it. A student never receives a draft, whatever they put in the query string.
    """

    permission_classes = (IsActiveUser,)
    serializer_class = CourseListSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = CourseFilterSet
    search_fields = ("title", "code", "short_description", "description")
    ordering_fields = ("title", "created_at", "published_at", "difficulty")
    ordering = ("-created_at",)

    def get_queryset(self):
        return _annotated(access.visible_courses(self.request.user))

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.request.query_params.get("mine") in ("1", "true", "True"):
            queryset = queryset.filter(assignments__user=self.request.user)
        return queryset

    @extend_schema(
        summary="List courses",
        parameters=[
            OpenApiParameter("search", str, description="Matches title, code and description."),
            OpenApiParameter("category", str, description="Category slug."),
            OpenApiParameter("mine", bool, description="Only courses assigned to me."),
        ],
        tags=COURSES_TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a course",
        request=CourseWriteSerializer,
        responses={201: CourseDetailSerializer},
        tags=COURSES_TAG,
    )
    def post(self, request, *args, **kwargs):
        if not has_capability(request.user, Capability.COURSE_CREATE):
            return _forbidden(request, "You do not have permission to create courses.")
        serializer = CourseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = services.create_course(actor=request.user, **serializer.validated_data)
        return Response(
            CourseDetailSerializer(course, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CourseDetailView(APIView):
    """Retrieve or update one course.

    Lookup accepts a UUID or a slug, so student-facing URLs can be readable
    without introducing a second identifier space.
    """

    permission_classes = (CanViewCourse,)

    def get_course(self, request, identifier) -> Course:
        lookup = Q(slug=str(identifier))
        try:
            lookup |= Q(pk=uuid_module.UUID(str(identifier)))
        except (ValueError, AttributeError, TypeError):
            pass
        course = get_object_or_404(_annotated(access.visible_courses(request.user)), lookup)
        self.check_object_permissions(request, course)
        return course

    @extend_schema(
        summary="Retrieve a course", responses={200: CourseDetailSerializer}, tags=COURSES_TAG
    )
    def get(self, request, identifier):
        course = self.get_course(request, identifier)
        return Response(CourseDetailSerializer(course, context={"request": request}).data)

    @extend_schema(
        summary="Update a course",
        request=CourseWriteSerializer,
        responses={200: CourseDetailSerializer},
        tags=COURSES_TAG,
    )
    def patch(self, request, identifier):
        course = self.get_course(request, identifier)
        if not access.can_manage_course(request.user, course):
            return _forbidden(request, "You do not have permission to edit this course.")
        serializer = CourseWriteSerializer(instance=course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_course(
            course=course, actor=request.user, **serializer.validated_data
        )
        return Response(CourseDetailSerializer(updated, context={"request": request}).data)


class CourseStatusView(APIView):
    """Move a course through the publishing workflow."""

    permission_classes = (CanPublishCourse,)

    @extend_schema(
        summary="Change a course's status",
        request=CourseStatusSerializer,
        responses={
            200: CourseDetailSerializer,
            400: OpenApiResponse(description="Invalid transition or not ready to publish."),
        },
        tags=COURSES_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(access.visible_courses(request.user), pk=course_id)
        # An assigned editor may submit for review; only an owner or an
        # administrator may publish or archive. The service enforces the split
        # from `may_publish`, so it holds for every caller.
        if not access.can_manage_course(request.user, course):
            return _forbidden(request, "You do not have permission to change this course.")

        serializer = CourseStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_course_status(
            course=course,
            target=serializer.validated_data["status"],
            actor=request.user,
            may_publish=access.can_publish_course(request.user, course),
            note=serializer.validated_data.get("note", ""),
        )
        return Response(CourseDetailSerializer(updated, context={"request": request}).data)


class CoursePublishChecklistView(APIView):
    """What is stopping this course from being published."""

    permission_classes = (CanManageCourse,)

    @extend_schema(
        summary="Publishing checklist",
        responses={200: PublishChecklistSerializer},
        tags=COURSES_TAG,
    )
    def get(self, request, course_id):
        course = get_object_or_404(access.manageable_courses(request.user), pk=course_id)
        self.check_object_permissions(request, course)
        blockers = services.publishing_blockers(course)
        return Response({"ready": not blockers, "blockers": blockers})


class CourseThumbnailView(APIView):
    """Fetch or replace a course thumbnail."""

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        summary="Fetch a course thumbnail",
        responses={200: OpenApiResponse(description="JPEG image.")},
        tags=COURSES_TAG,
    )
    def get(self, request, course_id):
        course = get_object_or_404(access.visible_courses(request.user), pk=course_id)
        if not course.thumbnail:
            raise Http404
        response = FileResponse(course.thumbnail.open("rb"), content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response

    @extend_schema(
        summary="Upload a course thumbnail",
        request=CourseThumbnailSerializer,
        responses={200: CourseDetailSerializer},
        tags=COURSES_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(access.manageable_courses(request.user), pk=course_id)
        if not access.can_manage_course(request.user, course):
            return _forbidden(request, "You do not have permission to edit this course.")
        serializer = CourseThumbnailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_course_thumbnail(
            course=course, actor=request.user, uploaded_file=serializer.validated_data["image"]
        )
        return Response(CourseDetailSerializer(updated, context={"request": request}).data)


class CourseAuthorsView(APIView):
    """Manage who may author a course."""

    permission_classes = (HasCapability,)
    required_capability = Capability.COURSE_ASSIGN_AUTHORS

    @extend_schema(
        summary="List course authors", responses={200: CourseAssignmentSerializer}, tags=COURSES_TAG
    )
    def get(self, request, course_id):
        course = get_object_or_404(Course, pk=course_id)
        return Response(
            CourseAssignmentSerializer(
                course.assignments.select_related("user").all(), many=True
            ).data
        )

    @extend_schema(
        summary="Assign a course author",
        request=AssignAuthorSerializer,
        responses={201: CourseAssignmentSerializer},
        tags=COURSES_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(Course, pk=course_id)
        serializer = AssignAuthorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=serializer.validated_data["user_id"])
        assignment = services.assign_author(
            course=course, user=user, role=serializer.validated_data["role"], actor=request.user
        )
        return Response(CourseAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class CourseAuthorDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.COURSE_ASSIGN_AUTHORS

    @extend_schema(
        summary="Remove a course author",
        request=None,
        responses={204: OpenApiResponse(description="Assignment removed.")},
        tags=COURSES_TAG,
    )
    def delete(self, request, course_id, user_id):
        course = get_object_or_404(Course, pk=course_id)
        user = get_object_or_404(User, pk=user_id)
        services.remove_author(course=course, user=user, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


def _serialise_modules(user, course: Course) -> list[dict]:
    """Modules with their lessons, both filtered through the access layer."""
    payload = []
    for module in access.visible_modules(user, course).prefetch_related("lessons"):
        data = ModuleSerializer(module).data
        data["lessons"] = LessonSummarySerializer(
            access.visible_lessons(user, module), many=True
        ).data
        payload.append(data)
    return payload


class CourseModulesView(APIView):
    """List a course's modules, or add one."""

    permission_classes = (CanViewCourse,)

    @extend_schema(summary="List modules", responses={200: ModuleSerializer}, tags=CONTENT_TAG)
    def get(self, request, course_id):
        course = get_object_or_404(access.visible_courses(request.user), pk=course_id)
        self.check_object_permissions(request, course)
        return Response(_serialise_modules(request.user, course))

    @extend_schema(
        summary="Add a module",
        request=ModuleWriteSerializer,
        responses={201: ModuleSerializer},
        tags=CONTENT_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(access.manageable_courses(request.user), pk=course_id)
        if not access.can_manage_course(request.user, course):
            return _forbidden(request, "You do not have permission to edit this course.")
        serializer = ModuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = services.create_module(
            course=course, actor=request.user, **serializer.validated_data
        )
        return Response(ModuleSerializer(module).data, status=status.HTTP_201_CREATED)


class CourseModuleReorderView(APIView):
    permission_classes = (CanManageCourse,)

    @extend_schema(
        summary="Reorder modules",
        request=ReorderSerializer,
        responses={200: ModuleSerializer(many=True)},
        tags=CONTENT_TAG,
    )
    def post(self, request, course_id):
        course = get_object_or_404(access.manageable_courses(request.user), pk=course_id)
        self.check_object_permissions(request, course)
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder(
            parent=course,
            related_name="modules",
            ordered_ids=serializer.validated_data["ordered_ids"],
            actor=request.user,
            resource_type="course",
        )
        return Response(ModuleSerializer(course.modules.all(), many=True).data)


def _module_for(request, module_id, *, manage: bool) -> Module:
    """Fetch a module through its course's visibility.

    The module id alone proves nothing: it is resolved against the courses the
    caller may already see (or manage), so a guessed id belonging to someone
    else's draft is simply not found.
    """
    scope = (
        access.manageable_courses(request.user) if manage else access.visible_courses(request.user)
    )
    return get_object_or_404(
        Module.objects.select_related("course"), pk=module_id, course__in=scope
    )


class ModuleDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(summary="Retrieve a module", responses={200: ModuleSerializer}, tags=CONTENT_TAG)
    def get(self, request, module_id):
        module = _module_for(request, module_id, manage=False)
        data = ModuleSerializer(module).data
        data["lessons"] = LessonSummarySerializer(
            access.visible_lessons(request.user, module), many=True
        ).data
        return Response(data)

    @extend_schema(
        summary="Update a module",
        request=ModuleWriteSerializer,
        responses={200: ModuleSerializer},
        tags=CONTENT_TAG,
    )
    def patch(self, request, module_id):
        module = _module_for(request, module_id, manage=True)
        serializer = ModuleWriteSerializer(instance=module, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_module(
            module=module, actor=request.user, **serializer.validated_data
        )
        return Response(ModuleSerializer(updated).data)

    @extend_schema(
        summary="Delete a module",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=CONTENT_TAG,
    )
    def delete(self, request, module_id):
        module = _module_for(request, module_id, manage=True)
        services.delete_module(module=module, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModuleStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish or unpublish a module",
        request=ModuleStatusSerializer,
        responses={200: ModuleSerializer},
        tags=CONTENT_TAG,
    )
    def post(self, request, module_id):
        module = _module_for(request, module_id, manage=True)
        serializer = ModuleStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.update_module(
            module=module, actor=request.user, status=serializer.validated_data["status"]
        )
        return Response(ModuleSerializer(updated).data)


class ModuleLessonsView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="List lessons in a module",
        responses={200: LessonSummarySerializer},
        tags=CONTENT_TAG,
    )
    def get(self, request, module_id):
        module = _module_for(request, module_id, manage=False)
        lessons = access.visible_lessons(request.user, module)
        return Response(LessonSummarySerializer(lessons, many=True).data)

    @extend_schema(
        summary="Add a lesson",
        request=LessonWriteSerializer,
        responses={201: LessonContentSerializer},
        tags=CONTENT_TAG,
    )
    def post(self, request, module_id):
        module = _module_for(request, module_id, manage=True)
        serializer = LessonWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = services.create_lesson(
            module=module, actor=request.user, **serializer.validated_data
        )
        return Response(LessonContentSerializer(lesson).data, status=status.HTTP_201_CREATED)


class ModuleLessonReorderView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reorder lessons",
        request=ReorderSerializer,
        responses={200: LessonSummarySerializer(many=True)},
        tags=CONTENT_TAG,
    )
    def post(self, request, module_id):
        module = _module_for(request, module_id, manage=True)
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder(
            parent=module,
            related_name="lessons",
            ordered_ids=serializer.validated_data["ordered_ids"],
            actor=request.user,
            resource_type="module",
        )
        return Response(LessonSummarySerializer(module.lessons.all(), many=True).data)


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------


def _lesson_for(request, lesson_id, *, manage: bool) -> Lesson:
    scope = (
        access.manageable_courses(request.user) if manage else access.visible_courses(request.user)
    )
    return get_object_or_404(
        Lesson.objects.select_related("module__course", "video").prefetch_related("resources"),
        pk=lesson_id,
        module__course__in=scope,
    )


def _content_gate(request, lesson: Lesson, message: str) -> Response | None:
    """Shared content check for lesson body, resources and video.

    Two questions, in order: is this lesson published at all (a draft lesson
    inside a published course must not leak), and is the caller entitled to its
    content. Returning ``None`` means the caller may proceed.
    """
    course = lesson.module.course
    if access.can_manage_course(request.user, course):
        return None
    if lesson.status != PublishStatus.PUBLISHED:
        raise Http404
    if not access.can_view_content(request.user, course, lesson=lesson):
        return _forbidden(request, message)
    return None


class LessonDetailView(APIView):
    """The lesson body."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Retrieve a lesson",
        responses={200: LessonContentSerializer, 403: OpenApiResponse(description="Not entitled.")},
        tags=CONTENT_TAG,
    )
    def get(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=False)
        refusal = _content_gate(request, lesson, "Enrol on this course to open this lesson.")
        if refusal is not None:
            return refusal
        return Response(LessonContentSerializer(lesson).data)

    @extend_schema(
        summary="Update a lesson",
        request=LessonWriteSerializer,
        responses={200: LessonContentSerializer},
        tags=CONTENT_TAG,
    )
    def patch(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=True)
        serializer = LessonWriteSerializer(instance=lesson, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_lesson(
            lesson=lesson, actor=request.user, **serializer.validated_data
        )
        return Response(LessonContentSerializer(updated).data)

    @extend_schema(
        summary="Delete a lesson",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=CONTENT_TAG,
    )
    def delete(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=True)
        services.delete_lesson(lesson=lesson, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LessonStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish or unpublish a lesson",
        request=LessonStatusSerializer,
        responses={200: LessonContentSerializer},
        tags=CONTENT_TAG,
    )
    def post(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=True)
        serializer = LessonStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.update_lesson(
            lesson=lesson, actor=request.user, status=serializer.validated_data["status"]
        )
        return Response(LessonContentSerializer(updated).data)


class LessonVideoPlaybackView(APIView):
    """Hand out a playable video URL, after checking entitlement.

    The URL exists here and nowhere else in the API surface. Keeping it out of
    list and detail payloads means it is never handed to a caller who is only
    browsing the catalogue.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Get video playback details",
        responses={200: VideoPlaybackSerializer},
        tags=CONTENT_TAG,
    )
    def get(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=False)
        refusal = _content_gate(request, lesson, "Enrol on this course to watch this video.")
        if refusal is not None:
            return refusal

        video = lesson.video
        if video is None:
            raise Http404

        # Only the external-URL provider is directly playable today. S3 and
        # managed services need a signed URL from their own API — that call
        # belongs here, and nothing else has to change when it is added.
        playback_url = video.source_url if video.provider == VideoProvider.EXTERNAL_URL else None
        return Response(
            {
                "provider": video.provider,
                "playback_url": playback_url or None,
                "duration_seconds": video.duration_seconds,
                "status": video.status,
            }
        )


class LessonResourcesView(APIView):
    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        summary="List lesson resources", responses={200: LessonResourceSerializer}, tags=CONTENT_TAG
    )
    def get(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=False)
        refusal = _content_gate(request, lesson, "Enrol on this course to see its resources.")
        if refusal is not None:
            return refusal
        return Response(LessonResourceSerializer(lesson.resources.all(), many=True).data)

    @extend_schema(
        summary="Upload a file resource",
        request=ResourceFileUploadSerializer,
        responses={
            201: LessonResourceSerializer,
            400: OpenApiResponse(description="Rejected file."),
        },
        tags=CONTENT_TAG,
    )
    def post(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=True)
        serializer = ResourceFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        resource = services.create_file_resource(
            lesson=lesson, actor=request.user, uploaded_file=data.pop("file"), **data
        )
        return Response(LessonResourceSerializer(resource).data, status=status.HTTP_201_CREATED)


class LessonResourceLinkView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Attach an external link",
        request=ResourceLinkSerializer,
        responses={201: LessonResourceSerializer},
        tags=CONTENT_TAG,
    )
    def post(self, request, lesson_id):
        lesson = _lesson_for(request, lesson_id, manage=True)
        serializer = ResourceLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = services.create_link_resource(
            lesson=lesson, actor=request.user, **serializer.validated_data
        )
        return Response(LessonResourceSerializer(resource).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def _resource_for(request, resource_id, *, manage: bool) -> LessonResource:
    scope = (
        access.manageable_courses(request.user) if manage else access.visible_courses(request.user)
    )
    return get_object_or_404(
        LessonResource.objects.select_related("lesson__module__course"),
        pk=resource_id,
        lesson__module__course__in=scope,
    )


def _safe_download_name(resource: LessonResource) -> str:
    """Build the download filename from the title, never from client input.

    The uploader's original filename is display text. Echoing it into a
    ``Content-Disposition`` header would carry quotes, newlines and traversal
    sequences straight into a response header.
    """
    extension = PurePosixPath(resource.file.name).suffix.lower()
    # Dots are stripped from the base as well as quotes and separators, so a
    # title like `report.sh` cannot produce a double-extension download name.
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", resource.title).strip("-") or "resource"
    return f"{base[:80]}{extension}"


class ResourceDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Update a resource",
        request=ResourceUpdateSerializer,
        responses={200: LessonResourceSerializer},
        tags=CONTENT_TAG,
    )
    def patch(self, request, resource_id):
        resource = _resource_for(request, resource_id, manage=True)
        serializer = ResourceUpdateSerializer(instance=resource, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(resource, field, value)
        resource.full_clean(exclude=["file"])
        resource.save()
        return Response(LessonResourceSerializer(resource).data)

    @extend_schema(
        summary="Delete a resource",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=CONTENT_TAG,
    )
    def delete(self, request, resource_id):
        resource = _resource_for(request, resource_id, manage=True)
        services.delete_resource(resource=resource, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResourceDownloadView(APIView):
    """Serve a resource file.

    Media is never web-served, so this is the only read path. It re-checks
    course *and* content access on every request, forces a download rather than
    a render, and sends a filename this server built.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a resource file",
        responses={200: OpenApiResponse(description="File download.")},
        tags=CONTENT_TAG,
    )
    def get(self, request, resource_id):
        resource = _resource_for(request, resource_id, manage=False)
        refusal = _content_gate(
            request, resource.lesson, "Enrol on this course to download this resource."
        )
        if refusal is not None:
            return refusal

        if resource.kind != ResourceKind.FILE or not resource.file or not resource.is_downloadable:
            raise Http404

        response = FileResponse(
            resource.file.open("rb"),
            content_type=resource.content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = f'attachment; filename="{_safe_download_name(resource)}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class MyCoursesView(ListAPIView):
    """Courses assigned to the caller for authoring.

    A trainer's home list. Separate from the catalogue because the question is
    different: "what may I edit?" rather than "what may I browse?".
    """

    permission_classes = (IsActiveUser,)
    serializer_class = CourseListSerializer
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ("title", "code")
    ordering_fields = ("title", "created_at", "status")
    ordering = ("-created_at",)

    def get_queryset(self):
        return _annotated(access.manageable_courses(self.request.user))

    @extend_schema(summary="Courses I can author", tags=COURSES_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
