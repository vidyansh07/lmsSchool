"""Discussion routes."""

from __future__ import annotations

from django.urls import path

from . import views

batch_urlpatterns = [
    path("<uuid:batch_id>/threads/", views.BatchThreadsView.as_view(), name="batch-threads"),
]

discussion_urlpatterns = [
    path("", views.ThreadListView.as_view(), name="thread-list"),
    path("<uuid:thread_id>/", views.ThreadDetailView.as_view(), name="thread-detail"),
    path("<uuid:thread_id>/replies/", views.ReplyView.as_view(), name="thread-reply"),
    path("<uuid:thread_id>/moderate/", views.ModerateThreadView.as_view(), name="thread-moderate"),
    path("replies/<uuid:reply_id>/hide/", views.HideReplyView.as_view(), name="reply-hide"),
]
