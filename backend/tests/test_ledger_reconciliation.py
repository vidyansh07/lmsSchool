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
from apps.enrollments.services import set_enrollment_status
from apps.fees.models import PaymentKind
from apps.fees.services import (
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

    def test_a_part_payment_splits_between_received_and_outstanding(
        self, plan, admin_user
    ):
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
    def test_a_refund_leaves_received_holding_only_what_is_still_held(
        self, plan, admin_user
    ):
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

    def test_a_refund_is_reported_but_is_not_part_of_the_identity(
        self, plan, admin_user
    ):
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

        assert (
            money["charged"]
            == money["received"] + money["written_off"] + money["outstanding"]
        )

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


class TestTheGapItIsSupposedToExpose:
    def test_a_cancelled_admission_leaves_money_nobody_has_placed(
        self, plan, admin_user, enrollment
    ):
        """The whole reason this report exists.

        Cancelling stops the chasing and settles nothing. The fee is still
        charged, the balance is owed by nobody, and no decision has been
        recorded to write it off — so it belongs in no bucket, and the report
        says so out loud instead of letting it disappear.
        """
        record_payment(plan=plan, actor=admin_user, amount="5000")
        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user
        )

        money = totals(admin_user)

        assert money["charged"] == FEE
        assert money["received"] == Decimal("5000.00")
        assert money["outstanding"] == ZERO, "a cancelled admission is not chased"
        assert money["written_off"] == ZERO, "and nothing has been written off yet"
        # The fifteen thousand nobody has accounted for.
        assert money["unreconciled"] == Decimal("15000.00")
        assert money["cancelled_enrolments"] == 1

    def test_the_gap_is_exactly_the_unsettled_balance(
        self, plan, admin_user, enrollment
    ):
        # Not an approximation: the number names precisely what cancelling
        # failed to decide, which is what the cancellation feature must drive
        # to zero.
        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user
        )

        money = totals(admin_user)

        assert money["unreconciled"] == FEE


class TestItIsScopedLikeEverythingElse:
    def test_a_counsellor_reconciles_their_own_centre(
        self, plan, admin_user, counsellor_user
    ):
        money = totals(counsellor_user)

        # Same centre as the fixture, so they see it.
        assert money["charged"] == FEE

    def test_another_centres_money_is_not_in_the_total(
        self, plan, admin_user, other_branch
    ):
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

    def test_staff_who_may_see_fees_can_reconcile(
        self, api_client_no_csrf, admin_user, plan
    ):
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
