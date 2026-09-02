"""Academic configuration routes."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("policy/effective/", views.EffectivePolicyView.as_view(), name="policy-effective"),
    path("policy/", views.GlobalPolicyView.as_view(), name="policy-global"),
    path(
        "policy/courses/<uuid:course_id>/",
        views.CoursePolicyView.as_view(),
        name="policy-course",
    ),
    path("calendar/", views.AcademicCalendarView.as_view(), name="academic-calendar"),
    path(
        "calendar/<uuid:event_id>/",
        views.AcademicCalendarEntryView.as_view(),
        name="academic-calendar-entry",
    ),
]
