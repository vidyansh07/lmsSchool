"""Batch CRUD, trainer assignment, status transitions and schedules."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import Batch, BatchStatus, Weekday

BATCHES_URL = "/api/v1/batches/"


@pytest.mark.django_db
def test_admin_creates_a_batch_with_a_generated_code(
    api_client_no_csrf, admin_user, published_course
):
    api_client_no_csrf.force_login(admin_user)
    today = timezone.localdate()
    response = api_client_no_csrf.post(
        BATCHES_URL,
        {
            "name": "Morning cohort",
            "course": str(published_course.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
            "capacity": 20,
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["code"].startswith("GRS-B-")
    assert body["status"] == BatchStatus.UPCOMING
    assert body["seats_available"] == 20


@pytest.mark.django_db
def test_batch_codes_are_unique_and_sequential(api_client_no_csrf, admin_user, published_course):
    api_client_no_csrf.force_login(admin_user)
    today = timezone.localdate()
    codes = []
    for index in range(3):
        response = api_client_no_csrf.post(
            BATCHES_URL,
            {
                "name": f"Cohort {index}",
                "course": str(published_course.id),
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=30)).isoformat(),
                "capacity": 10,
            },
            format="json",
        )
        codes.append(response.json()["code"])
    assert len(set(codes)) == 3
    assert codes == sorted(codes)


@pytest.mark.django_db
def test_end_date_before_start_date_is_refused(api_client_no_csrf, admin_user, published_course):
    api_client_no_csrf.force_login(admin_user)
    today = timezone.localdate()
    response = api_client_no_csrf.post(
        BATCHES_URL,
        {
            "name": "Backwards",
            "course": str(published_course.id),
            "start_date": today.isoformat(),
            "end_date": (today - timedelta(days=1)).isoformat(),
            "capacity": 10,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "end_date" in response.json()["error"]["details"]


@pytest.mark.django_db
@pytest.mark.parametrize("capacity", [0, -5])
def test_capacity_must_be_positive(api_client_no_csrf, admin_user, published_course, capacity):
    api_client_no_csrf.force_login(admin_user)
    today = timezone.localdate()
    response = api_client_no_csrf.post(
        BATCHES_URL,
        {
            "name": "Nobody",
            "course": str(published_course.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
            "capacity": capacity,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "capacity" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_a_batch_cannot_run_an_unpublished_course(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    today = timezone.localdate()
    response = api_client_no_csrf.post(
        BATCHES_URL,
        {
            "name": "Too early",
            "course": str(draft_course.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
            "capacity": 10,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "course" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_an_inactive_trainer_cannot_be_assigned(
    api_client_no_csrf, admin_user, batch, trainer_profile_two
):
    trainer_profile_two.user.is_active = False
    trainer_profile_two.user.save()

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/trainer/",
        {"trainer_id": str(trainer_profile_two.id)},
        format="json",
    )
    assert response.status_code == 400
    assert "trainer" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_trainer_assignment_is_audited(api_client_no_csrf, admin_user, batch, trainer_profile_two):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/trainer/",
        {"trainer_id": str(trainer_profile_two.id)},
        format="json",
    )
    assert response.status_code == 200
    entry = AuditLog.objects.filter(action=AuditAction.BATCH_TRAINER_ASSIGNED).first()
    assert entry is not None
    assert entry.context["trainer_code"] == trainer_profile_two.trainer_id


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_batch_without_a_trainer_cannot_go_active(
    api_client_no_csrf, admin_user, published_course
):
    from apps.batches.services import create_batch

    today = timezone.localdate()
    created = create_batch(
        actor=admin_user,
        name="Unstaffed",
        course=published_course,
        start_date=today,
        end_date=today + timedelta(days=30),
        capacity=5,
    )
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(f"{BATCHES_URL}{created.id}/status/", {"status": "active"})
    assert response.status_code == 400
    assert "trainer" in str(response.json()["error"]["details"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "target"),
    [
        (BatchStatus.COMPLETED, BatchStatus.ACTIVE),
        (BatchStatus.CANCELLED, BatchStatus.ACTIVE),
        (BatchStatus.ARCHIVED, BatchStatus.ACTIVE),
        (BatchStatus.UPCOMING, BatchStatus.COMPLETED),
    ],
)
def test_invalid_status_transitions_are_refused(
    api_client_no_csrf, admin_user, batch, start, target
):
    Batch.objects.filter(pk=batch.pk).update(status=start)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(f"{BATCHES_URL}{batch.id}/status/", {"status": target})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_transition"


@pytest.mark.django_db
def test_batch_status_changes_are_audited(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/status/", {"status": "completed", "note": "Course finished"}
    )
    entry = AuditLog.objects.filter(action=AuditAction.BATCH_STATUS_CHANGED).first()
    assert entry is not None
    assert entry.context["to"] == BatchStatus.COMPLETED


@pytest.mark.django_db
def test_capacity_cannot_drop_below_the_seats_already_taken(
    api_client_no_csrf, admin_user, batch, enrollment
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(f"{BATCHES_URL}{batch.id}/", {"capacity": 0}, format="json")
    assert response.status_code == 400

    # One seat is taken, so dropping to 1 is fine and to 0 is not.
    assert (
        api_client_no_csrf.patch(
            f"{BATCHES_URL}{batch.id}/", {"capacity": 1}, format="json"
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_schedule_can_be_added_to_a_batch(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/schedules/",
        {
            "weekday": Weekday.TUESDAY,
            "start_time": "14:00",
            "end_time": "16:00",
            "timezone_name": "Asia/Kolkata",
            "location": "Lab 2",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["weekday_label"] == "Tuesday"
    assert body["duration_minutes"] == 120


@pytest.mark.django_db
def test_a_schedule_ending_before_it_starts_is_refused(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/schedules/",
        {"weekday": Weekday.WEDNESDAY, "start_time": "11:00", "end_time": "09:00"},
        format="json",
    )
    assert response.status_code == 400
    assert "end_time" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_an_unknown_timezone_is_refused(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/schedules/",
        {
            "weekday": Weekday.THURSDAY,
            "start_time": "09:00",
            "end_time": "10:00",
            "timezone_name": "Mars/Olympus_Mons",
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_schedule_changes_are_audited(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"/api/v1/schedules/{schedule.id}/", {"location": "Lab 9"}, format="json"
    )
    assert AuditLog.objects.filter(action=AuditAction.SCHEDULE_CREATED).exists()
    entry = AuditLog.objects.filter(action=AuditAction.SCHEDULE_UPDATED).first()
    assert entry.context["changed_fields"] == ["location"]

    api_client_no_csrf.delete(f"/api/v1/schedules/{schedule.id}/")
    assert AuditLog.objects.filter(action=AuditAction.SCHEDULE_DELETED).exists()


@pytest.mark.django_db
def test_batch_listing_is_filtered_searched_and_paginated(
    api_client_no_csrf, admin_user, batch, upcoming_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{BATCHES_URL}?status=active").json()["count"] == 1
    assert api_client_no_csrf.get(f"{BATCHES_URL}?status=upcoming").json()["count"] == 1
    assert api_client_no_csrf.get(f"{BATCHES_URL}?search=Evening").json()["count"] == 1

    page = api_client_no_csrf.get(f"{BATCHES_URL}?page_size=1").json()
    assert page["count"] == 2
    assert len(page["results"]) == 1


@pytest.mark.django_db
def test_seat_counts_come_from_one_annotated_query(
    api_client_no_csrf, admin_user, batch, enrollment, django_assert_max_num_queries
):
    """A page of batches must not cost one count query per row."""
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(10):
        body = api_client_no_csrf.get(BATCHES_URL).json()
    row = next(item for item in body["results"] if item["code"] == batch.code)
    assert row["enrolled_count"] == 1
    assert row["seats_available"] == batch.capacity - 1


@pytest.mark.django_db
def test_schedules_appear_on_the_batch_detail(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").json()
    assert len(body["schedules"]) == 1
    assert body["schedules"][0]["start_time"] == "09:00:00"
    assert body["can_manage"] is True


@pytest.mark.django_db
def test_time_fields_survive_a_round_trip(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(
        f"{BATCHES_URL}{batch.id}/schedules/",
        {"weekday": Weekday.FRIDAY, "start_time": "18:30", "end_time": "20:00"},
        format="json",
    ).json()
    fetched = api_client_no_csrf.get(f"/api/v1/schedules/{created['id']}/").json()
    assert fetched["start_time"] == "18:30:00"
    assert fetched["end_time"] == "20:00:00"
    assert fetched["duration_minutes"] == 90


@pytest.mark.django_db
def test_schedule_default_trainer_is_the_batch_trainer(schedule, trainer_profile):
    assert schedule.trainer_id is None
    assert schedule.effective_trainer_id == trainer_profile.pk


@pytest.mark.django_db
def test_batch_helpers_report_seats(batch, enrollment):
    batch.refresh_from_db()
    assert batch.seats_taken() == 1
    assert batch.seats_available() == batch.capacity - 1
    assert batch.is_enrollable is True
    assert batch.grants_access is True


@pytest.mark.django_db
def test_schedule_times_are_bounded_by_the_batch_dates(admin_user, batch):
    """A class outside the batch's own dates never appears on the calendar."""
    from datetime import date

    from apps.batches.services import create_schedule
    from apps.dashboards.calendar import class_events

    create_schedule(
        batch=batch,
        actor=admin_user,
        weekday=Weekday.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
    )
    # A window entirely before the batch starts yields nothing.
    events = class_events(admin_user, date(2020, 1, 1), date(2020, 2, 1))
    assert events == []
