"""Fee routes (mounted at /api/v1/fees/)."""

from django.urls import path

from .views import (
    EnrollmentFeeEmailStatementView,
    EnrollmentFeeEmailsView,
    EnrollmentFeeHistoryView,
    EnrollmentFeeInstallmentsView,
    EnrollmentFeeNextDueView,
    EnrollmentFeePaymentsView,
    EnrollmentFeeStatementView,
    EnrollmentFeeView,
    FeeCollectionsTrendView,
    FeePaymentEmailReceiptView,
    FeePaymentReceiptView,
    FeePaymentVoidView,
    FeesOverviewView,
    MyFeesView,
    StudentFeesView,
)

app_name = "fees"

urlpatterns = [
    path("me/", MyFeesView.as_view(), name="me"),
    path("overview/", FeesOverviewView.as_view(), name="overview"),
    path("collections-trend/", FeeCollectionsTrendView.as_view(), name="collections-trend"),
    path("students/<uuid:student_id>/", StudentFeesView.as_view(), name="student"),
    path("enrollments/<uuid:enrollment_id>/", EnrollmentFeeView.as_view(), name="enrollment"),
    path(
        "enrollments/<uuid:enrollment_id>/next-due/",
        EnrollmentFeeNextDueView.as_view(),
        name="next-due",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/installments/",
        EnrollmentFeeInstallmentsView.as_view(),
        name="installments",
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
    path(
        "enrollments/<uuid:enrollment_id>/statement/",
        EnrollmentFeeStatementView.as_view(),
        name="statement",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/emails/",
        EnrollmentFeeEmailsView.as_view(),
        name="emails",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/email-statement/",
        EnrollmentFeeEmailStatementView.as_view(),
        name="email-statement",
    ),
    path("payments/<uuid:payment_id>/void/", FeePaymentVoidView.as_view(), name="void"),
    path(
        "payments/<uuid:payment_id>/email-receipt/",
        FeePaymentEmailReceiptView.as_view(),
        name="email-receipt",
    ),
    path(
        "payments/<uuid:payment_id>/receipt/",
        FeePaymentReceiptView.as_view(),
        name="receipt",
    ),
]
