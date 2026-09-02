"""Announcement routes."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.AnnouncementListView.as_view(), name="announcement-list"),
    path(
        "<uuid:announcement_id>/",
        views.AnnouncementDetailView.as_view(),
        name="announcement-detail",
    ),
    path(
        "<uuid:announcement_id>/publish/",
        views.PublishAnnouncementView.as_view(),
        name="announcement-publish",
    ),
    path(
        "<uuid:announcement_id>/archive/",
        views.ArchiveAnnouncementView.as_view(),
        name="announcement-archive",
    ),
    path(
        "<uuid:announcement_id>/audience/",
        views.AudiencePreviewView.as_view(),
        name="announcement-audience",
    ),
]
