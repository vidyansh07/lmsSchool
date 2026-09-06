"""Version 1 of the public API.

Every route the API exposes is registered here, so the versioned surface is
reviewable in one place. Phase 1 added identity and people management, Phase 2
the course catalogue and learning content, Phase 3 batches, enrolment,
scheduling and the dashboards. Assessment domains arrive with the features that
implement them.
"""

from django.urls import include, path

from apps.academics import urls as academics_urls
from apps.announcements import urls as announcement_urls
from apps.assessments import urls as assessment_urls
from apps.assignments import urls as assignment_urls
from apps.attendance import urls as attendance_urls
from apps.batches import urls as batch_urls
from apps.certificates import urls as certificate_urls
from apps.courses import urls as course_urls
from apps.dashboards import urls as dashboard_urls
from apps.discussions import urls as discussion_urls
from apps.dsr import urls as dsr_urls
from apps.enrollments import urls as enrollment_urls
from apps.exams import urls as exam_urls
from apps.learning import urls as learning_urls
from apps.notifications import urls as notification_urls
from apps.performance import urls as performance_urls
from apps.progress import urls as progress_urls
from apps.projects import urls as project_urls
from apps.questions import urls as question_urls
from apps.reporting import urls as reporting_urls
from apps.sessions import urls as session_urls

app_name = "v1"

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    # Deleted records, across every model that supports recovery.
    path("recovery/", include("apps.common.recovery_urls")),
    path("users/", include("apps.accounts.user_urls")),
    path("students/", include("apps.students.urls")),
    path(
        "trainers/",
        include((reporting_urls.trainer_rollup_urlpatterns, "trainer-rollups")),
    ),
    path("trainers/", include("apps.trainers.urls")),
    path("categories/", include((course_urls.category_patterns, "categories"))),
    path(
        "courses/",
        include(
            (
                course_urls.course_patterns
                + assignment_urls.course_urlpatterns
                + project_urls.course_urlpatterns,
                "courses",
            )
        ),
    ),
    path("assignments/", include((assignment_urls.assignment_urlpatterns, "assignments"))),
    path("assessments/", include((assessment_urls.assessment_urlpatterns, "assessments"))),
    path("results/", include((assessment_urls.result_urlpatterns, "results"))),
    path("academics/", include((academics_urls.urlpatterns, "academics"))),
    path("projects/", include((project_urls.project_urlpatterns, "projects"))),
    path("completions/", include((progress_urls.completion_urlpatterns, "completions"))),
    path("certificates/", include((certificate_urls.certificate_urlpatterns, "certificates"))),
    path("notifications/", include((notification_urls.urlpatterns, "notifications"))),
    path("announcements/", include((announcement_urls.urlpatterns, "announcements"))),
    path("discussions/", include((discussion_urls.discussion_urlpatterns, "discussions"))),
    path("learning/", include((learning_urls.urlpatterns, "learning"))),
    path("reports/", include((reporting_urls.report_urlpatterns, "reports"))),
    path("dashboards/", include((reporting_urls.dashboard_urlpatterns, "dashboards"))),
    path("imports/", include((reporting_urls.import_urlpatterns, "imports"))),
    # Anonymous by design: verifying a certificate is what the public does
    # with it (§6.8).
    path("verify/", include((certificate_urls.public_urlpatterns, "verify"))),
    path("questions/", include((question_urls.urlpatterns, "questions"))),
    path("exams/", include((exam_urls.exam_urlpatterns, "exams"))),
    path("attempts/", include((exam_urls.attempt_urlpatterns, "attempts"))),
    path("submissions/", include((assignment_urls.submission_urlpatterns, "submissions"))),
    path("modules/", include((course_urls.module_patterns, "modules"))),
    path("lessons/", include((course_urls.lesson_patterns, "lessons"))),
    path("resources/", include((course_urls.resource_patterns, "resources"))),
    path(
        "batches/",
        include(
            (
                batch_urls.batch_patterns
                + session_urls.batch_session_patterns
                + assessment_urls.batch_urlpatterns
                + exam_urls.batch_urlpatterns
                + progress_urls.batch_urlpatterns
                + reporting_urls.batch_rollup_urlpatterns
                + discussion_urls.batch_urlpatterns
                + dsr_urls.batch_urlpatterns
                + performance_urls.trainer_urlpatterns,
                "batches",
            )
        ),
    ),
    path(
        "sessions/",
        include(
            (
                session_urls.session_patterns
                + attendance_urls.session_attendance_patterns
                + dsr_urls.session_urlpatterns,
                "sessions",
            )
        ),
    ),
    path("attendance/", include((attendance_urls.attendance_patterns, "attendance"))),
    path("dsr/", include((dsr_urls.urlpatterns, "dsr"))),
    path("performance/", include((performance_urls.urlpatterns, "performance"))),
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
    path(
        "progress/",
        include(
            (
                enrollment_urls.progress_patterns + progress_urls.progress_urlpatterns,
                "progress",
            )
        ),
    ),
    path("calendar/", include((dashboard_urls.calendar_patterns, "calendar"))),
    path("dashboard/", include((dashboard_urls.dashboard_patterns, "dashboard"))),
]
