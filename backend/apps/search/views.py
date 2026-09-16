"""`GET /search/?q=&types=` (ERP Phase 11, `API_CONTRACTS.md` "Search and
productivity"). The view is the thin, capability-and-shape half; every
scoping decision lives in `services.search` and the domain `visible_*`
functions it calls — see that module's docstring for the rule this endpoint
exists to keep.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.audit.services import AuditAction, record
from apps.common.permissions import HasCapability
from apps.common.throttling import SearchThrottle

from .services import SOURCES, search

TAG = ["search"]

#: `q` shorter than this cannot mean anything (`API_CONTRACTS.md`): a
#: single-character wildcard against ten sources is a full-table scan
#: wearing a search box.
MIN_QUERY_LENGTH = 2


class GlobalSearchView(APIView):
    """Any authenticated user (`search.global` is in `BASE_CAPABILITIES` —
    see `apps.accounts.roles`) may search; what a hit reveals is bounded
    per-source by that domain's own `visible_*`, never by this view."""

    permission_classes = (HasCapability,)
    required_capability = Capability.SEARCH_GLOBAL
    throttle_classes = (SearchThrottle,)

    @extend_schema(
        summary="Global search",
        parameters=[
            OpenApiParameter("q", str, description="At least 2 characters."),
            OpenApiParameter(
                "types",
                str,
                description="Comma-separated source names to expand past the 5-hit cap.",
            ),
        ],
        responses={200: OpenApiResponse(description="Grouped search results.")},
        tags=TAG,
    )
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < MIN_QUERY_LENGTH:
            raise ValidationError(
                {"q": [f"Enter at least {MIN_QUERY_LENGTH} characters to search."]}
            )

        raw_types = request.query_params.get("types") or ""
        # Unknown names are ignored rather than rejected: a stale saved
        # command-palette state or a typo should not turn into a 400, and
        # expanding a type never widens *scoping* — only the source's own
        # `limit` — so silently no-op-ing an unknown one costs nothing.
        expand = frozenset(name.strip() for name in raw_types.split(",") if name.strip() in SOURCES)

        groups = search(request.user, query=query, expand=expand)

        # Counts only, per ADR-15/`AGENT_PLAYBOOK.md`'s secrets rule: the
        # query text and the ids it matched never enter the audit context —
        # a free-text box can carry anything a caller chose to type, and an
        # audit row is readable by anyone holding `audit.view`.
        record(
            action=AuditAction.SEARCH_PERFORMED,
            actor=request.user,
            resource_type="search",
            context={
                "query_length": len(query),
                "types_requested": sorted(expand),
                "hits_by_type": {group["type"]: group["total"] for group in groups},
            },
            durable=False,
        )
        return Response({"groups": groups})
