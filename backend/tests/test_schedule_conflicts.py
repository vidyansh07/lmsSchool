"""Schedule conflict detection.

Overlap is a relationship between rows, so it cannot be a column constraint and
must not be left to the interface. These tests drive the API directly.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.batches.conflicts import times_overlap
from apps.batches.models import Weekday

BATCHES_URL = "/api/v1/batches/"


def _add_class(client, batch, *, weekday=Weekday.MONDAY, start="09:00", end="11:00", **extra):
    return client.post(
        f"{BATCHES_URL}{batch.id}/schedules/",
        {"weekday": weekday, "start_time": start, "end_time": end, **extra},
        format="json",
    )


# ---------------------------------------------------------------------------
# The overlap primitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start_a", "end_a", "start_b", "end_b", "expected"),
    [
        # Identical, contained, straddling both edges.
        ((9, 0), (11, 0), (9, 0), (11, 0), True),
        ((9, 0), (11, 0), (9, 30), (10, 0), True),
        ((9, 30), (10, 0), (9, 0), (11, 0), True),
        ((9, 0), (11, 0), (10, 0), (12, 0), True),
        # Back-to-back must NOT clash — consecutive classes are normal.
        ((9, 0), (11, 0), (11, 0), (13, 0), False),
        ((11, 0), (13, 0), (9, 0), (11, 0), False),
        # Plainly apart.
        ((9, 0), (10, 0), (14, 0), (15, 0), False),
    ],
)
def test_overlap_is_half_open(start_a, end_a, start_b, end_b, expected):
    assert (
        times_overlap(time(*start_a), time(*end_a), "UTC", time(*start_b), time(*end_b), "UTC")
        is expected
    )


def test_overlap_is_time_zone_aware():
    """09:00 in Kolkata and 09:00 in London are different moments."""
    assert (
        times_overlap(
            time(9, 0), time(11, 0), "Asia/Kolkata", time(9, 0), time(11, 0), "Europe/London"
        )
        is False
    )
    # The same wall clock in the same zone does clash.
    assert (
        times_overlap(
            time(9, 0), time(11, 0), "Asia/Kolkata", time(9, 0), time(11, 0), "Asia/Kolkata"
        )
        is True
    )


# ---------------------------------------------------------------------------
# Batch conflicts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_batch_cannot_hold_two_overlapping_classes(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, batch, start="10:00", end="12:00")

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "schedule_conflict"
    assert "already has a class" in str(body["details"]["schedule"])
    assert batch.schedules.count() == 1


@pytest.mark.django_db
def test_back_to_back_classes_are_allowed(api_client_no_csrf, admin_user, batch, schedule):
    """A class ending at 11:00 and one starting at 11:00 do not clash."""
    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, batch, start="11:00", end="13:00")
    assert response.status_code == 201
    assert batch.schedules.count() == 2


@pytest.mark.django_db
def test_the_same_time_on_a_different_day_is_allowed(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, batch, weekday=Weekday.TUESDAY)
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Trainer conflicts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_cannot_teach_two_batches_at_once(
    api_client_no_csrf, admin_user, batch, schedule, published_course, trainer_profile
):
    """The core §11 rule, across two different batches."""
    from apps.batches.services import create_batch

    today = timezone.localdate()
    second = create_batch(
        actor=admin_user,
        name="Clashing cohort",
        course=published_course,
        trainer=trainer_profile,
        start_date=today,
        end_date=today + timedelta(days=60),
        capacity=10,
    )

    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, second, start="10:00", end="12:00")

    assert response.status_code == 409
    assert "already teaches" in str(response.json()["error"]["details"]["schedule"])
    assert second.schedules.count() == 0


@pytest.mark.django_db
def test_different_trainers_may_teach_at_the_same_time(
    api_client_no_csrf, admin_user, batch, schedule, upcoming_batch
):
    """Two trainers, one time slot — not a clash.

    The batches' dates overlap and the weekday matches, so only the trainer
    differs. Refusing this would make the timetable unusable.
    """
    from apps.batches.models import Batch

    today = timezone.localdate()
    Batch.objects.filter(pk=upcoming_batch.pk).update(
        start_date=today, end_date=today + timedelta(days=60)
    )
    upcoming_batch.refresh_from_db()

    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, upcoming_batch, start="09:30", end="10:30")
    assert response.status_code == 201


@pytest.mark.django_db
def test_batches_in_different_months_never_clash(
    api_client_no_csrf, admin_user, batch, schedule, published_course, trainer_profile
):
    """Same trainer, same weekday, same time — but the terms do not overlap."""
    from apps.batches.services import create_batch

    later = timezone.localdate() + timedelta(days=365)
    future = create_batch(
        actor=admin_user,
        name="Next year",
        course=published_course,
        trainer=trainer_profile,
        start_date=later,
        end_date=later + timedelta(days=60),
        capacity=10,
    )

    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, future, start="09:00", end="11:00")
    assert response.status_code == 201


@pytest.mark.django_db
def test_assigning_a_trainer_who_is_already_busy_is_refused(
    api_client_no_csrf, admin_user, batch, schedule, published_course, trainer_profile_two
):
    """Caught at assignment, so the refusal names the clashing class."""
    from apps.batches.services import create_batch, create_schedule

    today = timezone.localdate()
    second = create_batch(
        actor=admin_user,
        name="Second cohort",
        course=published_course,
        trainer=trainer_profile_two,
        start_date=today,
        end_date=today + timedelta(days=60),
        capacity=10,
    )
    create_schedule(
        batch=second,
        actor=admin_user,
        weekday=Weekday.MONDAY,
        start_time=time(10, 0),
        end_time=time(12, 0),
    )

    # Moving the busy trainer onto the first batch would double-book them.
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{second.id}/trainer/",
        {"trainer_id": str(batch.trainer_id)},
        format="json",
    )
    assert response.status_code == 409
    assert "already teaches" in str(response.json()["error"]["details"])

    second.refresh_from_db()
    assert second.trainer_id == trainer_profile_two.pk


@pytest.mark.django_db
def test_a_cancelled_batch_does_not_block_the_timetable(
    api_client_no_csrf, admin_user, batch, schedule, published_course, trainer_profile
):
    from apps.batches.models import Batch, BatchStatus
    from apps.batches.services import create_batch

    Batch.objects.filter(pk=batch.pk).update(status=BatchStatus.CANCELLED)

    today = timezone.localdate()
    replacement = create_batch(
        actor=admin_user,
        name="Replacement cohort",
        course=published_course,
        trainer=trainer_profile,
        start_date=today,
        end_date=today + timedelta(days=60),
        capacity=10,
    )
    api_client_no_csrf.force_login(admin_user)
    response = _add_class(api_client_no_csrf, replacement, start="09:00", end="11:00")
    assert response.status_code == 201


@pytest.mark.django_db
def test_an_inactive_slot_does_not_block_the_timetable(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"/api/v1/schedules/{schedule.id}/", {"is_active": False}, format="json"
    )
    response = _add_class(api_client_no_csrf, batch, start="09:00", end="11:00")
    assert response.status_code == 201


@pytest.mark.django_db
def test_editing_a_class_into_a_clash_is_refused(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    _add_class(api_client_no_csrf, batch, start="14:00", end="16:00")

    # Move the afternoon class onto the morning one.
    afternoon = batch.schedules.get(start_time=time(14, 0))
    response = api_client_no_csrf.patch(
        f"/api/v1/schedules/{afternoon.id}/", {"start_time": "10:00"}, format="json"
    )
    assert response.status_code == 409

    afternoon.refresh_from_db()
    assert afternoon.start_time == time(14, 0)


@pytest.mark.django_db
def test_editing_a_class_without_moving_it_is_allowed(
    api_client_no_csrf, admin_user, batch, schedule
):
    """A slot must not be treated as clashing with itself."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/schedules/{schedule.id}/", {"location": "Lab 7"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["location"] == "Lab 7"
