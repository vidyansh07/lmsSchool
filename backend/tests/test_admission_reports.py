"""The five admissions reports.

The property that matters across all of them: **the figures at the top are
the figures of the rows underneath**. A report that totals more than it lists
is worse than no report — somebody reads the tile out loud in a meeting and
nobody can find the missing money.

So every test here checks the tiles against the rows rather than against a
number written in the test, and the scoping tests check that a bounded caller
gets both narrowed together.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.admissions import services
from apps.admissions.models import DiscountKind

pytestmark = pytest.mark.django_db

REPORTS = "/api/v1/admissions/reports/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _admit(actor, student, course, fee="30000", **kwargs):
    return services.create_admission(
        actor=actor,
        student=student,
        lines=[{"kind": "course", "course": course, "unit_fee": fee}],
        **kwargs,
    )


def _pay(actor, admission, enrollment, amount, method="cash"):
    from apps.fees import services as fee_services

    services.attach_enrollment(
        actor=actor, line=admission.lines.filter(kind="course").first(), enrollment=enrollment
    )
    plan = fee_services.set_fee_plan(
        enrollment=enrollment, actor=actor, agreed_amount=admission.total_fees
    )
    return fee_services.record_payment(
        plan=plan, actor=actor, amount=amount, method=method, reference="X"
    )


def test_overall_totals_exactly_what_it_lists(
    api_client_no_csrf, admin_user, student_profile, published_course, enrollment
):
    admission = _admit(admin_user, student_profile, published_course, fee="30000")
    _pay(admin_user, admission, enrollment, "1000")

    body = _client(admin_user).get(f"{REPORTS}overall/").json()

    assert body["tiles"]["admissions"] == len(body["rows"])
    assert Decimal(body["tiles"]["total"]) == sum(Decimal(row["total"]) for row in body["rows"])
    assert Decimal(body["tiles"]["received"]) == sum(Decimal(row["paid"]) for row in body["rows"])
    assert Decimal(body["tiles"]["balance"]) == sum(Decimal(row["balance"]) for row in body["rows"])
    assert body["rows"][0]["courses"].startswith(published_course.title)


def test_cleared_is_received_less_uncleared_never_a_third_count(
    api_client_no_csrf, admin_user, student_profile, published_course, enrollment
):
    """A cheque is received the day it is taken and cleared the day the bank
    says so. Counting both as separate money would count it twice."""
    admission = _admit(admin_user, student_profile, published_course, fee="30000")
    _pay(admin_user, admission, enrollment, "5000", method="cheque")

    tiles = _client(admin_user).get(f"{REPORTS}overall/").json()["tiles"]

    assert Decimal(tiles["received"]) == Decimal("5000.00")
    assert Decimal(tiles["uncleared"]) == Decimal("5000.00")
    assert Decimal(tiles["cleared"]) == Decimal("0.00")
    assert Decimal(tiles["received"]) - Decimal(tiles["uncleared"]) == Decimal(tiles["cleared"])


def test_a_cancelled_admission_leaves_the_live_figures_and_lands_in_cancelled(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    admission = _admit(admin_user, student_profile, published_course, fee="20000")
    services.cancel_admission(actor=admin_user, admission=admission, reason="Moved.")

    tiles = _client(admin_user).get(f"{REPORTS}overall/").json()["tiles"]

    assert tiles["admissions"] == 0
    assert Decimal(tiles["total"]) == Decimal("0.00")
    assert Decimal(tiles["cancelled"]) == Decimal("20000.00")


def test_discount_lists_only_what_was_given_away(
    api_client_no_csrf, admin_user, student_profile, other_student_profile, published_course
):
    _admit(admin_user, student_profile, published_course, fee="30000")
    _admit(
        admin_user,
        other_student_profile,
        published_course,
        fee="30000",
        discount_kind=DiscountKind.FLAT,
        discount_value="2000",
    )

    body = _client(admin_user).get(f"{REPORTS}discount/").json()

    # The full-price admission is absent: a page of zeros buries the answer.
    assert body["tiles"]["admissions"] == 1
    assert Decimal(body["tiles"]["discount"]) == Decimal("2000.00")
    assert Decimal(body["rows"][0]["gross_total"]) == Decimal("30000.00")
    assert Decimal(body["rows"][0]["total"]) == Decimal("28000.00")


def test_a_percentage_discount_reports_both_the_rate_and_the_rupees(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    _admit(
        admin_user,
        student_profile,
        published_course,
        fee="30000",
        discount_kind=DiscountKind.PERCENT,
        discount_value="10",
    )
    row = _client(admin_user).get(f"{REPORTS}discount/").json()["rows"][0]
    assert row["discount_kind"] == "percent"
    assert Decimal(row["discount_percent"]) == Decimal("10.00")
    assert Decimal(row["discount"]) == Decimal("3000.00")


def test_expiry_lists_the_seats_that_end_and_leaves_out_the_ones_that_do_not(
    api_client_no_csrf, admin_user, student_profile, published_course, enrollment
):
    admission = _admit(admin_user, student_profile, published_course)
    services.attach_enrollment(actor=admin_user, line=admission.lines.get(), enrollment=enrollment)

    # No end date: "no expiry" is not an expiry.
    enrollment.access_end_date = None
    enrollment.save(update_fields=["access_end_date"])
    assert _client(admin_user).get(f"{REPORTS}expiry/").json()["rows"] == []

    enrollment.access_end_date = date.today() + timedelta(days=10)
    enrollment.save(update_fields=["access_end_date"])
    body = _client(admin_user).get(f"{REPORTS}expiry/").json()

    assert body["tiles"]["enrolments"] == 1
    assert body["tiles"]["expiring_in_30_days"] == 1
    assert body["tiles"]["expired"] == 0
    assert body["rows"][0]["days_left"] == 10


def test_expiry_counts_one_already_past_as_expired(
    api_client_no_csrf, admin_user, student_profile, published_course, enrollment
):
    admission = _admit(admin_user, student_profile, published_course)
    services.attach_enrollment(actor=admin_user, line=admission.lines.get(), enrollment=enrollment)
    enrollment.access_end_date = date.today() - timedelta(days=3)
    enrollment.save(update_fields=["access_end_date"])

    body = _client(admin_user).get(f"{REPORTS}expiry/").json()
    assert body["tiles"]["expired"] == 1
    assert body["rows"][0]["days_left"] == -3


def test_additional_fees_names_the_course_each_was_charged_on(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "30000"},
            {"kind": "additional_fee", "label": "Exam fee", "unit_fee": "2000"},
        ],
    )
    body = _client(admin_user).get(f"{REPORTS}additional-fees/").json()

    assert body["tiles"]["fees"] == 1
    assert Decimal(body["tiles"]["total"]) == Decimal("2000.00")
    assert body["rows"][0]["label"] == "Exam fee"
    assert body["rows"][0]["charged_on"] == published_course.title


def test_coursewise_counts_a_two_course_admission_under_each(
    api_client_no_csrf, admin_user, student_profile, published_course, category
):
    from apps.courses import services as course_services

    second = course_services.create_course(
        actor=admin_user,
        title="Linux",
        category=category,
        short_description="A course.",
        description="Full description.",
        learning_objectives=["Learn it"],
    )
    services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "20000"},
            {"kind": "course", "course": second, "unit_fee": "10000"},
        ],
    )

    body = _client(admin_user).get(f"{REPORTS}coursewise/").json()

    assert body["tiles"]["courses"] == 2
    # One student, two courses: each course counts the admission once. The
    # money, though, is that course's own line.
    assert body["tiles"]["admissions"] == 2
    by_course = {row["course"]: row for row in body["rows"]}
    assert Decimal(by_course[published_course.title]["total"]) == Decimal("20000.00")
    assert Decimal(by_course["Linux"]["total"]) == Decimal("10000.00")
    # And the parts still add back to what was charged.
    assert Decimal(body["tiles"]["total"]) == Decimal("30000.00")


def test_a_discount_is_taken_off_the_course_it_belonged_to(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "30000"}],
        discount_kind=DiscountKind.FLAT,
        discount_value="5000",
    )
    row = _client(admin_user).get(f"{REPORTS}coursewise/").json()["rows"][0]
    assert Decimal(row["total"]) == Decimal("25000.00")


def test_every_tab_narrows_with_the_filters_and_none_of_them_widens(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    _admit(admin_user, student_profile, published_course, fee="30000")
    client = _client(admin_user)

    # A date range that excludes it empties the report rather than ignoring
    # the filter.
    empty = client.get(
        f"{REPORTS}overall/", {"start_date": "2020-01-01", "end_date": "2020-12-31"}
    ).json()
    assert empty["rows"] == []
    assert empty["tiles"]["admissions"] == 0

    by_course = client.get(f"{REPORTS}overall/", {"course": str(published_course.pk)}).json()
    assert len(by_course["rows"]) == 1


def test_a_malformed_filter_is_a_bad_request_not_an_unfiltered_report(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    """Ignoring a filter it could not read would show more than was asked
    for, which on a money report is the wrong way to fail."""
    _admit(admin_user, student_profile, published_course)
    response = _client(admin_user).get(f"{REPORTS}overall/", {"course": "not-a-uuid"})
    assert response.status_code == 400


def test_an_unknown_tab_is_refused(api_client_no_csrf, admin_user):
    assert _client(admin_user).get(f"{REPORTS}whatever/").status_code == 400


def test_the_reports_are_scoped_and_the_tiles_narrow_with_the_rows(
    api_client_no_csrf, admin_user, student_profile, published_course, other_branch_manager
):
    _admit(admin_user, student_profile, published_course, fee="30000")

    body = _client(other_branch_manager).get(f"{REPORTS}overall/").json()
    assert body["rows"] == []
    assert body["tiles"]["admissions"] == 0
    assert Decimal(body["tiles"]["total"]) == Decimal("0.00")


def test_a_student_cannot_read_the_centres_money(
    api_client_no_csrf, admin_user, student_profile, published_course
):
    _admit(admin_user, student_profile, published_course)
    assert _client(student_profile.user).get(f"{REPORTS}overall/").status_code == 403
