"""Class session API.

Same authorization pattern as everywhere else: resolve the record inside a
queryset the caller is entitled to, then run the object-level check. A session
id from a client proves nothing.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser

from . import access, services
from .models import ClassSession, SessionStatus, TrainerAssignmentHistory
from .serializers import (
    ClassSessionSerializer,
    ClassSessionWriteSerializer,
    GenerateSessionsSerializer,
    GenerationResultSerializer,
    RescheduleSerializer,
    SessionStatusSerializer,
    TrainerHistorySerializer,
)

SESSIONS_TAG = ["class sessions"]


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


class SessionFilterSet(django_filters.FilterSet):
    batch = django_filters.UUIDFilter(field_name="batch_id")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    date_from = django_filters.DateFilter(field_name="session_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="session_date", lookup_expr="lte")
    trainer = django_filters.UUIDFilter(field_name="trainer_id")

    class Meta:
        model = ClassSession
        fields = ("batch", "status", "trainer")


class SessionListView(ListAPIView):
    """Classes the caller may see.

    A trainer's daily driver: `?date_from=today&date_to=today` is the register
    list for the day.
    """

    permission_classes = (IsActiveUser,)
    serializer_class = ClassSessionSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = SessionFilterSet
    search_fields = ("topic", "batch__code", "batch__name", "batch__course__title")
    ordering_fields = ("session_date", "start_time", "status")
    ordering = ("-session_date", "start_time")

    def get_queryset(self):
        return access.visible_sessions(self.request.user)

    @extend_schema(
        summary="List class sessions",
        parameters=[
            OpenApiParameter("batch", str, description="Batch id."),
            OpenApiParameter("date_from", str, description="ISO date."),
            OpenApiParameter("date_to", str, description="ISO date."),
            OpenApiParameter(
                "status",
                str,
                description="scheduled | in_progress | completed | cancelled | rescheduled",
            ),
        ],
        tags=SESSIONS_TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MySessionsTodayView(APIView):
    """Today's classes for the caller. The trainer's landing list."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My classes today", responses={200: ClassSessionSerializer}, tags=SESSIONS_TAG
    )
    def get(self, request):
        from django.utils import timezone

        from apps.batches.models import BatchStatus

        today = timezone.localdate()
        sessions = (
            access.visible_sessions(request.user)
            .filter(session_date=today)
            # A cancelled batch is not teaching today. Its students have lost
            # access, so a register for it would record attendance nobody can
            # act on — and it pushes the real class down the page, which is how
            # a trainer comes to open the wrong one.
            .exclude(batch__status=BatchStatus.CANCELLED)
            # Neither is a class that was itself called off or moved. Both leave
            # a row behind on purpose, so that history survives; neither is work
            # for today.
            .exclude(status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED))
        )
        return Response(ClassSessionSerializer(sessions, many=True).data)


def _session_for(request, session_id, *, manage: bool = False) -> ClassSession:
    session = get_object_or_404(access.visible_sessions(request.user), pk=session_id)
    if manage and not access.can_manage_session(request.user, session):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("You do not have permission to manage this class.")
    return session


class SessionDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Retrieve a class", responses={200: ClassSessionSerializer}, tags=SESSIONS_TAG
    )
    def get(self, request, session_id):
        return Response(ClassSessionSerializer(_session_for(request, session_id)).data)

    @extend_schema(
        summary="Update a class",
        request=ClassSessionWriteSerializer,
        responses={200: ClassSessionSerializer},
        tags=SESSIONS_TAG,
    )
    def patch(self, request, session_id):
        session = _session_for(request, session_id, manage=True)
        serializer = ClassSessionWriteSerializer(instance=session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_session(
            session=session, actor=request.user, **serializer.validated_data
        )
        return Response(ClassSessionSerializer(updated).data)


class SessionStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Change a class's status",
        request=SessionStatusSerializer,
        responses={
            200: ClassSessionSerializer,
            400: OpenApiResponse(description="Invalid transition."),
        },
        tags=SESSIONS_TAG,
    )
    def post(self, request, session_id):
        session = _session_for(request, session_id, manage=True)
        serializer = SessionStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_session_status(
            session=session,
            target=serializer.validated_data["status"],
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(ClassSessionSerializer(updated).data)


class SessionRescheduleView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reschedule a class",
        request=RescheduleSerializer,
        responses={201: ClassSessionSerializer},
        tags=SESSIONS_TAG,
    )
    def post(self, request, session_id):
        session = _session_for(request, session_id, manage=True)
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        replacement = services.reschedule_session(
            session=session,
            actor=request.user,
            new_date=data["session_date"],
            new_start=data["start_time"],
            new_end=data["end_time"],
            reason=data.get("reason", ""),
        )
        return Response(
            ClassSessionSerializer(replacement).data, status=http_status.HTTP_201_CREATED
        )


class BatchSessionsView(APIView):
    """A batch's classes, and the endpoint that generates them."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="List a batch's classes", responses={200: ClassSessionSerializer}, tags=SESSIONS_TAG
    )
    def get(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        sessions = (
            ClassSession.objects.with_related()
            .filter(batch=batch)
            .order_by("session_date", "start_time")
        )
        return Response(ClassSessionSerializer(sessions, many=True).data)

    @extend_schema(
        summary="Add a one-off class",
        request=ClassSessionWriteSerializer,
        responses={201: ClassSessionSerializer},
        tags=SESSIONS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not batch_access.can_manage_schedule(request.user, batch):
            return _forbidden(request, "You do not have permission to manage this timetable.")

        serializer = ClassSessionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = services.create_session(
            batch=batch, actor=request.user, **serializer.validated_data
        )
        return Response(ClassSessionSerializer(session).data, status=http_status.HTTP_201_CREATED)


class BatchSessionGenerateView(APIView):
    """Materialise classes from the batch's weekly timetable. Idempotent."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Generate classes from the timetable",
        request=GenerateSessionsSerializer,
        responses={200: GenerationResultSerializer},
        tags=SESSIONS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not batch_access.can_manage_schedule(request.user, batch):
            return _forbidden(request, "You do not have permission to manage this timetable.")

        serializer = GenerateSessionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.generate_sessions(
            batch=batch,
            actor=request.user,
            start=serializer.validated_data.get("start"),
            end=serializer.validated_data.get("end"),
        )
        return Response(
            {
                "created": result["created"],
                "skipped": result["skipped"],
                # Days the academic calendar marks as holidays. Without this the
                # operator sees "12 created" for a fortnight that should have
                # produced twenty and has nothing to explain the gap.
                "on_holiday": result["on_holiday"],
                "start": result["from"],
                "end": result["to"],
            }
        )


class BatchTrainerHistoryView(APIView):
    """Who has taught this batch, and when."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Trainer assignment history",
        responses={200: TrainerHistorySerializer},
        tags=SESSIONS_TAG,
    )
    def get(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not batch_access.can_view_roster(request.user, batch):
            return _forbidden(request, "You do not have permission to see this batch's history.")

        rows = (
            TrainerAssignmentHistory.objects.filter(batch=batch)
            .select_related("trainer__user")
            .order_by("-assigned_at")
        )
        return Response(
            [
                {
                    "id": row.pk,
                    "trainer_name": row.trainer.user.full_name if row.trainer else "",
                    "trainer_code": row.trainer.trainer_id if row.trainer else "",
                    "assigned_at": row.assigned_at,
                    "ended_at": row.ended_at,
                    "is_current": row.is_current,
                    "note": row.note,
                }
                for row in rows
            ]
        )
