"""Student routes (mounted at /api/v1/students/)."""

from django.urls import path

from .views import (
    StudentDetailView,
    StudentFeeAmountView,
    StudentFeeStatusView,
    StudentListCreateView,
    StudentMeView,
)

app_name = "students"

urlpatterns = [
    path("", StudentListCreateView.as_view(), name="list"),
    # `me/` is declared before the UUID route so it can never be shadowed.
    path("me/", StudentMeView.as_view(), name="me"),
    path("<uuid:student_id>/", StudentDetailView.as_view(), name="detail"),
    path("<uuid:student_id>/fee-status/", StudentFeeStatusView.as_view(), name="fee-status"),
    path("<uuid:student_id>/fee-amount/", StudentFeeAmountView.as_view(), name="fee-amount"),
]
