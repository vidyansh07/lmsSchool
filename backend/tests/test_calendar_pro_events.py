"""The event settings the reference CRM's Calendar Pro puts on an event type.

Four of its settings had no equivalent here, and two of them are rules rather
than labels:

* **Check conflict** — one person cannot be booked twice over the same
  minutes for this kind of work. Per type, because two follow-up calls
  overlapping on a busy morning is normal and two mock interviews with one
  trainer at four o'clock is a mistake.
* **Open completed event** — whether a completed one can be opened again.
  On by default here, unlike the reference product, because reopening is
  behaviour trainers already rely on; a type where "done" must mean done
  turns it off.

The other two (invite the organiser, invite the owner) are recorded
settings that the Add Event drawer reads; nothing is emailed from here yet,
and the screen says so rather than implying an invitation went out.

Who created and last changed a type is listed on the catalog screen, so it
is tested here too — including that a seeded row says it was seeded rather
than naming whoever ran the migration.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.exceptions import ApplicationError, ConflictError
from apps.work import services
from apps.work.models import Activity, ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _make_type(**overrides) -> ActivityType:
    defaults = {
        "slug": f"event-{ActivityType.objects.count()}",
        "name": "Mock Interview",
        "category": "mentoring",
        "allowed_creator_roles": ["manager", "trainer"],
        "allowed_assignee_roles": ["trainer"],
        "default_duration_minutes": 60,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _at(hour: int):
    """A fixed hour today, so two bookings in one test really do overlap."""
    return timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Check conflict
# ---------------------------------------------------------------------------


def test_a_clash_is_refused_for_a_type_that_checks(
    admin_user, student_profile, trainer_profile, enrollment
):
    kind = _make_type(check_conflict=True)
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
        title="Mock interview with Ravi",
    )

    with pytest.raises(ConflictError) as refused:
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=kind,
            enrollment=enrollment,
            assigned_to=trainer_profile.user,
            planned_at=_at(16) + timedelta(minutes=30),
        )
    # The sentence names what is already there, which is the thing the
    # counsellor needs in order to move it.
    assert "Mock interview with Ravi" in str(refused.value.detail)
    assert Activity.objects.filter(activity_type=kind).count() == 1


def test_a_booking_after_the_first_one_ends_is_fine(
    admin_user, student_profile, trainer_profile, enrollment
):
    kind = _make_type(check_conflict=True, default_duration_minutes=30)
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
    )
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16) + timedelta(minutes=30),
    )
    assert Activity.objects.filter(activity_type=kind).count() == 2


def test_a_type_with_no_duration_still_guards_the_same_slot(
    admin_user, student_profile, trainer_profile, enrollment
):
    """Treated as taking a minute. A zero-length window overlaps nothing, and
    the setting would quietly do nothing at all."""
    kind = _make_type(check_conflict=True, default_duration_minutes=None)
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
    )
    with pytest.raises(ConflictError):
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=kind,
            enrollment=enrollment,
            assigned_to=trainer_profile.user,
            planned_at=_at(16),
        )


def test_a_cancelled_one_does_not_block_the_slot(
    admin_user, student_profile, trainer_profile, enrollment
):
    kind = _make_type(check_conflict=True)
    first = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
    )
    Activity.objects.filter(pk=first.pk).update(status=ActivityStatus.CANCELLED)

    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
    )
    assert Activity.objects.filter(activity_type=kind).count() == 2


def test_another_persons_slot_is_their_own(
    admin_user, student_profile, trainer_profile, enrollment
):
    """The clash is one person's diary, not the institute's."""
    kind = _make_type(check_conflict=True, allowed_assignee_roles=["trainer", "admin"])
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=_at(16),
    )
    services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=admin_user,
        planned_at=_at(16),
    )
    assert Activity.objects.filter(activity_type=kind).count() == 2


def test_a_type_that_does_not_check_allows_the_overlap(
    admin_user, student_profile, trainer_profile, enrollment
):
    """Two follow-up calls at once is a busy morning, not an error."""
    kind = _make_type(check_conflict=False)
    for _ in range(2):
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=kind,
            enrollment=enrollment,
            assigned_to=trainer_profile.user,
            planned_at=_at(16),
        )
    assert Activity.objects.filter(activity_type=kind).count() == 2


# ---------------------------------------------------------------------------
# Open completed event
# ---------------------------------------------------------------------------


def test_a_type_can_refuse_to_reopen_a_completed_one(
    admin_user, student_profile, trainer_profile, enrollment
):
    kind = _make_type(reopen_allowed=False)
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    Activity.objects.filter(pk=activity.pk).update(status=ActivityStatus.COMPLETED)
    activity.refresh_from_db()

    with pytest.raises(ApplicationError) as refused:
        services.transition_activity(
            actor=admin_user,
            activity=activity,
            to_status=ActivityStatus.REOPENED,
            note="Trainer asked for another go.",
        )
    assert "cannot be opened again" in str(refused.value.detail)
    activity.refresh_from_db()
    assert activity.status == ActivityStatus.COMPLETED


def test_reopening_is_allowed_by_default(admin_user, student_profile, trainer_profile, enrollment):
    kind = _make_type()
    assert kind.reopen_allowed is True
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    Activity.objects.filter(pk=activity.pk).update(status=ActivityStatus.COMPLETED)
    activity.refresh_from_db()

    reopened = services.transition_activity(
        actor=admin_user,
        activity=activity,
        to_status=ActivityStatus.REOPENED,
        note="Trainer asked for another go.",
    )
    assert reopened.status == ActivityStatus.REOPENED


def test_a_missed_one_can_always_be_reopened(
    admin_user, student_profile, trainer_profile, enrollment
):
    """Undoing a mistake is never the thing to forbid, whatever the type says
    about completed ones."""
    kind = _make_type(reopen_allowed=False)
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    Activity.objects.filter(pk=activity.pk).update(status=ActivityStatus.MISSED)
    activity.refresh_from_db()

    reopened = services.transition_activity(
        actor=admin_user,
        activity=activity,
        to_status=ActivityStatus.REOPENED,
        note="Marked missed by mistake.",
    )
    assert reopened.status == ActivityStatus.REOPENED


# ---------------------------------------------------------------------------
# The catalog screen's columns
# ---------------------------------------------------------------------------


def test_the_api_records_and_reports_who_set_the_event_up(api_client_no_csrf, admin_user):
    client = _client(admin_user)
    created = client.post(
        "/api/v1/activity-types/",
        {
            "slug": "technical-talk",
            "name": "Technical Talk with Trainer",
            "category": "mentoring",
            "default_duration_minutes": 5,
            "check_conflict": True,
            "invite_organiser": True,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["check_conflict"] is True
    assert body["invite_organiser"] is True
    assert body["created_by_name"] == admin_user.get_full_name()
    assert body["updated_by_name"] == admin_user.get_full_name()


def test_the_person_who_changed_it_last_is_the_one_listed(
    api_client_no_csrf, admin_user, unbounded_superadmin
):
    _client(admin_user).post(
        "/api/v1/activity-types/",
        {"slug": "center-visit", "name": "Center Visit", "category": "mentoring"},
        format="json",
    )
    changed = _client(unbounded_superadmin).patch(
        "/api/v1/activity-types/center-visit/",
        {"status": "disabled"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    assert changed.json()["created_by_name"] == admin_user.get_full_name()
    assert changed.json()["updated_by_name"] == unbounded_superadmin.get_full_name()


def test_a_seeded_event_says_it_was_seeded_rather_than_naming_a_migration(
    api_client_no_csrf, admin_user
):
    seeded = ActivityType.objects.filter(is_system=True).first()
    assert seeded is not None, "the catalog migration seeds these"
    rows = _client(admin_user).get("/api/v1/activity-types/").json()["results"]
    row = next(item for item in rows if item["slug"] == seeded.slug)
    assert row["created_by_name"] == "Seeded with the catalog"


# ---------------------------------------------------------------------------
# The reminder the Add Event drawer sets
# ---------------------------------------------------------------------------


def test_an_event_can_carry_its_own_reminder(
    admin_user, student_profile, trainer_profile, enrollment
):
    """The drawer offers "5 minutes before" per event. Null falls back to the
    type's; 0 is this one event saying "no reminder", which a type-level
    default cannot say on its behalf."""
    from apps.notifications.models import Notification, NotificationKind

    kind = _make_type(reminder_minutes_before=60)
    soon = timezone.now() + timedelta(minutes=5)

    own = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=soon,
        due_at=soon,
        reminder_minutes_before=5,
        title="Reminds in five",
    )
    Activity.objects.filter(pk=own.pk).update(status=ActivityStatus.ASSIGNED)

    silent = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=soon,
        due_at=soon,
        reminder_minutes_before=0,
        title="Reminds never",
    )
    Activity.objects.filter(pk=silent.pk).update(status=ActivityStatus.ASSIGNED)

    assert services.send_activity_reminders() == 1
    reminded = Notification.objects.filter(
        recipient=trainer_profile.user, kind=NotificationKind.ACTIVITY_REMINDER
    )
    assert [note.title for note in reminded] == ["Reminder: Reminds in five"]


def test_an_event_takes_its_types_duration_unless_told_otherwise(
    admin_user, student_profile, trainer_profile, enrollment
):
    kind = _make_type(default_duration_minutes=45)
    default = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    assert default.duration_minutes == 45

    longer = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=kind,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        duration_minutes=90,
    )
    assert longer.duration_minutes == 90
