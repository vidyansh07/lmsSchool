"""Activity review endpoints. `audit.view` — the administrator's right."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.caching import MINUTE, remember
from apps.common.pagination import DefaultPagination
from apps.common.permissions import Capability, HasCapability

from . import services
from .serializers import (
    FeedEntrySerializer,
    FeedQuerySerializer,
    ScorecardQuerySerializer,
    ScorecardsResponseSerializer,
)

ACTIVITY_TAG = ["Activity"]


def _feed_row(entry) -> dict:
    actor = entry.actor
    return {
        "id": entry.pk,
        "created_at": entry.created_at,
        "action": entry.action,
        "action_label": entry.get_action_display(),
        "kind": services.kind_of(entry.action),
        "actor_id": entry.actor_id,
        "actor_label": entry.actor_label or (actor.email if actor else "system"),
        "actor_role": actor.role if actor else None,
        "actor_branch": actor.branch.name if actor and actor.branch_id else None,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "summary": services.describe(entry),
        "href": services.link_for(entry),
        "context": entry.context,
    }


class ActivityFeedView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUDIT_VIEW

    @extend_schema(
        summary="Who did what, when — the audit log without the noise",
        parameters=[
            OpenApiParameter("since", str, description="Date, inclusive."),
            OpenApiParameter("until", str, description="Date, inclusive."),
            OpenApiParameter("actor", str),
            OpenApiParameter("role", str),
            OpenApiParameter(
                "kind",
                str,
                description=(
                    "admissions, fees, teaching, reviews, courses, outcomes, accounts, "
                    "communication, institution, other"
                ),
            ),
            OpenApiParameter("branch", str),
            OpenApiParameter("search", str),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
        responses={200: FeedEntrySerializer(many=True)},
        tags=ACTIVITY_TAG,
    )
    def get(self, request):
        query = FeedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        rows = services.feed(
            since=params.get("since"),
            until=params.get("until"),
            actor_id=params.get("actor"),
            role=params.get("role"),
            kind=params.get("kind"),
            branch_id=params.get("branch"),
            search=params.get("search", ""),
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        data = FeedEntrySerializer([_feed_row(entry) for entry in page], many=True).data
        return paginator.get_paginated_response(data)


class ActivityScorecardsView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.AUDIT_VIEW

    @extend_schema(
        summary="Each staff member's figures for the period",
        parameters=[
            OpenApiParameter("period", str, description="today, week, month or custom"),
            OpenApiParameter("since", str),
            OpenApiParameter("until", str),
            OpenApiParameter("branch", str),
            OpenApiParameter("role", str),
        ],
        responses={200: ScorecardsResponseSerializer},
        tags=ACTIVITY_TAG,
    )
    def get(self, request):
        query = ScorecardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        if params["period"] == "custom":
            since, until = params["since"], params["until"]
        else:
            since, until = services.period_bounds(params["period"])
        data = remember(
            "activity:scorecards",
            (since, until, params.get("branch"), params.get("role")),
            MINUTE,
            lambda: (
                ScorecardsResponseSerializer(
                    {
                        "since": since,
                        "until": until,
                        "cards": services.scorecards(
                            since=since,
                            until=until,
                            branch_id=params.get("branch"),
                            role=params.get("role"),
                        ),
                    }
                ).data
            ),
        )
        return Response(data)
