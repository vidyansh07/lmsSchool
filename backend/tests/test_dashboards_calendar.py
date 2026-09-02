"""Calendar, dashboards, progress — and the end-to-end integration flow."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.batches.models import Weekday

CALENDAR_URL = "/api/v1/calendar/"
STUDENT_DASHBOARD = "/api/v1/dashboard/student/"
TRAINER_DASHBOARD = "/api/v1/dashboard/trainer/"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_weekly_class_expands_into_occurrences(api_client_no_csrf, enrollment, schedule):
    api_client_no_csrf.force_login(enrollment.student.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=28)}"
    ).json()

    classes = [event for event in body["events"] if event["kind"] == "class"]
    # Four weeks of a weekly class: four or five occurrences depending on the
    # weekday the window opens on.
    assert 4 <= len(classes) <= 5
    assert all(event["batch_code"] == schedule.batch.code for event in classes)


@pytest.mark.django_db
def test_calendar_events_carry_what_a_timetable_needs(api_client_no_csrf, enrollment, schedule):
    api_client_no_csrf.force_login(enrollment.student.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=14)}"
    ).json()

    event = next(item for item in body["events"] if item["kind"] == "class")
    assert event["course_title"]
    assert event["location"] == "Lab 1"
    assert event["trainer_name"]
    assert event["start"] and event["end"]
    assert event["metadata"]["timezone"] == "Asia/Kolkata"


@pytest.mark.django_db
def test_batch_milestones_appear_as_all_day_events(api_client_no_csrf, enrollment, batch):
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={batch.end_date}&end={batch.end_date}"
    ).json()

    ends = [event for event in body["events"] if event["kind"] == "batch_end"]
    assert len(ends) == 1
    assert ends[0]["all_day"] is True


@pytest.mark.django_db
def test_the_calendar_only_shows_what_the_caller_may_see(
    api_client_no_csrf, enrollment, schedule, admin_user, upcoming_batch
):
    """A student's calendar carries no trace of a batch they are not on."""
    from apps.batches.services import create_schedule

    create_schedule(
        batch=upcoming_batch,
        actor=admin_user,
        weekday=Weekday.WEDNESDAY,
        start_time=time(18, 0),
        end_time=time(20, 0),
    )

    api_client_no_csrf.force_login(enrollment.student.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=90)}"
    ).content.decode()
    assert upcoming_batch.code not in body


@pytest.mark.django_db
def test_a_cancelled_batch_leaves_the_calendar(
    api_client_no_csrf, admin_user, enrollment, schedule, batch
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"/api/v1/batches/{batch.id}/status/", {"status": "cancelled"})

    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=30)}"
    ).content.decode()
    assert batch.code not in body


@pytest.mark.django_db
def test_the_calendar_range_is_bounded(api_client_no_csrf, enrollment):
    """A calendar query is cheap per day and expensive per year."""
    from apps.dashboards.calendar import MAX_RANGE_DAYS

    api_client_no_csrf.force_login(enrollment.student.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=3650)}"
    ).json()

    from datetime import date

    assert (
        date.fromisoformat(body["end"]) - date.fromisoformat(body["start"])
    ).days == MAX_RANGE_DAYS


@pytest.mark.django_db
def test_an_invalid_calendar_range_is_refused(api_client_no_csrf, enrollment):
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(f"{CALENDAR_URL}?start=not-a-date").status_code == 400
    assert (
        api_client_no_csrf.get(f"{CALENDAR_URL}?start=2026-06-01&end=2026-05-01").status_code == 400
    )


@pytest.mark.django_db
def test_a_failing_calendar_source_does_not_blank_the_timetable(
    api_client_no_csrf, monkeypatch, enrollment, schedule
):
    """One broken feed must not empty everyone's calendar."""
    from apps.dashboards import calendar as calendar_module

    def broken(user, start, end):
        raise RuntimeError("this source is broken")

    monkeypatch.setattr(calendar_module, "EVENT_SOURCES", [broken, calendar_module.class_events])

    api_client_no_csrf.force_login(enrollment.student.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=14)}"
    ).json()
    assert body["count"] > 0


# ---------------------------------------------------------------------------
# Student dashboard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_student_dashboard_shows_courses_batches_and_classes(
    api_client_no_csrf, enrollment, schedule
):
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(STUDENT_DASHBOARD).json()

    assert body["is_student"] is True
    assert len(body["courses"]) == 1
    assert body["courses"][0]["course_title"] == enrollment.course.title
    assert body["courses"][0]["grants_access"] is True
    assert len(body["batches"]) == 1
    assert body["upcoming_classes"]
    assert body["notifications"] == []


@pytest.mark.django_db
def test_the_student_dashboard_reports_progress(
    api_client_no_csrf, enrollment, preview_lesson, paid_lesson
):
    from apps.enrollments.services import set_lesson_completion

    set_lesson_completion(student=enrollment.student, lesson=preview_lesson, completed=True)

    api_client_no_csrf.force_login(enrollment.student.user)
    course = api_client_no_csrf.get(STUDENT_DASHBOARD).json()["courses"][0]

    assert course["total_lessons"] == 2
    assert course["completed_lessons"] == 1
    assert course["progress_percent"] == 50


@pytest.mark.django_db
def test_continue_learning_points_at_the_last_lesson_opened(
    api_client_no_csrf, enrollment, paid_lesson
):
    from apps.enrollments.services import touch_lesson

    touch_lesson(student=enrollment.student, lesson=paid_lesson)

    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(STUDENT_DASHBOARD).json()
    assert body["continue_learning"]["last_lesson_title"] == paid_lesson.title


@pytest.mark.django_db
def test_a_suspended_enrolment_drops_out_of_current_courses(
    api_client_no_csrf, admin_user, enrollment
):
    from apps.enrollments.models import EnrollmentStatus
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.SUSPENDED, actor=admin_user, note="Absent"
    )
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(STUDENT_DASHBOARD).json()

    assert body["courses"] == []
    # The batch stays listed, so the student can see what happened.
    assert len(body["batches"]) == 1
    assert body["batches"][0]["enrollment_status"] == "suspended"


@pytest.mark.django_db
def test_the_student_dashboard_is_empty_but_valid_for_a_trainer(api_client_no_csrf, trainer):
    api_client_no_csrf.force_login(trainer)
    body = api_client_no_csrf.get(STUDENT_DASHBOARD).json()
    assert body["is_student"] is False
    assert body["courses"] == []


@pytest.mark.django_db
def test_the_student_dashboard_costs_a_bounded_number_of_queries(
    api_client_no_csrf, enrollment, schedule, django_assert_max_num_queries
):
    """§17: a dashboard must not issue a query per enrolment."""
    api_client_no_csrf.force_login(enrollment.student.user)
    with django_assert_max_num_queries(25):
        assert api_client_no_csrf.get(STUDENT_DASHBOARD).status_code == 200


# ---------------------------------------------------------------------------
# Trainer dashboard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_trainer_dashboard_shows_batches_students_and_classes(
    api_client_no_csrf, trainer_profile, batch, schedule, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(TRAINER_DASHBOARD).json()

    assert body["is_trainer"] is True
    assert len(body["batches"]) == 1
    assert body["batches"][0]["code"] == batch.code
    assert body["batches"][0]["enrolled_count"] == 1
    assert body["student_count"] == 1
    assert len(body["courses"]) == 1


@pytest.mark.django_db
def test_the_trainer_dashboard_excludes_other_trainers_batches(
    api_client_no_csrf, trainer_profile, batch, upcoming_batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(TRAINER_DASHBOARD).content.decode()
    assert batch.code in body
    assert upcoming_batch.code not in body


@pytest.mark.django_db
def test_the_trainer_dashboard_is_empty_but_valid_for_a_student(api_client_no_csrf, enrollment):
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(TRAINER_DASHBOARD).json()
    assert body["is_trainer"] is False
    assert body["batches"] == []


@pytest.mark.django_db
def test_the_trainer_dashboard_costs_a_bounded_number_of_queries(
    api_client_no_csrf, trainer_profile, batch, schedule, enrollment, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(trainer_profile.user)
    with django_assert_max_num_queries(25):
        assert api_client_no_csrf.get(TRAINER_DASHBOARD).status_code == 200


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_lesson_can_be_marked_complete_and_reopened(api_client_no_csrf, enrollment, paid_lesson):
    api_client_no_csrf.force_login(enrollment.student.user)
    url = f"/api/v1/progress/lessons/{paid_lesson.id}/completion/"

    done = api_client_no_csrf.post(url, {"completed": True}, format="json")
    assert done.status_code == 200
    assert done.json()["status"] == "completed"

    reopened = api_client_no_csrf.post(url, {"completed": False}, format="json")
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["completed_at"] is None


@pytest.mark.django_db
def test_progress_needs_a_live_enrolment(api_client_no_csrf, student_profile, paid_lesson):
    """A student with a profile but no enrolment cannot record progress."""
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/progress/lessons/{paid_lesson.id}/completion/",
        {"completed": True},
        format="json",
    )
    assert response.status_code == 400
    assert "enrolment" in str(response.json()["error"]["details"])


@pytest.mark.django_db
def test_only_students_track_progress(api_client_no_csrf, trainer, paid_lesson):
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.post(
        f"/api/v1/progress/lessons/{paid_lesson.id}/completion/",
        {"completed": True},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_browsing_a_preview_lesson_creates_no_progress(student_profile, preview_lesson):
    """Progress is a record of study, not of curiosity.

    ``student_profile`` has no enrolment, so opening a free preview must not
    manufacture a progress row for a course they never joined.
    """
    from apps.enrollments.models import LessonProgress
    from apps.enrollments.services import touch_lesson

    assert touch_lesson(student=student_profile, lesson=preview_lesson) is None
    assert LessonProgress.objects.count() == 0


@pytest.mark.django_db
def test_progress_is_visible_only_to_its_owner(
    api_client_no_csrf, enrollment, other_enrollment, paid_lesson
):
    api_client_no_csrf.force_login(enrollment.student.user)
    mine = api_client_no_csrf.get(f"/api/v1/enrollments/{enrollment.id}/progress/")
    theirs = api_client_no_csrf.get(f"/api/v1/enrollments/{other_enrollment.id}/progress/")
    assert mine.status_code == 200
    assert theirs.status_code == 404


# ---------------------------------------------------------------------------
# §19 integration flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_creates_batch_assigns_trainer_enrols_student_who_then_gets_access(
    api_client_no_csrf, admin_user, published_course, trainer_profile, student_profile, paid_lesson
):
    """The whole Phase 3 story, through the API, as three different people."""
    today = timezone.localdate()

    # 1. An administrator creates a batch.
    api_client_no_csrf.force_login(admin_user)
    batch = api_client_no_csrf.post(
        "/api/v1/batches/",
        {
            "name": "Integration cohort",
            "course": str(published_course.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=45)).isoformat(),
            "capacity": 5,
        },
        format="json",
    ).json()
    assert batch["status"] == "upcoming"

    # 2. Assigns a trainer, then a class.
    assigned = api_client_no_csrf.post(
        f"/api/v1/batches/{batch['id']}/trainer/",
        {"trainer_id": str(trainer_profile.id)},
        format="json",
    )
    assert assigned.status_code == 200

    scheduled = api_client_no_csrf.post(
        f"/api/v1/batches/{batch['id']}/schedules/",
        {"weekday": Weekday.THURSDAY, "start_time": "15:00", "end_time": "17:00"},
        format="json",
    )
    assert scheduled.status_code == 201

    # 3. Activates the batch and enrols the student.
    activated = api_client_no_csrf.post(
        f"/api/v1/batches/{batch['id']}/status/", {"status": "active"}
    )
    assert activated.status_code == 200

    enrolled = api_client_no_csrf.post(
        "/api/v1/enrollments/",
        {"student_id": str(student_profile.id), "batch_id": batch["id"]},
        format="json",
    )
    assert enrolled.status_code == 201
    assert enrolled.json()["grants_access"] is True

    # 4. The student now reads the paid lesson they could not reach before.
    api_client_no_csrf.force_login(student_profile.user)
    lesson = api_client_no_csrf.get(f"/api/v1/lessons/{paid_lesson.id}/")
    assert lesson.status_code == 200
    assert lesson.json()["text_content"] == "Secret paid content."

    # 5. And sees it all on their dashboard and calendar.
    dashboard = api_client_no_csrf.get(STUDENT_DASHBOARD).json()
    assert any(row["batch_code"] == batch["code"] for row in dashboard["courses"])

    calendar = api_client_no_csrf.get(
        f"{CALENDAR_URL}?start={today}&end={today + timedelta(days=21)}"
    ).json()
    assert any(event["batch_code"] == batch["code"] for event in calendar["events"])

    # 6. The trainer sees the cohort on theirs.
    api_client_no_csrf.force_login(trainer_profile.user)
    trainer_view = api_client_no_csrf.get(TRAINER_DASHBOARD).json()
    assert any(row["code"] == batch["code"] for row in trainer_view["batches"])
    assert trainer_view["student_count"] >= 1

    roster = api_client_no_csrf.get(f"/api/v1/batches/{batch['id']}/roster/")
    assert roster.status_code == 200
    assert roster.json()[0]["student_code"] == student_profile.student_id
