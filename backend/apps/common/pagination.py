"""Pagination strategy.

Page-number pagination is the default: it is predictable for UI clients, cheap
to reason about, and works with the admin-style listings Phase 1 will need.
The page size is client-adjustable but hard-capped so a single request cannot
be turned into a full-table export.

Endpoints over large, append-only tables (audit log, activity feeds) should
switch to cursor pagination when they arrive; the response envelope below is
shaped so that change stays backwards compatible for consumers reading
``results``.

Every paginated queryset is given a unique tiebreaker before it is sliced. See
:func:`stable_order` for why that is not optional.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


def stable_order(queryset):
    """Append the primary key to a queryset's ordering, unless it already ends there.

    SQL does not promise an order for rows that tie on the ORDER BY columns, and
    PostgreSQL takes that literally: the same query, run twice, may return tied
    rows in different orders. Pagination runs the query twice — once to count,
    once per page — so a list ordered by a column with duplicates or NULLs can
    show a row on two consecutive pages and never show another one at all.

    Most orderings here are on a nullable timestamp (`end_date`, `submitted_at`,
    `opens_at`), and every row a feature creates in one action shares a
    timestamp, so ties are the normal case rather than the exotic one. This was
    found by an end-to-end journey that could not see a project it had just
    created: it was on page two, behind thirty-seven others that all sorted
    equally.

    Applied here rather than in each view so a list added later cannot forget.
    """
    ordering = queryset.query.order_by or queryset.model._meta.ordering or ()
    fields = [str(field) for field in ordering]
    if any(field.lstrip("-") in ("pk", "id") for field in fields):
        return queryset
    return queryset.order_by(*ordering, "pk")


class DefaultPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def paginate_queryset(self, queryset, request, view=None):
        if hasattr(queryset, "order_by") and hasattr(queryset, "query"):
            queryset = stable_order(queryset)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("page", self.page.number),
                    ("page_size", self.get_page_size(self.request)),
                    ("total_pages", self.page.paginator.num_pages),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["count", "page", "page_size", "total_pages", "results"],
            "properties": {
                "count": {"type": "integer", "example": 123},
                "page": {"type": "integer", "example": 1},
                "page_size": {"type": "integer", "example": 25},
                "total_pages": {"type": "integer", "example": 5},
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "results": schema,
            },
        }
