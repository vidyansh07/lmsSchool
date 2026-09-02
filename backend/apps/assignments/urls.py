"""Assignment routes.

Split by the noun they hang off, mounted in ``config/api_urls.py``:

* ``courses/<id>/assignments/``     create work on a course
* ``assignments/…``                 the brief, its attachments, its queue
* ``submissions/…``                 one attempt: read, grade, return, download
"""

from __future__ import annotations

from django.urls import path

from . import views

course_urlpatterns = [
    path(
        "<uuid:course_id>/assignments/",
        views.CourseAssignmentsView.as_view(),
        name="course-assignments",
    ),
]

assignment_urlpatterns = [
    path("", views.AssignmentListView.as_view(), name="assignment-list"),
    path("mine/", views.MyAssignmentsView.as_view(), name="assignment-mine"),
    path("<uuid:assignment_id>/", views.AssignmentDetailView.as_view(), name="assignment-detail"),
    path(
        "<uuid:assignment_id>/status/",
        views.AssignmentStatusView.as_view(),
        name="assignment-status",
    ),
    path(
        "<uuid:assignment_id>/attachments/",
        views.AssignmentAttachmentsView.as_view(),
        name="assignment-attachments",
    ),
    path(
        "<uuid:assignment_id>/submissions/",
        views.AssignmentSubmissionsView.as_view(),
        name="assignment-submissions",
    ),
    path("<uuid:assignment_id>/submit/", views.SubmitView.as_view(), name="assignment-submit"),
    path(
        "attachments/<uuid:attachment_id>/",
        views.AttachmentDetailView.as_view(),
        name="assignment-attachment-detail",
    ),
]

submission_urlpatterns = [
    path("mine/", views.MySubmissionsView.as_view(), name="submission-mine"),
    path("<uuid:submission_id>/", views.SubmissionDetailView.as_view(), name="submission-detail"),
    path(
        "<uuid:submission_id>/grade/",
        views.GradeSubmissionView.as_view(),
        name="submission-grade",
    ),
    path(
        "<uuid:submission_id>/return/",
        views.ReturnSubmissionView.as_view(),
        name="submission-return",
    ),
    path(
        "files/<uuid:file_id>/download/",
        views.SubmissionFileDownloadView.as_view(),
        name="submission-file-download",
    ),
]
