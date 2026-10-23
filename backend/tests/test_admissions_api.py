"""`/api/v1/admissions/` — recording, reading and cancelling an admission.

The leak questions this answers, which are the ones that would matter:

* a write names three ids (student, year, course) and every one of them is
  resolved out of the caller's own scoped queryset, so naming a student at
  another centre is a 404 rather than an admission filed where nobody can
  see it;
* reading borrows the student's rule exactly — a trainer who may read a
  student may read their admissions, a student may read their own, and
  neither may write one;
* `?student=` narrows an already-scoped list and can never widen it.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.admissions.models import Admission

pytestmark = pytest.mark.django_db

ADMISSIONS = "/api/v1/admissions/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _payload(student, course, **overrides):
    body = {
        "student": str(student.pk),
        "lines": [{"kind": "course", "course": str(course.pk), "unit_fee": "30000"}],
    }
    body.update(overrides)
    return body


def test_an_admission_is_recorded_and_read_back_whole(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    client = _client(counsellor_user)
    created = client.post(
        ADMISSIONS,
        _payload(
            student_profile,
            published_course,
            lines=[
                {"kind": "course", "course": str(published_course.pk), "unit_fee": "30000"},
                {"kind": "additional_fee", "label": "Exam fee", "unit_fee": "2000"},
            ],
            discount_kind="flat",
            discount_value="2000",
            note="Agreed with the father.",
        ),
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()

    assert body["gross_total"] == "32000.00"
    assert body["total_fees"] == "30000.00"
    assert body["student_name"]
    assert [line["kind"] for line in body["lines"]] == ["course", "additional_fee"]
    # The year comes from the current one without being asked for.
    assert body["academic_year"] is not None

    read = client.get(f"{ADMISSIONS}{body['id']}/")
    assert read.status_code == 200
    assert read.json()["id"] == body["id"]


def test_the_current_academic_year_is_used_when_none_is_named(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    from apps.organisation.models import AcademicYear

    current = AcademicYear.objects.current()
    assert current is not None, "the seed migration should have created one"

    created = _client(counsellor_user).post(
        ADMISSIONS, _payload(student_profile, published_course), format="json"
    )
    assert created.json()["academic_year"] == current.name


def test_a_student_at_another_centre_is_a_404_not_an_admission(
    api_client_no_csrf, other_branch_manager, student_profile, published_course
):
    response = _client(other_branch_manager).post(
        ADMISSIONS, _payload(student_profile, published_course), format="json"
    )
    assert response.status_code == 404
    assert Admission.objects.count() == 0


def test_a_student_may_read_their_own_admissions_and_write_none(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    _client(counsellor_user).post(
        ADMISSIONS, _payload(student_profile, published_course), format="json"
    )
    client = _client(student_profile.user)

    listed = client.get(ADMISSIONS)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    refused = client.post(ADMISSIONS, _payload(student_profile, published_course), format="json")
    assert refused.status_code == 403
    assert Admission.objects.count() == 1


def test_another_students_admissions_are_not_in_a_students_list(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile, published_course
):
    staff = _client(counsellor_user)
    staff.post(ADMISSIONS, _payload(student_profile, published_course), format="json")
    staff.post(ADMISSIONS, _payload(other_student_profile, published_course), format="json")

    mine = _client(student_profile.user).get(ADMISSIONS).json()
    assert mine["count"] == 1
    assert mine["results"][0]["student_id"] == str(student_profile.pk)

    # Naming the other student narrows an already-scoped list; it cannot widen it.
    asked = _client(student_profile.user).get(
        ADMISSIONS, {"student": str(other_student_profile.pk)}
    )
    assert asked.json()["count"] == 0


def test_another_centres_manager_sees_none_of_this_centres_admissions(
    api_client_no_csrf, counsellor_user, student_profile, published_course, other_branch_manager
):
    created = _client(counsellor_user).post(
        ADMISSIONS, _payload(student_profile, published_course), format="json"
    )
    admission_id = created.json()["id"]
    client = _client(other_branch_manager)

    assert client.get(ADMISSIONS).json()["count"] == 0
    assert client.get(f"{ADMISSIONS}{admission_id}/").status_code == 404
    assert (
        client.post(f"{ADMISSIONS}{admission_id}/cancel/", {"reason": "Mine."}, format="json")
    ).status_code == 404


def test_an_admission_is_cancelled_with_a_reason_and_only_once(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    client = _client(counsellor_user)
    admission_id = client.post(
        ADMISSIONS, _payload(student_profile, published_course), format="json"
    ).json()["id"]

    assert client.post(f"{ADMISSIONS}{admission_id}/cancel/", {}, format="json").status_code == 400

    cancelled = client.post(
        f"{ADMISSIONS}{admission_id}/cancel/", {"reason": "Moved city."}, format="json"
    )
    assert cancelled.status_code == 200, cancelled.content
    assert cancelled.json()["is_cancelled"] is True
    assert cancelled.json()["cancellation_reason"] == "Moved city."

    again = client.post(f"{ADMISSIONS}{admission_id}/cancel/", {"reason": "Again."}, format="json")
    assert again.status_code == 400


def test_a_student_cannot_cancel_their_own_admission(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    admission_id = (
        _client(counsellor_user)
        .post(ADMISSIONS, _payload(student_profile, published_course), format="json")
        .json()["id"]
    )

    refused = _client(student_profile.user).post(
        f"{ADMISSIONS}{admission_id}/cancel/", {"reason": "I changed my mind."}, format="json"
    )
    assert refused.status_code == 403
    assert Admission.objects.get(pk=admission_id).status == "active"


def test_an_unknown_field_in_the_request_is_refused_not_dropped(
    api_client_no_csrf, counsellor_user, student_profile, published_course
):
    response = _client(counsellor_user).post(
        ADMISSIONS,
        _payload(student_profile, published_course, branch="whatever"),
        format="json",
    )
    assert response.status_code == 400


def test_an_admission_with_no_line_is_refused(api_client_no_csrf, counsellor_user, student_profile):
    response = _client(counsellor_user).post(
        ADMISSIONS, {"student": str(student_profile.pk), "lines": []}, format="json"
    )
    assert response.status_code == 400
    assert Admission.objects.count() == 0


def test_admissions_can_be_narrowed_to_one_course_and_one_status(
    api_client_no_csrf, counsellor_user, student_profile, published_course, category, admin_user
):
    from apps.courses import services as course_services

    other = course_services.create_course(
        actor=admin_user,
        title="Linux",
        category=category,
        short_description="A course.",
        description="Full description.",
        learning_objectives=["Learn it"],
    )
    client = _client(counsellor_user)
    client.post(ADMISSIONS, _payload(student_profile, published_course), format="json")
    second = client.post(ADMISSIONS, _payload(student_profile, other), format="json").json()
    client.post(f"{ADMISSIONS}{second['id']}/cancel/", {"reason": "Moved."}, format="json")

    by_course = client.get(ADMISSIONS, {"course": str(other.pk)}).json()
    assert [row["id"] for row in by_course["results"]] == [second["id"]]

    live = client.get(ADMISSIONS, {"status": "active"}).json()
    assert second["id"] not in [row["id"] for row in live["results"]]
