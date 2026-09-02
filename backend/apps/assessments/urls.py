"""Assessment and result routes."""

from __future__ import annotations

from django.urls import path

from . import views

batch_urlpatterns = [
    path(
        "<uuid:batch_id>/assessments/",
        views.BatchAssessmentsView.as_view(),
        name="batch-assessments",
    ),
]

assessment_urlpatterns = [
    path("", views.AssessmentListView.as_view(), name="assessment-list"),
    path("mine/", views.MyAssessmentsView.as_view(), name="assessment-mine"),
    path("<uuid:assessment_id>/", views.AssessmentDetailView.as_view(), name="assessment-detail"),
    path(
        "<uuid:assessment_id>/status/",
        views.AssessmentStatusView.as_view(),
        name="assessment-status",
    ),
    path(
        "<uuid:assessment_id>/marks/",
        views.MarksSheetView.as_view(),
        name="assessment-marks",
    ),
    path(
        "<uuid:assessment_id>/imports/",
        views.ResultImportPreviewView.as_view(),
        name="assessment-imports",
    ),
]

result_urlpatterns = [
    path("mine/", views.MyResultsView.as_view(), name="result-mine"),
    path(
        "imports/<uuid:import_id>/",
        views.ResultImportDetailView.as_view(),
        name="result-import-detail",
    ),
    path(
        "imports/<uuid:import_id>/confirm/",
        views.ResultImportConfirmView.as_view(),
        name="result-import-confirm",
    ),
    path(
        "imports/<uuid:import_id>/reject/",
        views.ResultImportRejectView.as_view(),
        name="result-import-reject",
    ),
]
