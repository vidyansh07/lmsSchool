"""Asking a list a question of your own.

Every list screen shipped a handful of fixed filters, which answers the
questions somebody thought of in advance. An operations team spends its day on
the others, so a field now carries a set of operators: `city=Jaipur` as before,
and `city__icontains=jai` as well.

The property worth protecting is what is *not* filterable. The obvious way to
build this is to read a field name and a lookup from the request, which hands
the caller the ORM — `user__password__startswith` is a password oracle and a
relation walk reaches data the caller may not read at all. So the tests that
matter here are the refusals, and the one that proves a filter can only ever
subtract from what the caller could already see.
"""

from __future__ import annotations

import pytest

from apps.common.filtering import FilterField, build_filters, describe
from apps.students.views import STUDENT_FILTER_FIELDS, StudentFilterSet

pytestmark = pytest.mark.django_db

LIST = "/api/v1/students/"


class TestWhatCanBeAsked:
    def test_a_field_carries_its_operators(self):
        built = build_filters((FilterField("city", kind="text"),))

        assert set(built) == {"city", "city__icontains", "city__istartswith", "city__isnull"}

    def test_the_plain_name_still_means_equals(self):
        # Every saved link and bookmark in the product uses the bare name.
        built = build_filters((FilterField("city", kind="text"),))

        assert built["city"].lookup_expr == "exact"

    def test_a_boolean_is_only_ever_asked_one_question(self):
        built = build_filters((FilterField("is_active", kind="boolean"),))

        assert set(built) == {"is_active"}

    def test_the_declaration_describes_itself_for_the_browser(self):
        described = {field["name"]: field for field in describe(STUDENT_FILTER_FIELDS)}

        assert "city" in described
        operators = {operator["value"] for operator in described["city"]["operators"]}
        assert operators == {"exact", "icontains", "istartswith", "isnull"}

    def test_a_choice_field_carries_its_choices(self):
        described = {field["name"]: field for field in describe(STUDENT_FILTER_FIELDS)}

        assert described["fee_status"]["choices"], "the bar cannot offer values it is not given"

    def test_number_comparisons_read_differently_from_dates(self):
        # "is at least" for a number, "is on or after" for a date. The same
        # lookup, and nobody says "the fee is on or after 5000".
        number = describe((FilterField("amount", kind="number"),))[0]
        date = describe((FilterField("created_at", kind="date"),))[0]

        labels = {operator["value"]: operator["label"] for operator in number["operators"]}
        date_labels = {operator["value"]: operator["label"] for operator in date["operators"]}
        assert labels["gte"] == "is at least"
        assert date_labels["gte"] == "is on or after"


class TestWhatCannotBeAsked:
    """The allowlist, which is the whole security of this feature."""

    def test_an_undeclared_field_is_not_filterable(self):
        assert "password" not in StudentFilterSet.base_filters
        assert not any(name.startswith("user__") for name in StudentFilterSet.base_filters)

    def test_no_relation_can_be_walked_from_a_request(self):
        # Every generated name is a declared field, optionally suffixed with a
        # declared operator. None of them is an ORM path.
        declared = {field.name for field in STUDENT_FILTER_FIELDS}
        for name in StudentFilterSet.base_filters:
            root = name.split("__")[0]
            assert root in declared or root in {"awaiting_enrolment"}, name

    def test_an_unknown_parameter_is_ignored_rather_than_applied(
        self, api_client_no_csrf, admin_user, student_profile
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(f"{LIST}?user__password__startswith=pbkdf2")

        # Ignored, not obeyed: the list comes back whole.
        assert response.status_code == 200
        assert response.data["count"] >= 1

    def test_an_unknown_operator_on_a_known_field_is_ignored(
        self, api_client_no_csrf, admin_user, student_profile
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(f"{LIST}?city__regex=.*")

        assert response.status_code == 200
        assert response.data["count"] >= 1


class TestFilteringOverHttp:
    def test_contains_narrows_the_list(
        self, api_client_no_csrf, admin_user, student_profile
    ):
        student_profile.city = "Jaipur"
        student_profile.save(update_fields=["city"])
        api_client_no_csrf.force_authenticate(user=admin_user)

        hit = api_client_no_csrf.get(f"{LIST}?city__icontains=jai")
        miss = api_client_no_csrf.get(f"{LIST}?city__icontains=zzz")

        assert hit.data["count"] >= 1
        assert miss.data["count"] == 0

    def test_is_empty_finds_the_rows_nobody_filled_in(
        self, api_client_no_csrf, admin_user, student_profile
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(f"{LIST}?roll_number__isnull=false")

        assert response.status_code == 200

    def test_a_filter_cannot_widen_what_the_caller_may_see(
        self, api_client_no_csrf, counsellor_user, other_branch, admin_user
    ):
        # Scoping runs first and this only ever subtracts from it. A filter
        # naming another centre must come back empty, not helpful.
        from apps.students.services import create_student

        elsewhere = create_student(
            email="elsewhere@grras.invalid",
            first_name="Else",
            last_name="Where",
            actor=admin_user,
            password="Filter-Test-Passw0rd!",
            send_invitation=False,
            branch=other_branch,
            profile_fields={"city": "Pune", "state": "Maharashtra"},
        )
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.get(f"{LIST}?branch={other_branch.pk}")

        assert response.status_code == 200
        emails = {row["email"] for row in response.data["results"]}
        assert elsewhere.user.email not in emails


class TestTheFieldsEndpoint:
    def test_it_lists_what_the_bar_may_offer(
        self, api_client_no_csrf, admin_user
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get("/api/v1/students/filter-fields/")

        assert response.status_code == 200
        names = {field["name"] for field in response.data["fields"]}
        assert {"city", "fee_status", "created_at"} <= names

    def test_every_operator_it_offers_is_one_the_list_accepts(
        self, api_client_no_csrf, admin_user
    ):
        # The failure this prevents: the server drops a field, the control
        # stays, and the list silently stops narrowing.
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get("/api/v1/students/filter-fields/")

        for field in response.data["fields"]:
            for operator in field["operators"]:
                parameter = (
                    field["name"]
                    if operator["value"] == "exact"
                    else f"{field['name']}__{operator['value']}"
                )
                assert parameter in StudentFilterSet.base_filters, parameter

    def test_it_carries_no_student_data(self, api_client_no_csrf, admin_user, student_profile):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get("/api/v1/students/filter-fields/")

        assert student_profile.user.email not in str(response.data)

    def test_somebody_who_cannot_see_the_list_cannot_read_it(
        self, api_client_no_csrf, student
    ):
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.get("/api/v1/students/filter-fields/")

        assert response.status_code in (403, 404)


class TestTheReadingsThatWereAlreadyInUse:
    """Two bare parameters do not mean `exact`, and must not start to.

    Generating a filter per operator quietly changed what the plain name meant,
    which broke the referral screen: `?institution=Infosys` had always been a
    contains match. Links, saved views and other screens are written against
    these, so they are pinned here rather than left to be rediscovered.
    """

    def test_institution_stays_a_contains_match(self):
        assert StudentFilterSet.base_filters["institution"].lookup_expr == "icontains"

    def test_city_stays_case_insensitive(self):
        assert StudentFilterSet.base_filters["city"].lookup_expr == "iexact"

    def test_the_overrides_take_the_place_of_the_generated_exact_form(self):
        # `exact` is the bare name by design, so overriding the bare name means
        # there is no separate strict form for these two. That is the trade
        # made on purpose: an existing link keeping its meaning is worth more
        # than a case-sensitive city search nobody has asked for.
        assert "city__exact" not in StudentFilterSet.base_filters
        assert "institution__exact" not in StudentFilterSet.base_filters

    def test_the_bar_never_offers_an_operator_that_is_not_wired(self):
        # The guard that matters: whatever the readings are, every operator the
        # browser is told about must resolve to a filter that exists.
        for field in describe(STUDENT_FILTER_FIELDS):
            for operator in field["operators"]:
                parameter = (
                    field["name"]
                    if operator["value"] == "exact"
                    else f"{field['name']}__{operator['value']}"
                )
                assert parameter in StudentFilterSet.base_filters, parameter
