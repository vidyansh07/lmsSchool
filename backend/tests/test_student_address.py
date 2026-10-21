"""An address somebody can actually find the house from.

The record held address lines, a city, a state and a postcode — a postal
address. It is not how anybody in Jaipur gives directions, so the part a local
would say went into "address line 2" and stopped being searchable, or went
nowhere at all.

Three fields, each because it is used: the **area** is what a person names
first, the **landmark** is what they say when asked where that is, and
**nationality** is asked for on a form the institute has to file.

None of them joins `COMPLETION_FIELDS`. That tuple drives the "% complete"
figure on every student's profile, and adding to it would drop every existing
student's percentage overnight for fields nobody has been asked for yet.
"""

from __future__ import annotations

import pytest

from apps.students.models import StudentProfile

pytestmark = pytest.mark.django_db

ME = "/api/v1/students/me/"


def test_a_student_can_fill_in_the_part_people_navigate_by(
    api_client_no_csrf, student_profile
):
    api_client_no_csrf.force_authenticate(user=student_profile.user)

    response = api_client_no_csrf.patch(
        ME,
        {
            "area": "Vaishali Nagar",
            "landmark": "Opposite the petrol pump",
            "nationality": "Indian",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    student_profile.refresh_from_db()
    assert student_profile.area == "Vaishali Nagar"
    assert student_profile.landmark == "Opposite the petrol pump"


def test_staff_see_the_whole_address(api_client_no_csrf, counsellor_user, student_profile):
    student_profile.area = "Vaishali Nagar"
    student_profile.landmark = "Opposite the petrol pump"
    student_profile.save(update_fields=["area", "landmark"])
    api_client_no_csrf.force_authenticate(user=counsellor_user)

    response = api_client_no_csrf.get(f"/api/v1/students/{student_profile.pk}/")

    assert response.data["area"] == "Vaishali Nagar"
    assert response.data["landmark"] == "Opposite the petrol pump"


def test_an_address_is_searchable_by_area(
    api_client_no_csrf, admin_user, student_profile
):
    # The reason it is its own column rather than a second address line.
    student_profile.area = "Vaishali Nagar"
    student_profile.save(update_fields=["area"])
    api_client_no_csrf.force_authenticate(user=admin_user)

    hit = api_client_no_csrf.get("/api/v1/students/?area__icontains=vaishali")
    miss = api_client_no_csrf.get("/api/v1/students/?area__icontains=nowhere")

    # Both halves: a filter that is ignored returns everything and would pass
    # the first assertion on its own.
    assert hit.data["count"] >= 1
    assert miss.data["count"] == 0


def test_the_completion_percentage_does_not_move(student_profile):
    # Adding optional detail must not tell every existing student their
    # profile got worse overnight.
    for field in ("area", "landmark", "nationality"):
        assert field not in StudentProfile.COMPLETION_FIELDS


def test_all_three_are_the_students_own_to_edit(student_profile):
    for field in ("area", "landmark", "nationality"):
        assert field in StudentProfile.SELF_EDITABLE_FIELDS


def test_control_characters_are_refused(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_authenticate(user=student_profile.user)

    response = api_client_no_csrf.patch(ME, {"area": "Vaishali\x00Nagar"}, format="json")

    assert response.status_code == 400
