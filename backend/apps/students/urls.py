"""Student routes (mounted at /api/v1/students/)."""

from django.urls import path

from .views import (
    Student360View,
    StudentDetailView,
    StudentDuplicatesView,
    StudentFeeAmountView,
    StudentFeeStatusView,
    StudentFollowUpView,
    StudentListCreateView,
    StudentMeView,
)

app_name = "students"

urlpatterns = [
    path("", StudentListCreateView.as_view(), name="list"),
    # `me/` and `duplicates/` are declared before the UUID route so neither
    # can ever be shadowed by it (though the `uuid` converter would already
    # refuse to match either as an id).
    path("me/", StudentMeView.as_view(), name="me"),
    path("duplicates/", StudentDuplicatesView.as_view(), name="duplicates"),
    path("<uuid:student_id>/", StudentDetailView.as_view(), name="detail"),
    path("<uuid:student_id>/360/", Student360View.as_view(), name="360"),
    path("<uuid:student_id>/fee-status/", StudentFeeStatusView.as_view(), name="fee-status"),
    path("<uuid:student_id>/fee-amount/", StudentFeeAmountView.as_view(), name="fee-amount"),
    path("<uuid:student_id>/follow-ups/", StudentFollowUpView.as_view(), name="follow-ups"),
]
