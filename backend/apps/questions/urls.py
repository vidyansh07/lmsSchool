"""Question bank routes. Staff only — every response carries the answers."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.QuestionListView.as_view(), name="question-list"),
    path("create/", views.QuestionCreateView.as_view(), name="question-create"),
    path("<uuid:question_id>/", views.QuestionDetailView.as_view(), name="question-detail"),
]
