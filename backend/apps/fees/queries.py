"""Fee totals as annotations, for the list screens.

A table of students or enrolments needs "paid so far", "still owed" and "next
expected" on every row without a query per row. These helpers add them as
subqueries — one per figure, correlated on the row — rather than joining
plans and payments onto the list, which would multiply rows and make every
other aggregate on the page wrong.

Nothing here decides anything: the arithmetic is the same as on ``FeePlan``,
only expressed in SQL.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import FeePayment, FeePlan

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0"), output_field=_MONEY)


def _sum(queryset: QuerySet, group_by: str, expression) -> Subquery:
    return Subquery(
        queryset.order_by().values(group_by).annotate(total=Sum(expression)).values("total")[:1],
        output_field=_MONEY,
    )


def annotate_student_fee_totals(students: QuerySet) -> QuerySet:
    """``fee_payable``, ``fee_paid``, ``fee_balance``, ``fee_next_due_on`` per student."""
    plans = FeePlan.objects.filter(
        enrollment__student=OuterRef("pk"), enrollment__deleted_at__isnull=True
    )
    payments = FeePayment.objects.filter(
        plan__enrollment__student=OuterRef("pk"),
        plan__enrollment__deleted_at__isnull=True,
        voided_at__isnull=True,
    )
    next_due = (
        plans.filter(next_due_on__isnull=False).order_by("next_due_on").values("next_due_on")[:1]
    )
    return students.annotate(
        fee_payable=Coalesce(
            _sum(plans, "enrollment__student", F("agreed_amount") - F("discount_amount")), _ZERO
        ),
        fee_paid=Coalesce(_sum(payments, "plan__enrollment__student", F("amount")), _ZERO),
        fee_next_due_on=Subquery(next_due),
    ).annotate(fee_balance=F("fee_payable") - F("fee_paid"))


def annotate_enrollment_fee(enrollments: QuerySet) -> QuerySet:
    """The same four figures per enrolment. ``fee_payable`` is null with no plan."""
    plan = FeePlan.objects.filter(enrollment=OuterRef("pk"))
    payments = FeePayment.objects.filter(plan__enrollment=OuterRef("pk"), voided_at__isnull=True)
    return enrollments.annotate(
        fee_payable=Subquery(
            plan.values("enrollment")
            .annotate(total=Sum(F("agreed_amount") - F("discount_amount")))
            .values("total")[:1],
            output_field=_MONEY,
        ),
        fee_paid=Coalesce(_sum(payments, "plan__enrollment", F("amount")), _ZERO),
        fee_next_due_on=Subquery(plan.values("next_due_on")[:1]),
    ).annotate(fee_balance=F("fee_payable") - F("fee_paid"))
