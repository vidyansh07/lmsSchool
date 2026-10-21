"""One college, one row.

The student record carried the institution as free text from the beginning,
and free text drifts: "Arya College of Engineering", "Arya college" and "ARYA
COLLEGE OF ENGG" are one place and three rows, and no report can add them up.
The seeded data looks tidy only because a seed wrote it.

So it becomes something to pick, with a way to add one from inside the flow
that needed it — because a counsellor who cannot find a college will otherwise
type it into the old free-text box and start the drift again.
"""

from __future__ import annotations

import pytest

from apps.organisation.models import College
from apps.organisation.services import find_or_create_college

pytestmark = pytest.mark.django_db

LIST = "/api/v1/colleges/"


class TestOneCollegeOneRow:
    def test_adding_a_college_records_it(self, admin_user):
        college = find_or_create_college(
            actor=admin_user, name="Arya College of Engineering", city="Jaipur"
        )

        assert college.name == "Arya College of Engineering"
        assert College.objects.count() == 1

    def test_the_same_college_typed_again_is_the_same_row(self, admin_user):
        first = find_or_create_college(actor=admin_user, name="Arya College of Engineering")
        second = find_or_create_college(actor=admin_user, name="arya college of engineering")

        assert first.pk == second.pk
        assert College.objects.count() == 1

    def test_spacing_does_not_make_a_twin(self, admin_user):
        first = find_or_create_college(actor=admin_user, name="Arya  College   of Engineering")
        second = find_or_create_college(actor=admin_user, name="Arya College of Engineering")

        assert first.pk == second.pk

    def test_two_genuinely_different_places_stay_apart(self, admin_user):
        # Deliberately not fuzzy: a system that silently merged these would be
        # worse than one that occasionally holds both.
        find_or_create_college(actor=admin_user, name="Arya College")
        find_or_create_college(actor=admin_user, name="Arya Institute")

        assert College.objects.count() == 2

    def test_a_retired_college_asked_for_again_comes_back(self, admin_user):
        college = find_or_create_college(actor=admin_user, name="Arya College")
        college.is_active = False
        college.save(update_fields=["is_active"])

        again = find_or_create_college(actor=admin_user, name="Arya College")

        assert again.pk == college.pk
        assert again.is_active is True

    def test_an_empty_name_is_refused(self, admin_user):
        from apps.common.exceptions import ApplicationError

        with pytest.raises(ApplicationError):
            find_or_create_college(actor=admin_user, name="   ")


class TestThePicker:
    def test_a_counsellor_reads_the_list(self, api_client_no_csrf, counsellor_user, admin_user):
        find_or_create_college(actor=admin_user, name="Arya College of Engineering")
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.get(LIST)

        assert response.status_code == 200
        assert response.data["count"] == 1

    def test_a_counsellor_adds_one_from_the_registration_flow(
        self, api_client_no_csrf, counsellor_user
    ):
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.post(
            LIST, {"name": "Poornima College", "city": "Jaipur"}, format="json"
        )

        assert response.status_code == 201, response.data
        assert College.objects.filter(name="Poornima College").exists()

    def test_adding_one_that_exists_returns_it_rather_than_failing(
        self, api_client_no_csrf, counsellor_user, admin_user
    ):
        find_or_create_college(actor=admin_user, name="Arya College")
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.post(LIST, {"name": "arya college"}, format="json")

        # 200, not 201: nothing was created, and the caller gets the row they
        # meant rather than a duplicate-name error they cannot act on.
        assert response.status_code == 200
        assert College.objects.count() == 1

    def test_the_list_is_searchable(self, api_client_no_csrf, admin_user):
        find_or_create_college(actor=admin_user, name="Arya College of Engineering")
        find_or_create_college(actor=admin_user, name="Poornima College")
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(f"{LIST}?search=arya")

        assert response.data["count"] == 1

    def test_a_retired_college_is_not_offered(self, api_client_no_csrf, admin_user):
        college = find_or_create_college(actor=admin_user, name="Closed College")
        college.is_active = False
        college.save(update_fields=["is_active"])
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(LIST)

        assert response.data["count"] == 0


class TestWhoMay:
    def test_a_student_cannot_read_the_college_list(self, api_client_no_csrf, student):
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.get(LIST)

        assert response.status_code in (403, 404)

    def test_a_student_cannot_add_a_college(self, api_client_no_csrf, student):
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.post(LIST, {"name": "Made Up"}, format="json")

        assert response.status_code in (403, 404)
        assert College.objects.count() == 0

    def test_an_anonymous_caller_is_refused(self, api_client_no_csrf):
        response = api_client_no_csrf.get(LIST)

        assert response.status_code in (401, 403)


class TestTheFreeTextIsNotThrownAway:
    def test_a_student_may_have_both(self, admin_user, student_profile):
        """The link is what a report groups by; the text is what somebody wrote.

        A thousand real students answered the free-text question, some naming
        an employer rather than a college. Discarding those to make a foreign
        key tidy would be losing data to gain a diagram.
        """
        college = find_or_create_college(actor=admin_user, name="Arya College of Engineering")
        student_profile.college = college
        student_profile.institution = "Arya College of Engg (2021 batch)"
        student_profile.save(update_fields=["college", "institution"])

        student_profile.refresh_from_db()
        assert student_profile.college == college
        assert student_profile.institution == "Arya College of Engg (2021 batch)"
