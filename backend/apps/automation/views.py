"""Automation builder API (``/api/v1/automation-rules/``, ERP Phase 14,
ADR-13). One capability, ``automation.manage``, guards every read and write
— the catalog's own PERMISSION_CATALOG.md row: there is nothing in a rule's
conditions or actions a read-only view would show that a person who may not
change it should see, since seeing it *is* seeing exactly how to reproduce
or defeat it.
"""

from __future__ import annotations

import uuid as uuid_lib

from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, ListCreateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.common.pagination import DefaultPagination
from apps.common.permissions import HasCapability
from apps.organisation.models import Branch

from . import services
from .models import AutomationRule, AutomationRun
from .serializers import (
    AutomationRuleCreateSerializer,
    AutomationRuleSerializer,
    AutomationRuleWriteSerializer,
    AutomationRunSerializer,
    DeleteReasonSerializer,
    DryRunResultSerializer,
    PauseReasonSerializer,
)

TAG = ["Automation"]


def _rule_or_404(pk: str) -> AutomationRule:
    try:
        pk = str(uuid_lib.UUID(str(pk)))
    except (ValueError, AttributeError, TypeError):
        raise Http404("Not a valid automation rule id.") from None
    return get_object_or_404(AutomationRule.objects.with_related(), pk=pk)


def _branch_or_400(branch_id) -> Branch | None:
    if not branch_id:
        return None
    return get_object_or_404(Branch.objects.all(), pk=branch_id)


class AutomationRuleListCreateView(ListCreateAPIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    pagination_class = DefaultPagination
    queryset = AutomationRule.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AutomationRule.objects.none()
        # "A cheap check on read" (`AUTOMATION_CATALOG.md`) — pauses any
        # rule whose author has since lost a permission one of its own
        # actions needs, before the list is served.
        services.sync_rule_authors()
        return AutomationRule.objects.with_related().order_by("name")

    @extend_schema(
        summary="List automation rules",
        responses={200: AutomationRuleSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create an automation rule",
        request=AutomationRuleCreateSerializer,
        responses={
            201: AutomationRuleSerializer,
            403: OpenApiResponse(description="An action needs a permission you do not hold"),
        },
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = AutomationRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        branch = _branch_or_400(data.pop("branch", None))
        rule = services.create_rule(actor=request.user, branch=branch, **data)
        return Response(AutomationRuleSerializer(rule).data, status=http_status.HTTP_201_CREATED)


class AutomationRuleDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    serializer_class = AutomationRuleSerializer

    @extend_schema(
        summary="Read one automation rule",
        responses={200: AutomationRuleSerializer},
        tags=TAG,
    )
    def get(self, request, pk):
        rule = _rule_or_404(pk)
        return Response(AutomationRuleSerializer(rule).data)

    @extend_schema(
        summary="Edit an automation rule",
        request=AutomationRuleWriteSerializer,
        responses={
            200: AutomationRuleSerializer,
            403: OpenApiResponse(description="An action needs a permission you do not hold"),
        },
        tags=TAG,
    )
    def patch(self, request, pk):
        rule = _rule_or_404(pk)
        serializer = AutomationRuleWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "branch" in data:
            data["branch"] = _branch_or_400(data["branch"])
        rule = services.update_rule(rule=rule, actor=request.user, **data)
        return Response(AutomationRuleSerializer(rule).data)

    @extend_schema(
        summary="Delete an automation rule",
        request=DeleteReasonSerializer,
        responses={204: OpenApiResponse(description="Deleted")},
        tags=TAG,
    )
    def delete(self, request, pk):
        rule = _rule_or_404(pk)
        serializer = DeleteReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.delete_rule(
            rule=rule, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class AutomationRuleActivateView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    serializer_class = AutomationRuleSerializer

    @extend_schema(
        summary="Activate an automation rule",
        responses={200: AutomationRuleSerializer},
        tags=TAG,
    )
    def post(self, request, pk):
        rule = _rule_or_404(pk)
        rule = services.activate_rule(rule=rule, actor=request.user)
        return Response(AutomationRuleSerializer(rule).data)


class AutomationRulePauseView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    serializer_class = AutomationRuleSerializer

    @extend_schema(
        summary="Pause an automation rule",
        request=PauseReasonSerializer,
        responses={200: AutomationRuleSerializer},
        tags=TAG,
    )
    def post(self, request, pk):
        rule = _rule_or_404(pk)
        serializer = PauseReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = services.pause_rule(
            rule=rule, actor=request.user, reason=serializer.validated_data.get("reason", "")
        )
        return Response(AutomationRuleSerializer(rule).data)


class AutomationRuleDryRunView(APIView):
    """ "Test against a recent event" (`AUTOMATION_CATALOG.md`'s builder
    contract) — evaluates, never executes, never writes an `AutomationRun`."""

    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    serializer_class = DryRunResultSerializer

    @extend_schema(
        summary="Dry-run an automation rule against its last 20 real events",
        responses={200: DryRunResultSerializer(many=True)},
        tags=TAG,
    )
    def post(self, request, pk):
        rule = _rule_or_404(pk)
        results = services.dry_run(rule)
        return Response(DryRunResultSerializer(results, many=True).data)


class AutomationRuleRunsView(ListAPIView):
    """A rule's own `AutomationRun` history, newest first."""

    permission_classes = (HasCapability,)
    required_capability = Capability.AUTOMATION_MANAGE
    serializer_class = AutomationRunSerializer
    pagination_class = DefaultPagination
    queryset = AutomationRun.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AutomationRun.objects.none()
        rule = _rule_or_404(self.kwargs["pk"])
        return AutomationRun.objects.with_related().filter(rule=rule)

    @extend_schema(
        summary="An automation rule's run history",
        responses={200: AutomationRunSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
