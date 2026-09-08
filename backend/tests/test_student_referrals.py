"""Who brought a student in, and where they come from.

A working professional who joins to learn a new skill is also a channel:
colleagues follow, and the institute wants to be able to credit that later.
So a counsellor may record who referred a new student, and may ask "everyone
from Infosys". What is pinned here is what would make the scheme worthless:

- a student cannot name their own referrer (that is how a scheme gets gamed);
- a student cannot refer themselves;
- the referral survives the referrer's record being removed;
- the referrer must be a real student, not any UUID.
"""

from __future__ import annotations

import pytest

from apps.students.models import StudentProfile

STUDENTS_URL = "/api/v1/students/"
ME_URL = "/api/v1/students/me/"


@pytest.mark.django_db
def test_a_counsellor_records_who_referred_a_new_student(
    api_client_no_csrf, counsellor_user, student_profile
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "referred@example.test",
            "first_name": "Ref",
            "profile": {
                "referred_by": str(student_profile.pk),
                "institution": "Infosys",
                "institution_kind": "employer",
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    body = response.json()
    assert body["referred_by"] == str(student_profile.pk)
    assert student_profile.student_id in body["referred_by_label"]


@pytest.mark.django_db
def test_the_referrer_is_counted_on_their_own_record(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(counsellor_user)
    other_student_profile.referred_by = student_profile
    other_student_profile.save(update_fields=["referred_by"])

    body = api_client_no_csrf.get(f"{STUDENTS_URL}{student_profile.pk}/").json()

    assert body["referrals_count"] == 1


@pytest.mark.django_db
def test_everyone_they_referred_is_one_filter_away(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(counsellor_user)
    other_student_profile.referred_by = student_profile
    other_student_profile.save(update_fields=["referred_by"])

    rows = api_client_no_csrf.get(f"{STUDENTS_URL}?referred_by={student_profile.pk}").json()["results"]

    assert [row["id"] for row in rows] == [str(other_student_profile.pk)]


@pytest.mark.django_db
def test_everyone_from_one_employer_is_one_filter_away(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(counsellor_user)
    student_profile.institution = "Infosys Limited"
    student_profile.institution_kind = "employer"
    student_profile.save(update_fields=["institution", "institution_kind"])

    rows = api_client_no_csrf.get(f"{STUDENTS_URL}?institution=infosys").json()["results"]

    assert [row["id"] for row in rows] == [str(student_profile.pk)]
    assert rows[0]["institution_kind"] == "employer"


@pytest.mark.django_db
def test_a_student_cannot_name_their_own_referrer(
    api_client_no_csrf, student_profile, other_student_profile
):
    """The field is refused by name, not silently dropped."""
    api_client_no_csrf.force_login(student_profile.user)

    response = api_client_no_csrf.patch(
        ME_URL, {"referred_by": str(other_student_profile.pk)}, format="json"
    )

    assert response.status_code == 400
    student_profile.refresh_from_db()
    assert student_profile.referred_by is None


@pytest.mark.django_db
def test_a_student_cannot_refer_themselves(api_client_no_csrf, counsellor_user, student_profile):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.patch(
        f"{STUDENTS_URL}{student_profile.pk}/", {"referred_by": str(student_profile.pk)}, format="json"
    )

    assert response.status_code == 400
    assert "referred_by" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_the_referrer_must_be_a_real_student(api_client_no_csrf, counsellor_user):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "ghost@example.test",
            "first_name": "G",
            "profile": {"referred_by": "00000000-0000-0000-0000-000000000000"},
        },
        format="json",
    )

    assert response.status_code == 400
    assert not StudentProfile.objects.filter(user__email="ghost@example.test").exists()


@pytest.mark.django_db
def test_the_referral_survives_the_referrer_being_removed(
    counsellor_user, student_profile, other_student_profile
):
    """Deleting the referrer clears the link rather than taking the referred
    student's record down with it."""
    other_student_profile.referred_by = student_profile
    other_student_profile.save(update_fields=["referred_by"])

    student_profile.delete()

    other_student_profile.refresh_from_db()
    assert other_student_profile.referred_by is None


@pytest.mark.django_db
def test_a_counsellor_can_set_the_referrer_later(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.patch(
        f"{STUDENTS_URL}{other_student_profile.pk}/",
        {"referred_by": str(student_profile.pk)},
        format="json",
    )

    assert response.status_code == 200, response.data
    other_student_profile.refresh_from_db()
    assert other_student_profile.referred_by == student_profile


@pytest.mark.django_db
def test_a_working_professional_is_registered_with_their_designation(
    api_client_no_csrf, counsellor_user
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "pro@example.test",
            "first_name": "Pro",
            "profile": {
                "institution": "Infosys",
                "institution_kind": "employer",
                "job_title": "Senior Systems Engineer",
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.json()["job_title"] == "Senior Systems Engineer"


@pytest.mark.django_db
def test_a_college_student_is_registered_with_their_graduation_year(
    api_client_no_csrf, counsellor_user
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "grad@example.test",
            "first_name": "Grad",
            "profile": {
                "institution": "JECRC University",
                "institution_kind": "college",
                "graduation_year": 2027,
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    body = response.json()
    assert body["graduation_year"] == 2027
    assert body["job_title"] == ""


@pytest.mark.django_db
def test_a_student_may_update_their_own_designation(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    response = api_client_no_csrf.patch(ME_URL, {"job_title": "Team Lead"}, format="json")

    assert response.status_code == 200, response.data
    assert response.json()["job_title"] == "Team Lead"
