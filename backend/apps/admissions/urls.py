from django.urls import path

from .views import (
    AdmissionCancelView,
    AdmissionDetailView,
    AdmissionListView,
    AdmissionReportView,
)

app_name = "admissions"

urlpatterns = [
    path("", AdmissionListView.as_view(), name="list"),
    # Before the `<uuid:admission_id>` route: "reports" is not a uuid, but a
    # reader should not have to know that to see why this is first.
    path("reports/<slug:tab>/", AdmissionReportView.as_view(), name="report"),
    path("<uuid:admission_id>/", AdmissionDetailView.as_view(), name="detail"),
    path("<uuid:admission_id>/cancel/", AdmissionCancelView.as_view(), name="cancel"),
]
