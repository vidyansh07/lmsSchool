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

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError
from apps.common.permissions import Capability, HasCapability, IsActiveUser

from . import messaging, services
from .models import (
    EVENT_TABS,
    MessageChannelKind,
    MessageEvent,
    MessageRecipient,
    MessageRule,
    Notification,
)
from .serializers import (
    MessageMatrixSerializer,
    NotificationSerializer,
    PreferenceSerializer,
    PreferenceWriteSerializer,
    SetMessageRulesSerializer,
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


class MessageSettingsView(APIView):
    """The message matrix: who hears about what, and how.

    `settings.manage` — the institution's own settings, which is an
    administrator's job. Deliberately not `platform.configure`, which is
    superadmin-only and exists to withhold the ladder's top rung: locking
    every administrator out of the screen they are the intended user of would
    be the wrong reading of "this is a policy decision".

    It is still not a counsellor's or a manager's. Whether a parent gets a
    text message about their child's money is a decision the institute takes
    once, not one that is made from whichever screen somebody happens to
    open.

    `GET` sends the shape as well as the data — the tabs, their events in
    order, the recipients and the channels — so the screen never carries its
    own copy of the list. A screen that hardcodes the events drifts the
    moment one is added, and the first anybody knows is a message nobody can
    turn off.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.SETTINGS_MANAGE
    serializer_class = MessageMatrixSerializer

    @extend_schema(
        summary="Message settings",
        responses={200: MessageMatrixSerializer},
        tags=["Notifications"],
    )
    def get(self, request):
        return Response(self._shape())

    @extend_schema(
        summary="Change message settings",
        request=SetMessageRulesSerializer,
        responses={200: MessageMatrixSerializer},
        tags=["Notifications"],
    )
    def put(self, request):
        serializer = SetMessageRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        known_events = set(MessageEvent.values)
        known_recipients = set(MessageRecipient.values)
        known_channels = set(MessageChannelKind.values)
        for row in serializer.validated_data["rules"]:
            if (
                row["event"] not in known_events
                or row["recipient"] not in known_recipients
                or row["channel"] not in known_channels
            ):
                # Refused rather than ignored: a cell nobody can see is a
                # message nobody can turn off.
                raise ApplicationError({"rules": ["No such event, recipient or channel."]})
            messaging.set_cell(
                event=row["event"],
                recipient=row["recipient"],
                channel=row["channel"],
                enabled=row["is_enabled"],
            )

        record(
            action=AuditAction.SYSTEM_SETTINGS_UPDATED,
            actor=request.user,
            resource_type="message_settings",
            resource_id="",
            context={"cells": len(serializer.validated_data["rules"])},
            durable=False,
        )
        return Response(self._shape())

    def _shape(self) -> dict:
        labels = dict(MessageEvent.choices)
        return {
            "tabs": [
                {
                    "title": title,
                    "events": [{"key": event, "label": labels[event]} for event in events],
                }
                for title, events in EVENT_TABS
            ],
            "recipients": [{"key": key, "label": label} for key, label in MessageRecipient.choices],
            "channels": [{"key": key, "label": label} for key, label in MessageChannelKind.choices],
            "rules": [
                {
                    "event": rule.event,
                    "recipient": rule.recipient,
                    "channel": rule.channel,
                    "is_enabled": rule.is_enabled,
                }
                for rule in MessageRule.objects.all()
            ],
        }
