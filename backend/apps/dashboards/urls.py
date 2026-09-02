"""Calendar and dashboard routes."""

from django.urls import path

from .views import CalendarView, StudentDashboardView, TrainerDashboardView

calendar_patterns = [
    path("", CalendarView.as_view(), name="events"),
]

dashboard_patterns = [
    path("student/", StudentDashboardView.as_view(), name="student"),
    path("trainer/", TrainerDashboardView.as_view(), name="trainer"),
]
