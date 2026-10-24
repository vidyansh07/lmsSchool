"""Fee routes (mounted at /api/v1/fees/)."""

from django.urls import path

from .views import (
    CancelAdmissionView,
    EnrollmentFeeEmailStatementView,
    EnrollmentFeeEmailsView,
    EnrollmentFeeHistoryView,
    EnrollmentFeeInstallmentsView,
    EnrollmentFeeNextDueView,
    EnrollmentFeePaymentsView,
    EnrollmentFeeStatementView,
    EnrollmentFeeView,
    FeeCollectionsTrendView,
    FeePaymentBounceView,
    FeePaymentClearView,
    FeePaymentEmailReceiptView,
    FeePaymentReceiptView,
    FeePaymentRefundView,
    FeePaymentVoidView,
    FeesOverviewView,
    LedgerReconciliationView,
    MyFeesView,
    PaymentCategoryDetailView,
    PaymentCategoryListView,
    StudentFeesView,
    TaxGroupDetailView,
    TaxGroupListView,
)

app_name = "fees"

urlpatterns = [
    path("me/", MyFeesView.as_view(), name="me"),
    path("overview/", FeesOverviewView.as_view(), name="overview"),
    path("payment-categories/", PaymentCategoryListView.as_view(), name="payment-categories"),
    path(
        "payment-categories/<uuid:category_id>/",
        PaymentCategoryDetailView.as_view(),
        name="payment-category-detail",
    ),
    path("tax-groups/", TaxGroupListView.as_view(), name="tax-groups"),
    path("tax-groups/<uuid:group_id>/", TaxGroupDetailView.as_view(), name="tax-group-detail"),
    path("reconciliation/", LedgerReconciliationView.as_view(), name="reconciliation"),
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
        "enrollments/<uuid:enrollment_id>/cancel/",
        CancelAdmissionView.as_view(),
        name="cancel",
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
    path("payments/<uuid:payment_id>/clear/", FeePaymentClearView.as_view(), name="clear"),
    path("payments/<uuid:payment_id>/bounce/", FeePaymentBounceView.as_view(), name="bounce"),
    path(
        "payments/<uuid:payment_id>/refund/",
        FeePaymentRefundView.as_view(),
        name="refund",
    ),
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
