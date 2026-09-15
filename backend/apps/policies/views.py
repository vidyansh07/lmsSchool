"""Policy API (``/api/v1/policies/``, ERP Phase 3, ADR-04).

Reading is `policy.view` (superadmin, admin, manager); writing and resetting
are `policy.manage` (superadmin, admin only — `docs/erp/PERMISSION_CATALOG.md`).
A branch-scoped caller (a manager holds `policy.view` at scope `branch`, per
ADR-02) may only name their own centre; an unbounded caller may name any
branch or none (the institution-wide row). A critical key additionally needs
a fresh step-up (SECURITY_DECISIONS "critical policy change") and, on write,
`confirm` naming the key exactly.
"""

from __future__ import annotations

import uuid as uuid_lib

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.accounts.stepup import StepUpRequired, is_fresh
from apps.authorization.scopes import ALL, effective_scope
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.pagination import DefaultPagination
from apps.common.permissions import HasCapability
from apps.organisation.models import Branch
from apps.organisation.scoping import actor_branch_id

from . import services
from .models import PolicyVersion
from .schemas import schema_for
from .serializers import PolicyEntrySerializer, PolicyVersionSerializer, PolicyWriteSerializer

TAG = ["Policies"]

BRANCH_PARAM = OpenApiParameter(
    "branch", str, description="A branch id, to read or write that centre's override."
)
CATEGORY_PARAM = OpenApiParameter("category", str, description="Narrow to one policy category.")


def _schema_or_404(category: str, key: str) -> dict:
    schema = schema_for(category, key)
    if schema is None:
        raise Http404(f"Unknown policy: {category}.{key}")
    return schema


def _resolve_branch(user, branch_id, *, capability: str, require_own_when_scoped: bool):
    """Which branch this caller may act on, or ``None`` for the institution-
    wide row. A guessed branch id 404s before the scope check runs (rule 2);
    a real branch outside the caller's reach is refused (403), never leaked
    as a 404 that would tell an attacker the id was valid."""
    scope = effective_scope(user, capability)
    if branch_id is None:
        if require_own_when_scoped and scope != ALL:
            raise AuthorityError(
                "Choose your own centre: a branch-scoped role cannot set the "
                "institution-wide value."
            )
        return None
    try:
        branch_id = str(uuid_lib.UUID(str(branch_id)))
    except (ValueError, AttributeError, TypeError):
        raise ApplicationError({"branch": ["Enter a valid branch id."]}) from None
    branch = get_object_or_404(Branch.objects.all(), pk=branch_id)
    if scope != ALL and str(branch.pk) != str(actor_branch_id(user)):
        raise AuthorityError("You may only reach policies for your own centre.")
    return branch


class PolicyListView(APIView):
    """Every policy key, resolved for a branch (or institution-wide)."""

    permission_classes = (HasCapability,)
    required_capability = Capability.POLICY_VIEW

    @extend_schema(
        summary="Every policy, resolved",
        parameters=[CATEGORY_PARAM, BRANCH_PARAM],
        responses={200: PolicyEntrySerializer(many=True)},
        tags=TAG,
    )
    def get(self, request):
        category = request.query_params.get("category") or None
        branch = _resolve_branch(
            request.user,
            request.query_params.get("branch") or None,
            capability=Capability.POLICY_VIEW,
            require_own_when_scoped=False,
        )
        entries = services.list_policies(category=category, branch=branch)
        return Response(PolicyEntrySerializer(entries, many=True).data)


class PolicyDetailView(APIView):
    """Read, change or reset one policy key."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.POLICY_VIEW,
        "PUT": Capability.POLICY_MANAGE,
        "DELETE": Capability.POLICY_MANAGE,
    }

    @extend_schema(
        summary="One policy, resolved",
        parameters=[BRANCH_PARAM],
        responses={200: PolicyEntrySerializer, 404: OpenApiResponse(description="Unknown policy")},
        tags=TAG,
    )
    def get(self, request, category, key):
        _schema_or_404(category, key)
        branch = _resolve_branch(
            request.user,
            request.query_params.get("branch") or None,
            capability=Capability.POLICY_VIEW,
            require_own_when_scoped=False,
        )
        return Response(
            PolicyEntrySerializer(
                services.get_policy(category=category, key=key, branch=branch)
            ).data
        )

    @extend_schema(
        summary="Change a policy",
        request=PolicyWriteSerializer,
        responses={
            200: PolicyEntrySerializer,
            400: OpenApiResponse(description="Fails the schema, or a critical key without confirm"),
            403: OpenApiResponse(description="Outside the caller's scope, or step-up required"),
            404: OpenApiResponse(description="Unknown policy"),
        },
        tags=TAG,
    )
    def put(self, request, category, key):
        schema = _schema_or_404(category, key)
        if schema.get("critical") and not is_fresh(request):
            raise StepUpRequired()
        serializer = PolicyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        branch = _resolve_branch(
            request.user,
            data.pop("branch"),
            capability=Capability.POLICY_MANAGE,
            require_own_when_scoped=True,
        )
        services.update_policy(
            actor=request.user, category=category, key=key, branch=branch, **data
        )
        return Response(
            PolicyEntrySerializer(
                services.get_policy(category=category, key=key, branch=branch)
            ).data
        )

    @extend_schema(
        summary="Reset a policy to its schema default",
        parameters=[BRANCH_PARAM],
        responses={
            200: PolicyEntrySerializer,
            403: OpenApiResponse(description="Outside the caller's scope, or step-up required"),
            404: OpenApiResponse(description="Unknown policy"),
        },
        tags=TAG,
    )
    def delete(self, request, category, key):
        schema = _schema_or_404(category, key)
        if schema.get("critical") and not is_fresh(request):
            raise StepUpRequired()
        branch = _resolve_branch(
            request.user,
            request.query_params.get("branch") or None,
            capability=Capability.POLICY_MANAGE,
            require_own_when_scoped=True,
        )
        services.reset_policy(actor=request.user, category=category, key=key, branch=branch)
        return Response(
            PolicyEntrySerializer(
                services.get_policy(category=category, key=key, branch=branch)
            ).data,
            status=http_status.HTTP_200_OK,
        )


class PolicyHistoryView(ListAPIView):
    """A policy's `PolicyVersion` rows, newest first."""

    permission_classes = (HasCapability,)
    required_capability = Capability.POLICY_VIEW
    serializer_class = PolicyVersionSerializer
    pagination_class = DefaultPagination
    queryset = PolicyVersion.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PolicyVersion.objects.none()
        category, key = self.kwargs["category"], self.kwargs["key"]
        _schema_or_404(category, key)
        branch = _resolve_branch(
            self.request.user,
            self.request.query_params.get("branch") or None,
            capability=Capability.POLICY_VIEW,
            require_own_when_scoped=False,
        )
        return services.policy_history_queryset(category=category, key=key, branch=branch)

    @extend_schema(
        summary="A policy's change history",
        parameters=[BRANCH_PARAM],
        responses={200: PolicyVersionSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
