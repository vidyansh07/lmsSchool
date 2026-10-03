from django.urls import path

from .views import EnquiryDetailView, EnquiryListView, EnquirySummaryView

app_name = "enquiries"

urlpatterns = [
    path("", EnquiryListView.as_view(), name="list"),
    path("summary/", EnquirySummaryView.as_view(), name="summary"),
    path("<uuid:enquiry_id>/", EnquiryDetailView.as_view(), name="detail"),
]
