"""Discussion API — §7.6."""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser

from . import access, services
from .models import Reply, Thread
from .serializers import (
    HideSerializer,
    ModerationSerializer,
    ReplySerializer,
    ReplyWriteSerializer,
    ThreadDetailSerializer,
    ThreadSerializer,
    ThreadWriteSerializer,
)

DISCUSSIONS_TAG = ["discussions"]


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


class ThreadFilterSet(django_filters.FilterSet):
    batch = django_filters.UUIDFilter(field_name="batch_id")
    is_closed = django_filters.BooleanFilter(field_name="is_closed")
    unanswered = django_filters.BooleanFilter(method="filter_unanswered")

    class Meta:
        model = Thread
        fields = ("batch", "is_closed")

    def filter_unanswered(self, queryset, name, value):
        return queryset.filter(has_trainer_reply=False) if value else queryset


class ThreadListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ThreadSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ThreadFilterSet
    search_fields = ("title", "body")
    ordering_fields = ("created_at", "last_reply_at")
    ordering = ("-is_pinned", "-last_reply_at", "-created_at")

    def get_queryset(self):
        return access.visible_threads(self.request.user)

    @extend_schema(summary="Discussion threads", tags=DISCUSSIONS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BatchThreadsView(APIView):
    """Start a thread on a batch."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Start a discussion",
        request=ThreadWriteSerializer,
        responses={201: ThreadSerializer},
        tags=DISCUSSIONS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not access.can_post_in(request.user, batch):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="batch",
                resource_id=batch.pk,
                result="failure",
                context={"attempted": "discussion.create"},
            )
            return _forbidden(request, "You are not on this batch.")

        serializer = ThreadWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        thread = services.create_thread(
            batch=batch, actor=request.user, **serializer.validated_data
        )
        return Response(ThreadSerializer(thread).data, status=http_status.HTTP_201_CREATED)


def _thread_for(request, thread_id) -> Thread:
    return get_object_or_404(access.visible_threads(request.user), pk=thread_id)


class ThreadDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="A discussion thread",
        responses={200: ThreadDetailSerializer},
        tags=DISCUSSIONS_TAG,
    )
    def get(self, request, thread_id):
        thread = _thread_for(request, thread_id)
        thread.replies_visible = access.visible_replies(request.user, thread)
        payload = ThreadDetailSerializer(thread).data
        payload["replies"] = ReplySerializer(thread.replies_visible, many=True).data
        payload["can_reply"] = not thread.is_closed and access.can_post_in(
            request.user, thread.batch
        )
        payload["can_moderate"] = access.can_moderate(request.user, thread.batch)
        return Response(payload)


class ReplyView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reply to a thread",
        request=ReplyWriteSerializer,
        responses={201: ReplySerializer},
        tags=DISCUSSIONS_TAG,
    )
    def post(self, request, thread_id):
        thread = _thread_for(request, thread_id)
        if not access.can_post_in(request.user, thread.batch):
            return _forbidden(request, "You are not on this batch.")

        serializer = ReplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.reply(thread=thread, actor=request.user, **serializer.validated_data)
        return Response(ReplySerializer(row).data, status=http_status.HTTP_201_CREATED)


class ModerateThreadView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Pin or close a thread",
        request=ModerationSerializer,
        responses={200: ThreadSerializer},
        tags=DISCUSSIONS_TAG,
    )
    def post(self, request, thread_id):
        thread = _thread_for(request, thread_id)
        if not access.can_moderate(request.user, thread.batch):
            return _forbidden(request, "You cannot moderate this discussion.")

        serializer = ModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "pinned" in data:
            thread = services.set_pinned(thread=thread, actor=request.user, pinned=data["pinned"])
        if "closed" in data:
            thread = services.set_closed(thread=thread, actor=request.user, closed=data["closed"])
        return Response(ThreadSerializer(thread).data)


class HideReplyView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Hide a reply",
        request=HideSerializer,
        responses={200: ReplySerializer},
        tags=DISCUSSIONS_TAG,
    )
    def post(self, request, reply_id):
        row = get_object_or_404(
            Reply.objects.filter(thread__in=access.visible_threads(request.user)).select_related(
                "thread", "thread__batch"
            ),
            pk=reply_id,
        )
        if not access.can_moderate(request.user, row.thread.batch):
            return _forbidden(request, "You cannot moderate this discussion.")

        serializer = HideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = services.hide_reply(
            row=row, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(ReplySerializer(row).data)

    @extend_schema(
        summary="Restore a hidden reply",
        request=None,
        responses={200: ReplySerializer},
        tags=DISCUSSIONS_TAG,
    )
    def delete(self, request, reply_id):
        row = get_object_or_404(
            Reply.objects.filter(thread__in=access.visible_threads(request.user)).select_related(
                "thread", "thread__batch"
            ),
            pk=reply_id,
        )
        if not access.can_moderate(request.user, row.thread.batch):
            return _forbidden(request, "You cannot moderate this discussion.")
        row = services.unhide_reply(row=row, actor=request.user)
        return Response(ReplySerializer(row).data)
