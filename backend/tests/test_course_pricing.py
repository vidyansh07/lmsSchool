"""What a course cost, and from when.

The rule the institution cares about: raising a course fee must not reach a
student already enrolled. That has always held, because `FeePlan.agreed_amount`
copies the figure at enrolment and never reads the course again — so the first
test here is a regression guard on a guarantee, not a new feature.

What is new is the institution's own record. A single mutable column could say
what a course costs today and nothing about what it cost in April, which is the
question an accountant closing a quarter and a student disputing an instalment
both ask.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.courses.models import CoursePrice
from apps.courses.services import price_on, quoted_fee, record_price

pytestmark = pytest.mark.django_db


def test_raising_the_fee_does_not_touch_a_student_already_enrolled(
    published_course, enrollment, admin_user
):
    # The whole reason the ledger snapshots. If this ever fails, every past
    # student's balance moved under them.
    from apps.fees.services import set_fee_plan

    original = Decimal("20000.00")
    set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=original)
    enrollment.refresh_from_db()

    record_price(
        course=published_course,
        actor=admin_user,
        amount=original + Decimal("5000.00"),
        note="November rise",
    )

    enrollment.fee_plan.refresh_from_db()
    assert enrollment.fee_plan.agreed_amount == original


def test_the_course_quotes_the_new_fee_from_then_on(published_course, admin_user):
    record_price(course=published_course, actor=admin_user, amount=Decimal("25000.00"))

    published_course.refresh_from_db()
    assert published_course.default_fee == Decimal("25000.00")
    assert quoted_fee(published_course) == Decimal("25000.00")


def test_the_old_fee_is_still_answerable(published_course, admin_user):
    today = timezone.localdate()
    april = today - timedelta(days=180)
    record_price(
        course=published_course, actor=admin_user, amount=Decimal("18000.00"), effective_from=april
    )
    record_price(course=published_course, actor=admin_user, amount=Decimal("25000.00"))

    assert price_on(published_course, april) == Decimal("18000.00")
    assert price_on(published_course, april + timedelta(days=1)) == Decimal("18000.00")
    assert price_on(published_course, today) == Decimal("25000.00")


def test_a_fee_announced_for_next_month_does_not_change_todays_quote(published_course, admin_user):
    record_price(course=published_course, actor=admin_user, amount=Decimal("20000.00"))
    next_month = timezone.localdate() + timedelta(days=30)

    record_price(
        course=published_course,
        actor=admin_user,
        amount=Decimal("30000.00"),
        effective_from=next_month,
        note="Announced in October, applies in November",
    )

    published_course.refresh_from_db()
    assert quoted_fee(published_course) == Decimal("20000.00")
    assert published_course.default_fee == Decimal("20000.00")
    assert price_on(published_course, next_month) == Decimal("30000.00")


def test_a_price_before_any_history_falls_back_to_the_course(published_course):
    # Every course is in this state until somebody records a price, and all of
    # them must still quote.
    assert not CoursePrice.objects.filter(course=published_course).exists()
    assert quoted_fee(published_course) == published_course.default_fee


def test_correcting_todays_figure_edits_it_rather_than_adding_a_second(
    published_course, admin_user
):
    record_price(course=published_course, actor=admin_user, amount=Decimal("20000.00"))
    record_price(course=published_course, actor=admin_user, amount=Decimal("21000.00"), note="typo")

    assert CoursePrice.objects.filter(course=published_course).count() == 1
    published_course.refresh_from_db()
    assert published_course.default_fee == Decimal("21000.00")


def test_a_negative_fee_is_refused(published_course, admin_user):
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        record_price(course=published_course, actor=admin_user, amount=Decimal("-1.00"))

    assert not CoursePrice.objects.filter(course=published_course).exists()


def test_the_change_is_recorded_against_whoever_made_it(published_course, admin_user):
    price = record_price(
        course=published_course, actor=admin_user, amount=Decimal("22000.00"), note="rise"
    )

    assert price.recorded_by == admin_user
    assert price.note == "rise"


class TestThePriceEndpoint:
    """Changing a fee over HTTP, and who may.

    A fee is the one course field somebody is later asked to account for, so
    these check the refusals as carefully as the success: a refusal that still
    wrote the row is not a refusal.
    """

    def url(self, course) -> str:
        return f"/api/v1/courses/{course.pk}/price/"

    def test_an_administrator_changes_the_fee(
        self, api_client_no_csrf, admin_user, published_course
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.post(
            self.url(published_course),
            {"amount": "27000.00", "note": "Diwali revision"},
            format="json",
        )

        assert response.status_code == 201
        published_course.refresh_from_db()
        assert published_course.default_fee == Decimal("27000.00")

    def test_the_history_reads_back(self, api_client_no_csrf, admin_user, published_course):
        record_price(course=published_course, actor=admin_user, amount=Decimal("19000.00"))
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(self.url(published_course))

        assert response.status_code == 200
        assert [row["amount"] for row in response.data] == ["19000.00"]

    def test_the_history_names_the_person_and_not_their_address(
        self, api_client_no_csrf, admin_user, published_course
    ):
        record_price(course=published_course, actor=admin_user, amount=Decimal("19000.00"))
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(self.url(published_course))

        body = str(response.data)
        assert admin_user.get_full_name() in body
        assert admin_user.email not in body

    def test_a_student_cannot_change_the_fee(self, api_client_no_csrf, student, published_course):
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.post(
            self.url(published_course), {"amount": "1.00"}, format="json"
        )

        assert response.status_code in (403, 404)
        published_course.refresh_from_db()
        assert published_course.default_fee != Decimal("1.00")
        assert not CoursePrice.objects.filter(course=published_course).exists()

    def test_an_anonymous_caller_cannot_read_the_history(
        self, api_client_no_csrf, published_course
    ):
        response = api_client_no_csrf.get(self.url(published_course))

        assert response.status_code in (401, 403)

    def test_a_negative_fee_is_refused_at_the_edge(
        self, api_client_no_csrf, admin_user, published_course
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.post(
            self.url(published_course), {"amount": "-5.00"}, format="json"
        )

        assert response.status_code == 400
        assert not CoursePrice.objects.filter(course=published_course).exists()
