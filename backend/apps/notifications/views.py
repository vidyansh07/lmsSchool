"""Notification API.

Everything here is scoped to the caller by construction: a notification belongs
to exactly one person, and the queryset filters on `recipient=request.user`.
There is no staff view of somebody else's notifications, because there is no
reason for one — the audit trail is where "what did the system tell this
student?" is answered.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsActiveUser

from . import services
from .models import Notification
from .serializers import (
    NotificationSerializer,
    PreferenceSerializer,
    PreferenceWriteSerializer,
    UnreadCountSerializer,
)

NOTIFICATIONS_TAG = ["notifications"]


class NotificationFilterSet(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category", lookup_expr="exact")
    kind = django_filters.CharFilter(field_name="kind", lookup_expr="exact")
    unread = django_filters.BooleanFilter(method="filter_unread")

    class Meta:
        model = Notification
        fields = ("category", "kind")

    def filter_unread(self, queryset, name, value):
        return queryset.filter(read_at__isnull=True) if value else queryset


class NotificationListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = NotificationSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = NotificationFilterSet
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)
    # Declared so schema generation can find the model without a request; the
    # real queryset is built per request below.
    queryset = Notification.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.for_user(self.request.user)

    @extend_schema(summary="My notifications", tags=NOTIFICATIONS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UnreadCountView(APIView):
    """What the bell shows. Cheap enough to poll."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="How many notifications are unread",
        responses={200: UnreadCountSerializer},
        tags=NOTIFICATIONS_TAG,
    )
    def get(self, request):
        count = Notification.objects.for_user(request.user).unread().count()
        return Response(UnreadCountSerializer({"unread": count}).data)


class MarkReadView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Mark one notification read",
        request=None,
        responses={200: NotificationSerializer},
        tags=NOTIFICATIONS_TAG,
    )
    def post(self, request, notification_id):
        notification = get_object_or_404(
            Notification.objects.for_user(request.user), pk=notification_id
        )
        services.mark_read(notification=notification)
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Mark everything read",
        request=None,
        responses={200: UnreadCountSerializer},
        tags=NOTIFICATIONS_TAG,
    )
    def post(self, request):
        services.mark_all_read(user=request.user)
        return Response(UnreadCountSerializer({"unread": 0}).data)


class PreferenceView(APIView):
    """Which categories reach the caller by email."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My notification settings",
        responses={200: PreferenceSerializer},
        tags=NOTIFICATIONS_TAG,
    )
    def get(self, request):
        return Response(PreferenceSerializer(services.preferences_for(request.user)).data)

    @extend_schema(
        summary="Change my notification settings",
        request=PreferenceWriteSerializer,
        responses={200: PreferenceSerializer},
        tags=NOTIFICATIONS_TAG,
    )
    def patch(self, request):
        serializer = PreferenceWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        preference = services.update_preferences(user=request.user, **serializer.validated_data)
        return Response(PreferenceSerializer(preference).data)
