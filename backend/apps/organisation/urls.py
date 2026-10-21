"""Branch routes."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.BranchListCreateView.as_view(), name="list"),
    path("<uuid:branch_id>/", views.BranchDetailView.as_view(), name="detail"),
]

#: Mounted separately from the branches: a college is somewhere students come
#: *from*, not a place the institute runs.
college_urlpatterns = [
    path("", views.CollegeListCreateView.as_view(), name="list"),
]
