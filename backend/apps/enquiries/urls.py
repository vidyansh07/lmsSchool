from django.urls import path

from .views import (
    EnquiryBulkView,
    EnquiryDetailView,
    EnquiryListView,
    EnquiryNoteView,
    EnquiryRegisterView,
    EnquirySummaryView,
)

app_name = "enquiries"

urlpatterns = [
    path("", EnquiryListView.as_view(), name="list"),
    path("summary/", EnquirySummaryView.as_view(), name="summary"),
    path("bulk/", EnquiryBulkView.as_view(), name="bulk"),
    path("<uuid:enquiry_id>/", EnquiryDetailView.as_view(), name="detail"),
    path("<uuid:enquiry_id>/notes/", EnquiryNoteView.as_view(), name="notes"),
    path("<uuid:enquiry_id>/register/", EnquiryRegisterView.as_view(), name="register"),
]
