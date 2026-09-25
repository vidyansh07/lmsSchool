"""Calendar and dashboard routes."""

from django.urls import path

from .views import (
    CalendarView,
    CounsellorDashboardView,
    CounsellorPipelineView,
    StudentDashboardView,
    TrainerDashboardView,
)

calendar_patterns = [
    path("", CalendarView.as_view(), name="events"),
]

dashboard_patterns = [
    path("student/", StudentDashboardView.as_view(), name="student"),
    path("trainer/", TrainerDashboardView.as_view(), name="trainer"),
]

#: Mounted under the plural `dashboards/` prefix in `config.api_urls`,
#: alongside `apps.reporting`'s admin/manager dashboards — `GET
#: /dashboards/counsellor/` (`API_CONTRACTS.md`), not the singular
#: `dashboard/` prefix `dashboard_patterns` above shares with the student
#: and trainer ones.
counsellor_urlpatterns = [
    path("counsellor/", CounsellorDashboardView.as_view(), name="counsellor"),
    path(
        "counsellor/pipeline/",
        CounsellorPipelineView.as_view(),
        name="counsellor-pipeline",
    ),
]
