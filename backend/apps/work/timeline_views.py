"""`GET /students/{id}/timeline/` (ERP Phase 10, ADR-09).

Kept apart from `views.py` because this endpoint is not part of the activity
engine's own surface — it composes across every domain in `apps.work.timeline`
the same way `apps.dashboards.views.CalendarView` composes
`apps.dashboards.calendar`, and lives here rather than in `apps.dashboards`
because it is mounted under `students/`, alongside `StudentActivityListView`
(`apps/work/urls.py`'s `student_activity_urlpatterns`), not under a
dashboards prefix.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import AuthorityError
from apps.common.permissions import IsActiveUser
from apps.students import access as students_access

from .timeline import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, default_window, timeline_for

TAG = ["Activities"]


def _parse_moment(raw: str | None, field: str):
    if not raw:
        return None
    value = parse_datetime(raw)
    if value is None:
        raise ValidationError({field: ["Use an ISO datetime, e.g. 2026-01-01T00:00:00Z."]})
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


class StudentTimelineView(APIView):
    """One student's activity across every domain, newest first.

    Permission is exactly "may this caller see this student" — the same rule
    `StudentActivityListView` (Phase 9) already enforces, reused rather than
    reinvented. Which of *this* student's rows the caller may see is then a
    per-source question, answered by each source's own `visible_*`, the same
    two-step shape `StudentActivityListView.get_queryset` uses.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="A student's activity timeline",
        parameters=[
            OpenApiParameter(
                "kinds", str, description="Comma-separated kinds to include. Default: all."
            ),
            OpenApiParameter(
                "since", str, description="ISO datetime. Defaults to 12 months before `until`."
            ),
            OpenApiParameter("until", str, description="ISO datetime. Defaults to now."),
            OpenApiParameter("cursor", str, description="Opaque cursor from a previous page."),
            OpenApiParameter(
                "page_size",
                int,
                description=f"Default {DEFAULT_PAGE_SIZE}, capped at {MAX_PAGE_SIZE}.",
            ),
        ],
        responses={200: OpenApiResponse(description="A page of timeline entries.")},
        tags=TAG,
    )
    def get(self, request, student_id):
        student = get_object_or_404(students_access.reachable_students(request.user), pk=student_id)
        if not students_access.can_view_student(request.user, student):
            raise AuthorityError("You do not have authority to see this student.")

        until = _parse_moment(request.query_params.get("until"), "until") or timezone.now()
        default_since, _ = default_window(until)
        since = _parse_moment(request.query_params.get("since"), "since") or default_since
        if since > until:
            raise ValidationError({"since": ["The window cannot start after it ends."]})

        raw_kinds = request.query_params.get("kinds")
        kinds = (
            {kind.strip() for kind in raw_kinds.split(",") if kind.strip()} if raw_kinds else None
        )

        page_size_raw = request.query_params.get("page_size")
        try:
            page_size = int(page_size_raw) if page_size_raw else DEFAULT_PAGE_SIZE
        except ValueError:
            raise ValidationError({"page_size": ["Must be a whole number."]}) from None
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        entries, next_cursor = timeline_for(
            request.user,
            student,
            since=since,
            until=until,
            kinds=kinds,
            cursor=request.query_params.get("cursor") or None,
            page_size=page_size,
        )
        return Response(
            {"results": [entry.as_dict() for entry in entries], "next_cursor": next_cursor}
        )
