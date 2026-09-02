"""Version 1 of the public API.

Every route the API exposes is registered here, so the versioned surface is
reviewable in one place. Phase 1 added identity and people management, Phase 2
the course catalogue and learning content, Phase 3 batches, enrolment,
scheduling and the dashboards. Assessment domains arrive with the features that
implement them.
"""

from django.urls import include, path

from apps.attendance import urls as attendance_urls
from apps.batches import urls as batch_urls
from apps.courses import urls as course_urls
from apps.dashboards import urls as dashboard_urls
from apps.enrollments import urls as enrollment_urls
from apps.sessions import urls as session_urls

app_name = "v1"

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("users/", include("apps.accounts.user_urls")),
    path("students/", include("apps.students.urls")),
    path("trainers/", include("apps.trainers.urls")),
    path("categories/", include((course_urls.category_patterns, "categories"))),
    path("courses/", include((course_urls.course_patterns, "courses"))),
    path("modules/", include((course_urls.module_patterns, "modules"))),
    path("lessons/", include((course_urls.lesson_patterns, "lessons"))),
    path("resources/", include((course_urls.resource_patterns, "resources"))),
    path(
        "batches/",
        include((batch_urls.batch_patterns + session_urls.batch_session_patterns, "batches")),
    ),
    path(
        "sessions/",
        include(
            (
                session_urls.session_patterns + attendance_urls.session_attendance_patterns,
                "sessions",
            )
        ),
    ),
    path("attendance/", include((attendance_urls.attendance_patterns, "attendance"))),
    path("schedules/", include((batch_urls.schedule_patterns, "schedules"))),
    path(
        "enrollments/",
        include(
            (
                enrollment_urls.enrollment_patterns
                + attendance_urls.enrollment_attendance_patterns,
                "enrollments",
            )
        ),
    ),
    path("progress/", include((enrollment_urls.progress_patterns, "progress"))),
    path("calendar/", include((dashboard_urls.calendar_patterns, "calendar"))),
    path("dashboard/", include((dashboard_urls.dashboard_patterns, "dashboard"))),
]
