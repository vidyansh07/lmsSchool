"""Enrolment and progress routes."""

from django.urls import path

from .views import (
    EnrollmentDetailView,
    EnrollmentListCreateView,
    EnrollmentProgressView,
    EnrollmentStatusView,
    LessonCompletionView,
    MyEnrollmentsView,
)

enrollment_patterns = [
    path("", EnrollmentListCreateView.as_view(), name="list"),
    # Declared before the identifier route so it can never be shadowed.
    path("mine/", MyEnrollmentsView.as_view(), name="mine"),
    path("<uuid:enrollment_id>/", EnrollmentDetailView.as_view(), name="detail"),
    path("<uuid:enrollment_id>/status/", EnrollmentStatusView.as_view(), name="status"),
    path("<uuid:enrollment_id>/progress/", EnrollmentProgressView.as_view(), name="progress"),
]

progress_patterns = [
    path("lessons/<uuid:lesson_id>/completion/", LessonCompletionView.as_view(), name="completion"),
]
