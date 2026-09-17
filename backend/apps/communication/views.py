"""Communication centre API (ERP Phase 19).

The WhatsApp webhook lives in `webhooks.py`, not here — it is the one
endpoint in this codebase that is deliberately not session-authenticated,
and keeping it in its own module makes that easy to grep for during a
security review.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.accounts.stepup import StepUpRequired, is_fresh
from apps.common.pagination import DefaultPagination
from apps.common.permissions import HasCapability
from apps.common.throttling import CommunicationThrottle
from apps.organisation.scoping import scope_to_branch

from . import services
from .models import Delivery, MessageChannel, MessageTemplate, TemplateVersion
from .serializers import (
    DeliverySerializer,
    ManualSendSerializer,
    MessageTemplateSerializer,
    RenderResultSerializer,
    TemplateCreateSerializer,
    TemplateRenderRequestSerializer,
    TemplateVersionSerializer,
    TemplateVersionWriteSerializer,
)

COMMUNICATION_TAG = ["communication"]


def _template_for(key: str) -> MessageTemplate:
    return get_object_or_404(MessageTemplate.objects.with_related(), key=key)


def _version_for(template: MessageTemplate, number: int) -> TemplateVersion:
    return get_object_or_404(TemplateVersion.objects.filter(template=template), number=number)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateListCreateView(ListAPIView):
    permission_classes = (HasCapability,)
    capability_map = {"GET": Capability.TEMPLATE_MANAGE, "POST": Capability.TEMPLATE_MANAGE}
    serializer_class = MessageTemplateSerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MessageTemplate.objects.none()
        return MessageTemplate.objects.with_related().order_by("key")

    @extend_schema(summary="Message templates", tags=COMMUNICATION_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a message template",
        request=TemplateCreateSerializer,
        responses={201: MessageTemplateSerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = TemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = services.create_template(actor=request.user, **serializer.validated_data)
        return Response(MessageTemplateSerializer(template).data, status=201)


class TemplateDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    serializer_class = MessageTemplateSerializer

    @extend_schema(
        summary="A message template",
        responses={200: MessageTemplateSerializer},
        tags=COMMUNICATION_TAG,
    )
    def get(self, request, key):
        return Response(MessageTemplateSerializer(_template_for(key)).data)


class TemplateVersionCreateView(APIView):
    """`POST /templates/{key}/versions/` — a new draft on top of whatever
    is currently published."""

    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    serializer_class = TemplateVersionSerializer

    @extend_schema(
        summary="Open a new draft template version",
        request=None,
        responses={201: TemplateVersionSerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, key):
        template = _template_for(key)
        version = services.create_draft_version(actor=request.user, template=template)
        return Response(TemplateVersionSerializer(version).data, status=201)


class TemplateVersionDetailView(APIView):
    """`PUT /templates/{key}/versions/{number}/` — draft only, 409 once
    published."""

    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    serializer_class = TemplateVersionSerializer

    @extend_schema(
        summary="A template version",
        responses={200: TemplateVersionSerializer},
        tags=COMMUNICATION_TAG,
    )
    def get(self, request, key, number):
        template = _template_for(key)
        return Response(TemplateVersionSerializer(_version_for(template, number)).data)

    @extend_schema(
        summary="Edit a draft template version",
        request=TemplateVersionWriteSerializer,
        responses={200: TemplateVersionSerializer},
        tags=COMMUNICATION_TAG,
    )
    def put(self, request, key, number):
        template = _template_for(key)
        version = _version_for(template, number)
        serializer = TemplateVersionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        version = services.update_draft_version(
            actor=request.user, version=version, **serializer.validated_data
        )
        return Response(TemplateVersionSerializer(version).data)


class TemplateVersionApproveView(APIView):
    """`POST .../versions/{number}/approve/` — `template.approve`. A
    WhatsApp-channel template additionally requires a fresh step-up
    (`API_CONTRACTS.md`'s own "WhatsApp: step-up" note) — checked here,
    before the service is called, the same place `apps.policies.views` and
    `apps.authorization.views` check it for their own critical actions."""

    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_APPROVE
    serializer_class = TemplateVersionSerializer

    @extend_schema(
        summary="Approve a template version",
        request=None,
        responses={200: TemplateVersionSerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, key, number):
        template = _template_for(key)
        version = _version_for(template, number)
        if template.channel == MessageChannel.WHATSAPP and not is_fresh(request):
            raise StepUpRequired()
        version = services.approve_version(actor=request.user, version=version)
        return Response(TemplateVersionSerializer(version).data)


class TemplateVersionPublishView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    serializer_class = TemplateVersionSerializer

    @extend_schema(
        summary="Publish a template version",
        request=None,
        responses={200: TemplateVersionSerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, key, number):
        template = _template_for(key)
        version = _version_for(template, number)
        version = services.publish_version(actor=request.user, version=version)
        return Response(TemplateVersionSerializer(version).data)


class TemplateVersionPreviewView(APIView):
    """`POST .../versions/{number}/preview/` — render only. Never sends,
    never creates a `Delivery` row (D-051)."""

    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    serializer_class = RenderResultSerializer

    @extend_schema(
        summary="Preview a template version",
        request=TemplateRenderRequestSerializer,
        responses={200: RenderResultSerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, key, number):
        template = _template_for(key)
        version = _version_for(template, number)
        serializer = TemplateRenderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.preview_version(
            version=version, variables=serializer.validated_data.get("variables", {})
        )
        return Response(RenderResultSerializer(result).data)


class TemplateVersionTestSendView(APIView):
    """`POST .../versions/{number}/test-send/` — to the caller's own
    address only. Throttle scope `communication`."""

    permission_classes = (HasCapability,)
    required_capability = Capability.TEMPLATE_MANAGE
    throttle_classes = (CommunicationThrottle,)
    serializer_class = DeliverySerializer

    @extend_schema(
        summary="Send a live test of a template version to yourself",
        request=None,
        responses={201: DeliverySerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, key, number):
        template = _template_for(key)
        version = _version_for(template, number)
        delivery = services.test_send(actor=request.user, version=version)
        return Response(DeliverySerializer(delivery).data, status=201)


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


class DeliveryFilterSet(django_filters.FilterSet):
    channel = django_filters.CharFilter(field_name="channel")
    state = django_filters.CharFilter(field_name="state")
    recipient = django_filters.UUIDFilter(field_name="recipient_id")
    template = django_filters.CharFilter(field_name="template_version__template__key")
    since = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Delivery
        fields = ("channel", "state", "recipient", "template", "since", "until")


class DeliveryListView(ListAPIView):
    """`GET /deliveries/` — `communication.view_any`, scoped by the
    recipient's own branch. Every OTP send bypasses this app entirely (see
    `services.py`'s module docstring), so there is no OTP-purposed row to
    ever appear here or need scrubbing."""

    permission_classes = (HasCapability,)
    required_capability = Capability.COMMUNICATION_VIEW_ANY
    serializer_class = DeliverySerializer
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DeliveryFilterSet

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Delivery.objects.none()
        return scope_to_branch(
            Delivery.objects.with_related(),
            self.request.user,
            path="recipient__branch",
            capability=Capability.COMMUNICATION_VIEW_ANY,
        ).order_by("-created_at")

    @extend_schema(summary="Delivery log", tags=COMMUNICATION_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _delivery_for(request, delivery_id) -> Delivery:
    return get_object_or_404(
        scope_to_branch(
            Delivery.objects.with_related(),
            request.user,
            path="recipient__branch",
            capability=Capability.COMMUNICATION_VIEW_ANY,
        ),
        pk=delivery_id,
    )


class DeliveryRetryView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.COMMUNICATION_SEND
    serializer_class = DeliverySerializer

    @extend_schema(
        summary="Retry a failed delivery",
        request=None,
        responses={200: DeliverySerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, delivery_id):
        delivery = _delivery_for(request, delivery_id)
        delivery = services.retry_delivery(actor=request.user, delivery=delivery)
        return Response(DeliverySerializer(delivery).data)


class DeliveryCancelView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.COMMUNICATION_SEND
    serializer_class = DeliverySerializer

    @extend_schema(
        summary="Cancel a queued delivery",
        request=None,
        responses={200: DeliverySerializer},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request, delivery_id):
        delivery = _delivery_for(request, delivery_id)
        delivery = services.cancel_delivery(actor=request.user, delivery=delivery)
        return Response(DeliverySerializer(delivery).data)


# ---------------------------------------------------------------------------
# Manual send
# ---------------------------------------------------------------------------


class ManualSendView(APIView):
    """`POST /communication/send/` — `communication.send`, throttle
    `communication`. `confirm_count` must match the freshly recomputed
    recipient count or the request is refused with 409."""

    permission_classes = (HasCapability,)
    required_capability = Capability.COMMUNICATION_SEND
    throttle_classes = (CommunicationThrottle,)
    serializer_class = ManualSendSerializer

    @extend_schema(
        summary="Send a message to a resolved recipient set",
        request=ManualSendSerializer,
        responses={201: None},
        tags=COMMUNICATION_TAG,
    )
    def post(self, request):
        serializer = ManualSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.manual_send(
            actor=request.user,
            channel=data["channel"],
            template_key=data["template"],
            recipients_spec=data["recipients"],
            variables=data.get("variables"),
            confirm_count=data["confirm_count"],
        )
        return Response(result, status=201)
