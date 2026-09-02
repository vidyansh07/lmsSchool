"""Reporting routes."""

from __future__ import annotations

from django.urls import path

from . import views

report_urlpatterns = [
    path("", views.ReportCatalogueView.as_view(), name="report-catalogue"),
    path("metrics/", views.MetricsView.as_view(), name="report-metrics"),
    path("metrics/attendance-trend/", views.AttendanceTrendView.as_view(), name="report-trend"),
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
