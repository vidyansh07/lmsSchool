"""Integration endpoints.

`POST leads/` is the one door from outside: no session, no CSRF, an API key
in `Authorization: Bearer grk_…` (or `X-Api-Key`), throttled per key. All the
rest is the administrator's screen, behind `integration.manage`.
"""

from __future__ import annotations

from django.db.models import Count
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import Capability, HasCapability

from . import services
from .models import ApiKey, IntakeStatus, Webhook
from .presets import LEAD_FIELDS, WEBHOOK_HEADERS
from .serializers import (
    ApiKeyCreatedSerializer,
    ApiKeySerializer,
    ApiKeyWriteSerializer,
    LeadIntakeSerializer,
    LeadResponseSerializer,
    WebhookDeliverySerializer,
    WebhookSavedSerializer,
    WebhookSerializer,
    WebhookWriteSerializer,
)

TAG = ["Integrations"]


def _branch(branch_id):
    if not branch_id:
        return None
    from apps.organisation.models import Branch

    return get_object_or_404(Branch, pk=branch_id)


class _ManageView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.INTEGRATION_MANAGE


class LeadKeyThrottle(SimpleRateThrottle):
    scope = "integration_leads"

    def get_cache_key(self, request, view):
        header = request.headers.get("Authorization") or request.headers.get("X-Api-Key") or ""
        token = header.split()[-1] if header else ""
        ident = token[:16] if token.startswith(services.KEY_PREFIX) else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LeadIntakeView(APIView):
    """Create or update an enquiry from another system."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (LeadKeyThrottle,)

    @extend_schema(
        summary="Send a lead (API key)",
        description=(
            "Authenticate with `Authorization: Bearer grk_…`. One lead per request, as a "
            "JSON object. `full_name`/`name` and `mobile`/`phone` are required; Meritto's "
            "field names are accepted by a Meritto key."
        ),
        request={"application/json": {"type": "object"}},
        responses={
            201: LeadResponseSerializer,
            200: LeadResponseSerializer,
            400: LeadResponseSerializer,
            401: OpenApiResponse(description="No valid API key."),
        },
        tags=TAG,
    )
    def post(self, request):
        header = request.headers.get("Authorization") or request.headers.get("X-Api-Key") or ""
        key = services.authenticate(header)
        if key is None:
            return Response(
                {"detail": "A valid API key is required."}, status=status.HTTP_401_UNAUTHORIZED
            )
        intake = services.receive_lead(key=key, payload=request.data)
        body = {
            "status": intake.status,
            "enquiry_id": intake.enquiry_id,
        }
        if intake.status == IntakeStatus.REJECTED:
            body["errors"] = intake.errors
            return Response(body, status=status.HTTP_400_BAD_REQUEST)
        code = status.HTTP_201_CREATED if intake.status == IntakeStatus.CREATED else 200
        return Response(body, status=code)


class PresetsView(_ManageView):
    @extend_schema(summary="What each preset maps", responses={200: dict}, tags=TAG)
    def get(self, request):
        return Response(
            {
                preset: {"lead_fields": LEAD_FIELDS[preset], "headers": WEBHOOK_HEADERS[preset]}
                for preset in LEAD_FIELDS
            }
        )


class ApiKeyListView(_ManageView):
    @extend_schema(summary="API keys", responses={200: ApiKeySerializer(many=True)}, tags=TAG)
    def get(self, request):
        rows = (
            ApiKey.objects.select_related("branch", "created_by")
            .annotate(intake_count=Count("intakes"))
            .order_by("-created_at")
        )
        return Response(ApiKeySerializer(rows, many=True).data)

    @extend_schema(
        summary="Create an API key (the key is shown once)",
        request=ApiKeyWriteSerializer,
        responses={201: ApiKeyCreatedSerializer},
        tags=TAG,
    )
    def post(self, request):
        serializer = ApiKeyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data.get("name"):
            return Response({"name": ["Give the key a name."]}, status=400)
        key, plaintext = services.create_api_key(
            actor=request.user,
            name=data["name"],
            preset=data.get("preset", "generic"),
            branch=_branch(data.get("branch")),
            default_source=data.get("default_source", "website"),
            field_map=data.get("field_map") or {},
        )
        key.key = plaintext
        return Response(ApiKeyCreatedSerializer(key).data, status=status.HTTP_201_CREATED)


class ApiKeyDetailView(_ManageView):
    @extend_schema(
        summary="Change an API key",
        request=ApiKeyWriteSerializer,
        responses={200: ApiKeySerializer},
        tags=TAG,
    )
    def patch(self, request, key_id):
        key = get_object_or_404(ApiKey, pk=key_id)
        serializer = ApiKeyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        fields.pop("preset", None)  # a key's preset is fixed at creation
        if "branch" in fields:
            fields["branch"] = _branch(fields["branch"])
        services.update_api_key(actor=request.user, key=key, **fields)
        return Response(ApiKeySerializer(key).data)


class ApiKeyRevokeView(_ManageView):
    @extend_schema(
        summary="Revoke an API key", request=None, responses={200: ApiKeySerializer}, tags=TAG
    )
    def post(self, request, key_id):
        key = get_object_or_404(ApiKey, pk=key_id)
        services.revoke_api_key(actor=request.user, key=key)
        return Response(ApiKeySerializer(key).data)


class ApiKeyIntakesView(_ManageView):
    @extend_schema(
        summary="The last leads a key sent",
        responses={200: LeadIntakeSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, key_id):
        key = get_object_or_404(ApiKey, pk=key_id)
        rows = key.intakes.select_related("enquiry").order_by("-created_at")[:100]
        return Response(LeadIntakeSerializer(rows, many=True).data)


class WebhookListView(_ManageView):
    @extend_schema(summary="Webhooks", responses={200: WebhookSerializer(many=True)}, tags=TAG)
    def get(self, request):
        return Response(WebhookSerializer(Webhook.objects.order_by("name"), many=True).data)

    @extend_schema(
        summary="Create a webhook (the signing secret is shown once)",
        request=WebhookWriteSerializer,
        responses={201: WebhookSavedSerializer},
        tags=TAG,
    )
    def post(self, request):
        serializer = WebhookWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("rotate_secret", None)
        webhook, secret = services.save_webhook(actor=request.user, **data)
        webhook.secret = secret
        return Response(WebhookSavedSerializer(webhook).data, status=status.HTTP_201_CREATED)


class WebhookDetailView(_ManageView):
    @extend_schema(
        summary="Change a webhook",
        request=WebhookWriteSerializer,
        responses={200: WebhookSavedSerializer},
        tags=TAG,
    )
    def patch(self, request, webhook_id):
        webhook = get_object_or_404(Webhook, pk=webhook_id)
        serializer = WebhookWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook, secret = services.save_webhook(
            actor=request.user, webhook=webhook, **serializer.validated_data
        )
        webhook.secret = secret
        return Response(WebhookSavedSerializer(webhook).data)


class WebhookTestView(_ManageView):
    @extend_schema(
        summary="Send a test event to a webhook",
        request=None,
        responses={200: WebhookDeliverySerializer},
        tags=TAG,
    )
    def post(self, request, webhook_id):
        webhook = get_object_or_404(Webhook, pk=webhook_id)
        delivery = services.send_test(actor=request.user, webhook=webhook)
        return Response(WebhookDeliverySerializer(delivery).data)


class WebhookDeliveriesView(_ManageView):
    @extend_schema(
        summary="The last deliveries to a webhook",
        responses={200: WebhookDeliverySerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, webhook_id):
        webhook = get_object_or_404(Webhook, pk=webhook_id)
        rows = webhook.deliveries.select_related("rule").order_by("-created_at")[:100]
        return Response(WebhookDeliverySerializer(rows, many=True).data)
