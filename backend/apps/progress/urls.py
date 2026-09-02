"""Progress and completion routes."""

from __future__ import annotations

from django.urls import path

from . import views

progress_urlpatterns = [
    path("mine/", views.MyProgressView.as_view(), name="progress-mine"),
    path(
        "enrollments/<uuid:enrollment_id>/",
        views.EnrollmentProgressView.as_view(),
        name="progress-enrollment",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/report/",
        views.ProgressReportView.as_view(),
        name="progress-report",
    ),
]

completion_urlpatterns = [
    path("", views.CompletionListView.as_view(), name="completion-list"),
    path(
        "enrollments/<uuid:enrollment_id>/approve/",
        views.ApproveCompletionView.as_view(),
        name="completion-approve",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/reject/",
        views.RejectCompletionView.as_view(),
        name="completion-reject",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/reopen/",
        views.ReopenCompletionView.as_view(),
        name="completion-reopen",
    ),
]

batch_urlpatterns = [
    path(
        "<uuid:batch_id>/completions/refresh/",
        views.RefreshCompletionsView.as_view(),
        name="batch-completions-refresh",
    ),
]
