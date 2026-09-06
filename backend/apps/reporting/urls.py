"""Reporting routes."""

from __future__ import annotations

from django.urls import include, path

from . import views

#: Background export jobs. Nested under `report_urlpatterns` at `exports/`
#: rather than mounted from `config.api_urls` directly — that file is owned by
#: another change in flight, and this list is where the URL space for the
#: reporting app already lives.
export_urlpatterns = [
    path("", views.ExportJobQueueView.as_view(), name="export-list"),
    path("<uuid:job_id>/", views.ExportJobDetailView.as_view(), name="export-detail"),
    path("<uuid:job_id>/download/", views.ExportJobDownloadView.as_view(), name="export-download"),
    path("<uuid:job_id>/cancel/", views.ExportJobCancelView.as_view(), name="export-cancel"),
]

report_urlpatterns = [
    path("", views.ReportCatalogueView.as_view(), name="report-catalogue"),
    path("metrics/", views.MetricsView.as_view(), name="report-metrics"),
    path("metrics/attendance-trend/", views.AttendanceTrendView.as_view(), name="report-trend"),
    path("exports/", include(export_urlpatterns)),
    path("<slug:key>/", views.ReportView.as_view(), name="report-run"),
    path("<slug:key>/export/", views.ReportExportView.as_view(), name="report-export"),
]

dashboard_urlpatterns = [
    path("admin/", views.AdminDashboardView.as_view(), name="dashboard-admin"),
    path("workload/", views.TrainerWorkloadView.as_view(), name="dashboard-workload"),
    path("batches/", views.BatchSummaryView.as_view(), name="dashboard-batches"),
]

import_urlpatterns = [
    path("students/", views.StudentImportView.as_view(), name="import-students"),
    path(
        "sessions/<uuid:session_id>/attendance/",
        views.AttendanceImportView.as_view(),
        name="import-attendance",
    ),
    path("<uuid:import_id>/", views.ImportDetailView.as_view(), name="import-detail"),
    path("<uuid:import_id>/confirm/", views.ImportConfirmView.as_view(), name="import-confirm"),
    path("<uuid:import_id>/reject/", views.ImportRejectView.as_view(), name="import-reject"),
]
