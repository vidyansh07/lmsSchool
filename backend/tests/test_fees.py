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
def test_a_discount_typed_as_a_percentage_is_worked_out_in_rupees(
    api_client_no_csrf, counsellor_user, enrollment
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        fee_url(enrollment),
        {
            "agreed_amount": "24999",
            "discount_percent": "12.5",
            # Ignored when a percentage is sent: the server works it out.
            "discount_amount": "1",
            "discount_reason": "Scholarship",
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["discount_percent"] == "12.50"
    assert body["discount_amount"] == "3124.88"  # 24,999 × 12.5% = 3,124.875, half up
    assert body["payable"] == "21874.12"
    entry = AuditLog.objects.get(action=AuditAction.FEE_PLAN_SET)
    assert entry.context["discount_percent"] == "12.50"


@pytest.mark.django_db
def test_a_percentage_discount_follows_a_changed_fee_and_can_turn_flat(
    counsellor_user, enrollment
):
    services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="20000",
        discount_percent="10",
        discount_reason="Referral",
    )
    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="30000",
        discount_percent="10",
        discount_reason="Referral",
    )
    assert plan.discount_amount == money("3000")
    assert plan.payable == money("27000")

    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="30000",
        discount_amount="500",
        discount_reason="Referral",
    )
    assert plan.discount_percent is None
    assert plan.discount_amount == money("500")
    entry = AuditLog.objects.filter(action=AuditAction.FEE_PLAN_UPDATED).latest("created_at")
    assert entry.context["changes"]["discount_percent"] == {"from": "10.00", "to": "None"}


@pytest.mark.django_db
@pytest.mark.parametrize("percent", ["-1", "100.01", "abc", "10.555"])
def test_a_discount_percentage_must_be_a_real_percentage(counsellor_user, enrollment, percent):
    with pytest.raises(ApplicationError) as refused:
        services.set_fee_plan(
            enrollment=enrollment,
            actor=counsellor_user,
            agreed_amount="5000",
            discount_percent=percent,
            discount_reason="Scholarship",
        )
    assert "discount_percent" in refused.value.detail


@pytest.mark.django_db
def test_a_full_percentage_discount_waives_the_fee(counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="5000",
        discount_percent="100",
        discount_reason="Staff ward",
        installments=[],
    )
    assert plan.payable == money("0")
    assert plan.status == "waived"


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
    # Ad hoc collection (no schedule): "next expected" is set by hand.
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000", installments=[]
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
        AuditAction.FEE_INSTALLMENTS_SET,
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
    # Somebody else's record is not theirs to know about: a 404, never a 403
    # that confirms the id exists.
    assert api_client_no_csrf.get(fee_url(other_enrollment)).status_code == 404
    assert (
        api_client_no_csrf.get(f"/api/v1/fees/students/{other_enrollment.student_id}/").status_code
        == 404
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


# ---------------------------------------------------------------------------
# Centres
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counsellor_at_another_centre_cannot_reach_the_fee(
    api_client_no_csrf, counsellor_user, other_branch_manager, enrollment
):
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="9000")
    payment = services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    api_client_no_csrf.force_login(other_branch_manager)
    assert api_client_no_csrf.get(fee_url(enrollment)).status_code == 404
    assert (
        api_client_no_csrf.put(
            fee_url(enrollment), {"agreed_amount": "1"}, format="json"
        ).status_code
        == 404
    )
    assert (
        api_client_no_csrf.post(
            f"{fee_url(enrollment)}payments/", {"amount": "1000", "method": "cash"}, format="json"
        ).status_code
        == 404
    )
    assert (
        api_client_no_csrf.post(
            f"/api/v1/fees/payments/{payment.pk}/void/", {"reason": "Not mine"}, format="json"
        ).status_code
        == 404
    )
    assert (
        api_client_no_csrf.get(f"/api/v1/fees/students/{enrollment.student_id}/").status_code == 404
    )
    overview = api_client_no_csrf.get("/api/v1/fees/overview/")
    assert overview.status_code == 200
    assert overview.json()["collected_today"] == "0.00"
    assert overview.json()["outstanding_total"] == "0.00"
    assert overview.json()["enrollments_without_plan"] == 0


@pytest.mark.django_db
def test_the_overview_counts_only_the_callers_centre(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, enrollment, other_branch_enrollment
):
    services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="9000")
    services.set_fee_plan(
        enrollment=other_branch_enrollment, actor=unbounded_superadmin, agreed_amount="5000"
    )
    api_client_no_csrf.force_login(counsellor_user)
    mine = api_client_no_csrf.get("/api/v1/fees/overview/").json()
    assert mine["outstanding_total"] == "9000.00"
    api_client_no_csrf.force_login(unbounded_superadmin)
    everything = api_client_no_csrf.get("/api/v1/fees/overview/").json()
    assert everything["outstanding_total"] == "14000.00"


# ---------------------------------------------------------------------------
# The instalment schedule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_new_fee_gets_six_instalments_thirty_days_apart(
    api_client_no_csrf, counsellor_user, enrollment
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        fee_url(enrollment),
        {"agreed_amount": "25000", "discount_amount": "1000", "discount_reason": "Early bird"},
        format="json",
    )
    assert response.status_code == 200, response.json()
    rows = response.json()["installments"]
    assert len(rows) == 6
    today = timezone.localdate()
    assert [row["due_on"] for row in rows] == [
        str(today + timedelta(days=30 * index)) for index in range(6)
    ]
    assert sum(money(row["amount"]) for row in rows) == money("24000")
    assert [row["status"] for row in rows] == ["pending"] + ["upcoming"] * 5
    # The plan's "next expected" follows the schedule, so the overdue flag,
    # the fees panel and the student's status keep reading the one field.
    assert response.json()["next_due_amount"] == rows[0]["amount"]
    assert response.json()["next_due_on"] == str(today)
    assert AuditLog.objects.filter(action=AuditAction.FEE_INSTALLMENTS_SET).count() == 1


@pytest.mark.django_db
def test_the_odd_paisa_lands_on_the_first_instalment(counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="10000", installment_count=3
    )
    amounts = [item.amount for item in plan.installments.all()]
    assert amounts == [money("3333.34"), money("3333.33"), money("3333.33")]


@pytest.mark.django_db
def test_the_counsellor_shapes_the_schedule_before_saving(
    api_client_no_csrf, counsellor_user, enrollment
):
    today = timezone.localdate()
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        fee_url(enrollment),
        {
            "agreed_amount": "9000",
            "installments": [
                {"amount": "5000", "due_on": str(today)},
                {"amount": "4000", "due_on": str(today + timedelta(days=45))},
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    rows = response.json()["installments"]
    assert [(row["amount"], row["due_on"]) for row in rows] == [
        ("5000.00", str(today)),
        ("4000.00", str(today + timedelta(days=45))),
    ]


@pytest.mark.django_db
def test_a_schedule_must_add_up_to_the_fee_after_discount(
    api_client_no_csrf, counsellor_user, enrollment
):
    today = timezone.localdate()
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        fee_url(enrollment),
        {"agreed_amount": "9000", "installments": [{"amount": "5000", "due_on": str(today)}]},
        format="json",
    )
    assert response.status_code == 400
    assert "add up to" in response.json()["error"]["details"]["installments"][0]
    assert not FeePlan.objects.exists()


@pytest.mark.django_db
def test_instalment_states_follow_the_ledger(counsellor_user, enrollment):
    today = timezone.localdate()
    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="12000",
        installments=[
            {"amount": "4000", "due_on": today - timedelta(days=40)},
            {"amount": "4000", "due_on": today - timedelta(days=10)},
            {"amount": "4000", "due_on": today + timedelta(days=20)},
        ],
    )
    # ₹5,000 covers the first instalment and a quarter of the second.
    services.record_payment(plan=plan, actor=counsellor_user, amount="5000")
    plan = FeePlan.objects.with_totals().get(pk=plan.pk)
    rows = services.installment_rows(plan)
    assert [row["status"] for row in rows] == ["paid", "overdue", "pending"]
    assert rows[1]["paid_amount"] == money("1000")
    assert rows[1]["balance"] == money("3000")
    assert plan.next_due_amount == money("3000")
    assert plan.next_due_on == today - timedelta(days=10)
    assert plan.is_overdue is True
    enrollment.student.refresh_from_db()
    assert enrollment.student.fee_status == FeeStatus.OVERDUE

    # Paying the rest of it moves "next expected" on to the third instalment.
    services.record_payment(plan=plan, actor=counsellor_user, amount="3000")
    plan.refresh_from_db()
    assert plan.next_due_on == today + timedelta(days=20)
    assert plan.is_overdue is False

    # Voiding brings the overdue instalment back.
    payment = plan.payments.get(amount=money("3000"))
    services.void_payment(payment=payment, actor=counsellor_user, reason="Wrong student")
    plan.refresh_from_db()
    assert plan.next_due_on == today - timedelta(days=10)


@pytest.mark.django_db
def test_the_schedule_can_be_replaced_later(api_client_no_csrf, counsellor_user, enrollment):
    today = timezone.localdate()
    plan = services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="6000")
    assert plan.installments.count() == 6
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.put(
        f"{fee_url(enrollment)}installments/",
        {
            "installments": [
                {"amount": "3000", "due_on": str(today)},
                {"amount": "3000", "due_on": str(today + timedelta(days=30))},
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert len(response.json()["installments"]) == 2
    # An empty schedule means "collect ad hoc".
    response = api_client_no_csrf.put(
        f"{fee_url(enrollment)}installments/", {"installments": []}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["installments"] == []


@pytest.mark.django_db
def test_changing_the_fee_respreads_the_schedule_over_its_dates(counsellor_user, enrollment):
    plan = services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="6000", installment_count=2
    )
    dates = [item.due_on for item in plan.installments.all()]
    services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount="8000", installment_count=2
    )
    plan.refresh_from_db()
    rows = list(plan.installments.all())
    assert [item.due_on for item in rows] == dates
    assert [item.amount for item in rows] == [money("4000"), money("4000")]


@pytest.mark.django_db
def test_a_trainer_cannot_touch_the_schedule(
    api_client_no_csrf, trainer, counsellor_user, enrollment
):
    services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="6000")
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.put(
        f"{fee_url(enrollment)}installments/", {"installments": []}, format="json"
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Who paid, and how
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_payment_keeps_its_method_reference_and_who_handed_it_over(
    api_client_no_csrf, counsellor_user, enrollment
):
    services.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="10000")
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        f"{fee_url(enrollment)}payments/",
        {
            "amount": "2000",
            "method": "upi",
            "reference": "UPI-4471-XK",
            "reference_name": "Father (Ramesh)",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["method"] == "upi"
    assert body["reference"] == "UPI-4471-XK"
    assert body["reference_name"] == "Father (Ramesh)"
    entry = AuditLog.objects.get(action=AuditAction.FEE_PAYMENT_RECORDED)
    assert entry.context["reference_name"] == "Father (Ramesh)"
    # And it is visible in the student's payment history.
    history = api_client_no_csrf.get(fee_url(enrollment)).json()["payments"]
    assert history[0]["reference_name"] == "Father (Ramesh)"
