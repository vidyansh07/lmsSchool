from django.urls import path

from .views import AdmissionCancelView, AdmissionDetailView, AdmissionListView

app_name = "admissions"

urlpatterns = [
    path("", AdmissionListView.as_view(), name="list"),
    path("<uuid:admission_id>/", AdmissionDetailView.as_view(), name="detail"),
    path("<uuid:admission_id>/cancel/", AdmissionCancelView.as_view(), name="cancel"),
]
