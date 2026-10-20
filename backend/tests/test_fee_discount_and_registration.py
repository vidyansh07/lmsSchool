"""Discounts given as a percentage, and the booking amount that goes back.

Two things a counsellor does that the ledger could not record:

* agree a discount as "twenty percent" rather than as a figure — and the
  arithmetic has to be the institution's, not the counsellor's mental
  arithmetic, or two people quote two numbers;
* take a booking amount to hold a seat, sometimes on terms that allow it to be
  returned.

The second is the one with teeth. A refund that still counted towards what a
student had paid would overstate their payments and understate their balance
everywhere the figure appears — the student's own screen, the fee list, the
counsellor's dashboard and the collection totals. Those are different queries,
so each is checked, not just the model property.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.exceptions import ApplicationError, ConflictError
from apps.fees.models import PaymentKind
from apps.fees.services import (
    discount_for_percent,
    record_payment,
    refund_payment,
    set_fee_plan,
    void_payment,
)

pytestmark = pytest.mark.django_db

FEE = Decimal("20000.00")


@pytest.fixture
def plan(enrollment, admin_user):
    return set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)


class TestDiscountAsAPercentage:
    def test_a_percentage_becomes_money(self, enrollment, admin_user):
        plan = set_fee_plan(
            enrollment=enrollment,
            actor=admin_user,
            agreed_amount=FEE,
            discount_percent="20",
            discount_reason="Early bird",
        )

        assert plan.discount_amount == Decimal("4000.00")
        assert plan.discount_percent == Decimal("20.00")
        assert plan.payable == Decimal("16000.00")

    def test_the_percentage_is_kept_as_well_as_the_money(self, enrollment, admin_user):
        # What was agreed is "twenty percent"; what the ledger subtracts is
        # 4,000. A student remembers the first and an accountant needs the
        # second.
        plan = set_fee_plan(
            enrollment=enrollment,
            actor=admin_user,
            agreed_amount=FEE,
            discount_percent="20",
            discount_reason="Early bird",
        )
        plan.refresh_from_db()

        assert (plan.discount_percent, plan.discount_amount) == (
            Decimal("20.00"),
            Decimal("4000.00"),
        )

    def test_a_flat_discount_still_works_and_records_no_percentage(
        self, enrollment, admin_user
    ):
        plan = set_fee_plan(
            enrollment=enrollment,
            actor=admin_user,
            agreed_amount=FEE,
            discount_amount="2500",
            discount_reason="Agreed with the owner",
        )

        assert plan.discount_amount == Decimal("2500.00")
        assert plan.discount_percent is None

    def test_rounding_lands_where_a_person_with_a_calculator_lands(self):
        # 12.5% of 17,555 is 2,194.375. A person rounds that up; banker's
        # rounding would give 2,194.38 here but 2,194.36 a paisa either side,
        # and a student notices a rupee.
        assert discount_for_percent(Decimal("17555.00"), Decimal("12.5")) == Decimal("2194.38")

    def test_a_percentage_over_a_hundred_is_refused(self, enrollment, admin_user):
        with pytest.raises(ApplicationError):
            set_fee_plan(
                enrollment=enrollment,
                actor=admin_user,
                agreed_amount=FEE,
                discount_percent="120",
                discount_reason="no",
            )

    def test_a_full_discount_waives_the_fee(self, enrollment, admin_user):
        plan = set_fee_plan(
            enrollment=enrollment,
            actor=admin_user,
            agreed_amount=FEE,
            discount_percent="100",
            discount_reason="Staff child",
        )

        assert plan.payable == Decimal("0.00")


class TestTheBookingAmount:
    def test_it_counts_towards_the_fee_like_any_payment(self, plan, admin_user):
        record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )

        plan.refresh_from_db()
        assert plan.paid == Decimal("1000.00")
        assert plan.balance == FEE - Decimal("1000.00")

    def test_refunding_it_stops_it_counting(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )

        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        plan.refresh_from_db()
        assert plan.paid == Decimal("0.00")
        assert plan.balance == FEE

    def test_a_refund_is_not_the_same_as_a_void(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )

        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        payment.refresh_from_db()
        assert payment.is_refunded is True
        assert payment.is_voided is False, "an accountant must be able to tell these apart"
        assert payment.refunded_by == admin_user

    def test_a_payment_not_taken_on_refundable_terms_cannot_be_refunded(
        self, plan, admin_user
    ):
        payment = record_payment(
            plan=plan, actor=admin_user, amount="1000", kind=PaymentKind.REGISTRATION
        )

        with pytest.raises(ApplicationError):
            refund_payment(payment=payment, actor=admin_user, reason="changed their mind")

        payment.refresh_from_db()
        assert payment.is_refunded is False

    def test_an_instalment_cannot_be_marked_refundable(self, plan, admin_user):
        with pytest.raises(ApplicationError):
            record_payment(plan=plan, actor=admin_user, amount="5000", is_refundable=True)

    def test_refunding_twice_is_refused(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        with pytest.raises(ConflictError):
            refund_payment(payment=payment, actor=admin_user, reason="again")

    def test_a_voided_payment_cannot_also_be_refunded(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        void_payment(payment=payment, actor=admin_user, reason="entered twice")

        with pytest.raises(ConflictError):
            refund_payment(payment=payment, actor=admin_user, reason="and refund it")

    def test_a_refund_needs_a_reason(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )

        with pytest.raises(ApplicationError):
            refund_payment(payment=payment, actor=admin_user, reason="   ")


class TestARefundReachesEveryTotal:
    """The model property is the easy one. These are the queries that forgot."""

    def test_the_student_list_total(self, plan, admin_user, student_profile):
        from apps.fees.queries import annotate_student_fee_totals
        from apps.students.models import StudentProfile

        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        row = annotate_student_fee_totals(
            StudentProfile.objects.filter(pk=plan.enrollment.student_id)
        ).get()
        assert row.fee_paid == Decimal("0.00")

    def test_the_enrolment_list_total(self, plan, admin_user):
        from apps.enrollments.models import Enrollment
        from apps.fees.queries import annotate_enrollment_fee

        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        row = annotate_enrollment_fee(
            Enrollment.objects.filter(pk=plan.enrollment_id)
        ).get()
        assert row.fee_paid == Decimal("0.00")

    def test_the_annotated_plan_total(self, plan, admin_user):
        from apps.fees.models import FeePlan

        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        assert FeePlan.objects.with_totals().get(pk=plan.pk).paid == Decimal("0.00")


class TestOverHttp:
    """The same two features as a counsellor's browser meets them."""

    def plan_url(self, enrollment) -> str:
        return f"/api/v1/fees/enrollments/{enrollment.pk}/"

    def payments_url(self, enrollment) -> str:
        return f"/api/v1/fees/enrollments/{enrollment.pk}/payments/"

    def test_a_counsellor_sets_a_percentage_discount(
        self, api_client_no_csrf, counsellor_user, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.put(
            self.plan_url(enrollment),
            {
                "agreed_amount": "20000.00",
                "discount_percent": "15",
                "discount_reason": "Group booking",
            },
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["discount_amount"] == "3000.00"
        assert response.data["discount_percent"] == "15.00"

    def test_a_counsellor_takes_a_refundable_booking_amount(
        self, api_client_no_csrf, counsellor_user, enrollment, admin_user
    ):
        set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.post(
            self.payments_url(enrollment),
            {"amount": "1000.00", "kind": "registration", "is_refundable": True},
            format="json",
        )

        assert response.status_code == 201, response.data
        assert response.data["kind"] == "registration"
        assert response.data["is_refundable"] is True

    def test_refunding_over_http_clears_it_from_the_balance(
        self, api_client_no_csrf, admin_user, enrollment
    ):
        plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.post(
            f"/api/v1/fees/payments/{payment.pk}/refund/",
            {"reason": "Decided not to join"},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["is_refunded"] is True
        plan.refresh_from_db()
        assert plan.paid == Decimal("0.00")

    def test_a_student_cannot_refund_their_own_payment(
        self, api_client_no_csrf, admin_user, enrollment, student
    ):
        plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.post(
            f"/api/v1/fees/payments/{payment.pk}/refund/",
            {"reason": "I want my money"},
            format="json",
        )

        assert response.status_code in (403, 404)
        payment.refresh_from_db()
        assert payment.is_refunded is False
