"""Money taken that the bank has not confirmed yet.

A cheque handed over on Tuesday is money received — the student has paid, the
balance drops, the receipt prints — but it is not money the institute holds
until the bank says so. This suite fixes three things in place:

1. **Uncleared still counts as received.** The balance follows what was
   taken, as it always has; `Uncleared` is a view of part of it, not a fourth
   bucket. Were it otherwise, every balance in the product would shift the
   day this landed, and the reconciliation identity would stop holding.
2. **A bounce is a void**, not a new kind of state for the money. The cheque
   was never payment, so it leaves received, leaves the balance and leaves
   every total — which is exactly what voiding already does.
3. The clearing state is derived from *how* it was paid, never accepted from
   the request, so no screen can record a cheque that claims to have cleared
   already.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.exceptions import ApplicationError
from apps.fees import services
from apps.fees.models import ClearingStatus, FeePlan, PaymentMethod

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def plan(admin_user, enrollment) -> FeePlan:
    return services.set_fee_plan(
        enrollment=enrollment, actor=admin_user, agreed_amount="20000", installments=[]
    )


@pytest.mark.parametrize(
    "method,expected",
    [
        (PaymentMethod.CHEQUE, ClearingStatus.UNCLEARED),
        (PaymentMethod.DEMAND_DRAFT, ClearingStatus.UNCLEARED),
        (PaymentMethod.CASH_DEPOSIT, ClearingStatus.UNCLEARED),
        (PaymentMethod.CASH, ClearingStatus.CLEARED),
        (PaymentMethod.UPI, ClearingStatus.CLEARED),
        (PaymentMethod.GOOGLE_PAY, ClearingStatus.CLEARED),
        (PaymentMethod.NET_BANKING, ClearingStatus.CLEARED),
    ],
)
def test_how_it_was_paid_decides_whether_it_has_cleared(admin_user, plan, method, expected):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=method, reference="X1"
    )
    assert payment.clearing_status == expected
    # Cash is cleared the day it is taken; a cheque has no clearing date yet.
    assert (payment.cleared_on is None) is (expected == ClearingStatus.UNCLEARED)


def test_an_uncleared_cheque_still_counts_as_received(admin_user, plan):
    """The student has paid. What is uncertain is whether the bank will
    honour it — and the balance must not pretend the money never arrived."""
    services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE, reference="44190"
    )
    plan.refresh_from_db()
    fresh = FeePlan.objects.with_totals().get(pk=plan.pk)
    assert fresh.paid == Decimal("5000.00")
    assert fresh.balance == Decimal("15000.00")


def test_clearing_one_moves_only_the_clearing_state(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE, reference="44190"
    )
    before = FeePlan.objects.with_totals().get(pk=plan.pk).paid

    cleared = services.mark_payment_cleared(payment=payment, actor=admin_user)

    assert cleared.clearing_status == ClearingStatus.CLEARED
    assert cleared.cleared_on == timezone.localdate()
    assert cleared.cleared_by_id == admin_user.pk
    # Nothing about the money moved: it was already received.
    assert FeePlan.objects.with_totals().get(pk=plan.pk).paid == before


def test_a_bounced_cheque_leaves_received_entirely(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE, reference="44190"
    )
    assert FeePlan.objects.with_totals().get(pk=plan.pk).paid == Decimal("5000.00")

    services.mark_payment_bounced(payment=payment, actor=admin_user, reason="Insufficient funds.")

    payment.refresh_from_db()
    assert payment.clearing_status == ClearingStatus.BOUNCED
    # The void is what moves the money, and it is the existing act for
    # "this should never have counted".
    assert payment.voided_at is not None
    assert "Insufficient funds." in payment.void_reason
    fresh = FeePlan.objects.with_totals().get(pk=plan.pk)
    assert fresh.paid == Decimal("0.00")
    assert fresh.balance == Decimal("20000.00")


def test_a_bounce_needs_a_reason(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE
    )
    with pytest.raises(ApplicationError):
        services.mark_payment_bounced(payment=payment, actor=admin_user, reason="  ")
    payment.refresh_from_db()
    assert payment.voided_at is None


def test_cash_cannot_clear_or_bounce(admin_user, plan):
    """Neither is a question about cash. Refusing says so, rather than
    recording a state that means nothing."""
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CASH
    )
    with pytest.raises(ApplicationError):
        services.mark_payment_cleared(payment=payment, actor=admin_user)
    with pytest.raises(ApplicationError):
        services.mark_payment_bounced(payment=payment, actor=admin_user, reason="No.")


def test_clearing_twice_is_refused_rather_than_recorded_twice(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE
    )
    services.mark_payment_cleared(payment=payment, actor=admin_user)
    with pytest.raises(ApplicationError):
        services.mark_payment_cleared(payment=payment, actor=admin_user)


def test_it_cannot_have_cleared_before_it_was_taken(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE
    )
    with pytest.raises(ApplicationError):
        services.mark_payment_cleared(
            payment=payment, actor=admin_user, cleared_on=payment.paid_on - timedelta(days=1)
        )


def test_a_voided_payment_cannot_clear(admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE
    )
    services.void_payment(payment=payment, actor=admin_user, reason="Wrong student.")
    with pytest.raises(ApplicationError):
        services.mark_payment_cleared(payment=payment, actor=admin_user)


def test_the_tax_and_the_bank_are_recorded_not_computed(admin_user, plan, branch):
    """The amount is the amount. These say what the desk declared at the
    counter, so the receipt and an accountant's export can repeat it."""
    from apps.fees.models import PaymentCategory, TaxGroup
    from apps.organisation.models import Bank

    bank = Bank.objects.create(name="HDFC Bank")
    category = PaymentCategory.objects.get(name="Fees")
    tax = TaxGroup.objects.get(name="GST")

    payment = services.record_payment(
        plan=plan,
        actor=admin_user,
        amount="5000",
        method=PaymentMethod.CHEQUE,
        bank=bank,
        category=category,
        apply_tax=True,
        tax_group=tax,
    )
    assert payment.amount == Decimal("5000.00")
    assert payment.bank_id == bank.pk
    assert payment.category_id == category.pk
    assert payment.apply_tax is True
    assert payment.tax_group_id == tax.pk


def test_a_tax_group_without_apply_tax_is_not_kept(admin_user, plan):
    """ "Tax group: GST" on a payment nobody applied tax to is a lie waiting to
    be read off a report."""
    from apps.fees.models import TaxGroup

    payment = services.record_payment(
        plan=plan,
        actor=admin_user,
        amount="5000",
        apply_tax=False,
        tax_group=TaxGroup.objects.get(name="GST"),
    )
    assert payment.apply_tax is False
    assert payment.tax_group_id is None


def test_an_instalment_from_another_fee_cannot_be_named(admin_user, plan, other_enrollment):
    other = services.set_fee_plan(
        enrollment=other_enrollment, actor=admin_user, agreed_amount="10000"
    )
    with pytest.raises(ApplicationError):
        services.record_payment(
            plan=plan, actor=admin_user, amount="5000", instalment=other.installments.first()
        )


def test_the_endpoints_clear_and_bounce_and_refuse_a_student(
    api_client_no_csrf, admin_user, plan, student_profile
):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.CHEQUE
    )
    url = f"/api/v1/fees/payments/{payment.pk}/"

    # The student whose fee it is cannot clear their own cheque.
    refused = _client(plan.enrollment.student.user).post(f"{url}clear/", {}, format="json")
    assert refused.status_code == 403

    cleared = _client(admin_user).post(f"{url}clear/", {}, format="json")
    assert cleared.status_code == 200, cleared.content
    assert cleared.json()["clearing_status"] == "cleared"


def test_the_bounce_endpoint_voids_the_money(api_client_no_csrf, admin_user, plan):
    payment = services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method=PaymentMethod.DEMAND_DRAFT
    )
    response = _client(admin_user).post(
        f"/api/v1/fees/payments/{payment.pk}/bounce/",
        {"reason": "Signature mismatch."},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["is_voided"] is True
    assert FeePlan.objects.with_totals().get(pk=plan.pk).paid == Decimal("0.00")
