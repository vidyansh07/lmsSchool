"""Attendance routes."""

from django.urls import path

from .views import (
    AttendanceCorrectionView,
    EnrollmentAttendanceView,
    MyAttendanceView,
    SessionAttendanceListView,
    SessionRegisterView,
)

#: Mounted under the session routes: a register belongs to a class.
session_attendance_patterns = [
    path("<uuid:session_id>/register/", SessionRegisterView.as_view(), name="register"),
    path("<uuid:session_id>/attendance/", SessionAttendanceListView.as_view(), name="attendance"),
]

attendance_patterns = [
    path("mine/", MyAttendanceView.as_view(), name="mine"),
    path("<uuid:record_id>/correct/", AttendanceCorrectionView.as_view(), name="correct"),
]

enrollment_attendance_patterns = [
    path(
        "<uuid:enrollment_id>/attendance/",
        EnrollmentAttendanceView.as_view(),
        name="attendance",
    ),
]
