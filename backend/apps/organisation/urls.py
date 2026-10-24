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

#: The years an admission is filed under, and the banks a payment came
#: through. Both are reference lists a screen picks from, mounted beside the
#: colleges for the same reason: they are not places the institute runs.
academic_year_urlpatterns = [
    path("", views.AcademicYearListView.as_view(), name="list"),
    path("<uuid:year_id>/", views.AcademicYearDetailView.as_view(), name="detail"),
]

bank_urlpatterns = [
    path("", views.BankListView.as_view(), name="list"),
    path("<uuid:bank_id>/", views.BankDetailView.as_view(), name="detail"),
]
