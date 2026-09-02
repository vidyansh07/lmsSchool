"""Phase 3 security tests.

Every test drives the API directly. The UI is not the control — hiding a button
proves nothing about what an HTTP client can do.
"""

from __future__ import annotations

import uuid

import pytest

from apps.enrollments.models import Enrollment, EnrollmentStatus

BATCHES_URL = "/api/v1/batches/"
ENROLLMENTS_URL = "/api/v1/enrollments/"


# ---------------------------------------------------------------------------
# A student cannot enrol anybody
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_enrol_themselves(api_client_no_csrf, student_profile, upcoming_batch):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        ENROLLMENTS_URL,
        {"student_id": str(student_profile.id), "batch_id": str(upcoming_batch.id)},
        format="json",
    )
    assert response.status_code == 403
    assert not Enrollment.objects.filter(student=student_profile, batch=upcoming_batch).exists()


@pytest.mark.django_db
def test_a_student_cannot_enrol_another_student(
    api_client_no_csrf, student_profile, other_student_profile, upcoming_batch
):
    """The named §16 attack."""
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        ENROLLMENTS_URL,
        {"student_id": str(other_student_profile.id), "batch_id": str(upcoming_batch.id)},
        format="json",
    )
    assert response.status_code == 403
    assert not Enrollment.objects.filter(student=other_student_profile).exists()


@pytest.mark.django_db
def test_a_trainer_cannot_enrol_students(api_client_no_csrf, trainer, student_profile, batch):
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.post(
        ENROLLMENTS_URL,
        {"student_id": str(student_profile.id), "batch_id": str(batch.id)},
        format="json",
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# A student cannot see another student's enrolment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_read_another_students_enrolment(
    api_client_no_csrf, student_profile, other_student_profile, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(student_profile.user)

    mine = api_client_no_csrf.get(f"{ENROLLMENTS_URL}{enrollment.id}/")
    theirs = api_client_no_csrf.get(f"{ENROLLMENTS_URL}{other_enrollment.id}/")

    assert mine.status_code == 200
    assert theirs.status_code == 404
    assert other_student_profile.student_id not in theirs.content.decode()


@pytest.mark.django_db
def test_the_enrolment_list_shows_a_student_only_their_own(
    api_client_no_csrf, student_profile, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(ENROLLMENTS_URL).json()
    assert body["count"] == 1
    assert body["results"][0]["code"] == enrollment.code


@pytest.mark.django_db
def test_a_student_never_sees_the_administrative_status_note(
    api_client_no_csrf, admin_user, enrollment
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment,
        target=EnrollmentStatus.SUSPENDED,
        actor=admin_user,
        note="Internal: fees outstanding since March",
    )
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(f"{ENROLLMENTS_URL}{enrollment.id}/").content.decode()
    assert "fees outstanding" not in body
    assert "status_note" not in body


@pytest.mark.django_db
def test_a_student_cannot_change_their_own_enrolment_status(
    api_client_no_csrf, enrollment, admin_user
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.SUSPENDED, actor=admin_user, note="Absent"
    )

    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.post(
        f"{ENROLLMENTS_URL}{enrollment.id}/status/", {"status": "active"}
    )
    assert response.status_code == 403

    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.SUSPENDED


# ---------------------------------------------------------------------------
# Trainers are scoped to their own batches
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_cannot_see_an_unrelated_batch(
    api_client_no_csrf, trainer_profile, batch, upcoming_batch
):
    """`upcoming_batch` belongs to a different trainer."""
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").status_code == 200
    assert api_client_no_csrf.get(f"{BATCHES_URL}{upcoming_batch.id}/").status_code == 404

    listing = api_client_no_csrf.get(BATCHES_URL).json()
    assert listing["count"] == 1
    assert listing["results"][0]["code"] == batch.code


@pytest.mark.django_db
def test_a_trainer_cannot_manage_an_unrelated_batch(
    api_client_no_csrf, trainer_profile, upcoming_batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    for method, url, payload in (
        ("patch", f"{BATCHES_URL}{upcoming_batch.id}/", {"name": "Hijacked"}),
        ("post", f"{BATCHES_URL}{upcoming_batch.id}/status/", {"status": "active"}),
        (
            "post",
            f"{BATCHES_URL}{upcoming_batch.id}/schedules/",
            {"weekday": 0, "start_time": "09:00", "end_time": "10:00"},
        ),
    ):
        response = getattr(api_client_no_csrf, method)(url, payload, format="json")
        assert response.status_code == 404, url

    upcoming_batch.refresh_from_db()
    assert upcoming_batch.name != "Hijacked"


@pytest.mark.django_db
def test_a_trainer_cannot_manage_even_their_own_batch(api_client_no_csrf, trainer_profile, batch):
    """Viewing is not managing.

    A trainer sees their batch, but editing it — capacity, dates, status — is an
    institutional decision, so the capability is not theirs.
    """
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").status_code == 200

    response = api_client_no_csrf.patch(
        f"{BATCHES_URL}{batch.id}/", {"capacity": 500}, format="json"
    )
    assert response.status_code == 403
    batch.refresh_from_db()
    assert batch.capacity != 500


@pytest.mark.django_db
def test_a_trainer_cannot_assign_themselves_to_a_batch(
    api_client_no_csrf, trainer_profile, upcoming_batch
):
    """The named §16 attack: self-assignment to an arbitrary batch."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"{BATCHES_URL}{upcoming_batch.id}/trainer/",
        {"trainer_id": str(trainer_profile.id)},
        format="json",
    )
    assert response.status_code == 404

    upcoming_batch.refresh_from_db()
    assert upcoming_batch.trainer_id != trainer_profile.pk


@pytest.mark.django_db
def test_a_trainer_sees_the_roster_of_their_own_batch_only(
    api_client_no_csrf, trainer_profile, batch, upcoming_batch, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    mine = api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/roster/")
    assert mine.status_code == 200
    assert len(mine.json()) == 1

    assert api_client_no_csrf.get(f"{BATCHES_URL}{upcoming_batch.id}/roster/").status_code == 404


@pytest.mark.django_db
def test_a_student_cannot_see_a_batch_roster(api_client_no_csrf, enrollment, batch):
    """A classmate list is other people's personal data."""
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").status_code == 200
    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/roster/").status_code == 403


@pytest.mark.django_db
def test_a_student_sees_only_the_batches_they_are_on(
    api_client_no_csrf, enrollment, batch, upcoming_batch
):
    api_client_no_csrf.force_login(enrollment.student.user)
    body = api_client_no_csrf.get(BATCHES_URL).json()
    assert body["count"] == 1
    assert body["results"][0]["code"] == batch.code
    assert api_client_no_csrf.get(f"{BATCHES_URL}{upcoming_batch.id}/").status_code == 404


# ---------------------------------------------------------------------------
# Identifier manipulation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_random_identifiers_are_not_found(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    for url in (
        f"{BATCHES_URL}{uuid.uuid4()}/",
        f"{BATCHES_URL}{uuid.uuid4()}/roster/",
        f"{ENROLLMENTS_URL}{uuid.uuid4()}/",
        f"/api/v1/schedules/{uuid.uuid4()}/",
    ):
        response = api_client_no_csrf.get(url)
        assert response.status_code == 404, url
        assert "Traceback" not in response.content.decode()


@pytest.mark.django_db
def test_anonymous_callers_are_refused_everywhere(api_client_no_csrf, batch, enrollment, schedule):
    for url in (
        BATCHES_URL,
        f"{BATCHES_URL}{batch.id}/",
        f"{BATCHES_URL}{batch.id}/roster/",
        ENROLLMENTS_URL,
        f"{ENROLLMENTS_URL}mine/",
        f"/api/v1/schedules/{schedule.id}/",
        "/api/v1/calendar/",
        "/api/v1/dashboard/student/",
        "/api/v1/dashboard/trainer/",
    ):
        response = api_client_no_csrf.get(url)
        assert response.status_code in (401, 403), url


@pytest.mark.django_db
def test_filters_cannot_widen_visibility(api_client_no_csrf, enrollment, upcoming_batch):
    """Paging, sorting or filtering must not reach past the caller's own world."""
    api_client_no_csrf.force_login(enrollment.student.user)
    for query in ("?page_size=100", "?status=upcoming", "?ordering=-start_date", "?trainer="):
        body = api_client_no_csrf.get(f"{BATCHES_URL}{query}").json()
        assert upcoming_batch.code not in str(body), query


@pytest.mark.django_db
def test_a_deactivated_user_loses_everything_immediately(api_client_no_csrf, enrollment, batch):
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").status_code == 200

    enrollment.student.user.is_active = False
    enrollment.student.user.save()

    assert api_client_no_csrf.get(f"{BATCHES_URL}{batch.id}/").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Mass assignment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [{"status": "active"}, {"code": "GRS-B-99999"}, {"trainer": None}, {"created_by": None}],
)
def test_protected_batch_fields_cannot_be_set_through_the_editor(
    api_client_no_csrf, admin_user, batch, payload
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(f"{BATCHES_URL}{batch.id}/", payload, format="json")
    assert response.status_code == 400
    assert set(payload) & set(response.json()["error"]["details"])


@pytest.mark.django_db
def test_the_enrolment_course_cannot_be_supplied_by_the_client(
    api_client_no_csrf, admin_user, student_profile, batch, draft_course
):
    """The course is derived from the batch, so it cannot be pointed elsewhere."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        ENROLLMENTS_URL,
        {
            "student_id": str(student_profile.id),
            "batch_id": str(batch.id),
            "course_id": str(draft_course.id),
        },
        format="json",
    )
    assert response.status_code == 400
    assert "course_id" in response.json()["error"]["details"]
