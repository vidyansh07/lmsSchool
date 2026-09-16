"""Activity engine routes.

Mounted at `/api/v1/activity-types/` and `/api/v1/activities/`
(`config/api_urls.py`) — deliberately *not* `/api/v1/activity/`, which stays
exactly where the pre-existing audit-feed app (`apps.activity`) already has
it (ADR-08). `student_activity_urlpatterns` is appended to the `students/`
mount instead of living under its own prefix, the same way
`apps.dsr.urls.batch_urlpatterns` extends `batches/`; `me_patterns` is
appended to a top-level `me/` mount alongside `apps.accounts`'s own.
`student_timeline_urlpatterns` (Phase 10) joins `student_activity_urlpatterns`
on that same `students/` mount, for the same reason.
"""

from __future__ import annotations

from django.urls import path

from . import views
from .timeline_views import StudentTimelineView

app_name = "work"

activity_type_patterns = [
    path("", views.ActivityTypeListCreateView.as_view(), name="activity-type-list"),
    path("<slug:slug>/", views.ActivityTypeDetailView.as_view(), name="activity-type-detail"),
]

activity_patterns = [
    path("", views.ActivityListCreateView.as_view(), name="list"),
    path("<uuid:activity_id>/", views.ActivityDetailView.as_view(), name="detail"),
    path(
        "<uuid:activity_id>/transition/", views.ActivityTransitionView.as_view(), name="transition"
    ),
    path("<uuid:activity_id>/complete/", views.ActivityCompleteView.as_view(), name="complete"),
    path("<uuid:activity_id>/review/", views.ActivityReviewView.as_view(), name="review"),
]

student_activity_urlpatterns = [
    path(
        "<uuid:student_id>/activities/",
        views.StudentActivityListView.as_view(),
        name="student-activities",
    ),
]

student_timeline_urlpatterns = [
    path(
        "<uuid:student_id>/timeline/",
        StudentTimelineView.as_view(),
        name="student-timeline",
    ),
]

me_patterns = [
    path("activities/", views.MeActivitiesView.as_view(), name="me-activities"),
]
