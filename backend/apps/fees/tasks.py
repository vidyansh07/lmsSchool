"""The morning sweep over fee schedules.

Every unpaid instalment due within the next `DUE_WINDOW_DAYS` days is offered
to automation as "due soon" with how many days are left, and every one whose
date has passed (up to `OVERDUE_WINDOW_DAYS` back) as "overdue" with how many
days late. Offered every morning, once: the automation engine keys each run by
the day, and a rule's own condition chooses the day it acts on — "3 days
before", "on the day", "a week late".

"Unpaid" is read off the ledger the way the fee screen reads it
(`installment_rows`): payments are poured over the schedule in order, so an
instalment half-covered by an earlier overpayment is still owed its balance.
"""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

DUE_WINDOW_DAYS = 7
OVERDUE_WINDOW_DAYS = 60


def sweep(today=None) -> dict[str, int]:
    from .mail import is_suppressed
    from .models import FeeInstallment, FeePlan, InstallmentStatus, installment_rows
    from .signals import instalment_due, instalment_overdue

    if is_suppressed():
        return {"due": 0, "overdue": 0}
    today = today or timezone.localdate()
    window_start = today - timedelta(days=OVERDUE_WINDOW_DAYS)
    window_end = today + timedelta(days=DUE_WINDOW_DAYS)
    # By id, not by joining the instalments: a join would multiply the
    # payments the totals annotation sums, and over-count what is paid.
    in_window = FeeInstallment.objects.filter(
        due_on__gte=window_start, due_on__lte=window_end
    ).values("plan_id")
    plans = (
        FeePlan.objects.filter(pk__in=in_window, enrollment__status__in=_live_statuses())
        .with_totals()
        .prefetch_related("installments")
    )
    counts = {"due": 0, "overdue": 0}
    for plan in plans.iterator(chunk_size=200):
        if plan.balance <= 0:
            continue
        installments = {item.pk: item for item in plan.installments.all()}
        for row in installment_rows(plan, list(installments.values()), today=today):
            if row["status"] == InstallmentStatus.PAID:
                continue
            due_on = row["due_on"]
            installment = installments[row["id"]]
            if today <= due_on <= window_end:
                instalment_due.send(
                    sender=FeePlan, installment=installment, days=(due_on - today).days
                )
                counts["due"] += 1
            elif window_start <= due_on < today:
                instalment_overdue.send(
                    sender=FeePlan, installment=installment, days=(today - due_on).days
                )
                counts["overdue"] += 1
    return counts


def _live_statuses():
    from apps.enrollments.models import LIVE_STATUSES

    return list(LIVE_STATUSES)


@shared_task(name="fees.sweep_instalments", ignore_result=True)
def sweep_instalments() -> dict[str, int]:
    return sweep()
