"""Daily attendance: bulk marking, scoping, corrections and percentages."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceStatus, attendance_summary
from apps.audit.models import AuditAction, AuditLog
from apps.sessions.models import SessionStatus


@pytest.fixture
def past_session(admin_user, batch, schedule):
    """A class that has already finished, so a register may be taken."""
    from datetime import time, timedelta

    from apps.sessions.services import create_session

    return create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Filesystem basics",
    )


def _register_url(session) -> str:
    return f"/api/v1/sessions/{session.id}/register/"


def _mark(client, session, enrollment, status="present", **extra):
    return client.post(
        _register_url(session),
        {"entries": [{"enrollment_id": str(enrollment.id), "status": status, **extra}]},
        format="json",
    )


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_register_lists_every_enrolled_student_unmarked(
    api_client_no_csrf, trainer_profile, past_session, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(_register_url(past_session)).json()

    assert body["can_mark"] is True
    assert len(body["entries"]) == 2
    assert all(entry["status"] is None for entry in body["entries"])
    # Stable order, so a register does not reshuffle between page loads.
    codes = [entry["student_code"] for entry in body["entries"]]
    assert codes == sorted(codes)


@pytest.mark.django_db
def test_a_whole_register_is_saved_in_one_request(
    api_client_no_csrf, trainer_profile, past_session, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _register_url(past_session),
        {
            "entries": [
                {"enrollment_id": str(enrollment.id), "status": "present"},
                {"enrollment_id": str(other_enrollment.id), "status": "absent", "note": "No show"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json() == {"created": 2, "updated": 0, "corrections": 0}
    assert AttendanceRecord.objects.filter(session=past_session).count() == 2


@pytest.mark.django_db
def test_bulk_marking_costs_a_bounded_number_of_queries(
    api_client_no_csrf,
    trainer_profile,
    past_session,
    enrollment,
    other_enrollment,
    django_assert_max_num_queries,
):
    """A trainer marks a room in one action; the API must not go row by row."""
    api_client_no_csrf.force_login(trainer_profile.user)
    with django_assert_max_num_queries(20):
        api_client_no_csrf.post(
            _register_url(past_session),
            {
                "entries": [
                    {"enrollment_id": str(enrollment.id), "status": "present"},
                    {"enrollment_id": str(other_enrollment.id), "status": "late"},
                ]
            },
            format="json",
        )


@pytest.mark.django_db
def test_taking_the_register_completes_a_finished_class(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment)

    past_session.refresh_from_db()
    assert past_session.status == SessionStatus.COMPLETED
    assert past_session.attendance_taken_at is not None
    assert past_session.attendance_taken_by == trainer_profile.user


@pytest.mark.django_db
def test_a_bad_row_rejects_the_whole_register(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    """Nothing is written until everything validates — no half-saved register."""
    import uuid

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _register_url(past_session),
        {
            "entries": [
                {"enrollment_id": str(enrollment.id), "status": "present"},
                {"enrollment_id": str(uuid.uuid4()), "status": "present"},
            ]
        },
        format="json",
    )
    assert response.status_code == 400
    assert AttendanceRecord.objects.filter(session=past_session).count() == 0


@pytest.mark.django_db
def test_a_student_from_another_batch_cannot_be_marked(
    api_client_no_csrf,
    trainer_profile,
    past_session,
    admin_user,
    upcoming_batch,
    other_student_profile,
):
    from apps.enrollments.services import enrol_student

    outsider = enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _mark(api_client_no_csrf, past_session, outsider)

    assert response.status_code == 400
    assert "not on this class's register" in str(response.json()["error"]["details"])


@pytest.mark.django_db
def test_a_duplicate_student_in_one_register_is_refused(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _register_url(past_session),
        {
            "entries": [
                {"enrollment_id": str(enrollment.id), "status": "present"},
                {"enrollment_id": str(enrollment.id), "status": "absent"},
            ]
        },
        format="json",
    )
    assert response.status_code == 400
    assert "Duplicate" in str(response.json()["error"]["details"])


@pytest.mark.django_db
def test_attendance_cannot_be_taken_for_a_cancelled_class(
    api_client_no_csrf, admin_user, trainer_profile, past_session, enrollment
):
    from apps.sessions.services import set_session_status

    set_session_status(session=past_session, target=SessionStatus.CANCELLED, actor=admin_user)
    api_client_no_csrf.force_login(trainer_profile.user)

    response = _mark(api_client_no_csrf, past_session, enrollment)
    assert response.status_code == 400
    assert "nobody could attend" in str(response.json()["error"]["details"])


@pytest.mark.django_db
def test_attendance_cannot_be_taken_before_the_class_starts(
    api_client_no_csrf, admin_user, trainer_profile, batch, enrollment
):
    from datetime import time, timedelta

    from apps.sessions.services import create_session

    future = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() + timedelta(days=3),
        start_time=time(9, 0),
        end_time=time(11, 0),
    )
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _mark(api_client_no_csrf, future, enrollment)
    assert response.status_code == 400
    assert "not started" in str(response.json()["error"]["details"])


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_re_marking_records_a_correction(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="absent")
    response = _mark(api_client_no_csrf, past_session, enrollment, status="present")

    assert response.json() == {"created": 0, "updated": 1, "corrections": 1}
    row = AttendanceRecord.objects.get(session=past_session, enrollment=enrollment)
    assert row.status == AttendanceStatus.PRESENT
    # The previous value survives, so a dispute has an answer.
    assert row.previous_status == AttendanceStatus.ABSENT
    assert row.was_corrected is True


@pytest.mark.django_db
def test_a_single_mark_can_be_corrected_with_a_reason(
    api_client_no_csrf, admin_user, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="absent")
    row = AttendanceRecord.objects.get(session=past_session, enrollment=enrollment)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/attendance/{row.id}/correct/",
        {"status": "excused", "reason": "Medical certificate provided"},
        format="json",
    )
    assert response.status_code == 200

    row.refresh_from_db()
    assert row.status == AttendanceStatus.EXCUSED
    assert row.previous_status == AttendanceStatus.ABSENT
    assert row.correction_reason == "Medical certificate provided"


@pytest.mark.django_db
def test_marking_and_correcting_are_audited(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="present")
    assert AuditLog.objects.filter(action=AuditAction.ATTENDANCE_MARKED).exists()

    _mark(api_client_no_csrf, past_session, enrollment, status="absent")
    entry = AuditLog.objects.filter(action=AuditAction.ATTENDANCE_CORRECTED).first()
    assert entry is not None
    assert entry.context["corrections"] == 1


# ---------------------------------------------------------------------------
# Scoping — §4.2's core rule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_cannot_mark_an_unrelated_batches_class(
    api_client_no_csrf, admin_user, trainer_profile, upcoming_batch, other_student_profile
):
    from datetime import time, timedelta

    from apps.batches.models import Batch, BatchStatus
    from apps.enrollments.services import enrol_student
    from apps.sessions.services import create_session

    Batch.objects.filter(pk=upcoming_batch.pk).update(
        status=BatchStatus.ACTIVE, start_date=timezone.localdate() - timedelta(days=10)
    )
    upcoming_batch.refresh_from_db()

    outsider = enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)
    session = create_session(
        batch=upcoming_batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(18, 0),
        end_time=time(20, 0),
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(_register_url(session)).status_code == 404
    assert _mark(api_client_no_csrf, session, outsider).status_code == 404
    assert AttendanceRecord.objects.filter(session=session).count() == 0


@pytest.mark.django_db
def test_a_student_cannot_mark_attendance(api_client_no_csrf, past_session, enrollment):
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(_register_url(past_session)).status_code == 403
    assert _mark(api_client_no_csrf, past_session, enrollment).status_code == 403


@pytest.mark.django_db
def test_a_student_cannot_correct_their_own_mark(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="absent")
    row = AttendanceRecord.objects.get(session=past_session, enrollment=enrollment)

    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.post(
        f"/api/v1/attendance/{row.id}/correct/",
        {"status": "present", "reason": "I was there honest"},
        format="json",
    )
    assert response.status_code == 403
    row.refresh_from_db()
    assert row.status == AttendanceStatus.ABSENT


@pytest.mark.django_db
def test_a_student_cannot_read_another_students_attendance(
    api_client_no_csrf, trainer_profile, past_session, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(
        _register_url(past_session),
        {
            "entries": [
                {"enrollment_id": str(enrollment.id), "status": "present"},
                {"enrollment_id": str(other_enrollment.id), "status": "absent"},
            ]
        },
        format="json",
    )

    api_client_no_csrf.force_login(enrollment.student.user)
    assert (
        api_client_no_csrf.get(f"/api/v1/enrollments/{enrollment.id}/attendance/").status_code
        == 200
    )
    assert (
        api_client_no_csrf.get(f"/api/v1/enrollments/{other_enrollment.id}/attendance/").status_code
        == 404
    )


@pytest.mark.django_db
def test_a_student_never_sees_who_marked_them(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="present")

    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(
        f"/api/v1/enrollments/{enrollment.id}/attendance/"
    ).content.decode()
    assert trainer_profile.user.email not in body
    assert "marked_by_email" not in body


@pytest.mark.django_db
def test_anonymous_callers_are_refused(api_client_no_csrf, past_session, enrollment):
    for url in (
        _register_url(past_session),
        f"/api/v1/sessions/{past_session.id}/attendance/",
        "/api/v1/attendance/mine/",
        f"/api/v1/enrollments/{enrollment.id}/attendance/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


# ---------------------------------------------------------------------------
# Percentages
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_late_counts_as_attended_and_excused_leaves_the_denominator(admin_user, batch, enrollment):
    """A student excused for half a term must not be punished for it."""
    from datetime import time, timedelta

    from apps.sessions.services import create_session

    statuses = ["present", "late", "absent", "excused"]
    for index, status in enumerate(statuses):
        session = create_session(
            batch=batch,
            actor=admin_user,
            session_date=timezone.localdate() - timedelta(days=index + 1),
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        AttendanceRecord.objects.create(
            session=session, enrollment=enrollment, status=status, marked_by=admin_user
        )

    summary = attendance_summary(enrollment)
    # Excused is excluded, so the denominator is 3 not 4; present + late = 2.
    assert summary["total_sessions"] == 3
    assert summary["attended"] == 2
    assert summary["excused"] == 1
    assert summary["percentage"] == 67


@pytest.mark.django_db
def test_percentage_is_null_with_no_countable_sessions(enrollment):
    """Zero classes is not zero per cent — it is no answer yet."""
    assert attendance_summary(enrollment)["percentage"] is None


@pytest.mark.django_db
def test_a_student_sees_their_own_attendance_and_percentage(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    _mark(api_client_no_csrf, past_session, enrollment, status="present")

    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get("/api/v1/attendance/mine/").json()

    assert len(body) >= 1
    entry = next(row for row in body if row["batch_code"] == past_session.batch.code)
    assert entry["summary"]["percentage"] == 100
    assert entry["records"][0]["status"] == "present"
    assert entry["records"][0]["topic"] == "Filesystem basics"
