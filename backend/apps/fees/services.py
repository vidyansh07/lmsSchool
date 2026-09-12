"""Fee services: every path to a number in the ledger ends here.

Rules, and the reason for each:

* **Permission is checked here, not only at the endpoint.** `fee.manage_any`
  is what lets a counsellor or manager set a fee, discount it, record a
  payment or void one. A caller that reaches these functions some other way —
  a management command, a future import — is held to the same rule.
* **A payment cannot exceed the balance.** Overpayment is a claim the ledger
  cannot substantiate; if a student really did pay more, the agreed fee is
  wrong and that is what should change.
* **A first payment is at least ₹1,000** — the registration payment — unless
  the whole fee is smaller than that.
* **Nothing is deleted.** A payment is voided with a reason; a plan is edited
  with the old and new values written to the audit log.
* **The student's coarse `fee_status` follows the ledger.** It stays on the
  student because the list screens filter on it, but it is derived from these
  numbers after every change rather than set by hand beside them.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.audit.models import AuditLog
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.common.identifiers import next_receipt_number
from apps.enrollments.models import LIVE_STATUSES, Enrollment
from apps.students.models import FeeStatus, StudentProfile

from .models import MIN_FIRST_PAYMENT, ZERO, FeePayment, FeePlan, PaymentMethod

RESOURCE_PLAN = "fee_plan"
RESOURCE_PAYMENT = "fee_payment"


def _require_manage(actor: User) -> None:
    if not has_capability(actor, Capability.FEE_MANAGE_ANY):
        raise AuthorityError("You do not have permission to manage fees.")


def _money(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ApplicationError({field: ["Enter an amount in rupees."]}) from exc
    if amount != amount.quantize(Decimal("0.01")):
        raise ApplicationError(
            {field: ["Amounts are kept to the paisa; use at most two decimals."]}
        )
    return amount.quantize(Decimal("0.01"))


def _plan_context(plan: FeePlan) -> dict[str, Any]:
    enrollment = plan.enrollment
    return {
        "enrollment_id": str(enrollment.pk),
        "enrollment_code": enrollment.code,
        "student_id": str(enrollment.student_id),
        "batch_code": enrollment.batch.code,
    }


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@transaction.atomic
def set_fee_plan(
    *,
    enrollment: Enrollment,
    actor: User,
    agreed_amount: Any,
    discount_amount: Any = ZERO,
    discount_reason: str = "",
    notes: str | None = None,
) -> FeePlan:
    """Create the fee for an enrolment, or change it. Audited with old and new."""
    _require_manage(actor)
    agreed = _money(agreed_amount, "agreed_amount")
    discount = _money(discount_amount, "discount_amount")
    problems: dict[str, list[str]] = {}
    if agreed < ZERO:
        problems["agreed_amount"] = ["The fee cannot be negative."]
    if discount < ZERO:
        problems["discount_amount"] = ["A discount cannot be negative."]
    elif discount > agreed:
        problems["discount_amount"] = ["A discount cannot be more than the fee."]
    if discount > ZERO and not discount_reason.strip():
        problems["discount_reason"] = [
            "Say why the discount was given; it is kept with the record."
        ]
    if problems:
        raise ApplicationError(problems)

    plan = FeePlan.objects.select_for_update().filter(enrollment=enrollment).first()
    if plan is None:
        plan = FeePlan(
            enrollment=enrollment,
            agreed_amount=agreed,
            discount_amount=discount,
            discount_reason=discount_reason.strip(),
            notes=(notes or "").strip(),
            created_by=actor,
            updated_by=actor,
        )
        plan.full_clean()
        plan.save()
        record(
            action=AuditAction.FEE_PLAN_SET,
            actor=actor,
            resource_type=RESOURCE_PLAN,
            resource_id=plan.pk,
            context={
                **_plan_context(plan),
                "agreed_amount": str(agreed),
                "discount_amount": str(discount),
                "discount_reason": plan.discount_reason,
            },
        )
        sync_student_fee_status(enrollment.student, actor=actor)
        return plan

    # Changing a fee that already has payments against it: the new payable
    # must still cover what has been received, or the ledger would show a
    # negative balance nobody can explain.
    if agreed - discount < plan.paid:
        raise ApplicationError(
            {
                "agreed_amount": [
                    f"₹{plan.paid:,.0f} has already been paid; "
                    "the fee after discount cannot be less than that."
                ]
            }
        )

    changes: dict[str, dict[str, str]] = {}
    for field, new_value in (
        ("agreed_amount", agreed),
        ("discount_amount", discount),
        ("discount_reason", discount_reason.strip()),
        ("notes", (notes if notes is not None else plan.notes).strip()),
    ):
        old_value = getattr(plan, field)
        if old_value != new_value:
            changes[field] = {"from": str(old_value), "to": str(new_value)}
            setattr(plan, field, new_value)
    if not changes:
        return plan

    plan.updated_by = actor
    plan.full_clean()
    plan.save()
    record(
        action=AuditAction.FEE_PLAN_UPDATED,
        actor=actor,
        resource_type=RESOURCE_PLAN,
        resource_id=plan.pk,
        context={**_plan_context(plan), "changes": changes},
    )
    sync_student_fee_status(enrollment.student, actor=actor)
    return plan


@transaction.atomic
def set_next_due(
    *, plan: FeePlan, actor: User, amount: Any = None, on: date | None = None
) -> FeePlan:
    """ "The next ₹N is expected by <date>." Both empty clears it."""
    _require_manage(actor)
    if (amount is None) != (on is None):
        raise ApplicationError(
            {"next_due_on": ["An expected payment needs both an amount and a date, or neither."]}
        )
    next_amount = _money(amount, "next_due_amount") if amount is not None else None
    if next_amount is not None:
        if next_amount <= ZERO:
            raise ApplicationError(
                {"next_due_amount": ["The expected amount must be more than zero."]}
            )
        if next_amount > plan.balance:
            raise ApplicationError(
                {"next_due_amount": [f"Only ₹{plan.balance:,.0f} is still owed."]}
            )

    previous = {"amount": plan.next_due_amount, "on": plan.next_due_on}
    if previous["amount"] == next_amount and previous["on"] == on:
        return plan
    plan.next_due_amount = next_amount
    plan.next_due_on = on
    plan.updated_by = actor
    plan.save(update_fields=["next_due_amount", "next_due_on", "updated_by", "updated_at"])
    record(
        action=AuditAction.FEE_NEXT_DUE_SET,
        actor=actor,
        resource_type=RESOURCE_PLAN,
        resource_id=plan.pk,
        context={
            **_plan_context(plan),
            "from": {
                "amount": str(previous["amount"]) if previous["amount"] is not None else None,
                "on": previous["on"].isoformat() if previous["on"] else None,
            },
            "to": {
                "amount": str(next_amount) if next_amount is not None else None,
                "on": on.isoformat() if on else None,
            },
        },
    )
    return plan


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@transaction.atomic
def record_payment(
    *,
    plan: FeePlan,
    actor: User,
    amount: Any,
    paid_on: date | None = None,
    method: str = PaymentMethod.CASH,
    reference: str = "",
    note: str = "",
) -> FeePayment:
    _require_manage(actor)
    plan = (
        FeePlan.objects.select_for_update()
        .select_related("enrollment__student", "enrollment__batch")
        .get(pk=plan.pk)
    )
    value = _money(amount, "amount")
    when = paid_on or timezone.localdate()
    problems: dict[str, list[str]] = {}
    if value <= ZERO:
        problems["amount"] = ["A payment must be more than zero."]
    if when > timezone.localdate():
        problems["paid_on"] = ["A payment cannot be dated in the future."]
    if method not in PaymentMethod.values:
        problems["method"] = ["Choose how it was paid."]
    if problems:
        raise ApplicationError(problems)

    balance = plan.balance
    if value > balance:
        raise ApplicationError(
            {
                "amount": [
                    f"Only ₹{balance:,.0f} is still owed. "
                    "If the student really paid more, change the agreed fee first."
                ]
            }
        )
    has_paid_before = plan.payments.filter(voided_at__isnull=True).exists()
    if not has_paid_before and value < MIN_FIRST_PAYMENT and plan.payable >= MIN_FIRST_PAYMENT:
        raise ApplicationError(
            {
                "amount": [
                    "The first payment is the registration fee: "
                    f"at least ₹{MIN_FIRST_PAYMENT:,.0f}."
                ]
            }
        )

    payment = FeePayment(
        plan=plan,
        receipt_number=next_receipt_number(),
        amount=value,
        paid_on=when,
        method=method,
        reference=reference.strip(),
        note=note.strip(),
        recorded_by=actor,
    )
    payment.full_clean()
    payment.save()

    # An expected payment that has now arrived is no longer expected.
    if plan.next_due_amount is not None and value >= plan.next_due_amount:
        plan.next_due_amount = None
        plan.next_due_on = None
        plan.updated_by = actor
        plan.save(update_fields=["next_due_amount", "next_due_on", "updated_by", "updated_at"])

    record(
        action=AuditAction.FEE_PAYMENT_RECORDED,
        actor=actor,
        resource_type=RESOURCE_PAYMENT,
        resource_id=payment.pk,
        context={
            **_plan_context(plan),
            "receipt_number": payment.receipt_number,
            "amount": str(value),
            "paid_on": when.isoformat(),
            "method": method,
            "reference": payment.reference,
            "balance_after": str(plan.balance),
        },
    )
    sync_student_fee_status(plan.enrollment.student, actor=actor)
    return payment


@transaction.atomic
def void_payment(*, payment: FeePayment, actor: User, reason: str) -> FeePayment:
    """Mark a payment as a mistake. It stays in the ledger, crossed out."""
    _require_manage(actor)
    if not reason.strip():
        raise ApplicationError(
            {"reason": ["Say why this payment is being voided; it is kept with the record."]}
        )
    if payment.is_voided:
        raise ConflictError({"payment": ["This payment has already been voided."]})
    payment.voided_at = timezone.now()
    payment.voided_by = actor
    payment.void_reason = reason.strip()
    payment.save(update_fields=["voided_at", "voided_by", "void_reason", "updated_at"])
    record(
        action=AuditAction.FEE_PAYMENT_VOIDED,
        actor=actor,
        resource_type=RESOURCE_PAYMENT,
        resource_id=payment.pk,
        context={
            **_plan_context(payment.plan),
            "receipt_number": payment.receipt_number,
            "amount": str(payment.amount),
            "reason": payment.void_reason,
        },
    )
    sync_student_fee_status(payment.plan.enrollment.student, actor=actor)
    return payment


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


def plans_for_student(student: StudentProfile):
    return (
        FeePlan.objects.filter(enrollment__student=student)
        .select_related("enrollment__batch", "enrollment__course")
        .with_totals()
        .order_by("-created_at")
    )


def student_fee_summary(student: StudentProfile) -> dict[str, Any]:
    """Totals across every course the student is on, plus the plans themselves."""
    plans = list(plans_for_student(student))
    payable = sum((plan.payable for plan in plans), ZERO)
    paid = sum((plan.paid for plan in plans), ZERO)
    next_due = min(
        (plan for plan in plans if plan.next_due_on and plan.balance > ZERO),
        key=lambda plan: plan.next_due_on,
        default=None,
    )
    live_enrollments = student.enrollments.filter(status__in=LIVE_STATUSES)
    without_plan = live_enrollments.exclude(pk__in=[plan.enrollment_id for plan in plans]).count()
    return {
        "payable_total": payable,
        "paid_total": paid,
        "balance_total": payable - paid,
        "next_due_amount": next_due.next_due_amount if next_due else None,
        "next_due_on": next_due.next_due_on if next_due else None,
        "is_overdue": any(plan.is_overdue for plan in plans),
        "enrollments_without_plan": without_plan,
        "plans": plans,
    }


def fee_history(enrollment: Enrollment):
    """Every audited change to this enrolment's fee, newest first."""
    plan = FeePlan.objects.filter(enrollment=enrollment).first()
    if plan is None:
        return AuditLog.objects.none()
    payment_ids = [str(pk) for pk in plan.payments.values_list("pk", flat=True)]
    return (
        AuditLog.objects.filter(
            Q(resource_type=RESOURCE_PLAN, resource_id=str(plan.pk))
            | Q(resource_type=RESOURCE_PAYMENT, resource_id__in=payment_ids)
        )
        .select_related("actor")
        .order_by("-created_at")
    )


def sync_student_fee_status(student: StudentProfile, *, actor: User) -> None:
    """The coarse flag on the student follows the ledger.

    Kept because the students table filters on it; derived so it can never
    disagree with the numbers beside it. A student with no fee plan at all is
    left as they were — there is nothing to derive from.
    """
    from apps.students.services import set_fee_status

    plans = list(
        FeePlan.objects.filter(
            enrollment__student=student, enrollment__status__in=LIVE_STATUSES
        ).with_totals()
    )
    if not plans:
        return
    payable = sum((plan.payable for plan in plans), ZERO)
    paid = sum((plan.paid for plan in plans), ZERO)
    if payable <= ZERO:
        status = FeeStatus.WAIVED
    elif paid >= payable:
        status = FeeStatus.PAID
    elif any(plan.is_overdue for plan in plans):
        status = FeeStatus.OVERDUE
    elif paid > ZERO:
        status = FeeStatus.PARTIAL
    else:
        status = FeeStatus.PENDING
    if student.fee_status != status:
        set_fee_status(
            profile=student, fee_status=status, actor=actor, note="Derived from the fee ledger."
        )


def fees_overview(*, limit: int = 20) -> dict[str, Any]:
    """The counsellor's fees panel: what came in, who is late, who has no fee."""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    live = FeePayment.objects.filter(voided_at__isnull=True)

    def collected(since: date) -> Decimal:
        return Decimal(live.filter(paid_on__gte=since).aggregate(total=Sum("amount"))["total"] or 0)

    plans = (
        FeePlan.objects.filter(enrollment__status__in=LIVE_STATUSES)
        .select_related("enrollment__student__user", "enrollment__batch")
        .with_totals()
    )
    overdue = sorted(
        (plan for plan in plans if plan.is_overdue),
        key=lambda plan: plan.next_due_on,
    )
    due_soon = sorted(
        (
            plan
            for plan in plans
            if plan.next_due_on and plan.next_due_on >= today and plan.balance > ZERO
        ),
        key=lambda plan: plan.next_due_on,
    )
    unpaid = [plan for plan in plans if plan.paid <= ZERO and plan.payable > ZERO]
    without_plan = Enrollment.objects.filter(
        status__in=LIVE_STATUSES, fee_plan__isnull=True
    ).count()
    outstanding = sum((plan.balance for plan in plans if plan.balance > ZERO), ZERO)
    return {
        "collected_today": collected(today),
        "collected_this_week": collected(week_start),
        "collected_this_month": collected(month_start),
        "outstanding_total": outstanding,
        "overdue_count": len(overdue),
        "unpaid_count": len(unpaid),
        "enrollments_without_plan": without_plan,
        "overdue": overdue[:limit],
        "due_soon": due_soon[:limit],
    }
