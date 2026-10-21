"""What a student says about themselves.

Everything the profile held was a fact the institute recorded *about* a
student — address, fee status, who referred them. None of it answered the
questions the institute actually needs a person to answer: what do you want to
do, what can you already do, when can you attend.

That gap had costs. A placement officer looking for somebody to put in front of
an employer was guessing from a course code. A batch scheduled at a time most
of its students could not make emptied out in the second week.

So these are self-edited by definition — nobody else can answer "what do you
want to do" — and the tests that matter are the boundaries: a student may write
them and may not write anything else, and what they write must not become a way
to put script into somebody else's screen.
"""

from __future__ import annotations

import pytest

from apps.students.models import StudentProfile

pytestmark = pytest.mark.django_db

ME = "/api/v1/students/me/"


@pytest.fixture
def learner(student_profile):
    return student_profile


def sign_in(client, profile):
    client.force_authenticate(user=profile.user)


class TestAStudentFillingInTheirOwnProfile:
    def test_they_can_say_what_they_want_to_do(self, api_client_no_csrf, learner):
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME,
            {
                "career_goal": "Linux system administrator",
                "about": "Final year student, happiest on a terminal.",
            },
            format="json",
        )

        assert response.status_code == 200, response.data
        learner.refresh_from_db()
        assert learner.career_goal == "Linux system administrator"

    def test_they_can_list_interests_skills_and_languages(
        self, api_client_no_csrf, learner
    ):
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME,
            {
                "interests": ["Linux", "cloud", "cyber security"],
                "skills": ["Bash", "Python"],
                "languages": ["Hindi", "English"],
            },
            format="json",
        )

        assert response.status_code == 200, response.data
        learner.refresh_from_db()
        assert learner.interests == ["Linux", "cloud", "cyber security"]
        assert learner.skills == ["Bash", "Python"]

    def test_they_can_say_when_they_can_attend(self, api_client_no_csrf, learner):
        # The field exists because a batch at the wrong time empties out.
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME, {"preferred_class_time": "evening"}, format="json"
        )

        assert response.status_code == 200, response.data
        learner.refresh_from_db()
        assert learner.preferred_class_time == "evening"

    def test_they_can_say_whether_they_want_a_job(self, api_client_no_csrf, learner):
        # A placement officer should not ring somebody who is not looking, and
        # somebody who is looking should not have to hope they get noticed.
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME, {"open_to_placement": True, "willing_to_relocate": True}, format="json"
        )

        assert response.status_code == 200
        learner.refresh_from_db()
        assert learner.open_to_placement is True

    def test_what_they_wrote_comes_back_on_their_profile(
        self, api_client_no_csrf, learner
    ):
        sign_in(api_client_no_csrf, learner)
        api_client_no_csrf.patch(ME, {"career_goal": "Cloud engineer"}, format="json")

        response = api_client_no_csrf.get(ME)

        assert response.data["career_goal"] == "Cloud engineer"

    def test_an_empty_profile_is_still_a_valid_one(self, api_client_no_csrf, learner):
        # The institute has no business insisting on somebody's LinkedIn.
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.get(ME)

        assert response.status_code == 200
        assert response.data["interests"] == []
        assert response.data["career_goal"] == ""


class TestTheBoundaries:
    def test_a_student_still_cannot_change_their_fee_status(
        self, api_client_no_csrf, learner
    ):
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(ME, {"fee_status": "paid"}, format="json")

        assert response.status_code == 400
        learner.refresh_from_db()
        assert learner.fee_status != "paid"

    def test_a_student_cannot_read_the_internal_notes(self, api_client_no_csrf, learner):
        learner.notes = "Thinking of leaving; do not mention."
        learner.save(update_fields=["notes"])
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.get(ME)

        assert "notes" not in response.data
        assert "do not mention" not in str(response.data)

    def test_one_student_cannot_write_another_students_profile(
        self, api_client_no_csrf, learner, other_student_profile
    ):
        # There is no id in the URL at all: the record comes from the session.
        sign_in(api_client_no_csrf, learner)

        api_client_no_csrf.patch(ME, {"career_goal": "Mine"}, format="json")

        other_student_profile.refresh_from_db()
        assert other_student_profile.career_goal != "Mine"

    def test_a_staff_account_is_refused_rather_than_given_an_empty_profile(
        self, api_client_no_csrf, admin_user
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(ME)

        assert response.status_code == 403

    def test_an_over_long_list_is_a_four_hundred_naming_the_field(
        self, api_client_no_csrf, learner
    ):
        # Enforced at the edge, not by the database: the model's `size` turns
        # this into a 500 with no useful message.
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME, {"interests": [f"topic {n}" for n in range(40)]}, format="json"
        )

        assert response.status_code == 400
        assert "interests" in response.data.get("error", {}).get("details", response.data)

    def test_control_characters_are_refused(self, api_client_no_csrf, learner):
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME, {"career_goal": "Engineer\x00injected"}, format="json"
        )

        assert response.status_code == 400

    def test_a_rubbish_class_time_is_refused(self, api_client_no_csrf, learner):
        sign_in(api_client_no_csrf, learner)

        response = api_client_no_csrf.patch(
            ME, {"preferred_class_time": "whenever"}, format="json"
        )

        assert response.status_code == 400


class TestWhatStaffSee:
    def test_a_counsellor_sees_what_the_student_wrote(
        self, api_client_no_csrf, counsellor_user, learner
    ):
        # The whole point: this is asked for because somebody uses it.
        learner.career_goal = "Linux system administrator"
        learner.open_to_placement = True
        learner.save(update_fields=["career_goal", "open_to_placement"])
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.get(f"/api/v1/students/{learner.pk}/")

        assert response.status_code == 200
        assert response.data["career_goal"] == "Linux system administrator"
        assert response.data["open_to_placement"] is True

    def test_the_fields_exist_on_the_model_as_self_editable(self):
        # Pinned: moving one of these out of the self-editable set would
        # silently stop a student being able to answer a question only they
        # can answer.
        for field in (
            "about",
            "career_goal",
            "interests",
            "skills",
            "languages",
            "preferred_class_time",
            "open_to_placement",
        ):
            assert field in StudentProfile.SELF_EDITABLE_FIELDS
