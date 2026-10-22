from django.urls import path

from .views import PlacementDetailView, PlacementListView, PlacementSummaryView

app_name = "placements"

urlpatterns = [
    path("", PlacementListView.as_view(), name="list"),
    path("summary/", PlacementSummaryView.as_view(), name="summary"),
    path("<uuid:placement_id>/", PlacementDetailView.as_view(), name="detail"),
]
