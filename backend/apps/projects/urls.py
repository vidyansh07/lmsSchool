"""Project routes."""

from __future__ import annotations

from django.urls import path

from . import views

course_urlpatterns = [
    path("<uuid:course_id>/projects/", views.CourseProjectsView.as_view(), name="course-projects"),
]

project_urlpatterns = [
    path("", views.ProjectListView.as_view(), name="project-list"),
    path("mine/", views.MyProjectsView.as_view(), name="project-mine"),
    path("mine/required/", views.MyRequiredProjectsView.as_view(), name="project-required"),
    path("<uuid:project_id>/", views.ProjectDetailView.as_view(), name="project-detail"),
    path("<uuid:project_id>/status/", views.ProjectStatusView.as_view(), name="project-status"),
    path("<uuid:project_id>/assign/", views.ProjectAssignView.as_view(), name="project-assign"),
    path("<uuid:project_id>/work/", views.ProjectWorkView.as_view(), name="project-work"),
    path(
        "<uuid:project_id>/submissions/",
        views.ProjectWorkListView.as_view(),
        name="project-submissions",
    ),
    # A reviewer's view of one student's work. Named `submissions` rather than
    # `work` so it does not collide with the student's own `.../work/` route in
    # the generated schema.
    path(
        "submissions/<uuid:work_id>/",
        views.ProjectWorkDetailView.as_view(),
        name="project-work-detail",
    ),
    path(
        "submissions/<uuid:work_id>/review/",
        views.ProjectReviewView.as_view(),
        name="project-review",
    ),
    path("files/<uuid:file_id>/", views.ProjectFileView.as_view(), name="project-file"),
]
