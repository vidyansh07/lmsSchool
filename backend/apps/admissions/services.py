"""Making an admission, and cancelling one.

The one piece of arithmetic worth reading closely is `split_discount`. Every
other number here is copied, never computed.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError

from .models import (
    ZERO,
    Admission,
    AdmissionLine,
    AdmissionStatus,
    DiscountKind,
    LineKind,
)

PAISE = Decimal("0.01")


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(PAISE, rounding=ROUND_HALF_UP)


def split_discount(totals: list[Decimal], discount: Decimal) -> list[Decimal]:
    """Share one discount across several course lines, exactly.

    Pro-rata by what each line is worth, which is the only split that does not
    advantage one course over another. The hard part is the remainder: ₹2,000
    off lines of ₹20,000 and ₹15,000 is 1,142.857… and 857.142…, and rounding
    each independently loses or gains a paisa. A paisa is not a rounding
    detail here — it is the difference between the reconciliation balancing
    and reporting an unexplained amount every day for the rest of the year.

    So the shares are floored, and the leftover paise are handed out one at a
    time to the lines with the largest discarded fraction (the largest
    remainder method). The result always sums to exactly `discount`, which is
    asserted before returning rather than trusted.

    A discount larger than the lines are worth is capped at the total: the
    institute can waive a fee, and cannot owe money for having agreed to.
    """
    discount = _money(discount)
    if discount <= ZERO or not totals:
        return [ZERO for _ in totals]

    gross = sum(totals, ZERO)
    if gross <= ZERO:
        return [ZERO for _ in totals]
    discount = min(discount, gross)

    exact = [(total / gross) * discount for total in totals]
    floored = [value.quantize(PAISE, rounding="ROUND_DOWN") for value in exact]
    leftover = int(((discount - sum(floored, ZERO)) / PAISE).to_integral_value())

    # Largest discarded fraction first; ties go to the earlier line, so the
    # same inputs always produce the same split.
    order = sorted(range(len(totals)), key=lambda i: (-(exact[i] - floored[i]), i))
    for position in range(leftover):
        floored[order[position % len(order)]] += PAISE

    assert sum(floored, ZERO) == discount, "discount split lost money"
    return floored


def discount_amount_for(gross: Decimal, *, kind: str, value: Any) -> Decimal:
    """The rupees to take off, given what was typed and which toggle was set."""
    value = _money(value)
    if value <= ZERO:
        return ZERO
    if kind == DiscountKind.PERCENT:
        if value > Decimal("100"):
            raise ApplicationError({"discount": ["A discount cannot be more than 100%."]})
        return _money(gross * value / Decimal("100"))
    return min(value, gross)


@transaction.atomic
def create_admission(
    *,
    actor,
    student,
    lines: list[dict[str, Any]],
    academic_year=None,
    admission_date=None,
    discount_kind: str = DiscountKind.FLAT,
    discount_value: Any = ZERO,
    note: str = "",
) -> Admission:
    """Record an admission and everything it implies.

    `lines` is what the form collected, in order::

        {"kind": "course", "course": <Course>, "quantity": 1, "unit_fee": "30000"}
        {"kind": "additional_fee", "label": "Exam fee", "unit_fee": "2000",
         "charged_on": 0}

    An additional fee's `charged_on` is the *index* of the course line it is
    charged with; left out, it goes on the first course line. Enrolments and
    fee plans are not created here — the wizard's later steps choose the batch
    and shape the instalments, and an admission with no batch yet is a real
    state (`Admission` holds the agreement; `apps.enrollments` holds the
    seat). `attach_enrollment` fills in the link when the seat is chosen.
    """
    from apps.students import access as students_access

    if student not in students_access.visible_students(actor):
        raise AuthorityError("You cannot admit this student.")

    course_lines = [line for line in lines if line.get("kind", LineKind.COURSE) == LineKind.COURSE]
    if not course_lines:
        raise ApplicationError({"lines": ["An admission needs at least one course."]})
    if academic_year is not None and academic_year.is_closed:
        raise ApplicationError({"academic_year": ["That academic year is closed."]})

    gross = sum(
        (_money(line.get("unit_fee")) * int(line.get("quantity", 1) or 1) for line in lines),
        ZERO,
    )
    discount = discount_amount_for(gross, kind=discount_kind, value=discount_value)

    admission = Admission.objects.create(
        student=student,
        branch=student.branch,
        academic_year=academic_year,
        admission_date=admission_date or timezone.localdate(),
        discount_kind=discount_kind,
        discount_amount=discount,
        discount_percent=(
            _money(discount_value) if discount_kind == DiscountKind.PERCENT else None
        ),
        note=note or "",
        created_by=actor,
    )

    created: list[AdmissionLine] = []
    for line in lines:
        kind = line.get("kind", LineKind.COURSE)
        quantity = int(line.get("quantity", 1) or 1)
        if quantity < 1:
            raise ApplicationError({"quantity": ["A line is for at least one."]})
        if kind == LineKind.COURSE and line.get("course") is None:
            raise ApplicationError({"course": ["Choose the course."]})
        if kind == LineKind.ADDITIONAL_FEE and not (line.get("label") or "").strip():
            raise ApplicationError({"label": ["Name the additional fee."]})
        created.append(
            AdmissionLine.objects.create(
                admission=admission,
                kind=kind,
                course=line.get("course") if kind == LineKind.COURSE else None,
                label=(line.get("label") or "").strip(),
                quantity=quantity,
                unit_fee=_money(line.get("unit_fee")),
            )
        )

    # Additional fees point at the course line they are charged with, by the
    # index the caller gave, or the first course line.
    first_course = next((row for row in created if row.kind == LineKind.COURSE), None)
    for index, line in enumerate(lines):
        if line.get("kind") != LineKind.ADDITIONAL_FEE:
            continue
        target_index = line.get("charged_on")
        target = first_course
        if target_index is not None:
            if not 0 <= int(target_index) < len(created):
                raise ApplicationError({"charged_on": ["No such line on this admission."]})
            candidate = created[int(target_index)]
            if candidate.kind != LineKind.COURSE:
                raise ApplicationError(
                    {"charged_on": ["An additional fee is charged on a course line."]}
                )
            target = candidate
        created[index].charged_on = target
        created[index].save(update_fields=["charged_on", "updated_at"])

    # The discount is split across the *course* lines only. An additional fee
    # is charged on a course line, so discounting it separately would take the
    # same rupees off twice.
    course_rows = [row for row in created if row.kind == LineKind.COURSE]
    shares = split_discount([row.line_total for row in course_rows], discount)
    for row, share in zip(course_rows, shares, strict=True):
        row.discount_share = share
        row.save(update_fields=["discount_share", "updated_at"])

    record(
        action=AuditAction.ADMISSION_CREATED,
        actor=actor,
        resource_type="admission",
        resource_id=admission.pk,
        context={
            "student": str(student.pk),
            "lines": len(created),
            "gross": str(gross),
            "discount": str(discount),
        },
        # Inline, not queued: this is a successful action, so the record and
        # the admission it describes commit together or not at all.
        durable=False,
    )
    return admission


def charge_for(line: AdmissionLine) -> Decimal:
    """What one course line's fee plan should be agreed at: the line itself,
    plus every additional fee charged on it. The discount is *not* taken off
    here — `FeePlan` holds it in its own column, so the plan can say what was
    charged and what was given separately, exactly as it does today."""
    if line.kind != LineKind.COURSE:
        return ZERO
    extras = sum(
        (extra.line_total for extra in line.additional_fees.all()),
        ZERO,
    )
    return line.line_total + extras


@transaction.atomic
def attach_enrollment(*, actor, line: AdmissionLine, enrollment) -> AdmissionLine:
    """Record which enrolment a course line became, once a batch is chosen."""
    if line.kind != LineKind.COURSE:
        raise ApplicationError({"line": ["Only a course line has an enrolment."]})
    if enrollment.student_id != line.admission.student_id:
        raise ApplicationError({"enrollment": ["That enrolment belongs to another student."]})
    if line.course_id and enrollment.course_id != line.course_id:
        raise ApplicationError({"enrollment": ["That enrolment is for another course."]})
    line.enrollment = enrollment
    line.save(update_fields=["enrollment", "updated_at"])
    return line


@transaction.atomic
def cancel_admission(*, actor, admission: Admission, reason: str) -> Admission:
    """End an admission. Each course line's money is settled by the fee
    ledger's own `cancel_admission`, which already knows how to write off what
    is not being pursued and record what is owed back."""
    if admission.is_cancelled:
        raise ApplicationError({"non_field_errors": ["This admission is already cancelled."]})
    if not (reason or "").strip():
        raise ApplicationError({"reason": ["Say why it was cancelled."]})

    from apps.fees import services as fee_services

    for line in admission.lines.filter(kind=LineKind.COURSE).select_related("enrollment"):
        if line.enrollment_id is None:
            continue
        fee_services.cancel_admission(
            enrollment=line.enrollment,
            actor=actor,
            cancellation_charge=ZERO,
            reason=reason,
        )

    admission.status = AdmissionStatus.CANCELLED
    admission.cancelled_at = timezone.now()
    admission.cancelled_by = actor
    admission.cancellation_reason = reason.strip()
    admission.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "updated_at",
        ]
    )
    record(
        action=AuditAction.ADMISSION_CANCELLED,
        actor=actor,
        resource_type="admission",
        resource_id=admission.pk,
        context={"reason": admission.cancellation_reason},
        durable=False,
    )
    return admission
