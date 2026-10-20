"""Transfers through the API: one enrolment, or many at once.

Both go through `transfer_student`, so the old row becomes `transferred` and
points at the new one — the screens used to enrol and cancel, which recorded
every move as a drop-out.
"""

from __future__ import annotations

import pytest

from apps.enrollments.models import Enrollment, EnrollmentStatus

BULK_URL = "/api/v1/enrollments/bulk-transfer/"


def _url(enrollment) -> str:
    return f"/api/v1/enrollments/{enrollment.pk}/transfer/"


@pytest.fixture
def third_enrollment(admin_user, batch):
    from apps.enrollments.services import enrol_student
    from apps.students.services import create_student

    third = create_student(
        email="third@example.test",
        first_name="Third",
        last_name="Learner",
        actor=admin_user,
        password=None,
        send_invitation=False,
    )
    return enrol_student(student=third, batch=batch, actor=admin_user)


@pytest.mark.django_db
def test_a_transfer_keeps_the_journey_in_one_chain(
    api_client_no_csrf, counsellor_user, enrollment, upcoming_batch
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        _url(enrollment),
        {"batch_id": str(upcoming_batch.pk), "reason": "Evening suits their job."},
        format="json",
    )

    assert response.status_code == 201, response.content
    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.TRANSFERRED
    assert str(enrollment.transferred_to_id) == response.json()["id"]
    assert enrollment.status_note == "Evening suits their job."
    assert enrollment.transferred_to.batch_id == upcoming_batch.pk


@pytest.mark.django_db
def test_a_transfer_needs_a_reason(api_client_no_csrf, counsellor_user, enrollment, upcoming_batch):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        _url(enrollment), {"batch_id": str(upcoming_batch.pk), "reason": ""}, format="json"
    )
    assert response.status_code == 400
    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.ACTIVE


@pytest.mark.django_db
def test_a_trainer_cannot_transfer(api_client_no_csrf, trainer_profile, enrollment, upcoming_batch):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _url(enrollment), {"batch_id": str(upcoming_batch.pk), "reason": "x"}, format="json"
    )
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_a_batch_at_another_centre_is_not_found(
    api_client_no_csrf, manager_user, enrollment, other_branch_batch
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _url(enrollment), {"batch_id": str(other_branch_batch.pk), "reason": "x"}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_moving_many_skips_the_ones_that_no_longer_fit(
    api_client_no_csrf,
    counsellor_user,
    enrollment,
    other_enrollment,
    third_enrollment,
    upcoming_batch,
):
    """The target holds two; the third is skipped with the reason, not lost."""
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        BULK_URL,
        {
            "ids": [str(row.pk) for row in (enrollment, other_enrollment, third_enrollment)],
            "batch_id": str(upcoming_batch.pk),
            "reason": "Morning batch merged into evening.",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 3
    assert body["done"] == 2
    assert len(body["skipped"]) == 1
    skipped = Enrollment.objects.get(pk=body["skipped"][0]["id"])
    assert skipped.status == EnrollmentStatus.ACTIVE
    assert Enrollment.objects.filter(batch=upcoming_batch).count() == 2


@pytest.mark.django_db
def test_moving_every_enrolment_the_filter_matches(
    api_client_no_csrf, counsellor_user, enrollment, batch, upcoming_batch
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        BULK_URL,
        {
            "filters": {"batch": str(batch.pk), "search": enrollment.code},
            "batch_id": str(upcoming_batch.pk),
            "reason": "Moving one by search.",
            "is_upgrade": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["done"] == 1
    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.TRANSFERRED
    assert enrollment.is_upgrade is True


@pytest.mark.django_db
def test_an_already_transferred_enrolment_is_skipped_with_the_reason(
    api_client_no_csrf, counsellor_user, enrollment, upcoming_batch, admin_user
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user, note="Left."
    )
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        BULK_URL,
        {"ids": [str(enrollment.pk)], "batch_id": str(upcoming_batch.pk), "reason": "x"},
        format="json",
    )
    assert response.json()["done"] == 0
    assert "cannot be transferred" in response.json()["skipped"][0]["reason"]
