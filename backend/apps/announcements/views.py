"""Announcement API — §7.3."""

from __future__ import annotations

import django_filters
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import visible_accounts
from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.courses import access as course_access

from . import access, services
from .models import Announcement, Audience
from .serializers import (
    AnnouncementDeleteSerializer,
    AnnouncementScheduleSerializer,
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
    role_id = fields.pop("role", None)
    branch_id = fields.pop("branch", None)
    recipient_ids = fields.pop("recipients", None)

    if course_id:
        fields["course"] = get_object_or_404(
            course_access.visible_courses(request.user), pk=course_id
        )
    if batch_id:
        fields["batch"] = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
    if role_id:
        from apps.authorization.models import Role

        fields["role"] = get_object_or_404(Role.objects, pk=role_id)
    if branch_id:
        from apps.organisation.models import Branch

        fields["branch"] = get_object_or_404(Branch.objects, pk=branch_id)

    recipients = []
    if recipient_ids:
        # Through the caller's own reach, like the course and the batch above.
        # Resolving these from `User.objects` let a manager in one city address
        # a student in another — a notice on their board and a notification in
        # their tray — and made the create a quiet existence oracle for account
        # ids, since only a real active account survived the filter.
        #
        # Every named id must resolve, so a wrong one is a 404 rather than a
        # silently shorter recipient list.
        reachable = visible_accounts(request.user).filter(pk__in=recipient_ids, is_active=True)
        recipients = list(reachable)
        if len(recipients) != len(set(recipient_ids)):
            raise Http404("No such recipient.")
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


class ScheduleAnnouncementView(APIView):
    """`POST /announcements/{id}/schedule/` — draft → scheduled."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Schedule an announcement",
        request=AnnouncementScheduleSerializer,
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        serializer = AnnouncementScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = services.schedule(
            announcement=announcement,
            actor=request.user,
            publish_at=serializer.validated_data["publish_at"],
        )
        return Response(AnnouncementSerializer(announcement).data)


class CancelScheduledAnnouncementView(APIView):
    """`POST /announcements/{id}/cancel/` — scheduled → cancelled."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Cancel a scheduled announcement",
        request=None,
        responses={200: AnnouncementSerializer},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        announcement = services.cancel_scheduled(announcement=announcement, actor=request.user)
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


class DeleteAnnouncementView(APIView):
    """Soft-delete a notice (Phase 7). Reversible, and always with a reason —
    distinct from :class:`ArchiveAnnouncementView`, which is the editorial
    "take it off the board" transition, not a removal into the recycle bin."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Delete an announcement",
        request=AnnouncementDeleteSerializer,
        responses={204: None},
        tags=ANNOUNCEMENTS_TAG,
    )
    def post(self, request, announcement_id):
        announcement = _announcement_for(request, announcement_id, manage=True)
        serializer = AnnouncementDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_announcement(
            announcement=announcement,
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


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
