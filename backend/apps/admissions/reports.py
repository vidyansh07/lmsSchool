"""The admissions reports: the five tabs the desk reads its month from.

Every figure is read from the records themselves — the admission for what was
agreed, the fee ledger for what has been received — and nothing is cached or
denormalised. A report that keeps its own copy of a total is a report that
disagrees with the screen it was taken from, and the one the owner reads out
loud has to be the same number the counsellor sees.

All five are scoped through `access.visible_admissions`, so a counsellor
bounded to one centre reports on that centre and the figures at the top are
the figures of the rows underneath. A report that totalled more than it
listed would be worse than no report.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from apps.enrollments.models import Enrollment

from .models import ZERO, Admission, AdmissionStatus, LineKind

#: The tabs, in the order the screen shows them.
TABS = ("overall", "discount", "expiry", "additional-fees", "coursewise")


def _course_names(admission: Admission) -> str:
    """ "Advance Python (2026), Data Science (2026)" — how the table names an
    admission's courses, year included, exactly as the record shows it."""
    year = admission.academic_year.name if admission.academic_year_id else None
    names = [
        f"{line.name} ({year})" if year else line.name
        for line in admission.lines.all()
        if line.kind == LineKind.COURSE
    ]
    return ", ".join(names)


def _row(admission: Admission) -> dict[str, Any]:
    money = admission.money()
    return {
        "id": str(admission.pk),
        "admission_date": admission.admission_date,
        "student_id": str(admission.student_id),
        "student_name": (
            admission.student.user.get_full_name() or admission.student.user.email
            if admission.student.user_id
            else ""
        ),
        "student_code": admission.student.student_id,
        "courses": _course_names(admission),
        "status": admission.status,
        "total": money["total"],
        "paid": money["paid"],
        "uncleared": money["uncleared"],
        "refund": money["refund"],
        "balance": money["balance"],
    }


def overall(admissions) -> dict[str, Any]:
    """Every admission, with the eight figures above it.

    `cleared` is received less uncleared, not a third thing counted
    separately: a cheque is received the day it is taken and cleared the day
    the bank says so, and adding them as if they were different money would
    count it twice.

    `cancelled` is what was charged on the admissions that ended, which is a
    different question from what was written off, and is the one the owner
    asks ("how much did we lose this month").
    """
    rows = [_row(admission) for admission in admissions]
    live = [row for row in rows if row["status"] != AdmissionStatus.CANCELLED]
    cancelled = [row for row in rows if row["status"] == AdmissionStatus.CANCELLED]

    received = sum((row["paid"] for row in live), ZERO)
    uncleared = sum((row["uncleared"] for row in live), ZERO)
    return {
        "tiles": {
            "admissions": len(live),
            "total": sum((row["total"] for row in live), ZERO),
            "received": received,
            "cleared": received - uncleared,
            "uncleared": uncleared,
            "balance": sum((row["balance"] for row in live), ZERO),
            "refund": sum((row["refund"] for row in rows), ZERO),
            "cancelled": sum((row["total"] for row in cancelled), ZERO),
        },
        "rows": rows,
    }


def discount(admissions) -> dict[str, Any]:
    """Only the admissions something was taken off, and what it came to.

    Zero-discount admissions are left out rather than listed with a zero: the
    question this tab answers is "what did we give away", and a page of zeros
    buries the answer in the ones that matter.
    """
    rows = []
    for admission in admissions:
        if admission.discount_amount <= ZERO:
            continue
        row = _row(admission)
        row["gross_total"] = admission.gross_total
        row["discount"] = admission.discount_amount
        row["discount_kind"] = admission.discount_kind
        row["discount_percent"] = admission.discount_percent
        rows.append(row)
    return {
        "tiles": {
            "admissions": len(rows),
            "discount": sum((row["discount"] for row in rows), ZERO),
            "total": sum((row["total"] for row in rows), ZERO),
        },
        "rows": rows,
    }


def expiry(admissions, *, today: date | None = None) -> dict[str, Any]:
    """When each enrolment's access runs out, and what is still owed on it.

    Read from the enrolment rather than the admission: access is a property
    of the seat, and two courses on one admission can end months apart. An
    enrolment with no end date is left out — "no expiry" is not an expiry,
    and listing it as one would have somebody chasing a date that does not
    exist.
    """
    today = today or date.today()
    enrolment_ids = [
        line.enrollment_id
        for admission in admissions
        for line in admission.lines.all()
        if line.kind == LineKind.COURSE and line.enrollment_id
    ]
    rows = []
    enrolments = (
        Enrollment.objects.filter(pk__in=enrolment_ids, access_end_date__isnull=False)
        .select_related("student__user", "course", "batch", "fee_plan")
        .order_by("access_end_date")
    )
    for enrolment in enrolments:
        plan = getattr(enrolment, "fee_plan", None)
        rows.append(
            {
                "enrollment_id": str(enrolment.pk),
                "student_id": str(enrolment.student_id),
                "student_name": (
                    enrolment.student.user.get_full_name() or enrolment.student.user.email
                    if enrolment.student.user_id
                    else ""
                ),
                "course": enrolment.course.title,
                "batch": enrolment.batch.name if enrolment.batch_id else "",
                "access_end_date": enrolment.access_end_date,
                "days_left": (enrolment.access_end_date - today).days,
                "balance": plan.balance if plan is not None else ZERO,
            }
        )
    return {
        "tiles": {
            "enrolments": len(rows),
            "expired": len([row for row in rows if row["days_left"] < 0]),
            "expiring_in_30_days": len([row for row in rows if 0 <= row["days_left"] <= 30]),
            "balance": sum((row["balance"] for row in rows), ZERO),
        },
        "rows": rows,
    }


def additional_fees(admissions) -> dict[str, Any]:
    """Every charge beside a course — exam fees, kits — and which course each
    was charged on."""
    rows = []
    for admission in admissions:
        by_key = {line.pk: line for line in admission.lines.all()}
        for line in admission.lines.all():
            if line.kind != LineKind.ADDITIONAL_FEE:
                continue
            charged_on = by_key.get(line.charged_on_id)
            rows.append(
                {
                    "id": str(line.pk),
                    "admission_id": str(admission.pk),
                    "admission_date": admission.admission_date,
                    "student_id": str(admission.student_id),
                    "student_name": (
                        admission.student.user.get_full_name() or admission.student.user.email
                        if admission.student.user_id
                        else ""
                    ),
                    "label": line.label,
                    "charged_on": charged_on.name if charged_on is not None else "",
                    "quantity": line.quantity,
                    "amount": line.line_total,
                }
            )
    return {
        "tiles": {"fees": len(rows), "total": sum((row["amount"] for row in rows), ZERO)},
        "rows": rows,
    }


def coursewise(admissions) -> dict[str, Any]:
    """One row per course: how many took it and what it brought in.

    An admission with two courses counts once under each — the question is
    "how is this course doing", and halving a student between two courses
    would answer a question nobody asked. The money, though, is the money of
    *that course's* line, not the admission's total, so the column still adds
    up to what was charged.
    """
    totals: dict[str, dict[str, Any]] = {}
    for admission in admissions:
        money = admission.money()
        gross = admission.gross_total or ZERO
        for line in admission.lines.all():
            if line.kind != LineKind.COURSE:
                continue
            key = str(line.course_id)
            bucket = totals.setdefault(
                key,
                {
                    "course_id": key,
                    "course": line.name,
                    "admissions": 0,
                    "total": ZERO,
                    "received": ZERO,
                    "balance": ZERO,
                },
            )
            bucket["admissions"] += 1
            charged = line.line_total - line.discount_share
            bucket["total"] += charged
            # What has been received against this course, apportioned by what
            # it is worth: the ledger is per course, but an admission's
            # payments are read together here.
            share = (charged / gross) if gross > ZERO else Decimal("0")
            bucket["received"] += money["paid"] * share
            bucket["balance"] += max(charged - money["paid"] * share, ZERO)

    rows = sorted(totals.values(), key=lambda row: row["course"])
    for row in rows:
        row["received"] = row["received"].quantize(Decimal("0.01"))
        row["balance"] = row["balance"].quantize(Decimal("0.01"))
    return {
        "tiles": {
            "courses": len(rows),
            "admissions": sum(row["admissions"] for row in rows),
            "total": sum((row["total"] for row in rows), ZERO),
        },
        "rows": rows,
    }


BUILDERS = {
    "overall": overall,
    "discount": discount,
    "expiry": expiry,
    "additional-fees": additional_fees,
    "coursewise": coursewise,
}
