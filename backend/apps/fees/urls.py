"""Fee routes (mounted at /api/v1/fees/)."""

from django.urls import path

from .views import (
    EnrollmentFeeHistoryView,
    EnrollmentFeeNextDueView,
    EnrollmentFeePaymentsView,
    EnrollmentFeeView,
    FeePaymentVoidView,
    FeesOverviewView,
    MyFeesView,
    StudentFeesView,
)

app_name = "fees"

urlpatterns = [
    path("me/", MyFeesView.as_view(), name="me"),
    path("overview/", FeesOverviewView.as_view(), name="overview"),
    path("students/<uuid:student_id>/", StudentFeesView.as_view(), name="student"),
    path("enrollments/<uuid:enrollment_id>/", EnrollmentFeeView.as_view(), name="enrollment"),
    path(
        "enrollments/<uuid:enrollment_id>/next-due/",
        EnrollmentFeeNextDueView.as_view(),
        name="next-due",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/payments/",
        EnrollmentFeePaymentsView.as_view(),
        name="payments",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/history/",
        EnrollmentFeeHistoryView.as_view(),
        name="history",
    ),
    path("payments/<uuid:payment_id>/void/", FeePaymentVoidView.as_view(), name="void"),
]
