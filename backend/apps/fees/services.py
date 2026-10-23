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
* **A schedule must add up.** The instalments of a plan always sum to the
  fee after discount, so "what is still owed" and "what is still scheduled"
  are the same number. The plan's "next expected" fields are kept in step
  with the schedule after every change, so the overdue flag, the counsellor's
  fees panel and the student's fee status keep reading the one field they
  always read.
* **Nothing is deleted.** A payment is voided with a reason; a plan is edited
  with the old and new values written to the audit log.
* **The student's coarse `fee_status` follows the ledger.** It stays on the
  student because the list screens filter on it, but it is derived from these
  numbers after every change rather than set by hand beside them.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.audit.models import AuditLog
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.common.identifiers import next_receipt_number
from apps.enrollments.models import LIVE_STATUSES, Enrollment, EnrollmentStatus
from apps.enrollments.services import set_enrollment_status
from apps.notifications.models import MessageEvent
from apps.students.models import FeeStatus, StudentProfile

from . import mail
from .models import (
    DEFAULT_INSTALLMENT_COUNT,
    DEFAULT_INSTALLMENT_GAP_DAYS,
    LIVE_PAYMENT,
    MAX_INSTALLMENTS,
    MIN_FIRST_PAYMENT,
    UNCLEARED_ON_ARRIVAL,
    ZERO,
    ClearingStatus,
    FeeInstallment,
    FeePayment,
    FeePlan,
    InstallmentStatus,
    PaymentKind,
    PaymentMethod,
    installment_rows,
)
from .signals import payment_recorded

logger = logging.getLogger("grras.fees")

HUNDRED = Decimal("100")

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


def _percent(value: Any) -> Decimal:
    try:
        percent = Decimal(str(value))
    except Exception as exc:
        raise ApplicationError({"discount_percent": ["Enter a percentage, like 10."]}) from exc
    if percent != percent.quantize(Decimal("0.01")):
        raise ApplicationError({"discount_percent": ["Use at most two decimals, like 12.5."]})
    if percent < ZERO or percent > HUNDRED:
        raise ApplicationError({"discount_percent": ["A percentage is between 0 and 100."]})
    return percent.quantize(Decimal("0.01"))


def discount_for_percent(agreed: Decimal, percent: Decimal) -> Decimal:
    """The rupee discount a percentage of the fee comes to, to the paisa."""
    return (agreed * percent / HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def refund_payment(*, payment: FeePayment, actor: User, reason: str) -> FeePayment:
    """Give a payment back.

    A different act from voiding. A void says the payment should never have been
    recorded — a typo, a double entry. A refund says it was recorded correctly
    and the money has since gone back to the student, which is what happens to a
    booking amount when somebody decides not to join.

    Both stop the payment counting towards what has been paid, and the ledger
    keeps the row either way so an accountant can tell the two apart.

    Only a payment taken on refundable terms can be refunded. Whether the
    institution gives money back is a commercial decision made when the money is
    taken, not one to be reopened months later by whoever is on the screen.
    """
    _require_manage(actor)
    if not reason.strip():
        raise ApplicationError(
            {"reason": ["Say why this payment is being refunded; it is kept with the record."]}
        )
    if payment.is_voided:
        raise ConflictError({"payment": ["This payment was voided; there is nothing to refund."]})
    if payment.is_refunded:
        raise ConflictError({"payment": ["This payment has already been refunded."]})
    if not payment.is_refundable:
        raise ApplicationError(
            {
                "payment": [
                    "This payment was not taken on refundable terms, so it cannot be refunded."
                ]
            }
        )

    payment.refunded_at = timezone.now()
    payment.refunded_by = actor
    payment.refund_reason = reason.strip()
    payment.full_clean()
    payment.save(update_fields=["refunded_at", "refunded_by", "refund_reason", "updated_at"])

    record(
        action=AuditAction.FEE_PAYMENT_VOIDED,
        actor=actor,
        resource_type=RESOURCE_PAYMENT,
        resource_id=payment.pk,
        context={
            "receipt_number": payment.receipt_number,
            "amount": str(payment.amount),
            "kind": payment.kind,
            "refunded": True,
            "reason": payment.refund_reason,
        },
    )
    return payment


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
    discount_percent: Any = None,
    discount_reason: str = "",
    notes: str | None = None,
    installments: list[dict[str, Any]] | None = None,
    installment_count: int | None = None,
) -> FeePlan:
    """Create the fee for an enrolment, or change it. Audited with old and new.

    `installments` is the schedule the counsellor shaped: a list of
    `{"amount", "due_on"}`; an empty list means "collect ad hoc, no schedule".
    Left out, a new plan gets the default schedule (`installment_count`
    instalments, default six, thirty days apart from today), and an existing
    plan keeps its dates with the amounts re-spread over them if the fee
    changed.

    A discount is given either as rupees (`discount_amount`) or as a
    percentage of the fee (`discount_percent`, what a counsellor types: `10`
    is 10%). Given as a percentage, the rupee amount is worked out here and
    both are kept, so the receipt and the ledger never round it differently.
    """
    _require_manage(actor)
    agreed = _money(agreed_amount, "agreed_amount")
    percent = None if discount_percent in (None, "") else _percent(discount_percent)
    if percent is not None:
        # A percentage is an instruction to work out the money, not a second
        # kind of discount. It is turned into rupees here, once, and the rupees
        # are what the ledger keeps.
        discount = discount_for_percent(agreed, percent)
    else:
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
            discount_percent=percent,
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
                "discount_percent": None if percent is None else str(percent),
                "discount_reason": plan.discount_reason,
            },
        )
        if installments is None:
            installments = default_installments(
                plan.payable, count=installment_count, start=timezone.localdate()
            )
        _replace_installments(plan, actor=actor, items=installments)
        sync_student_fee_status(enrollment.student, actor=actor)
        mail.queue_safely(mail.email_statement, plan)
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
        ("discount_percent", percent),
        ("discount_reason", discount_reason.strip()),
        ("notes", (notes if notes is not None else plan.notes).strip()),
    ):
        old_value = getattr(plan, field)
        if old_value != new_value:
            changes[field] = {"from": str(old_value), "to": str(new_value)}
            setattr(plan, field, new_value)
    if not changes:
        if installments is not None:
            _replace_installments(plan, actor=actor, items=installments)
            mail.queue_safely(mail.email_statement, plan)
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
    if installments is not None:
        _replace_installments(plan, actor=actor, items=installments)
    elif "agreed_amount" in changes or "discount_amount" in changes:
        existing = list(plan.installments.all())
        if existing:
            respread = default_installments(
                plan.payable, count=len(existing), dates=[item.due_on for item in existing]
            )
            _replace_installments(plan, actor=actor, items=respread)
    sync_student_fee_status(enrollment.student, actor=actor)
    if installments is not None or {"agreed_amount", "discount_amount"} & changes.keys():
        mail.queue_safely(mail.email_statement, plan)
    return plan


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def default_installments(
    payable: Decimal,
    *,
    count: int | None = None,
    start: date | None = None,
    dates: list[date] | None = None,
    gap_days: int = DEFAULT_INSTALLMENT_GAP_DAYS,
) -> list[dict[str, Any]]:
    """Split `payable` evenly into `count` instalments, the odd paisa on the first.

    Dates are `start`, then every `gap_days`, unless `dates` are given
    (which is how an existing schedule keeps its dates when the fee changes).
    Nothing to collect, or a count of zero, is an empty schedule.
    """
    if dates is not None:
        count = len(dates)
    if count is None:
        count = DEFAULT_INSTALLMENT_COUNT
    if count <= 0 or payable <= ZERO:
        return []
    count = min(count, MAX_INSTALLMENTS)
    first_day = start or timezone.localdate()
    each = (payable / count).quantize(Decimal("0.01"))
    remainder = payable - each * count
    items: list[dict[str, Any]] = []
    for index in range(count):
        amount = each + remainder if index == 0 else each
        due_on = dates[index] if dates is not None else first_day + timedelta(days=gap_days * index)
        items.append({"amount": amount, "due_on": due_on})
    return items


def _clean_installments(plan: FeePlan, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(items) > MAX_INSTALLMENTS:
        raise ApplicationError(
            {"installments": [f"At most {MAX_INSTALLMENTS} instalments can be scheduled."]}
        )
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        amount = _money(item.get("amount"), "installments")
        due_on = item.get("due_on")
        if amount <= ZERO:
            raise ApplicationError(
                {"installments": [f"Instalment {index + 1} must be more than zero."]}
            )
        if not isinstance(due_on, date):
            raise ApplicationError({"installments": [f"Instalment {index + 1} needs a due date."]})
        cleaned.append({"amount": amount, "due_on": due_on})
    cleaned.sort(key=lambda item: item["due_on"])
    total = sum((item["amount"] for item in cleaned), ZERO)
    if cleaned and total != plan.payable:
        raise ApplicationError(
            {
                "installments": [
                    f"The instalments add up to ₹{total:,.2f}; "
                    f"the fee after discount is ₹{plan.payable:,.2f}. They must match."
                ]
            }
        )
    return cleaned


def _replace_installments(plan: FeePlan, *, actor: User, items: list[dict[str, Any]]) -> None:
    cleaned = _clean_installments(plan, items)
    before = [
        {"amount": str(item.amount), "due_on": item.due_on.isoformat()}
        for item in plan.installments.all()
    ]
    after = [
        {"amount": str(item["amount"]), "due_on": item["due_on"].isoformat()} for item in cleaned
    ]
    if before == after:
        _sync_next_due_from_schedule(plan, actor=actor)
        return
    plan.installments.all().delete()
    FeeInstallment.objects.bulk_create(
        [
            FeeInstallment(plan=plan, sequence=index + 1, **item)
            for index, item in enumerate(cleaned)
        ]
    )
    record(
        action=AuditAction.FEE_INSTALLMENTS_SET,
        actor=actor,
        resource_type=RESOURCE_PLAN,
        resource_id=plan.pk,
        context={**_plan_context(plan), "from": before, "to": after},
    )
    _sync_next_due_from_schedule(plan, actor=actor)


@transaction.atomic
def set_installments(*, plan: FeePlan, actor: User, items: list[dict[str, Any]]) -> FeePlan:
    """Replace the schedule. An empty list goes back to ad hoc collection."""
    _require_manage(actor)
    # Locked without the totals annotation: Postgres refuses FOR UPDATE on an
    # aggregate. The sync step fetches the totals it needs itself.
    plan = FeePlan.objects.select_for_update().get(pk=plan.pk)
    _replace_installments(plan, actor=actor, items=items)
    sync_student_fee_status(plan.enrollment.student, actor=actor)
    mail.queue_safely(mail.email_statement, plan)
    return plan


def _sync_next_due_from_schedule(plan: FeePlan, *, actor: User) -> None:
    """The plan's "next ₹N expected by <date>" follows the schedule, when there is one.

    The first instalment that is not fully covered is what is expected next;
    its uncovered part is the amount. Everything that already reads the
    `next_due_*` fields — the overdue flag, the fees panel, the student's
    `fee_status` — keeps working without knowing a schedule exists.
    """
    installments = list(plan.installments.all())
    if not installments:
        return
    fresh = FeePlan.objects.with_totals().get(pk=plan.pk)
    rows = installment_rows(fresh, installments)
    nxt = next((row for row in rows if row["status"] != InstallmentStatus.PAID), None)
    amount = nxt["balance"] if nxt else None
    on = nxt["due_on"] if nxt else None
    if plan.next_due_amount == amount and plan.next_due_on == on:
        return
    plan.next_due_amount = amount
    plan.next_due_on = on
    plan.updated_by = actor
    plan.save(update_fields=["next_due_amount", "next_due_on", "updated_by", "updated_at"])


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
    reference_name: str = "",
    note: str = "",
    kind: str = PaymentKind.INSTALMENT,
    is_refundable: bool = False,
    bank=None,
    category=None,
    apply_tax: bool = False,
    tax_group=None,
    instalment=None,
) -> FeePayment:
    """Append a payment to a plan.

    `bank`, `category`, `apply_tax` and `tax_group` are recorded facts about
    one payment, never inputs to a calculation: the amount is the amount
    (owner's decision, 23 October 2026 — record the tax, do not compute it).

    `clearing_status` is derived from the method, not passed in. A cheque, a
    draft or a cash deposit is money taken that the bank has not confirmed, so
    it starts `UNCLEARED` and somebody marks it cleared later; everything
    else is settled the moment it is recorded. Deriving it here rather than
    accepting it means no screen can record a cheque that claims to have
    already cleared.
    """
    _require_manage(actor)
    if kind not in PaymentKind.values:
        raise ApplicationError({"kind": ["Choose what this payment was for."]})
    if is_refundable and kind != PaymentKind.REGISTRATION:
        # Refundable terms exist for the booking amount. An instalment of the
        # course fee is payment for teaching that has been or will be given, and
        # giving it back is a credit note, not a refund of this row.
        raise ApplicationError(
            {"is_refundable": ["Only a registration payment can be taken on refundable terms."]}
        )
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
    has_paid_before = plan.payments.filter(LIVE_PAYMENT).exists()
    if not has_paid_before and value < MIN_FIRST_PAYMENT and plan.payable >= MIN_FIRST_PAYMENT:
        raise ApplicationError(
            {
                "amount": [
                    "The first payment is the registration fee: "
                    f"at least ₹{MIN_FIRST_PAYMENT:,.0f}."
                ]
            }
        )

    if instalment is not None and instalment.plan_id != plan.pk:
        raise ApplicationError({"instalment": ["That instalment belongs to another fee."]})

    payment = FeePayment(
        plan=plan,
        receipt_number=next_receipt_number(),
        amount=value,
        paid_on=when,
        method=method,
        reference=reference.strip(),
        reference_name=reference_name.strip(),
        note=note.strip(),
        kind=kind,
        is_refundable=is_refundable,
        recorded_by=actor,
        bank=bank,
        category=category,
        apply_tax=bool(apply_tax),
        tax_group=tax_group if apply_tax else None,
        instalment=instalment,
        clearing_status=(
            ClearingStatus.UNCLEARED if method in UNCLEARED_ON_ARRIVAL else ClearingStatus.CLEARED
        ),
        cleared_on=None if method in UNCLEARED_ON_ARRIVAL else when,
    )
    payment.full_clean()
    payment.save()

    # An expected payment that has now arrived is no longer expected. With a
    # schedule, "expected next" is the next uncovered instalment instead.
    if plan.installments.exists():
        _sync_next_due_from_schedule(plan, actor=actor)
    elif plan.next_due_amount is not None and value >= plan.next_due_amount:
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
            "clearing": payment.clearing_status,
            "reference": payment.reference,
            "reference_name": payment.reference_name,
            "balance_after": str(plan.balance),
        },
    )
    sync_student_fee_status(plan.enrollment.student, actor=actor)
    mail.queue_safely(mail.email_receipt, payment)
    _announce_payment(payment, event=MessageEvent.PAYMENT_MADE)
    if not mail.is_suppressed():
        payment_recorded.send(sender=FeePayment, payment=payment, actor=actor)
    return payment


def _announce_payment(payment: FeePayment, *, event: str) -> None:
    """Tell whoever the message matrix says to tell about this payment.

    Wrapped and swallowed on purpose: a notification that fails must never
    roll back the payment that caused it. The receipt is the record; this is
    a courtesy on top of it.
    """
    from apps.notifications.messaging import deliver_for_event
    from apps.notifications.models import NotificationKind

    titles = {
        MessageEvent.PAYMENT_MADE: f"Payment of {payment.amount} received",
        MessageEvent.CHEQUE_CLEARANCE: f"Your payment of {payment.amount} has cleared",
        MessageEvent.CHEQUE_BOUNCED: f"Your payment of {payment.amount} did not clear",
    }
    try:
        deliver_for_event(
            event,
            student=payment.plan.enrollment.student,
            kind=NotificationKind.FEE_PAYMENT_RECEIVED,
            title=titles.get(event, "Payment update"),
            body=f"Receipt {payment.receipt_number}.",
            link_path="/my-fees",
            resource_type=RESOURCE_PAYMENT,
            resource_id=payment.pk,
        )
    except Exception:
        logger.exception("could not announce payment %s", payment.pk)


@transaction.atomic
def mark_payment_cleared(*, payment: FeePayment, actor: User, cleared_on: date | None = None):
    """The bank honoured it.

    Only moves a payment that is waiting: clearing one twice is a no-op worth
    refusing rather than a second audit entry saying the same thing. A voided
    payment cannot clear — there is nothing there to clear.
    """
    _require_manage(actor)
    if payment.voided_at is not None:
        raise ApplicationError({"non_field_errors": ["A voided payment cannot clear."]})
    if payment.clearing_status != ClearingStatus.UNCLEARED:
        raise ApplicationError({"non_field_errors": ["This payment is not waiting to clear."]})
    when = cleared_on or timezone.localdate()
    if when < payment.paid_on:
        raise ApplicationError({"cleared_on": ["It cannot have cleared before it was taken."]})
    payment.clearing_status = ClearingStatus.CLEARED
    payment.cleared_on = when
    payment.cleared_by = actor
    payment.save(update_fields=["clearing_status", "cleared_on", "cleared_by", "updated_at"])
    _announce_payment(payment, event=MessageEvent.CHEQUE_CLEARANCE)
    record(
        action=AuditAction.FEE_PAYMENT_CLEARED,
        actor=actor,
        resource_type=RESOURCE_PAYMENT,
        resource_id=payment.pk,
        context={**_plan_context(payment.plan), "receipt_number": payment.receipt_number},
        durable=False,
    )
    return payment


@transaction.atomic
def mark_payment_bounced(*, payment: FeePayment, actor: User, reason: str):
    """The bank did not honour it.

    A bounce is not a new kind of state for the money: the cheque was never
    payment, so the payment is *voided* — the existing act for "this should
    never have counted" — which takes it out of received, out of the balance
    and out of every total while leaving the record of it. `clearing_status`
    records why, so the fee tab can say "bounced" rather than the vaguer
    "voided".
    """
    _require_manage(actor)
    if payment.clearing_status != ClearingStatus.UNCLEARED:
        raise ApplicationError({"non_field_errors": ["This payment is not waiting to clear."]})
    if not (reason or "").strip():
        raise ApplicationError({"reason": ["Say what the bank said."]})

    payment.clearing_status = ClearingStatus.BOUNCED
    payment.save(update_fields=["clearing_status", "updated_at"])
    _announce_payment(payment, event=MessageEvent.CHEQUE_BOUNCED)
    # Voiding does the money part, the audit entry and the fee-status sync.
    return void_payment(payment=payment, actor=actor, reason=f"Bounced: {reason.strip()}")


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
    _sync_next_due_from_schedule(payment.plan, actor=actor)
    sync_student_fee_status(payment.plan.enrollment.student, actor=actor)
    return payment


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


def plans_for_student(student: StudentProfile):
    return (
        FeePlan.objects.filter(enrollment__student=student)
        .select_related("enrollment__batch", "enrollment__course")
        .prefetch_related("installments")
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


def _forget_overviews() -> None:
    """Every ledger write makes the collections overview stale."""
    from apps.common.caching import forget

    forget("fees:overview")


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
    _forget_overviews()


def fee_collections_trend(*, user: User, weeks: int = 12) -> list[dict[str, Any]]:
    """What was actually collected, per week, over the enrolments the caller sees.

    Lives here rather than in `apps/reporting/metrics.py` because it is fee
    data: the scoping that matters is `visible_enrollments`, the capability
    that matters is `fee.view_any`, and `fees_overview` right above it already
    established both. A reporting-side copy would have to re-derive them.

    Two constraints this shares with every other figure in this module.
    Voided payments are excluded -- a receipt that was cancelled was never
    money, and including it makes a collections chart disagree with the
    ledger it came from. And the aggregate is a `Sum` over `FeePayment`, not
    over `FeePlan`, because `FeePlan.paid`/`payable`/`balance`/`status` are
    Python properties rather than columns; grouping a queryset by one of them
    raises `FieldError`.

    `paid_on` is a `DateField`, so `TruncWeek` needs no timezone pinning
    here -- unlike the enrolment trend, which buckets a datetime.
    """
    from django.db.models.functions import TruncWeek

    from apps.batches.access import visible_enrollments

    since = timezone.localdate() - timedelta(weeks=weeks)
    live = FeePayment.objects.filter(
        LIVE_PAYMENT,
        plan__enrollment__in=visible_enrollments(user),
        paid_on__gte=since,
    )
    rows = (
        live.annotate(week=TruncWeek("paid_on"))
        .values("week")
        .annotate(amount=Sum("amount"), receipts=Count("id"))
        .order_by("week")
    )
    return [
        {
            "week": row["week"],
            "amount": Decimal(row["amount"] or 0),
            "receipts": row["receipts"],
        }
        for row in rows
    ]


def fees_overview(*, user: User, limit: int = 20) -> dict[str, Any]:
    """The counsellor's fees panel: what came in, who is late, who has no fee.

    Computed over the enrolments the caller may see — their centre — so a
    bounded counsellor's "collected today" is about their own desk.
    """
    from apps.batches.access import visible_enrollments

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    enrollments = visible_enrollments(user)
    live = FeePayment.objects.filter(LIVE_PAYMENT, plan__enrollment__in=enrollments)

    def collected(since: date) -> Decimal:
        return Decimal(live.filter(paid_on__gte=since).aggregate(total=Sum("amount"))["total"] or 0)

    plans = (
        FeePlan.objects.filter(enrollment__status__in=LIVE_STATUSES, enrollment__in=enrollments)
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
    without_plan = enrollments.filter(status__in=LIVE_STATUSES, fee_plan__isnull=True).count()
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


def ledger_reconciliation(*, user: User) -> dict[str, Any]:
    """Every rupee the institute has charged, placed in exactly one bucket.

    The fees panel answers "how are we doing": collected this month, who is
    late. It cannot answer "does it add up", because it never states what was
    charged in the first place and it drops a cancelled admission entirely —
    so money on a cancelled enrolment leaves the screen without ever being
    accounted for.

    This states the identity instead::

        charged = (received - refund due) + written off + outstanding + unreconciled

    and computes each side independently, so the two can disagree and say so.
    A summary that derives the last number by subtraction always balances and
    therefore proves nothing.

    What each bucket means
    ----------------------
    ``charged``      every plan's agreed fee less its discount, cancelled
                     admissions included. What the institute said was owed.
    ``received``     money it holds: payments that were neither voided nor
                     refunded. A void is a mistake and was never money, so it
                     is absent from both sides rather than netted off.
    ``refunded``     money taken and given back. Reported because an owner
                     asks for it, and *not* part of the identity — it is
                     already excluded from ``received``.
    ``written_off``  the balance on a cancelled admission the institute has
                     decided not to pursue.
    ``outstanding``  still owed on a live admission.
    ``refund_due``   money held that is no longer the institute's: somebody
                     paid more than the cancellation charge they ended up
                     owing. A liability from the moment of cancellation,
                     whether or not anybody has paid it back yet.
    ``unreconciled`` what the others fail to account for. It should be zero,
                     and it is — every rupee charged is now either held,
                     written off, still owed, or owed back. It is reported
                     rather than assumed so that the day it stops being zero,
                     somebody finds out.

    Scoped like every other figure here: computed over the enrolments the
    caller can already see, so a counsellor at one centre reconciles their own
    centre and not the institute.
    """
    from apps.batches.access import visible_enrollments

    enrollments = visible_enrollments(user)
    plans = FeePlan.objects.filter(enrollment__in=enrollments).with_totals()

    charged = ZERO
    received = ZERO
    written_off = ZERO
    outstanding = ZERO
    cancelled_count = 0

    refund_due = ZERO
    for plan in plans.select_related("enrollment"):
        # What was charged, before any cancellation. A settled plan still owes
        # its history to this figure.
        charged += plan.gross_payable
        received += plan.paid
        written_off += plan.written_off
        refund_due += plan.refund_due
        # What is still owed: the fee on a live admission, the agreed charge on
        # a cancelled one. A credit balance is clamped — somebody who overpaid
        # owes nothing, and letting it go negative would quietly reduce what
        # everybody else owes.
        outstanding += max(plan.payable - plan.paid, ZERO)

    refunded = Decimal(
        FeePayment.objects.filter(
            plan__enrollment__in=enrollments, refunded_at__isnull=False, voided_at__isnull=True
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    cancelled_count = enrollments.exclude(status__in=LIVE_STATUSES).count()

    return {
        "charged": charged,
        "received": received,
        "refunded": refunded,
        "refund_due": refund_due,
        "written_off": written_off,
        "outstanding": outstanding,
        # `refund_due` is subtracted because money owed back is held but not
        # earned. Without it a cancellation where the student had overpaid
        # would leave the identity short by exactly the amount to be returned.
        "unreconciled": charged - (received - refund_due) - written_off - outstanding,
        "cancelled_enrolments": cancelled_count,
    }


def cancel_admission(
    *,
    enrollment: Enrollment,
    actor: User,
    cancellation_charge: Any = ZERO,
    reason: str,
) -> FeePlan:
    """End an admission and settle its money in one act.

    Cancelling used to be a status change. It stopped the chasing and settled
    nothing: the fee was still charged, the balance was owed by nobody, and no
    decision to write it off had been recorded anywhere — so the money sat in
    no bucket and the ledger could not be made to add up.

    This decides all of it at once, because they are one decision in real life.
    Somebody looks at how much of the course has run, agrees a figure, and
    everything else follows:

    * the charge becomes what is owed, so a student who has paid nothing still
      owes it and still appears in what is outstanding;
    * the rest of the original fee is written off — recorded as a decision,
      not lost;
    * anything paid above the charge becomes a refund due, which is a
      liability from this moment whether or not anybody has paid it back yet.

    The original fee stays on the row. A cancellation that overwrote it would
    make "what did we charge" unanswerable, and that is the figure every
    reconciliation starts from.

    Cancelling is not reversible here. A student who comes back enrols again —
    which the model already allows, since only live enrolments are barred from
    repeating — and that is a new admission with its own fee, not this one
    reinstated with its history rewritten.
    """
    _require_manage(actor)
    if not reason.strip():
        raise ApplicationError(
            {"reason": ["Say why the admission is being cancelled; it is kept with the record."]}
        )

    charge = _money(cancellation_charge, "cancellation_charge")
    if charge < ZERO:
        raise ApplicationError({"cancellation_charge": ["A charge cannot be negative."]})

    with transaction.atomic():
        plan = (
            FeePlan.objects.select_for_update()
            .select_related("enrollment__student__user", "enrollment__batch")
            .filter(enrollment=enrollment)
            .first()
        )
        if plan is None:
            raise ApplicationError(
                {"enrollment": ["This admission has no fee to settle; cancel the enrolment."]}
            )
        if plan.is_cancelled:
            raise ConflictError({"enrollment": ["This admission has already been cancelled."]})
        if charge > plan.gross_payable:
            raise ApplicationError(
                {
                    "cancellation_charge": [
                        "A cancellation charge cannot be more than the fee itself."
                    ]
                }
            )

        plan.settled_amount = charge
        plan.cancelled_at = timezone.now()
        plan.cancelled_by = actor
        plan.cancellation_reason = reason.strip()
        # Nothing further is expected: what is owed is the charge, and chasing
        # a schedule drawn up for the full fee would be wrong.
        plan.next_due_amount = None
        plan.next_due_on = None
        plan.updated_by = actor
        plan.full_clean()
        plan.save(
            update_fields=[
                "settled_amount",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "next_due_amount",
                "next_due_on",
                "updated_by",
                "updated_at",
            ]
        )

        if enrollment.status != EnrollmentStatus.CANCELLED:
            # The enrolment and its money are one decision; doing half of it
            # is how the two came to disagree in the first place.
            set_enrollment_status(
                enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=actor
            )

    record(
        action=AuditAction.ENROLLMENT_CANCELLED,
        actor=actor,
        resource_type=RESOURCE_PLAN,
        resource_id=plan.pk,
        context={
            **_plan_context(plan),
            "charged": str(plan.gross_payable),
            "cancellation_charge": str(charge),
            "written_off": str(plan.written_off),
            "refund_due": str(plan.refund_due),
            "reason": plan.cancellation_reason,
        },
    )
    return plan
