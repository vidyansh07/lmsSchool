"""Does the money add up?

The fees panel answers "how are we doing" — collected this month, who is late.
It cannot answer "does it add up", because it never states what was charged and
it drops a cancelled admission entirely, so money on a cancelled enrolment
leaves the screen without being accounted for anywhere.

The reconciliation states an identity instead::

    charged = received + written off + outstanding + unreconciled

Each side is computed independently rather than deriving the last number by
subtraction, because a figure obtained by subtraction always balances and
therefore proves nothing. `unreconciled` is what the buckets fail to explain,
and these tests are mostly about keeping it honest: zero when it should be, and
exactly the missing amount when the system genuinely cannot place the money.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.enrollments.models import EnrollmentStatus
from apps.fees.models import PaymentKind
from apps.fees.services import (
    cancel_admission,
    ledger_reconciliation,
    record_payment,
    refund_payment,
    set_fee_plan,
    void_payment,
)

pytestmark = pytest.mark.django_db

FEE = Decimal("20000.00")
ZERO = Decimal("0.00")


@pytest.fixture
def plan(enrollment, admin_user):
    return set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)


def totals(user):
    return ledger_reconciliation(user=user)


class TestTheIdentityHolds:
    def test_a_fee_with_nothing_paid_is_all_outstanding(self, plan, admin_user):
        money = totals(admin_user)

        assert money["charged"] == FEE
        assert money["received"] == ZERO
        assert money["outstanding"] == FEE
        assert money["unreconciled"] == ZERO

    def test_a_part_payment_splits_between_received_and_outstanding(self, plan, admin_user):
        record_payment(plan=plan, actor=admin_user, amount="5000")

        money = totals(admin_user)

        assert money["received"] == Decimal("5000.00")
        assert money["outstanding"] == Decimal("15000.00")
        assert money["unreconciled"] == ZERO

    def test_a_fee_paid_in_full_leaves_nothing_outstanding(self, plan, admin_user):
        record_payment(plan=plan, actor=admin_user, amount="20000")

        money = totals(admin_user)

        assert money["received"] == FEE
        assert money["outstanding"] == ZERO
        assert money["unreconciled"] == ZERO

    def test_a_discount_reduces_what_was_charged_not_what_was_received(
        self, enrollment, admin_user
    ):
        set_fee_plan(
            enrollment=enrollment,
            actor=admin_user,
            agreed_amount=FEE,
            discount_percent="25",
            discount_reason="Group booking",
        )

        money = totals(admin_user)

        # A discount is money never asked for, not money lost.
        assert money["charged"] == Decimal("15000.00")
        assert money["unreconciled"] == ZERO


class TestMoneyThatCameBackOrNeverWas:
    def test_a_refund_leaves_received_holding_only_what_is_still_held(self, plan, admin_user):
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        money = totals(admin_user)

        assert money["received"] == ZERO, "refunded money is not money the institute holds"
        assert money["refunded"] == Decimal("1000.00")
        assert money["outstanding"] == FEE
        assert money["unreconciled"] == ZERO

    def test_a_refund_is_reported_but_is_not_part_of_the_identity(self, plan, admin_user):
        # It is already excluded from `received`; adding it to the identity
        # would count the same thousand rupees twice.
        payment = record_payment(
            plan=plan,
            actor=admin_user,
            amount="1000",
            kind=PaymentKind.REGISTRATION,
            is_refundable=True,
        )
        refund_payment(payment=payment, actor=admin_user, reason="Decided not to join")

        money = totals(admin_user)

        assert money["charged"] == money["received"] + money["written_off"] + money["outstanding"]

    def test_a_void_is_absent_from_both_sides(self, plan, admin_user):
        # A void says the payment should never have been recorded. It was
        # never money, so it is not netted off — it simply is not there.
        payment = record_payment(plan=plan, actor=admin_user, amount="5000")
        void_payment(payment=payment, actor=admin_user, reason="Entered twice")

        money = totals(admin_user)

        assert money["received"] == ZERO
        assert money["refunded"] == ZERO
        assert money["outstanding"] == FEE
        assert money["unreconciled"] == ZERO


class TestACancelledAdmissionSettlesItsMoney:
    """The gap this report was built to expose, now closed.

    Cancelling used to stop the chasing and settle nothing: the fee was still
    charged, nobody owed the balance, and no decision to write it off had been
    recorded — so the money sat in no bucket and `unreconciled` named it.
    Cancelling now decides all of it at once, and these check the sum closes in
    each of the three cases that differ.
    """

    def test_cancelling_with_nothing_kept_writes_the_fee_off(self, plan, admin_user, enrollment):
        cancel_admission(
            enrollment=enrollment, actor=admin_user, reason="Changed their mind, week one"
        )

        money = totals(admin_user)

        assert money["charged"] == FEE
        assert money["written_off"] == FEE
        assert money["outstanding"] == ZERO
        assert money["unreconciled"] == ZERO

    def test_a_charge_is_still_owed_when_nothing_was_paid(self, plan, admin_user, enrollment):
        cancel_admission(
            enrollment=enrollment,
            actor=admin_user,
            cancellation_charge="3000",
            reason="Four weeks attended",
        )

        money = totals(admin_user)

        assert money["written_off"] == Decimal("17000.00")
        # They still owe the charge, so it is outstanding — not written off and
        # not quietly forgotten because the admission ended.
        assert money["outstanding"] == Decimal("3000.00")
        assert money["unreconciled"] == ZERO

    def test_paying_more_than_the_charge_becomes_money_owed_back(
        self, plan, admin_user, enrollment
    ):
        record_payment(plan=plan, actor=admin_user, amount="8000")

        cancel_admission(
            enrollment=enrollment,
            actor=admin_user,
            cancellation_charge="3000",
            reason="Four weeks attended",
        )

        money = totals(admin_user)

        assert money["received"] == Decimal("8000.00")
        # Five thousand is held and is no longer the institute's.
        assert money["refund_due"] == Decimal("5000.00")
        assert money["written_off"] == Decimal("17000.00")
        assert money["outstanding"] == ZERO
        assert money["unreconciled"] == ZERO

    def test_the_original_fee_is_still_answerable_afterwards(self, plan, admin_user, enrollment):
        # A cancellation that overwrote the fee would make "what did we
        # charge" unanswerable, and that is where every reconciliation starts.
        cancel_admission(
            enrollment=enrollment, actor=admin_user, cancellation_charge="3000", reason="Attended"
        )

        plan.refresh_from_db()
        assert plan.gross_payable == FEE
        assert plan.payable == Decimal("3000.00")
        assert plan.written_off == Decimal("17000.00")

    def test_the_enrolment_and_its_money_end_together(self, plan, admin_user, enrollment):
        # Doing half of it is how the two came to disagree in the first place.
        cancel_admission(enrollment=enrollment, actor=admin_user, reason="Changed their mind")

        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.CANCELLED

    def test_cancelling_stops_expecting_another_instalment(self, plan, admin_user, enrollment):
        # Chasing a schedule drawn up for the full fee would be wrong.
        cancel_admission(enrollment=enrollment, actor=admin_user, reason="Left")

        plan.refresh_from_db()
        assert plan.next_due_on is None
        assert plan.next_due_amount is None

    def test_a_charge_above_the_fee_is_refused(self, plan, admin_user, enrollment):
        from apps.common.exceptions import ApplicationError

        with pytest.raises(ApplicationError):
            cancel_admission(
                enrollment=enrollment,
                actor=admin_user,
                cancellation_charge="25000",
                reason="More than the fee",
            )

        plan.refresh_from_db()
        assert plan.settled_amount is None

    def test_cancelling_needs_a_reason(self, plan, admin_user, enrollment):
        from apps.common.exceptions import ApplicationError

        with pytest.raises(ApplicationError):
            cancel_admission(enrollment=enrollment, actor=admin_user, reason="   ")

    def test_cancelling_twice_is_refused(self, plan, admin_user, enrollment):
        from apps.common.exceptions import ConflictError

        cancel_admission(enrollment=enrollment, actor=admin_user, reason="Left")

        with pytest.raises(ConflictError):
            cancel_admission(enrollment=enrollment, actor=admin_user, reason="Again")

    def test_zero_kept_and_never_cancelled_are_different_facts(self, plan, admin_user, enrollment):
        # Which is why the column is nullable: a zero cannot tell them apart.
        assert plan.settled_amount is None
        assert plan.is_cancelled is False

        cancel_admission(enrollment=enrollment, actor=admin_user, reason="Nothing kept")

        plan.refresh_from_db()
        assert plan.settled_amount == ZERO
        assert plan.is_cancelled is True


class TestItIsScopedLikeEverythingElse:
    def test_a_counsellor_reconciles_their_own_centre(self, plan, admin_user, counsellor_user):
        money = totals(counsellor_user)

        # Same centre as the fixture, so they see it.
        assert money["charged"] == FEE

    def test_another_centres_money_is_not_in_the_total(self, plan, admin_user, other_branch):
        """A reconciliation is still somebody's data.

        A total that silently includes another centre is the hardest kind of
        leak to notice, because the screen looks completely normal.
        """
        from apps.accounts.models import User, UserRole

        from .conftest import TEST_PASSWORD

        elsewhere = User.objects.create_user(
            email="manager.elsewhere@grras.invalid",
            password=TEST_PASSWORD,
            first_name="Else",
            last_name="Where",
            role=UserRole.MANAGER,
            branch=other_branch,
        )

        money = totals(elsewhere)

        assert money["charged"] == ZERO
        assert money["received"] == ZERO

    def test_a_student_reconciles_nothing(self, plan, student):
        # The endpoint this will sit behind is staff-only; the function itself
        # must not be the weak link if it is ever called with the wrong user.
        money = totals(student)

        assert money["charged"] == ZERO


class TestOverHttp:
    URL = "/api/v1/fees/reconciliation/"

    def test_staff_who_may_see_fees_can_reconcile(self, api_client_no_csrf, admin_user, plan):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.get(self.URL)

        assert response.status_code == 200
        assert response.data["charged"] == "20000.00"
        assert response.data["unreconciled"] == "0.00"

    def test_a_student_is_refused(self, api_client_no_csrf, student, plan):
        api_client_no_csrf.force_authenticate(user=student)

        response = api_client_no_csrf.get(self.URL)

        assert response.status_code in (403, 404)

    def test_a_trainer_is_refused(self, api_client_no_csrf, trainer, plan):
        # A trainer holds three capabilities and none of them is money.
        api_client_no_csrf.force_authenticate(user=trainer)

        response = api_client_no_csrf.get(self.URL)

        assert response.status_code in (403, 404)

    def test_an_anonymous_caller_is_refused(self, api_client_no_csrf, plan):
        response = api_client_no_csrf.get(self.URL)

        assert response.status_code in (401, 403)


class TestCancellingOverHttp:
    def url(self, enrollment) -> str:
        return f"/api/v1/fees/enrollments/{enrollment.pk}/cancel/"

    def test_a_counsellor_cancels_an_admission(
        self, api_client_no_csrf, counsellor_user, plan, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=counsellor_user)

        response = api_client_no_csrf.post(
            self.url(enrollment),
            {"cancellation_charge": "3000", "reason": "Four weeks attended"},
            format="json",
        )

        assert response.status_code == 200, response.data
        plan.refresh_from_db()
        assert plan.settled_amount == Decimal("3000.00")

    def test_a_student_cannot_cancel_their_own_admission(
        self, api_client_no_csrf, plan, enrollment
    ):
        # Nor write off their own fee by doing so.
        api_client_no_csrf.force_authenticate(user=enrollment.student.user)

        response = api_client_no_csrf.post(
            self.url(enrollment), {"reason": "I want out"}, format="json"
        )

        assert response.status_code in (403, 404)
        plan.refresh_from_db()
        assert plan.settled_amount is None

    def test_a_trainer_cannot_cancel_an_admission(
        self, api_client_no_csrf, trainer, plan, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=trainer)

        response = api_client_no_csrf.post(self.url(enrollment), {"reason": "no"}, format="json")

        assert response.status_code in (403, 404)
        plan.refresh_from_db()
        assert plan.settled_amount is None

    def test_cancelling_without_a_reason_is_refused_and_writes_nothing(
        self, api_client_no_csrf, admin_user, plan, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=admin_user)

        response = api_client_no_csrf.post(self.url(enrollment), {}, format="json")

        assert response.status_code == 400
        plan.refresh_from_db()
        assert plan.settled_amount is None
