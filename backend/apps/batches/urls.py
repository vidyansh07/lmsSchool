"""Batch and schedule routes."""

from django.urls import path

from .views import (
    BatchDetailView,
    BatchListCreateView,
    BatchRosterView,
    BatchSchedulesView,
    BatchStatusView,
    BatchTrainerView,
    ScheduleDetailView,
)

batch_patterns = [
    path("", BatchListCreateView.as_view(), name="list"),
    path("<uuid:batch_id>/", BatchDetailView.as_view(), name="detail"),
    path("<uuid:batch_id>/status/", BatchStatusView.as_view(), name="status"),
    path("<uuid:batch_id>/trainer/", BatchTrainerView.as_view(), name="trainer"),
    path("<uuid:batch_id>/roster/", BatchRosterView.as_view(), name="roster"),
    path("<uuid:batch_id>/schedules/", BatchSchedulesView.as_view(), name="schedules"),
]

schedule_patterns = [
    path("<uuid:schedule_id>/", ScheduleDetailView.as_view(), name="detail"),
]
