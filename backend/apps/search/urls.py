"""Global search routes (mounted at /api/v1/search/)."""

from django.urls import path

from .views import GlobalSearchView

app_name = "search"

urlpatterns = [
    path("", GlobalSearchView.as_view(), name="global"),
]
