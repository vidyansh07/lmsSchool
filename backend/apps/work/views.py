"""Activity engine API (ERP Phase 9).

Every route here requires an authenticated, active session — creating,
assigning, completing, reviewing and deleting all resolve authority inside
`services.py` against the concrete record (queryset-first: `access.py`'s
`visible_*` functions decide what a caller can even fetch, so a guessed id
404s before any permission code runs), the same shape `apps.dsr.views` uses.
None of these are anonymous-reachable, so `EnforceCSRFMixin` is moot here —
every view below inherits `IsActiveUser` or `HasCapability`, both of which
require a logged-in session.
"""

from __future__ import annotations

import django_filters
from django.db.models import Count, Q
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.roles import Capability
from apps.common.caching import MINUTE, remember
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import HasCapability, IsActiveUser
from apps.enrollments.models import Enrollment
from apps.forms.models import FormDefinition
from apps.students import access as students_access

from . import access, services
from .models import Activity, ActivityStatus, ActivityType
from .serializers import (
    ActivityCompleteSerializer,
    ActivityCreateSerializer,
    ActivityDeleteSerializer,
    ActivityDetailSerializer,
    ActivityListSerializer,
    ActivityPatchSerializer,
    ActivityReviewSerializer,
    ActivityTransitionSerializer,
    ActivityTypeCreateSerializer,
    ActivityTypePatchSerializer,
    ActivityTypeSerializer,
)

TAG = ["Activities"]

_TYPES_CACHE_TTL = 10 * MINUTE
_EDITABLE_STATUSES = frozenset(
    {ActivityStatus.DRAFT, ActivityStatus.PLANNED, ActivityStatus.ASSIGNED}
)


# ---------------------------------------------------------------------------
# Activity types
# ---------------------------------------------------------------------------


def _types_queryset():
    return ActivityType.objects.with_related().order_by("name")


class ActivityTypeListCreateView(ListAPIView):
    """Reading is any staff account; writing is `activity_type.manage`."""

    permission_classes = (IsActiveUser,)
    serializer_class = ActivityTypeSerializer
    pagination_class = None
    queryset = ActivityType.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ActivityType.objects.none()
        return _types_queryset()

    @extend_schema(summary="Every activity type", tags=TAG)
    def get(self, request, *args, **kwargs):
        student = access.caller_student_profile(request.user)
        if student is not None:
            raise AuthorityError("The activity catalog is staff-facing.")

        def _compute():
            return {"results": ActivityTypeSerializer(_types_queryset(), many=True).data}

        return Response(remember("work:types", (), _TYPES_CACHE_TTL, _compute))

    @extend_schema(
        summary="Create an activity type",
        request=ActivityTypeCreateSerializer,
        responses={201: ActivityTypeSerializer, 409: OpenApiResponse(description="Slug taken")},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = ActivityTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        form_slug = fields.pop("form", None)
        fields["form"] = (
            get_object_or_404(FormDefinition.objects.all(), slug=form_slug) if form_slug else None
        )
        activity_type = services.create_activity_type(actor=request.user, **fields)
        return Response(
            ActivityTypeSerializer(activity_type).data, status=http_status.HTTP_201_CREATED
        )


class ActivityTypeDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.ACTIVITY_TYPE_MANAGE
    serializer_class = ActivityTypeSerializer

    @extend_schema(
        summary="Change an activity type",
        request=ActivityTypePatchSerializer,
        responses={200: ActivityTypeSerializer},
        tags=TAG,
    )
    def patch(self, request, slug):
        activity_type = get_object_or_404(ActivityType.objects.with_related(), slug=slug)
        serializer = ActivityTypePatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if "form" in fields:
            form_slug = fields.pop("form")
            fields["form"] = (
                get_object_or_404(FormDefinition.objects.all(), slug=form_slug)
                if form_slug
                else None
            )
        activity_type = services.update_activity_type(
            actor=request.user, activity_type=activity_type, **fields
        )
        return Response(ActivityTypeSerializer(activity_type).data)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------


class ActivityFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    type = django_filters.CharFilter(field_name="activity_type__slug")
    category = django_filters.CharFilter(field_name="activity_type__category")
    student = django_filters.UUIDFilter(field_name="student_id")
    batch = django_filters.UUIDFilter(field_name="batch_id")
    assigned_to = django_filters.UUIDFilter(field_name="assigned_to_id")
    created_by = django_filters.UUIDFilter(field_name="created_by_id")
    due_before = django_filters.DateTimeFilter(field_name="due_at", lookup_expr="lte")
    due_after = django_filters.DateTimeFilter(field_name="due_at", lookup_expr="gte")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    mine = django_filters.BooleanFilter(method="filter_mine")

    class Meta:
        model = Activity
        fields = (
            "status",
            "type",
            "category",
            "student",
            "batch",
            "assigned_to",
            "created_by",
        )

    def filter_overdue(self, queryset, name, value):
        if value:
            return queryset.filter(status=ActivityStatus.OVERDUE)
        return queryset

    def filter_mine(self, queryset, name, value):
        user = getattr(self.request, "user", None)
        if value and user is not None:
            return queryset.filter(Q(assigned_to=user) | Q(created_by=user))
        return queryset


class ActivityListCreateView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ActivityListSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ActivityFilterSet
    ordering_fields = ("due_at", "created_at", "priority")
    ordering = ("-created_at",)
    queryset = Activity.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Activity.objects.none()
        return access.visible_activities(self.request.user).annotate(history_count=Count("history"))

    @extend_schema(summary="List activities", tags=TAG)
    def get(self, request, *args, **kwargs):
        if not access.can_read_staff_activities(request.user):
            raise AuthorityError(
                "Activities are staff-facing. See your own student record instead."
            )
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create an activity",
        request=ActivityCreateSerializer,
        responses={201: ActivityDetailSerializer},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = ActivityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        student = get_object_or_404(
            students_access.visible_students(request.user), pk=data["student"]
        )
        enrollment = None
        if data.get("enrollment"):
            enrollment = get_object_or_404(
                Enrollment.objects.filter(student=student), pk=data["enrollment"]
            )
        activity_type = get_object_or_404(ActivityType.objects.all(), slug=data["activity_type"])
        assigned_to = None
        if data.get("assigned_to"):
            assigned_to = get_object_or_404(
                User.objects.filter(is_active=True), pk=data["assigned_to"]
            )

        activity = services.create_activity(
            actor=request.user,
            student=student,
            activity_type=activity_type,
            enrollment=enrollment,
            title=data.get("title") or None,
            assigned_to=assigned_to,
            planned_at=data.get("planned_at"),
            due_at=data.get("due_at"),
            priority=data.get("priority"),
            student_visible=data.get("student_visible"),
            client_key=data.get("client_key") or None,
        )
        detail = get_object_or_404(access.visible_activities(request.user), pk=activity.pk)
        return Response(
            ActivityDetailSerializer(detail, context={"as_student": False}).data,
            status=http_status.HTTP_201_CREATED,
        )


def _staff_activity_or_404(user, activity_id):
    return get_object_or_404(access.visible_activities(user), pk=activity_id)


def _activity_for_detail(user, activity_id):
    """Staff surface first; falls back to the caller's own student-visible
    copy — the only way a student ever reaches this endpoint."""
    activity = access.visible_activities(user).filter(pk=activity_id).first()
    if activity is not None:
        return activity, False
    student = access.caller_student_profile(user)
    if student is not None:
        activity = access.student_visible_activities(student).filter(pk=activity_id).first()
        if activity is not None:
            return activity, True
    raise Http404


class ActivityDetailView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ActivityDetailSerializer

    @extend_schema(summary="Activity detail", responses={200: ActivityDetailSerializer}, tags=TAG)
    def get(self, request, activity_id):
        activity, as_student = _activity_for_detail(request.user, activity_id)
        return Response(ActivityDetailSerializer(activity, context={"as_student": as_student}).data)

    @extend_schema(
        summary="Edit an activity while it is still open",
        request=ActivityPatchSerializer,
        responses={200: ActivityDetailSerializer},
        tags=TAG,
    )
    def patch(self, request, activity_id):
        activity = _staff_activity_or_404(request.user, activity_id)
        if activity.status not in _EDITABLE_STATUSES:
            raise ApplicationError({"non_field_errors": ["This activity can no longer be edited."]})
        serializer = ActivityPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)

        if "assigned_to" in fields:
            if not access.can_assign(request.user, activity):
                raise AuthorityError("You do not have authority to assign this activity.")
            assigned_to_id = fields.pop("assigned_to")
            if assigned_to_id:
                assigned_to = get_object_or_404(
                    User.objects.filter(is_active=True), pk=assigned_to_id
                )
                # Same eligibility check `create_activity` applies to a new
                # activity's `assigned_to`: the type's `allowed_assignee_roles`
                # allowlist and `access.can_be_assigned`'s scope check. Being
                # able to reassign (`can_assign`, above) says nothing about
                # who is a legitimate assignee.
                services.validate_assignee(
                    activity.activity_type,
                    assigned_to,
                    branch_id=activity.branch_id,
                    batch_id=activity.batch_id,
                )
                fields["assigned_to"] = assigned_to
            else:
                fields["assigned_to"] = None
        if "student_visible" in fields:
            if fields["student_visible"] and not activity.student_visible:
                raise ApplicationError(
                    {"student_visible": ["An activity may only be hidden, never un-hidden."]}
                )

        changed = []
        for name, value in fields.items():
            if getattr(activity, name) != value:
                setattr(activity, name, value)
                changed.append(name)
        if changed:
            activity.save(update_fields=[*changed, "updated_at"])
        return Response(ActivityDetailSerializer(activity, context={"as_student": False}).data)

    @extend_schema(
        summary="Delete an activity",
        request=ActivityDeleteSerializer,
        responses={200: ActivityDetailSerializer},
        tags=TAG,
    )
    def delete(self, request, activity_id):
        activity = _staff_activity_or_404(request.user, activity_id)
        serializer = ActivityDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_activity(
            actor=request.user, activity=activity, reason=serializer.validated_data["reason"]
        )
        return Response(ActivityDetailSerializer(activity, context={"as_student": False}).data)


class ActivityTransitionView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ActivityTransitionSerializer

    @extend_schema(
        summary="Move an activity to another status",
        request=ActivityTransitionSerializer,
        responses={
            200: ActivityDetailSerializer,
            409: OpenApiResponse(description="Illegal transition"),
        },
        tags=TAG,
    )
    def post(self, request, activity_id):
        activity = _staff_activity_or_404(request.user, activity_id)
        serializer = ActivityTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition_activity(
            actor=request.user,
            activity=activity,
            to_status=serializer.validated_data["to"],
            note=serializer.validated_data.get("note"),
        )
        return Response(ActivityDetailSerializer(activity, context={"as_student": False}).data)


class ActivityCompleteView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ActivityCompleteSerializer

    @extend_schema(
        summary="Complete an activity",
        request=ActivityCompleteSerializer,
        responses={
            200: ActivityDetailSerializer,
            409: OpenApiResponse(description="Not completable"),
        },
        tags=TAG,
    )
    def post(self, request, activity_id):
        activity = _staff_activity_or_404(request.user, activity_id)
        serializer = ActivityCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.complete_activity(
            actor=request.user,
            activity=activity,
            form_values=data.get("form_values") or {},
            summary=data.get("summary"),
            duration_minutes=data.get("duration_minutes"),
            completed_at=data.get("completed_at"),
        )
        return Response(ActivityDetailSerializer(activity, context={"as_student": False}).data)


class ActivityReviewView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ActivityReviewSerializer

    @extend_schema(
        summary="Approve or send back a completed activity",
        request=ActivityReviewSerializer,
        responses={200: ActivityDetailSerializer},
        tags=TAG,
    )
    def post(self, request, activity_id):
        activity = _staff_activity_or_404(request.user, activity_id)
        serializer = ActivityReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.review_activity(
            actor=request.user,
            activity=activity,
            decision=serializer.validated_data["decision"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(ActivityDetailSerializer(activity, context={"as_student": False}).data)


class StudentActivityListView(ListAPIView):
    """The Student 360 tab's activities list. Permission is exactly "may this
    caller see this student" — the same rule `apps.students.access` already
    enforces for the profile itself, not a separate activity capability."""

    permission_classes = (IsActiveUser,)
    serializer_class = ActivityListSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ActivityFilterSet
    ordering_fields = ("due_at", "created_at", "priority")
    ordering = ("-created_at",)
    queryset = Activity.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Activity.objects.none()
        # `reachable_students` (branch only) then `can_view_student` (the
        # audience question) — the same two-step
        # `apps.students.views.StudentDetailView` uses, so a cross-branch id
        # 404s and a same-branch classmate a student may not read 403s,
        # instead of collapsing both into one answer.
        student = get_object_or_404(
            students_access.reachable_students(self.request.user), pk=self.kwargs["student_id"]
        )
        if not students_access.can_view_student(self.request.user, student):
            raise AuthorityError("You do not have authority to see this student.")
        caller_student = access.caller_student_profile(self.request.user)
        if caller_student is not None and caller_student.pk == student.pk:
            base = access.student_visible_activities(student)
        else:
            # Being able to see the student profile at all (`can_view_student`,
            # above) is a different question from which of *this* student's
            # activities the caller may see — the activity engine's own
            # branch/assigned-tier scoping still applies, the same pattern
            # `apps.dsr.views.BatchDSRListView` uses (intersecting the
            # parent's visible-batches queryset with `access.visible_dsrs`
            # rather than dropping the DSR-domain scope once the batch is
            # visible).
            base = access.visible_activities(self.request.user).filter(student=student)
        return base.annotate(history_count=Count("history"))

    @extend_schema(summary="One student's activities", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MeActivitiesView(ListAPIView):
    """Sugar for `?mine=1` on the caller — their own work list."""

    permission_classes = (IsActiveUser,)
    serializer_class = ActivityListSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ActivityFilterSet
    ordering_fields = ("due_at", "created_at", "priority")
    ordering = ("-created_at",)
    queryset = Activity.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Activity.objects.none()
        user = self.request.user
        return (
            Activity.objects.with_related()
            .filter(Q(assigned_to=user) | Q(created_by=user))
            .annotate(history_count=Count("history"))
            .distinct()
        )

    @extend_schema(summary="My activities", tags=TAG)
    def get(self, request, *args, **kwargs):
        if not access.can_read_staff_activities(request.user):
            raise AuthorityError(
                "Activities are staff-facing. See your own student record instead."
            )
        return super().get(request, *args, **kwargs)
