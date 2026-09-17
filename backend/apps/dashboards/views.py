"""Calendar and role dashboards.

These are read models. They own no tables and make no decisions — every query
goes through the access layer of the app that owns the data, so a dashboard
cannot become a way around a permission.

Query cost is the design constraint here. A dashboard that issues one query per
enrolment would be the slowest page in the product, so every list is fetched
with its relations in one go and every count is an annotation.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches import access as batch_access
from apps.batches.models import BatchStatus
from apps.common.caching import MINUTE, remember
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.enrollments.models import ACCESS_GRANTING_STATUSES, Enrollment, EnrollmentStatus
from apps.enrollments.services import course_progress
from apps.students import access as students_access
from apps.work import access as work_access
from apps.work.models import OPEN_STATUSES, ActivityCategory, ActivityStatus

from .calendar import MAX_RANGE_DAYS, events_for
from .serializers import (
    CalendarResponseSerializer,
    CounsellorDashboardSerializer,
    StudentDashboardSerializer,
    TrainerDashboardSerializer,
)

CALENDAR_TAG = ["calendar"]
DASHBOARD_TAG = ["dashboard"]

#: How many days ahead "upcoming" means on a dashboard.
UPCOMING_DAYS = 7
#: How many recent items a dashboard shows. Small on purpose — §8 asks for
#: useful information, not everything.
RECENT_LIMIT = 5


class CalendarView(APIView):
    """Every event the caller may see in a date range.

    One endpoint for the whole product. Adding assignment deadlines or exams
    later means registering a source in ``apps.dashboards.calendar``; this view
    does not change.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Calendar events",
        parameters=[
            OpenApiParameter("start", str, description="ISO date. Defaults to today."),
            OpenApiParameter(
                "end", str, description=f"ISO date. At most {MAX_RANGE_DAYS} days after start."
            ),
        ],
        responses={
            200: CalendarResponseSerializer,
            400: OpenApiResponse(description="Invalid range."),
        },
        tags=CALENDAR_TAG,
    )
    def get(self, request):
        from datetime import date as date_type

        today = timezone.localdate()
        try:
            start = (
                date_type.fromisoformat(request.query_params["start"])
                if request.query_params.get("start")
                else today
            )
            end = (
                date_type.fromisoformat(request.query_params["end"])
                if request.query_params.get("end")
                else start + timedelta(days=30)
            )
        except ValueError:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"start": ["Use an ISO date, e.g. 2026-03-01."]}) from None

        if end < start:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"end": ["The end date cannot be before the start date."]})

        # Bounded: a calendar query is cheap per day and expensive per year, so
        # the window is capped rather than trusted.
        if (end - start).days > MAX_RANGE_DAYS:
            end = start + timedelta(days=MAX_RANGE_DAYS)

        events = events_for(request.user, start, end)
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "count": len(events),
                "events": [event.as_dict() for event in events],
            }
        )


class StudentDashboardView(APIView):
    """What a student needs on opening the app.

    Deliberately short: current courses, the next few classes, where to pick up,
    and their batches. §8 asks for useful information, not a wall of it.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Student dashboard", responses={200: StudentDashboardSerializer}, tags=DASHBOARD_TAG
    )
    def get(self, request):
        student = batch_access.student_profile(request.user)
        if student is None:
            return Response(
                {
                    "is_student": False,
                    "courses": [],
                    "batches": [],
                    "upcoming_classes": [],
                    "continue_learning": None,
                    "recent_activity": [],
                    "notifications": [],
                }
            )

        # One query for every enrolment with its course, batch and trainer.
        enrollments = list(
            Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        )
        active = [row for row in enrollments if row.status in ACCESS_GRANTING_STATUSES]

        courses = []
        continue_learning = None
        for enrollment in active:
            progress = course_progress(enrollment)
            entry = {
                "enrollment_id": str(enrollment.pk),
                "course_id": str(enrollment.course_id),
                "course_title": enrollment.course.title,
                "course_slug": enrollment.course.slug,
                "batch_code": enrollment.batch.code,
                "batch_name": enrollment.batch.name,
                "status": enrollment.status,
                "grants_access": enrollment.grants_access(),
                "progress_percent": progress["percent"],
                "completed_lessons": progress["completed_lessons"],
                "total_lessons": progress["total_lessons"],
                "last_lesson_id": progress["last_lesson_id"],
                "last_lesson_title": progress["last_lesson_title"],
            }
            courses.append(entry)

            # "Continue learning" is the most recently opened lesson across all
            # live enrolments.
            if progress["last_accessed_at"] and (
                continue_learning is None or progress["last_accessed_at"] > continue_learning["_at"]
            ):
                continue_learning = {**entry, "_at": progress["last_accessed_at"]}

        if continue_learning is not None:
            continue_learning.pop("_at", None)

        today = timezone.localdate()
        upcoming = events_for(request.user, today, today + timedelta(days=UPCOMING_DAYS))

        return Response(
            {
                "is_student": True,
                "courses": courses,
                "batches": [
                    {
                        "id": str(row.batch_id),
                        "code": row.batch.code,
                        "name": row.batch.name,
                        "course_title": row.course.title,
                        "status": row.batch.status,
                        "enrollment_status": row.status,
                        "start_date": row.batch.start_date.isoformat(),
                        "end_date": row.batch.end_date.isoformat(),
                    }
                    for row in enrollments
                ],
                "upcoming_classes": [event.as_dict() for event in upcoming[:RECENT_LIMIT]],
                "continue_learning": continue_learning,
                "recent_activity": [
                    {
                        "kind": "enrollment",
                        "title": f"Enrolled on {row.course.title}",
                        "at": row.enrolled_at.isoformat(),
                        "status": row.status,
                    }
                    for row in enrollments[:RECENT_LIMIT]
                ],
                # Placeholder, as §8 asks. The shape is fixed now so the
                # notifications feature fills it rather than redesigning it.
                "notifications": [],
            }
        )


class TrainerDashboardView(APIView):
    """What a trainer needs: today, this week, and who they teach."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Trainer dashboard", responses={200: TrainerDashboardSerializer}, tags=DASHBOARD_TAG
    )
    def get(self, request):
        trainer = batch_access.trainer_profile(request.user)
        if trainer is None:
            return Response(
                {
                    "is_trainer": False,
                    "batches": [],
                    "today_classes": [],
                    "upcoming_classes": [],
                    "student_count": 0,
                    "courses": [],
                    "work": {"pending": 0, "overdue": 0},
                }
            )

        # One query, with the seat count annotated rather than counted per row.
        batches = list(
            batch_access.visible_batches(request.user)
            .with_counts()
            .exclude(status=BatchStatus.ARCHIVED)
            .order_by("-start_date")
        )

        today = timezone.localdate()
        week = events_for(request.user, today, today + timedelta(days=UPCOMING_DAYS))
        today_classes = [event for event in week if event.start.date() == today]

        student_count = (
            Enrollment.objects.filter(
                batch__trainer=trainer,
                status__in=(EnrollmentStatus.ACTIVE, EnrollmentStatus.PENDING),
            )
            .values("student_id")
            .distinct()
            .count()
        )

        # This trainer's own work queue (rule 2: queryset-first, never a raw
        # `Activity.objects` count) — the same `Q(assigned_to=user) |
        # Q(created_by=user)` filter `MeActivitiesView` already uses for "my
        # activities", layered on `visible_activities` rather than a second
        # unscoped query. Filtering to `assigned_to` alone would drift from
        # that endpoint: a trainer who created but did not self-assign an
        # activity (handed off, or still an unassigned draft) would show up
        # on `/me/activities` and `/teaching/work` but silently drop out of
        # this dashboard's counts and list.
        own_activities = work_access.visible_activities(request.user).filter(
            Q(assigned_to=request.user) | Q(created_by=request.user)
        )
        work_counts = own_activities.aggregate(
            pending=Count("id", filter=Q(status__in=OPEN_STATUSES)),
            overdue=Count("id", filter=Q(status=ActivityStatus.OVERDUE)),
        )

        seen: dict[str, dict] = {}
        for batch in batches:
            seen.setdefault(
                str(batch.course_id),
                {
                    "course_id": str(batch.course_id),
                    "title": batch.course.title,
                    "slug": batch.course.slug,
                    "batch_count": 0,
                },
            )
            seen[str(batch.course_id)]["batch_count"] += 1

        return Response(
            {
                "is_trainer": True,
                "batches": [
                    {
                        "id": str(batch.pk),
                        "code": batch.code,
                        "name": batch.name,
                        "course_title": batch.course.title,
                        "status": batch.status,
                        "start_date": batch.start_date.isoformat(),
                        "end_date": batch.end_date.isoformat(),
                        "capacity": batch.capacity,
                        "enrolled_count": getattr(batch, "enrolled_count", 0),
                    }
                    for batch in batches
                ],
                "today_classes": [event.as_dict() for event in today_classes],
                "upcoming_classes": [event.as_dict() for event in week[:RECENT_LIMIT]],
                "student_count": student_count,
                "courses": list(seen.values()),
                "work": {
                    "pending": work_counts["pending"] or 0,
                    "overdue": work_counts["overdue"] or 0,
                },
            }
        )


def _counsellor_dashboard(user) -> dict:
    """ERP Phase 17 (`USER_JOURNEYS.md` §4.1, `API_CONTRACTS.md` verbatim
    field names) — every count taken from the same access-layer queryset the
    counsellor's own list screens already use, never a second, unscoped
    definition of "mine".
    """
    from apps.warnings import services as warnings_services

    today = timezone.localdate()

    students = students_access.visible_students(user)
    new_students_today = students.filter(created_at__date=today).count()
    # "Registered, not yet placed on any batch" — the same underlying
    # condition `apps.warnings.services._admissions_warnings` raises its
    # `not_enrolled` warning from, minus that warning's week-old threshold:
    # this tile is a live count, not an escalation.
    unassigned_batch = students.filter(enrollments__isnull=True).count()

    # `EnrollmentStatus.PENDING` is this codebase's existing "awaiting its
    # next step" concept — the same status
    # `app/admissions/dashboard/page.tsx`'s pre-Phase-17 "Pending
    # confirmation" tile already fetches via `listEnrollments({status:
    # 'pending'})`, not a fresh definition of "pending".
    pending_registrations = (
        batch_access.visible_enrollments(user).filter(status=EnrollmentStatus.PENDING).count()
    )

    # The exact condition `apps.warnings.services._batch_warnings` already
    # raises its `batch_no_trainer` warning from, reused rather than
    # redefined so the tile and that warning can never disagree about what
    # "no trainer" means.
    unassigned_trainer = (
        batch_access.visible_batches(user)
        .filter(status__in=(BatchStatus.UPCOMING, BatchStatus.ACTIVE), trainer__isnull=True)
        .count()
    )

    # This counsellor's own follow-up work queue (rule 2: queryset-first,
    # never a raw `Activity.objects` count) — the identical
    # `Q(assigned_to=user) | Q(created_by=user)` filter Phase 16's
    # `TrainerDashboardView.work` above uses for "my work", layered on
    # `visible_activities` and narrowed to the follow-up category.
    own_follow_ups = work_access.visible_activities(user).filter(
        Q(assigned_to=user) | Q(created_by=user), activity_type__category=ActivityCategory.FOLLOW_UP
    )
    follow_up_counts = own_follow_ups.aggregate(
        due=Count("id", filter=Q(status__in=OPEN_STATUSES) & ~Q(status=ActivityStatus.OVERDUE)),
        overdue=Count("id", filter=Q(status=ActivityStatus.OVERDUE)),
    )

    return {
        "new_students_today": new_students_today,
        "pending_registrations": pending_registrations,
        "follow_ups_due": follow_up_counts["due"] or 0,
        "follow_ups_overdue": follow_up_counts["overdue"] or 0,
        "unassigned_batch": unassigned_batch,
        "unassigned_trainer": unassigned_trainer,
        "warnings": warnings_services.cached_warnings_for(user),
    }


class CounsellorDashboardView(APIView):
    """What a counsellor needs on opening `/admissions/dashboard`
    (`USER_JOURNEYS.md` §4.1) — one call replacing the five or six separate,
    ad-hoc list fetches the page made before Phase 17.

    Cached for a minute per caller, the same shape `AdminDashboardView`/
    `ManagerDashboardView` (`apps.reporting.views`) already use:
    `remember()` keyed on the user's own id, with no explicit invalidation —
    those two dashboards do not invalidate on write either, and a
    minute-stale count here is the same acceptable cost.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.STUDENT_CREATE

    @extend_schema(
        summary="Counsellor dashboard",
        responses={200: CounsellorDashboardSerializer},
        tags=DASHBOARD_TAG,
    )
    def get(self, request):
        data = remember(
            "dashboard:counsellor",
            (request.user.pk,),
            MINUTE,
            lambda: _counsellor_dashboard(request.user),
        )
        return Response(data)
