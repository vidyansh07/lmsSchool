"""Trainer routes (mounted at /api/v1/trainers/)."""

from django.urls import path

from .views import TrainerDetailView, TrainerListCreateView, TrainerMeView

app_name = "trainers"

urlpatterns = [
    path("", TrainerListCreateView.as_view(), name="list"),
    path("me/", TrainerMeView.as_view(), name="me"),
    path("<uuid:trainer_id>/", TrainerDetailView.as_view(), name="detail"),
]
