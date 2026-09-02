"""Announcement API — §7.3."""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.courses import access as course_access

from . import access, services
from .models import Announcement, Audience
from .serializers import (
    AnnouncementSerializer,
    AnnouncementWriteSerializer,
    StudentAnnouncementSerializer,
)

ANNOUNCEMENTS_TAG = ["announcements"]


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


def _resolve(request, data: dict) -> tuple[dict, list]:
    """Turn submitted ids into objects, inside the caller's own visibility."""
    fields = dict(data)
    course_id = fields.pop("course", None)
    batch_id = fields.pop("batch", None)
    recipient_ids = fields.pop("recipients", None)

    if course_id:
        fields["course"] = get_object_or_404(
            course_access.visible_courses(request.user), pk=course_id
        )
    if batch_id:
        fields["batch"] = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)

    recipients = []
    if recipient_ids:
        recipients = list(User.objects.filter(pk__in=recipient_ids, is_active=True))
    return fields, recipients


class AnnouncementFilterSet(django_filters.FilterSet):
    audience = django_filters.CharFilter(field_name="audience", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    batch = django_filters.UUIDFilter(field_name="batch_id")
    course = django_filters.UUIDFilter(field_name="course_id")

    class Meta:
        model = Announcement
        fields = ("audience", "status", "batch", "course")


class AnnouncementListView(ListAPIView):
    """The noticeboard, as the caller sees it."""

    permission_classes = (IsActiveUser,)
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = AnnouncementFilterSet
    search_fields = ("title", "body")
    ordering_fields = ("published_at", "created_at")
    ordering = ("-is_pinned", "-published_at")

    def get_serializer_class(self):
        # A student reads the board; they do not need its editorial state.
        return (
            AnnouncementSerializer
            if batch_access.student_profile(self.request.user) is None
            else StudentAnnouncementSerializer
        )

    def get_queryset(self):
        return access.visible_announcements(self.request.user)

    @extend_schema(summary="Announcements", tags=ANNOUNCEMENTS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Write an announcement",
        request=AnnouncementWriteSerializer,
        responses={201: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = AnnouncementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields, recipients = _resolve(request, serializer.validated_data)

        audience = fields.get("audience", Audience.BATCH)
        if not access.can_publish_to(
            request.user,
            audience=audience,
            course=fields.get("course"),
            batch=fields.get("batch"),
        ):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="announcement",
                resource_id="",
                result="failure",
                context={"attempted": "announcement.create", "audience": audience},
            )
            return _forbidden(request, "You cannot address that audience.")

        announcement = services.create_announcement(
            actor=request.user, recipients=recipients, **fields
        )
        return Response(
            AnnouncementSerializer(announcement).data, status=http_status.HTTP_201_CREATED
        )


def _announcement_for(request, announcement_id, *, manage: bool = False) -> Announcement:
    source = (
        access.manageable_announcements(request.user)
        if manage
        else access.visible_announcements(request.user)
    )
    return get_object_or_404(source, pk=announcement_id)


class AnnouncementDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="An announcement",
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def get(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id)
        if access.can_manage(request.user, announcement):
            return Response(AnnouncementSerializer(announcement).data)
        return Response(StudentAnnouncementSerializer(announcement).data)

    @extend_schema(
        summary="Edit an announcement",
        request=AnnouncementWriteSerializer,
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def patch(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        serializer = AnnouncementWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields, recipients = _resolve(request, serializer.validated_data)
        announcement = services.update_announcement(
            announcement=announcement,
            actor=request.user,
            recipients=recipients or None,
            **fields,
        )
        return Response(AnnouncementSerializer(announcement).data)


class PublishAnnouncementView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish an announcement",
        request=None,
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        announcement = services.publish(announcement=announcement, actor=request.user)
        return Response(AnnouncementSerializer(announcement).data)


class ArchiveAnnouncementView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Take an announcement off the board",
        request=None,
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        announcement = services.archive(announcement=announcement, actor=request.user)
        return Response(AnnouncementSerializer(announcement).data)


class AudiencePreviewView(APIView):
    """How many people an announcement would reach. Asked before publishing."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Who this announcement reaches",
        responses={200: OpenApiResponse(description="A count of recipients.")},
        tags=ANNOUNCEMENTS_TAG,
    )
    def get(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        return Response({"recipients": len(services.audience_for(announcement))})
