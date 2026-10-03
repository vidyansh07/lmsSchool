"""Daily status report routes.

Mounted by `config/api_urls.py`, which owns the mount points. Add paths to the
lists below; do not change where they are mounted.
"""

from django.urls import path

from .views import (
    BatchDSRExportView,
    BatchDSRListView,
    BatchDSRSummaryView,
    DSRCreateActivityView,
    DSRDeleteView,
    DSRDetailView,
    DSRHistoryView,
    DSRListView,
    DSRReopenView,
    DSRReviewView,
    DSRSubmitView,
    MissingDSRView,
    SessionDSRView,
    StudentClassNotesView,
)

urlpatterns: list = [
    path("", DSRListView.as_view(), name="list"),
    # Fixed segments before `<uuid:dsr_id>/`.
    path("mine/", StudentClassNotesView.as_view(), name="mine"),
    path("missing/", MissingDSRView.as_view(), name="missing"),
    path("<uuid:dsr_id>/", DSRDetailView.as_view(), name="detail"),
    path("<uuid:dsr_id>/reopen/", DSRReopenView.as_view(), name="reopen"),
    path("<uuid:dsr_id>/submit/", DSRSubmitView.as_view(), name="submit"),
    path("<uuid:dsr_id>/review/", DSRReviewView.as_view(), name="review"),
    path("<uuid:dsr_id>/delete/", DSRDeleteView.as_view(), name="delete"),
    path("<uuid:dsr_id>/create-activity/", DSRCreateActivityView.as_view(), name="create-activity"),
    path("<uuid:dsr_id>/history/", DSRHistoryView.as_view(), name="history"),
]

batch_urlpatterns: list = [
    path("<uuid:batch_id>/dsr/", BatchDSRListView.as_view(), name="dsr"),
    path("<uuid:batch_id>/dsr-summary/", BatchDSRSummaryView.as_view(), name="dsr-summary"),
    path("<uuid:batch_id>/dsr-export/", BatchDSRExportView.as_view(), name="dsr-export"),
]

session_urlpatterns: list = [
    path("<uuid:session_id>/dsr/", SessionDSRView.as_view(), name="dsr"),
]
