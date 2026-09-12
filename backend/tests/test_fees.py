"""The fee ledger: what was agreed for a course, what has been paid, by whom.

What is pinned:

- a fee belongs to an *enrolment*, and a counsellor or manager sets it without
  anybody's approval; a trainer or student cannot, whichever route they try;
- payments are ad hoc — any amount, any day — but the first one is the
  registration fee (at least ₹1,000) and none may exceed the balance;
- a payment is voided, never deleted, and the balance recovers;
- the student's coarse ``fee_status`` follows the ledger;
- every change is in the audit log with old and new values, and the history
  endpoint returns it for the enrolment;
- a student sees their own fees and nobody else's.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.fees import services
from apps.fees.models import FeePayment, FeePlan
from apps.students.models import FeeStatus


def fee_url(enrollment) -> str:
    return f"/api/v1/fees/enrollments/{enrollment.pk}/"


def money(value) -> Decimal:
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Setting the fee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_counsellor_sets_the_fee_without_approval(api_client_no_csrf, counsellor_user, enrollment):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        fee_url(enrollment),
        {"agreed_amount": "24000", "discount_amount": "2000", "discount_reason": "Early bird"},
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["payable"] == "22000.00"
    assert body["paid"] == "0.00"
    assert body["balance"] == "22000.00"
    assert body["status"] == "unpaid"
    assert body["created_by"] == "Kiran Counsellor"

    entry = AuditLog.objects.get(action=AuditAction.FEE_PLAN_SET)
    assert entry.actor_id == counsellor_user.pk
    assert entry.context["agreed_amount"] == "24000.00"
    assert entry.context["enrollment_code"] == enrollment.code


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["trainer", "student"])
def test_only_admissions_staff_may_set_a_fee(request, api_client_no_csrf, enrollment, fixture):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))
    response = api_client_no_csrf.put(fee_url(enrollment), {"agreed_amount": "1"}, format="json")
    assert response.status_code == 403
    assert not FeePlan.objects.exists()


@pytest.mark.django_db
def test_the_service_refuses_an_actor_without_the_capability(trainer, enrollment):
    with pytest.raises(AuthorityError):
        services.set_fee_plan(enrollment=enrollment, actor=trainer, agreed_amount="5000")


@pytest.mark.django_db
def test_a_discount_needs_a_reason_and_cannot_exceed_the_fee(counsellor_user, enrollment):
    with pytest.raises(ApplicationError) as refused:
        services.set_fee_plan(
            enrollment=enrollment,
            actor=counsellor_user,
            agreed_amount="5000",
            discount_amount="500",
        )
    assert "discount_reason" in refused.value.detail
    with pytest.raises(ApplicationError) as refused:
        services.set_fee_plan(
            enrollment=enrollment,
            actor=counsellor_user,
            agreed_amount="5000",
            discount_amount="6000",
            discount_reason="Typo",
        )
    assert "discount_amount" in refused.value.detail


@pytest.mark.django_db
def test_changing_the_fee_records_old_and_new_values(manager_user, enrollment):
    services.set_fee_plan(enrollment=enrollment, actor=manager_user, agreed_amount="20000")
    services.set_fee_plan(
        enrollment=enrollment,
        actor=manager_user,
        agreed_amount="18000",
        discount_amount="1000",
        discount_reason="Referral",
    )
    entry = AuditLog.objects.get(action=AuditAction.FEE_PLAN_UPDATED)
    assert entry.context["changes"]["agreed_amount"] == {"from": "20000.00", "to": "18000.00"}
    assert entry.context["changes"]["discount_amount"] == {"from": "0.00", "to": "1000.00"}
    assert FeePlan.objects.get().payable == money("17000")


@pytest.mark.django_db
def test_the_fee_cannot_be_lowered_below_what_was_already_paid(counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    services.record_payment(plan=plan, actor=counsellor_user, amount="6000")
    with pytest.raises(ApplicationError) as refused:
        services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="5000")
    assert "agreed_amount" in refused.value.detail


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_payments_are_ad_hoc_and_the_balance_follows(
    api_client_no_csrf, counsellor_user, enrollment
):
    api_client_no_csrf.force_login(counsellor_user)
    api_client_no_csrf.put(fee_url(enrollment), {"agreed_amount": "12000"}, format="json")

    first = api_client_no_csrf.post(
        f"{fee_url(enrollment)}payments/",
        {"amount": "1000", "method": "upi", "reference": "UPI-1"},
        format="json",
    )
    assert first.status_code == 201, first.json()
    assert first.json()["receipt_number"].startswith("GRS-R-")

    second = api_client_no_csrf.post(
        f"{fee_url(enrollment)}payments/",
        {
            "amount": "3500.50",
            "method": "cash",
            "paid_on": str(timezone.localdate() - timedelta(days=3)),
        },
        format="json",
    )
    assert second.status_code == 201, second.json()

    plan = api_client_no_csrf.get(fee_url(enrollment)).json()
    assert plan["paid"] == "4500.50"
    assert plan["balance"] == "7499.50"
    assert plan["status"] == "partial"
    assert len(plan["payments"]) == 2
    assert plan["payments"][0]["recorded_by"] == "Kiran Counsellor"

    enrollment.student.refresh_from_db()
    assert enrollment.student.fee_status == FeeStatus.PARTIAL


@pytest.mark.django_db
def test_the_first_payment_is_the_registration_fee(counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="12000"
    )
    with pytest.raises(ApplicationError) as refused:
        services.record_payment(plan=plan, actor=counsellor_user, amount="500")
    assert "1,000" in str(refused.value.detail["amount"])
    # A course cheaper than the registration fee can be paid in full at once.
    cheap = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="800")
    services.record_payment(plan=cheap, actor=counsellor_user, amount="800")
    assert FeePlan.objects.get().status == "paid"


@pytest.mark.django_db
def test_a_payment_cannot_exceed_the_balance_or_be_dated_ahead(counsellor_user, enrollment):
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="5000")
    with pytest.raises(ApplicationError) as refused:
        services.record_payment(plan=plan, actor=counsellor_user, amount="5001")
    assert "amount" in refused.value.detail
    with pytest.raises(ApplicationError) as refused:
        services.record_payment(
            plan=plan,
            actor=counsellor_user,
            amount="1000",
            paid_on=timezone.localdate() + timedelta(days=1),
        )
    assert "paid_on" in refused.value.detail
    assert not FeePayment.objects.exists()


@pytest.mark.django_db
def test_paying_in_full_marks_the_student_paid(counsellor_user, enrollment):
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="3000")
    services.record_payment(plan=plan, actor=counsellor_user, amount="3000")
    enrollment.student.refresh_from_db()
    assert enrollment.student.fee_status == FeeStatus.PAID
    assert FeePlan.objects.get().status == "paid"


@pytest.mark.django_db
def test_a_voided_payment_stays_in_the_ledger_but_not_in_the_total(
    api_client_no_csrf, manager_user, enrollment
):
    plan = services.set_fee_plan(enrollment=enrollment, actor=manager_user, agreed_amount="9000")
    payment = services.record_payment(plan=plan, actor=manager_user, amount="4000")
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        f"/api/v1/fees/payments/{payment.pk}/void/", {"reason": "Entered twice"}, format="json"
    )
    assert response.status_code == 200, response.json()
    assert response.json()["is_voided"] is True
    assert response.json()["voided_by"] == manager_user.full_name

    plan = FeePlan.objects.with_totals().get()
    assert plan.paid == money("0")
    assert plan.balance == money("9000")
    assert FeePayment.objects.count() == 1
    entry = AuditLog.objects.get(action=AuditAction.FEE_PAYMENT_VOIDED)
    assert entry.context["reason"] == "Entered twice"
    enrollment.student.refresh_from_db()
    assert enrollment.student.fee_status == FeeStatus.PENDING

    payment.refresh_from_db()
    with pytest.raises(ConflictError):
        services.void_payment(payment=payment, actor=manager_user, reason="Again")


@pytest.mark.django_db
def test_void_needs_a_reason(manager_user, enrollment):
    plan = services.set_fee_plan(enrollment=enrollment, actor=manager_user, agreed_amount="9000")
    payment = services.record_payment(plan=plan, actor=manager_user, amount="4000")
    with pytest.raises(ApplicationError):
        services.void_payment(payment=payment, actor=manager_user, reason="  ")
    payment.refresh_from_db()
    assert not payment.is_voided


# ---------------------------------------------------------------------------
# What is expected next
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_next_due_gives_an_expected_date_and_an_overdue_flag(
    api_client_no_csrf, counsellor_user, enrollment
):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    yesterday = timezone.localdate() - timedelta(days=1)
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        f"{fee_url(enrollment)}next-due/",
        {"next_due_amount": "4000", "next_due_on": str(yesterday)},
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert response.json()["is_overdue"] is True
    enrollment.student.refresh_from_db()
    # The coarse status is re-derived on the next ledger change, not on the
    # calendar; a payment now clears it.
    services.record_payment(plan=plan, actor=counsellor_user, amount="4000")
    plan.refresh_from_db()
    assert plan.next_due_on is None
    enrollment.student.refresh_from_db()
    assert enrollment.student.fee_status == FeeStatus.PARTIAL


@pytest.mark.django_db
def test_next_due_cannot_exceed_the_balance_or_come_half_filled(counsellor_user, enrollment):
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="5000")
    with pytest.raises(ApplicationError):
        services.set_next_due(
            plan=plan, actor=counsellor_user, amount="6000", on=timezone.localdate()
        )
    with pytest.raises(ApplicationError):
        services.set_next_due(plan=plan, actor=counsellor_user, amount="1000", on=None)


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_history_lists_every_change_newest_first(api_client_no_csrf, counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    payment = services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    services.void_payment(payment=payment, actor=counsellor_user, reason="Wrong student")
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get(f"{fee_url(enrollment)}history/")
    assert response.status_code == 200
    actions = [row["action"] for row in response.json()]
    assert actions == [
        AuditAction.FEE_PAYMENT_VOIDED,
        AuditAction.FEE_PAYMENT_RECORDED,
        AuditAction.FEE_PLAN_SET,
    ]
    assert all(row["actor_label"] == counsellor_user.email for row in response.json())


@pytest.mark.django_db
def test_a_student_sees_their_own_fees_and_nobody_elses(
    api_client_no_csrf, counsellor_user, enrollment, other_enrollment
):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    services.record_payment(plan=plan, actor=counsellor_user, amount="2500")
    api_client_no_csrf.force_login(enrollment.student.user)

    mine = api_client_no_csrf.get("/api/v1/fees/me/")
    assert mine.status_code == 200
    assert mine.json()["paid_total"] == "2500.00"
    assert mine.json()["balance_total"] == "7500.00"
    assert mine.json()["plans"][0]["course_title"] == enrollment.course.title

    assert api_client_no_csrf.get(fee_url(enrollment)).status_code == 200
    assert api_client_no_csrf.get(fee_url(other_enrollment)).status_code == 403
    assert (
        api_client_no_csrf.get(f"/api/v1/fees/students/{other_enrollment.student_id}/").status_code
        == 403
    )
    assert api_client_no_csrf.get("/api/v1/fees/overview/").status_code == 403


@pytest.mark.django_db
def test_the_overview_shows_collections_and_who_is_late(
    api_client_no_csrf, counsellor_user, enrollment, other_enrollment
):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    services.set_next_due(
        plan=plan, actor=counsellor_user, amount="3000", on=timezone.localdate() - timedelta(days=2)
    )
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get("/api/v1/fees/overview/")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["collected_today"] == "1000.00"
    assert body["outstanding_total"] == "9000.00"
    assert body["overdue_count"] == 1
    assert body["enrollments_without_plan"] == 1
    assert body["overdue"][0]["student_name"] == enrollment.student.user.full_name
    assert body["overdue"][0]["balance"] == "9000.00"


@pytest.mark.django_db
def test_a_student_summary_for_staff(api_client_no_csrf, manager_user, counsellor_user, enrollment):
    services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="10000")
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"/api/v1/fees/students/{enrollment.student_id}/")
    assert response.status_code == 200
    assert response.json()["payable_total"] == "10000.00"
    assert response.json()["enrollments_without_plan"] == 0


# ---------------------------------------------------------------------------
# The list screens
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_students_list_carries_paid_and_balance(
    api_client_no_csrf, manager_user, counsellor_user, enrollment, other_enrollment
):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000"
    )
    services.record_payment(plan=plan, actor=counsellor_user, amount="2500")
    voided = services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    services.void_payment(payment=voided, actor=counsellor_user, reason="Mistake")
    services.set_next_due(
        plan=plan, actor=counsellor_user, amount="2000", on=timezone.localdate() + timedelta(days=7)
    )
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get("/api/v1/students/")
    assert response.status_code == 200
    rows = {row["student_id"]: row for row in response.json()["results"]}
    paid = rows[enrollment.student.student_id]
    assert paid["fee_payable"] == "10000.00"
    assert paid["fee_paid"] == "2500.00"
    assert paid["fee_balance"] == "7500.00"
    assert paid["fee_next_due_on"] == str(timezone.localdate() + timedelta(days=7))
    unpaid = rows[other_enrollment.student.student_id]
    assert unpaid["fee_payable"] == "0.00"
    assert unpaid["fee_balance"] == "0.00"
    assert unpaid["fee_next_due_on"] is None


@pytest.mark.django_db
def test_the_enrolment_list_carries_the_fee_for_staff_only(
    api_client_no_csrf, counsellor_user, enrollment, other_enrollment
):
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="8000")
    services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get("/api/v1/enrollments/")
    rows = {row["id"]: row for row in response.json()["results"]}
    assert rows[str(enrollment.pk)]["fee_balance"] == "7000.00"
    assert rows[str(other_enrollment.pk)]["fee_payable"] is None
    assert rows[str(other_enrollment.pk)]["fee_balance"] is None

    api_client_no_csrf.force_login(enrollment.student.user)
    mine = api_client_no_csrf.get("/api/v1/enrollments/").json()["results"]
    assert "fee_balance" not in mine[0]
