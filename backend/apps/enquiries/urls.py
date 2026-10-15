from django.urls import path

from .views import EnquiryBulkView, EnquiryDetailView, EnquiryListView, EnquirySummaryView

app_name = "enquiries"

urlpatterns = [
    path("", EnquiryListView.as_view(), name="list"),
    path("summary/", EnquirySummaryView.as_view(), name="summary"),
    path("bulk/", EnquiryBulkView.as_view(), name="bulk"),
    path("<uuid:enquiry_id>/", EnquiryDetailView.as_view(), name="detail"),
]
