"""Class sessions: generation, lifecycle, scoping and trainer history."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.sessions.models import ClassSession, SessionStatus, TrainerAssignmentHistory

SESSIONS_URL = "/api/v1/sessions/"


def _generate(client, batch, **payload):
    return client.post(f"/api/v1/batches/{batch.id}/sessions/generate/", payload, format="json")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sessions_are_generated_from_the_weekly_timetable(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    response = _generate(api_client_no_csrf, batch)

    assert response.status_code == 200
    body = response.json()
    assert body["created"] > 0
    assert body["skipped"] == 0

    sessions = ClassSession.objects.filter(batch=batch)
    assert sessions.count() == body["created"]
    # Every generated class lands on the scheduled weekday, at the scheduled time.
    assert all(row.session_date.weekday() == schedule.weekday for row in sessions)
    assert all(row.start_time == schedule.start_time for row in sessions)


@pytest.mark.django_db
def test_generation_is_idempotent(api_client_no_csrf, admin_user, batch, schedule):
    """An operator running the command twice must not double the timetable."""
    api_client_no_csrf.force_login(admin_user)
    first = _generate(api_client_no_csrf, batch).json()
    second = _generate(api_client_no_csrf, batch).json()

    assert second["created"] == 0
    assert second["skipped"] == first["created"]
    assert ClassSession.objects.filter(batch=batch).count() == first["created"]


@pytest.mark.django_db
def test_generation_is_bounded_by_the_batch_dates(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)

    for session in ClassSession.objects.filter(batch=batch):
        assert batch.start_date <= session.session_date <= batch.end_date


@pytest.mark.django_db
def test_generation_freezes_the_trainer_on_each_class(
    api_client_no_csrf, admin_user, batch, schedule, trainer_profile, trainer_profile_two
):
    """Reassigning a batch must not claim the new trainer taught old classes."""
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    assert ClassSession.objects.filter(batch=batch, trainer=trainer_profile).exists()

    api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/trainer/",
        {"trainer_id": str(trainer_profile_two.id)},
        format="json",
    )

    # Existing classes keep the trainer who actually taught them.
    assert not ClassSession.objects.filter(batch=batch, trainer=trainer_profile_two).exists()
    assert ClassSession.objects.filter(batch=batch, trainer=trainer_profile).exists()


@pytest.mark.django_db
def test_generation_needs_an_active_timetable(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = _generate(api_client_no_csrf, batch)
    assert response.status_code == 400
    assert "timetable" in str(response.json()["error"]["details"])


@pytest.mark.django_db
def test_a_cancelled_batch_generates_nothing(api_client_no_csrf, admin_user, batch, schedule):
    from apps.batches.models import Batch, BatchStatus

    Batch.objects.filter(pk=batch.pk).update(status=BatchStatus.CANCELLED)
    api_client_no_csrf.force_login(admin_user)
    response = _generate(api_client_no_csrf, batch)
    assert response.status_code == 400


@pytest.mark.django_db
def test_generation_is_audited(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    entry = AuditLog.objects.filter(action=AuditAction.SESSIONS_GENERATED).first()
    assert entry is not None
    assert entry.context["batch_code"] == batch.code


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_one_off_class_can_be_added(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/sessions/",
        {
            "session_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "start_time": "15:00",
            "end_time": "17:00",
            "topic": "Catch-up class",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["topic"] == "Catch-up class"
    assert response.json()["duration_minutes"] == 120


@pytest.mark.django_db
def test_a_class_outside_the_batch_dates_is_refused(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/sessions/",
        {
            "session_date": (batch.end_date + timedelta(days=30)).isoformat(),
            "start_time": "09:00",
            "end_time": "10:00",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "session_date" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_a_duplicate_class_slot_is_refused(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    existing = ClassSession.objects.filter(batch=batch).first()

    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/sessions/",
        {
            "session_date": existing.session_date.isoformat(),
            "start_time": existing.start_time.isoformat(),
            "end_time": existing.end_time.isoformat(),
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_class_can_be_completed_and_a_topic_recorded(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    session = ClassSession.objects.filter(batch=batch).first()

    api_client_no_csrf.patch(
        f"{SESSIONS_URL}{session.id}/", {"topic": "Filesystem permissions"}, format="json"
    )
    response = api_client_no_csrf.post(
        f"{SESSIONS_URL}{session.id}/status/", {"status": "completed"}
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.status == SessionStatus.COMPLETED
    assert session.topic == "Filesystem permissions"


@pytest.mark.django_db
def test_a_completed_class_cannot_be_reopened(api_client_no_csrf, admin_user, batch, schedule):
    """Correcting a mistake means correcting the register, not the class."""
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    session = ClassSession.objects.filter(batch=batch).first()

    api_client_no_csrf.post(f"{SESSIONS_URL}{session.id}/status/", {"status": "completed"})
    response = api_client_no_csrf.post(
        f"{SESSIONS_URL}{session.id}/status/", {"status": "scheduled"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_transition"


@pytest.mark.django_db
def test_a_class_can_be_cancelled_with_a_reason(api_client_no_csrf, admin_user, batch, schedule):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    session = ClassSession.objects.filter(batch=batch).first()

    response = api_client_no_csrf.post(
        f"{SESSIONS_URL}{session.id}/status/",
        {"status": "cancelled", "reason": "Trainer unwell"},
    )
    assert response.status_code == 200
    session.refresh_from_db()
    assert session.cancellation_reason == "Trainer unwell"


@pytest.mark.django_db
def test_rescheduling_keeps_the_original_as_a_record(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    original = ClassSession.objects.filter(batch=batch).order_by("session_date").first()
    new_date = original.session_date + timedelta(days=1)

    response = api_client_no_csrf.post(
        f"{SESSIONS_URL}{original.id}/reschedule/",
        {
            "session_date": new_date.isoformat(),
            "start_time": "14:00",
            "end_time": "16:00",
            "reason": "Public holiday",
        },
        format="json",
    )
    assert response.status_code == 201

    original.refresh_from_db()
    assert original.status == SessionStatus.RESCHEDULED
    assert original.rescheduled_to is not None
    assert original.rescheduled_to.session_date == new_date
    # The original row survives, so a register already taken stays attached.
    assert ClassSession.objects.filter(pk=original.pk).exists()


@pytest.mark.django_db
def test_attendance_cannot_be_taken_before_a_class_starts(admin_user, batch, published_course):
    """Marking a register in advance records something that has not happened."""
    from apps.sessions.services import create_session

    future = create_session(
        batch=batch,
        actor=admin_user,
        session_date=batch.end_date,
        start_time=time(9, 0),
        end_time=time(11, 0),
    )
    assert future.can_take_attendance is False


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_sees_only_their_own_classes(
    api_client_no_csrf, admin_user, trainer_profile, batch, schedule, upcoming_batch
):
    from apps.batches.models import Weekday
    from apps.batches.services import create_schedule

    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)

    create_schedule(
        batch=upcoming_batch,
        actor=admin_user,
        weekday=Weekday.FRIDAY,
        start_time=time(18, 0),
        end_time=time(20, 0),
    )
    _generate(api_client_no_csrf, upcoming_batch)

    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(SESSIONS_URL).json()
    assert body["count"] > 0
    assert {row["batch_code"] for row in body["results"]} == {batch.code}


@pytest.mark.django_db
def test_a_student_sees_the_classes_of_batches_they_are_on(
    api_client_no_csrf, admin_user, enrollment, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)

    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(SESSIONS_URL).json()
    assert body["count"] > 0
    assert all(row["batch_code"] == batch.code for row in body["results"])


@pytest.mark.django_db
def test_a_student_cannot_manage_a_class(
    api_client_no_csrf, admin_user, enrollment, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)
    session = ClassSession.objects.filter(batch=batch).first()

    api_client_no_csrf.force_login(enrollment.student.user)
    assert (
        api_client_no_csrf.patch(
            f"{SESSIONS_URL}{session.id}/", {"topic": "Hijacked"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"{SESSIONS_URL}{session.id}/status/", {"status": "cancelled"}
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_trainer_cannot_touch_an_unrelated_batches_class(
    api_client_no_csrf, admin_user, trainer_profile, upcoming_batch
):
    """§4.2's core rule, at the session level."""
    from apps.batches.models import Weekday
    from apps.batches.services import create_schedule

    create_schedule(
        batch=upcoming_batch,
        actor=admin_user,
        weekday=Weekday.FRIDAY,
        start_time=time(18, 0),
        end_time=time(20, 0),
    )
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, upcoming_batch)
    session = ClassSession.objects.filter(batch=upcoming_batch).first()

    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(f"{SESSIONS_URL}{session.id}/").status_code == 404
    assert (
        api_client_no_csrf.patch(
            f"{SESSIONS_URL}{session.id}/", {"topic": "Hijacked"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_anonymous_callers_are_refused(api_client_no_csrf, batch):
    for url in (SESSIONS_URL, f"{SESSIONS_URL}today/", f"/api/v1/batches/{batch.id}/sessions/"):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


# ---------------------------------------------------------------------------
# Trainer history
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reassigning_a_trainer_writes_history(
    api_client_no_csrf, admin_user, batch, trainer_profile, trainer_profile_two
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/trainer/",
        {"trainer_id": str(trainer_profile_two.id)},
        format="json",
    )

    history = TrainerAssignmentHistory.objects.filter(batch=batch).order_by("assigned_at")
    assert history.count() >= 2
    # Exactly one open stint: the current trainer.
    current = history.filter(ended_at__isnull=True)
    assert current.count() == 1
    assert current.first().trainer_id == trainer_profile_two.pk


@pytest.mark.django_db
def test_trainer_history_is_readable_by_staff_only(
    api_client_no_csrf, admin_user, trainer_profile, enrollment, batch
):
    url = f"/api/v1/batches/{batch.id}/trainer-history/"

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(url).status_code == 200

    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(url).status_code == 200

    # A student has no business knowing the staffing history.
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(url).status_code == 403


@pytest.mark.django_db
def test_todays_classes_endpoint_returns_only_today(
    api_client_no_csrf, admin_user, batch, schedule
):
    api_client_no_csrf.force_login(admin_user)
    _generate(api_client_no_csrf, batch)

    today = timezone.localdate()
    body = api_client_no_csrf.get(f"{SESSIONS_URL}today/").json()
    assert all(row["session_date"] == today.isoformat() for row in body)
