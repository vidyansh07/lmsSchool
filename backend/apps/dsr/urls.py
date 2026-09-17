"""Daily status report routes.

Mounted by `config/api_urls.py`, which owns the mount points. Add paths to the
lists below; do not change where they are mounted.
"""

from django.urls import path

from .views import (
    BatchDSRListView,
    DSRCreateActivityView,
    DSRDeleteView,
    DSRDetailView,
    DSRHistoryView,
    DSRListView,
    DSRReopenView,
    DSRReviewView,
    DSRSubmitView,
    SessionDSRView,
)

urlpatterns: list = [
    path("", DSRListView.as_view(), name="list"),
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
]

session_urlpatterns: list = [
    path("<uuid:session_id>/dsr/", SessionDSRView.as_view(), name="dsr"),
]
