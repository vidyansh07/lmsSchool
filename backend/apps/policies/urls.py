from django.urls import path

from .views import PolicyDetailView, PolicyHistoryView, PolicyListView

app_name = "policies"

urlpatterns = [
    path("", PolicyListView.as_view(), name="list"),
    path("<str:category>/<str:key>/history/", PolicyHistoryView.as_view(), name="history"),
    path("<str:category>/<str:key>/", PolicyDetailView.as_view(), name="detail"),
]
