"""Setting a batch up for teaching in one action.

Writing the timetable, making the classes and putting the curriculum on them
were always one intention done in three places, in an order somebody had to
know. A batch that had only had the first two looked exactly like one nobody
had started, which is the failure this exists to prevent.

The two properties worth most of the tests here:

* **Monday to Saturday is the default.** Six days, not five. That is how this
  institute runs, so the common case should be no decision at all.
* **It is safe to run twice**, because an operator will. Every step underneath
  already refuses to duplicate itself; this checks that composing them did not
  lose that.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.batches.models import BatchSchedule, Weekday
from apps.batches.services import (
    DEFAULT_TEACHING_WEEKDAYS,
    ScheduleConflictError,
    setup_batch_timetable,
)
from apps.common.exceptions import ApplicationError
from apps.sessions.models import ClassSession

MORNING = (time(9, 0), time(11, 0))


def _set_up(batch, actor, **overrides):
    return setup_batch_timetable(
        batch=batch,
        actor=actor,
        start_time=overrides.pop("start_time", MORNING[0]),
        end_time=overrides.pop("end_time", MORNING[1]),
        **overrides,
    )


# ---------------------------------------------------------------------------
# The default week
# ---------------------------------------------------------------------------


def test_the_default_week_is_monday_to_saturday():
    """Stated as a test because it is a business fact, not a preference.

    Sunday is the only day off here. A five-day default would be wrong for every
    batch this institute has ever run, and wrong quietly — the timetable would
    simply be missing a day nobody noticed until a Saturday.
    """
    assert DEFAULT_TEACHING_WEEKDAYS == (
        Weekday.MONDAY,
        Weekday.TUESDAY,
        Weekday.WEDNESDAY,
        Weekday.THURSDAY,
        Weekday.FRIDAY,
        Weekday.SATURDAY,
    )
    assert Weekday.SUNDAY not in DEFAULT_TEACHING_WEEKDAYS


@pytest.mark.django_db
def test_setting_up_with_no_weekdays_gives_six_teaching_days(admin_user, batch):
    summary = _set_up(batch, admin_user, generate=False, autoplan=False)

    assert summary["schedules_created"] == 6
    assert summary["weekdays"] == [0, 1, 2, 3, 4, 5]

    days = sorted(BatchSchedule.objects.filter(batch=batch).values_list("weekday", flat=True))
    assert days == [0, 1, 2, 3, 4, 5]
    assert Weekday.SUNDAY not in days


@pytest.mark.django_db
def test_a_different_week_can_be_asked_for(admin_user, batch):
    """Passing a list is how somebody says "not the usual six"."""
    summary = _set_up(
        batch,
        admin_user,
        weekdays=[Weekday.SATURDAY, Weekday.SUNDAY],
        generate=False,
        autoplan=False,
    )

    assert summary["schedules_created"] == 2
    assert sorted(BatchSchedule.objects.filter(batch=batch).values_list("weekday", flat=True)) == [
        5,
        6,
    ]


@pytest.mark.django_db
def test_the_times_and_place_reach_every_day(admin_user, batch):
    _set_up(
        batch,
        admin_user,
        start_time=time(18, 0),
        end_time=time(20, 30),
        location="Lab 2",
        generate=False,
        autoplan=False,
    )

    for schedule in BatchSchedule.objects.filter(batch=batch):
        assert schedule.start_time == time(18, 0)
        assert schedule.end_time == time(20, 30)
        assert schedule.location == "Lab 2"


# ---------------------------------------------------------------------------
# Running it twice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_running_it_twice_does_not_double_the_timetable(admin_user, batch):
    """An operator will click it again. That must cost nothing."""
    first = _set_up(batch, admin_user, generate=False, autoplan=False)
    second = _set_up(batch, admin_user, generate=False, autoplan=False)

    assert first["schedules_created"] == 6
    assert second["schedules_created"] == 0
    assert second["schedules_already_present"] == 6
    assert BatchSchedule.objects.filter(batch=batch).count() == 6


@pytest.mark.django_db
def test_a_day_that_is_already_timetabled_is_left_alone(admin_user, batch, schedule):
    """The existing row is the one classes hang off; replacing it orphans them.

    `schedule` is a Monday slot created by hand at a different time. Setting the
    batch up must not overwrite it — somebody chose that time.
    """
    original_start = schedule.start_time

    summary = _set_up(
        batch,
        admin_user,
        start_time=time(14, 0),
        end_time=time(16, 0),
        generate=False,
        autoplan=False,
    )

    schedule.refresh_from_db()
    assert schedule.start_time == original_start
    assert summary["schedules_already_present"] == 1
    assert summary["schedules_created"] == 5


@pytest.mark.django_db
def test_running_it_twice_does_not_double_the_classes(admin_user, batch):
    _set_up(batch, admin_user, autoplan=False)
    after_first = ClassSession.objects.filter(batch=batch).count()

    second = _set_up(batch, admin_user, autoplan=False)

    assert after_first > 0
    assert ClassSession.objects.filter(batch=batch).count() == after_first
    assert second["sessions"]["created"] == 0


# ---------------------------------------------------------------------------
# The classes, and the curriculum on them
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_classes_are_made_across_the_batch_dates(admin_user, batch):
    summary = _set_up(batch, admin_user, autoplan=False)

    sessions = ClassSession.objects.filter(batch=batch)
    assert summary["sessions"]["created"] == sessions.count()
    assert sessions.exists()
    # Sunday is not a teaching day, so no class may land on one.
    assert not any(s.session_date.weekday() == 6 for s in sessions)


@pytest.mark.django_db
def test_the_curriculum_lands_on_the_classes_in_order(admin_user, batch):
    """The point of doing all three steps together: the batch is ready to teach."""
    summary = _set_up(batch, admin_user)

    assert summary["curriculum"] is not None
    planned = ClassSession.objects.filter(batch=batch, planned_lesson__isnull=False).order_by(
        "session_date", "start_time"
    )
    assert planned.exists()

    positions = [(s.planned_lesson.module.position, s.planned_lesson.position) for s in planned]
    assert positions == sorted(positions)


@pytest.mark.django_db
def test_the_timetable_survives_a_course_with_no_lessons(admin_user, batch):
    """Generating and planning fail differently, so they are separable.

    A batch whose course has nothing published yet should still get its
    timetable and its classes. Losing them because the curriculum is not written
    would be the tail wagging the dog.
    """
    from apps.courses.models import Lesson, PublishStatus

    Lesson.objects.filter(module__course=batch.course).update(status=PublishStatus.DRAFT)

    summary = _set_up(batch, admin_user)

    assert summary["schedules_created"] == 6
    assert summary["sessions"]["created"] > 0
    assert summary["curriculum"]["planned"] == 0


@pytest.mark.django_db
def test_generation_can_be_skipped(admin_user, batch):
    summary = _set_up(batch, admin_user, generate=False)

    assert summary["sessions"] is None
    assert summary["curriculum"] is None
    assert not ClassSession.objects.filter(batch=batch).exists()


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_class_must_end_after_it_starts(admin_user, batch):
    for start, end in ((time(11, 0), time(9, 0)), (time(9, 0), time(9, 0))):
        with pytest.raises(ApplicationError, match="end after"):
            _set_up(batch, admin_user, start_time=start, end_time=end)


@pytest.mark.django_db
def test_an_empty_week_is_refused(admin_user, batch):
    with pytest.raises(ApplicationError, match="at least one teaching day"):
        _set_up(batch, admin_user, weekdays=[])


@pytest.mark.django_db
def test_something_that_is_not_a_day_is_refused(admin_user, batch):
    with pytest.raises(ApplicationError, match="days of the week"):
        _set_up(batch, admin_user, weekdays=[0, 9])


@pytest.mark.django_db
def test_a_trainer_clash_refuses_the_whole_thing(
    admin_user, batch, upcoming_batch, trainer_profile
):
    """One transaction: a clash on day three must not leave two days timetabled.

    The trainer is already teaching another batch at this time, and
    `create_schedule` refuses it. Because the whole setup is atomic, the batch
    is left exactly as it was rather than half-configured — which is the state
    this feature exists to stop people ending up in.
    """
    from apps.batches.services import create_schedule

    upcoming_batch.trainer = trainer_profile
    upcoming_batch.save(update_fields=["trainer"])
    create_schedule(
        batch=upcoming_batch,
        actor=admin_user,
        weekday=Weekday.MONDAY,
        start_time=MORNING[0],
        end_time=MORNING[1],
        trainer=trainer_profile,
    )

    before = BatchSchedule.objects.filter(batch=batch).count()
    with pytest.raises(ScheduleConflictError):
        _set_up(batch, admin_user, trainer=trainer_profile, generate=False, autoplan=False)

    assert BatchSchedule.objects.filter(batch=batch).count() == before


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


def _url(batch):
    return f"/api/v1/batches/{batch.pk}/set-up/"


@pytest.mark.django_db
def test_the_endpoint_sets_a_batch_up_from_two_times(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _url(batch), {"start_time": "09:00", "end_time": "11:00"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["schedules_created"] == 6
    assert response.data["sessions"]["created"] > 0


@pytest.mark.django_db
def test_a_counsellor_may_set_a_batch_up(api_client_no_csrf, counsellor_user, batch):
    """They open batches, so they are the role that most often needs this."""
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        _url(batch), {"start_time": "09:00", "end_time": "11:00"}, format="json"
    )

    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_a_student_may_not(api_client_no_csrf, student_profile, batch):
    api_client_no_csrf.force_login(student_profile.user)

    response = api_client_no_csrf.post(
        _url(batch), {"start_time": "09:00", "end_time": "11:00"}, format="json"
    )

    assert response.status_code in (403, 404)
    assert not BatchSchedule.objects.filter(batch=batch).exists()


@pytest.mark.django_db
def test_a_trainer_may_not_set_up_a_batch_they_do_not_teach(
    api_client_no_csrf, trainer_profile_two, batch
):
    api_client_no_csrf.force_login(trainer_profile_two.user)

    response = api_client_no_csrf.post(
        _url(batch), {"start_time": "09:00", "end_time": "11:00"}, format="json"
    )

    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_the_endpoint_rejects_a_day_outside_the_week(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _url(batch),
        {"start_time": "09:00", "end_time": "11:00", "weekdays": [0, 7]},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_the_endpoint_rejects_an_unknown_field(api_client_no_csrf, admin_user, batch):
    """`StrictSerializer`: a typo is named, not silently ignored."""
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _url(batch),
        {"start_time": "09:00", "end_time": "11:00", "weekdys": [0]},
        format="json",
    )

    assert response.status_code == 400
    assert "weekdys" in str(response.data)


# ---------------------------------------------------------------------------
# The record of it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_setting_a_batch_up_is_audited(admin_user, batch):
    from apps.audit.models import AuditAction, AuditLog

    _set_up(batch, admin_user)

    entry = AuditLog.objects.filter(
        action=AuditAction.BATCH_TIMETABLE_SET, resource_id=str(batch.pk)
    ).first()
    assert entry is not None
    assert entry.context["code"] == batch.code
    assert entry.context["weekdays"] == [0, 1, 2, 3, 4, 5]
    assert entry.context["sessions_created"] > 0


@pytest.mark.django_db
def test_holidays_are_skipped(admin_user, batch):
    """The academic calendar already applies; setting up must not bypass it.

    A term break that produced thirty classes nobody attended would also produce
    thirty empty registers for somebody to explain later.
    """
    from apps.academics.models import AcademicEvent, AcademicEventKind

    today = timezone.localdate()
    AcademicEvent.objects.create(
        name="Diwali break",
        kind=AcademicEventKind.HOLIDAY,
        start_date=today,
        end_date=today + timedelta(days=6),
        created_by=admin_user,
    )

    summary = _set_up(batch, admin_user, autoplan=False)

    assert summary["sessions"]["on_holiday"] > 0
    for session in ClassSession.objects.filter(batch=batch):
        assert not (today <= session.session_date <= today + timedelta(days=6))
