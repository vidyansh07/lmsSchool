"""Batch and schedule API.

Same authorization pattern as the rest of the project:

1. Fetch the object from a queryset the caller is already entitled to.
2. Run the object-level check.
3. Only then serialise.

Step 1 is what makes a guessed ``batch_id`` useless — a batch the caller may not
see is not in the queryset, so it 404s before any permission code runs.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.common.permissions import IsActiveUser
from apps.enrollments.serializers import RosterEntrySerializer

from . import access, services
from .models import Batch, BatchSchedule
from .serializers import (
    AssignTrainerSerializer,
    BatchDetailSerializer,
    BatchListSerializer,
    BatchScheduleSerializer,
    BatchScheduleWriteSerializer,
    BatchStatusSerializer,
    BatchWriteSerializer,
    SetUpTimetableSerializer,
)

BATCHES_TAG = ["batches"]
SCHEDULES_TAG = ["schedules"]


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


class BatchFilterSet(django_filters.FilterSet):
    """Every filter maps to an indexed column or a small enumeration."""

    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    course = django_filters.CharFilter(field_name="course__slug", lookup_expr="iexact")
    trainer = django_filters.UUIDFilter(field_name="trainer_id")
    starts_after = django_filters.DateFilter(field_name="start_date", lookup_expr="gte")
    starts_before = django_filters.DateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model = Batch
        fields = ("status", "course", "trainer")


class BatchListCreateView(ListCreateAPIView):
    """Browse batches, or create one.

    The queryset *is* the authorization: administrators see everything, trainers
    see what they teach, students see what they are enrolled on.
    """

    permission_classes = (IsActiveUser,)
    serializer_class = BatchListSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = BatchFilterSet
    search_fields = ("code", "name", "course__title", "course__code")
    ordering_fields = ("start_date", "end_date", "name", "created_at", "status")
    ordering = ("-start_date",)

    def get_queryset(self):
        # `with_counts` annotates the seat count, so a page of batches costs one
        # query rather than one per row.
        return access.visible_batches(self.request.user).with_counts()

    @extend_schema(
        summary="List batches",
        parameters=[
            OpenApiParameter(
                "status", str, description="upcoming | active | completed | cancelled | archived"
            ),
            OpenApiParameter("course", str, description="Course slug."),
        ],
        tags=BATCHES_TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a batch",
        request=BatchWriteSerializer,
        responses={201: BatchDetailSerializer},
        tags=BATCHES_TAG,
    )
    def post(self, request, *args, **kwargs):
        if not has_capability(request.user, Capability.BATCH_CREATE):
            return _forbidden(request, "You do not have permission to create batches.")
        serializer = BatchWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = services.create_batch(actor=request.user, **serializer.validated_data)
        return Response(
            BatchDetailSerializer(batch, context={"request": request}).data,
            status=http_status.HTTP_201_CREATED,
        )


def _batch_for(request, batch_id, *, manage: bool = False) -> Batch:
    batch = get_object_or_404(access.visible_batches(request.user).with_counts(), pk=batch_id)
    if manage and not access.can_manage_batch(request.user, batch):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("You do not have permission to manage this batch.")
    return batch


class BatchDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Retrieve a batch", responses={200: BatchDetailSerializer}, tags=BATCHES_TAG
    )
    def get(self, request, batch_id):
        batch = _batch_for(request, batch_id)
        return Response(BatchDetailSerializer(batch, context={"request": request}).data)

    @extend_schema(
        summary="Update a batch",
        request=BatchWriteSerializer,
        responses={200: BatchDetailSerializer},
        tags=BATCHES_TAG,
    )
    def patch(self, request, batch_id):
        batch = _batch_for(request, batch_id, manage=True)
        serializer = BatchWriteSerializer(instance=batch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_batch(
            batch=batch, actor=request.user, **serializer.validated_data
        )
        return Response(BatchDetailSerializer(updated, context={"request": request}).data)


class BatchStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Change a batch's status",
        request=BatchStatusSerializer,
        responses={
            200: BatchDetailSerializer,
            400: OpenApiResponse(description="Invalid transition."),
        },
        tags=BATCHES_TAG,
    )
    def post(self, request, batch_id):
        batch = _batch_for(request, batch_id, manage=True)
        serializer = BatchStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_batch_status(
            batch=batch,
            target=serializer.validated_data["status"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(BatchDetailSerializer(updated, context={"request": request}).data)


class BatchTrainerView(APIView):
    """Assign or clear the batch trainer.

    Its own endpoint because assignment checks the trainer's whole timetable —
    a clash is refused with the clashing class named, not silently accepted.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Assign a trainer to a batch",
        request=AssignTrainerSerializer,
        responses={
            200: BatchDetailSerializer,
            409: OpenApiResponse(description="The trainer is already teaching at that time."),
        },
        tags=BATCHES_TAG,
    )
    def post(self, request, batch_id):
        from apps.trainers.models import TrainerProfile

        batch = _batch_for(request, batch_id, manage=True)
        serializer = AssignTrainerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        trainer_id = serializer.validated_data["trainer_id"]
        trainer = (
            get_object_or_404(TrainerProfile.objects.select_related("user"), pk=trainer_id)
            if trainer_id
            else None
        )
        updated = services.assign_trainer(batch=batch, trainer=trainer, actor=request.user)
        return Response(BatchDetailSerializer(updated, context={"request": request}).data)


class BatchRosterView(APIView):
    """Who is enrolled on this batch.

    Restricted to administrators and the batch's own trainer. A classmate list
    is other people's personal data, and nothing in this phase needs students to
    see it.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="List the students on a batch",
        responses={200: RosterEntrySerializer},
        tags=BATCHES_TAG,
    )
    def get(self, request, batch_id):
        batch = _batch_for(request, batch_id)
        if not access.can_view_roster(request.user, batch):
            return _forbidden(request, "You do not have permission to see this batch's students.")

        roster = batch.enrollments.select_related("student", "student__user").order_by(
            "student__student_id"
        )
        return Response(RosterEntrySerializer(roster, many=True).data)


class BatchTimetableSetupView(APIView):
    """Write the weekly timetable, make the classes, and plan the curriculum.

    One action because it was always one intention. Doing it by hand meant three
    screens visited in the right order, and a batch that had only had the first
    two looked identical to one nobody had started.

    Re-runnable: every step underneath already refuses to duplicate itself, so a
    second call reports zeroes rather than a second timetable.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Set up a batch's timetable, classes and curriculum",
        request=SetUpTimetableSerializer,
        responses={
            200: OpenApiResponse(description="What was created, and what already existed."),
            409: OpenApiResponse(description="The trainer is already teaching at that time."),
        },
        tags=BATCHES_TAG,
    )
    def post(self, request, batch_id):
        from apps.trainers.models import TrainerProfile

        batch = _batch_for(request, batch_id, manage=True)
        serializer = SetUpTimetableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        trainer = None
        trainer_id = data.get("trainer_id")
        if trainer_id:
            trainer = get_object_or_404(
                TrainerProfile.objects.select_related("user"), pk=trainer_id
            )

        summary = services.setup_batch_timetable(
            batch=batch,
            actor=request.user,
            start_time=data["start_time"],
            end_time=data["end_time"],
            weekdays=data.get("weekdays"),
            location=data.get("location", ""),
            trainer=trainer,
            generate=data["generate"],
            autoplan=data["autoplan"],
        )
        return Response(summary)


class BatchSchedulesView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="List a batch's classes",
        responses={200: BatchScheduleSerializer},
        tags=SCHEDULES_TAG,
    )
    def get(self, request, batch_id):
        batch = _batch_for(request, batch_id)
        schedules = batch.schedules.select_related("trainer__user", "batch__trainer__user").all()
        return Response(BatchScheduleSerializer(schedules, many=True).data)

    @extend_schema(
        summary="Add a class to a batch",
        request=BatchScheduleWriteSerializer,
        responses={
            201: BatchScheduleSerializer,
            409: OpenApiResponse(description="Clashes with an existing class."),
        },
        tags=SCHEDULES_TAG,
    )
    def post(self, request, batch_id):
        batch = _batch_for(request, batch_id)
        if not access.can_manage_schedule(request.user, batch):
            return _forbidden(request, "You do not have permission to manage this timetable.")

        serializer = BatchScheduleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = services.create_schedule(
            batch=batch, actor=request.user, **serializer.validated_data
        )
        return Response(BatchScheduleSerializer(schedule).data, status=http_status.HTTP_201_CREATED)


def _schedule_for(request, schedule_id) -> BatchSchedule:
    """Resolved through the batches the caller may see, never by id alone."""
    return get_object_or_404(
        BatchSchedule.objects.select_related("batch", "batch__trainer__user", "trainer__user"),
        pk=schedule_id,
        batch__in=access.visible_batches(request.user),
    )


class ScheduleDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Retrieve a class", responses={200: BatchScheduleSerializer}, tags=SCHEDULES_TAG
    )
    def get(self, request, schedule_id):
        return Response(BatchScheduleSerializer(_schedule_for(request, schedule_id)).data)

    @extend_schema(
        summary="Update a class",
        request=BatchScheduleWriteSerializer,
        responses={
            200: BatchScheduleSerializer,
            409: OpenApiResponse(description="Clashes with an existing class."),
        },
        tags=SCHEDULES_TAG,
    )
    def patch(self, request, schedule_id):
        schedule = _schedule_for(request, schedule_id)
        if not access.can_manage_schedule(request.user, schedule.batch):
            return _forbidden(request, "You do not have permission to manage this timetable.")

        serializer = BatchScheduleWriteSerializer(
            instance=schedule, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        updated = services.update_schedule(
            schedule=schedule, actor=request.user, **serializer.validated_data
        )
        return Response(BatchScheduleSerializer(updated).data)

    @extend_schema(
        summary="Delete a class",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=SCHEDULES_TAG,
    )
    def delete(self, request, schedule_id):
        schedule = _schedule_for(request, schedule_id)
        if not access.can_manage_schedule(request.user, schedule.batch):
            return _forbidden(request, "You do not have permission to manage this timetable.")
        services.delete_schedule(schedule=schedule, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)
