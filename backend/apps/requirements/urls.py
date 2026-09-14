from django.urls import path

from .views import (
    RequirementCloseView,
    RequirementDetailView,
    RequirementListView,
    RequirementReplyView,
)

app_name = "requirements"

urlpatterns = [
    path("", RequirementListView.as_view(), name="list"),
    path("<uuid:requirement_id>/", RequirementDetailView.as_view(), name="detail"),
    path("<uuid:requirement_id>/replies/", RequirementReplyView.as_view(), name="reply"),
    path("<uuid:requirement_id>/close/", RequirementCloseView.as_view(), name="close"),
]
