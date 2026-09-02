"""Learning-surface routes."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("home/", views.LearningHomeView.as_view(), name="learning-home"),
    path("upcoming/", views.UpcomingWorkView.as_view(), name="learning-upcoming"),
    path("bookmarks/", views.BookmarkListView.as_view(), name="learning-bookmarks"),
    path("notes/", views.NoteListView.as_view(), name="learning-notes"),
    path(
        "enrollments/<uuid:enrollment_id>/history/",
        views.HistoryView.as_view(),
        name="learning-history",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/classmates/",
        views.BatchDirectoryView.as_view(),
        name="learning-directory",
    ),
    path(
        "lessons/<uuid:lesson_id>/bookmark/",
        views.LessonBookmarkView.as_view(),
        name="learning-bookmark",
    ),
    path("lessons/<uuid:lesson_id>/note/", views.LessonNoteView.as_view(), name="learning-note"),
]
