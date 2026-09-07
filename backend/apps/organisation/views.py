"""Branch endpoints (``/api/v1/branches/``).

Staff-facing throughout. A bounded caller's ``GET`` returns their own centre and
nothing else, which is what makes this safe to hand a manager: the list is not a
map of the institution, it is the name of the place they work.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListCreateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import DefaultPagination
from apps.common.permissions import Capability, HasCapability

from . import access, services
from .models import Branch
from .serializers import BranchSerializer, BranchWriteSerializer

ORGANISATION_TAG = ["organisation"]


class BranchListCreateView(ListCreateAPIView):
    """The centres the caller may see, or a new one."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.ORGANISATION_VIEW_ANY,
        "POST": Capability.ORGANISATION_MANAGE,
    }
    serializer_class = BranchSerializer
    pagination_class = DefaultPagination
    # Declared for schema generation, which builds a view without a request;
    # the real queryset is scoped per caller in `get_queryset`.
    queryset = Branch.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Branch.objects.none()
        return access.visible_branches(self.request.user)

    @extend_schema(summary="List branches", tags=ORGANISATION_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Open a branch",
        request=BranchWriteSerializer,
        responses={
            201: BranchSerializer,
            409: OpenApiResponse(description="That code is already in use."),
        },
        tags=ORGANISATION_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = BranchWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = services.create_branch(actor=request.user, **serializer.validated_data)
        return Response(BranchSerializer(branch).data, status=http_status.HTTP_201_CREATED)


class BranchDetailView(APIView):
    """Read or rename one centre."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.ORGANISATION_VIEW_ANY,
        "PATCH": Capability.ORGANISATION_MANAGE,
    }

    def _branch_for(self, request, branch_id) -> Branch:
        # Resolved out of the scoped queryset, so another centre's id is a 404
        # rather than a 403 that would confirm it exists.
        return get_object_or_404(access.visible_branches(request.user), pk=branch_id)

    @extend_schema(
        summary="Retrieve a branch", responses={200: BranchSerializer}, tags=ORGANISATION_TAG
    )
    def get(self, request, branch_id):
        return Response(BranchSerializer(self._branch_for(request, branch_id)).data)

    @extend_schema(
        summary="Rename a branch",
        request=BranchWriteSerializer,
        responses={200: BranchSerializer},
        tags=ORGANISATION_TAG,
    )
    def patch(self, request, branch_id):
        branch = self._branch_for(request, branch_id)
        serializer = BranchWriteSerializer(instance=branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_branch(
            branch=branch, actor=request.user, **serializer.validated_data
        )
        return Response(BranchSerializer(updated).data)
