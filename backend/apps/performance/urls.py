"""Performance, risk and review routes.

Mounted by `config/api_urls.py`, which owns the mount points. Add paths to the
lists below; do not change where they are mounted.

`trainer_urlpatterns` is mounted under `batches/`, alongside
`apps.progress.urls.batch_urlpatterns` and `apps.dsr.urls.batch_urlpatterns` —
so every path here takes a leading `<uuid:batch_id>/`, exactly like theirs.
`student_urlpatterns` is not mounted anywhere yet; nothing here needs it, since
a student's own performance is reachable through `me/` below.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MyPerformanceView.as_view(), name="performance-me"),
    path("trainer/me/", views.MyTrainerPerformanceView.as_view(), name="performance-trainer-me"),
    path("reviews/", views.ReviewListView.as_view(), name="performance-review-list"),
    path(
        "reviews/<uuid:review_id>/",
        views.ReviewDetailView.as_view(),
        name="performance-review-detail",
    ),
    path("feedback/", views.FeedbackListView.as_view(), name="performance-feedback-list"),
    path(
        "feedback/<uuid:feedback_id>/",
        views.FeedbackDetailView.as_view(),
        name="performance-feedback-detail",
    ),
    path(
        "risk-thresholds/",
        views.RiskThresholdsView.as_view(),
        name="performance-risk-thresholds",
    ),
]
student_urlpatterns: list = []
trainer_urlpatterns = [
    path(
        "<uuid:batch_id>/performance/",
        views.BatchPerformanceView.as_view(),
        name="performance-batch",
    ),
]
