"""Class session routes."""

from django.urls import path

from .views import (
    BatchSessionGenerateView,
    BatchSessionsView,
    BatchTrainerHistoryView,
    MySessionsTodayView,
    SessionDetailView,
    SessionListView,
    SessionRescheduleView,
    SessionStatusView,
)

session_patterns = [
    path("", SessionListView.as_view(), name="list"),
    # Declared before the identifier route so it can never be shadowed.
    path("today/", MySessionsTodayView.as_view(), name="today"),
    path("<uuid:session_id>/", SessionDetailView.as_view(), name="detail"),
    path("<uuid:session_id>/status/", SessionStatusView.as_view(), name="status"),
    path("<uuid:session_id>/reschedule/", SessionRescheduleView.as_view(), name="reschedule"),
]

#: Mounted under the batch routes, because a batch is where classes come from.
batch_session_patterns = [
    path("<uuid:batch_id>/sessions/", BatchSessionsView.as_view(), name="sessions"),
    path(
        "<uuid:batch_id>/sessions/generate/",
        BatchSessionGenerateView.as_view(),
        name="session-generate",
    ),
    path(
        "<uuid:batch_id>/trainer-history/",
        BatchTrainerHistoryView.as_view(),
        name="trainer-history",
    ),
]
