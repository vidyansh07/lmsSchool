"""Stage 5 of the showcase: a fee ledger on every live showcase enrolment but
five, payments spread over the last twenty weeks in every method, a void and
its correction, ageing in every bucket, the student's derived status — and
a second run that creates nothing.

Runs the command up to and including ``fees`` on the empty test database,
twice. There are no SITP rows here, so the imported part is proved to be a
clean no-op. One test runs the command twice and checks everything, rather
than one test per promise: the four stages in front make a hundred accounts,
a catalogue and fifteen batches with their classes, and a run per test would
put the file well over its time budget.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import Batch
from apps.common.showcase.context import MARKER
from apps.common.showcase.stages.s05_fees import (
    DISCOUNTS,
    DUE_SOON,
    NO_PLAN,
    OVERDUE_BUCKETS,
    TAG_PREFIX,
    VOIDS,
    WEEKS,
)
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.fees.models import FeePayment, FeePlan, FeePlanStatus, PaymentMethod
from apps.students.models import FeeStatus, StudentProfile

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches,fees"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = ("fee_plan", "fee_payment", "fee_void", "fee_next_due")

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)
TAG_RE = re.compile(r"^\[showcase\]\[fee/(GRS-E-\d{5})/(\d+r?)\]")


def run(django_capture_on_commit_callbacks, *, stages: str = STAGES) -> str:
    """The command up to ``fees``, with every on_commit hook executed."""
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", stages, stdout=out, stderr=out)
    return out.getvalue()


def run_days_later(django_capture_on_commit_callbacks, days: int) -> str:
    """``--only fees`` on a database that ran the rest, with the clock moved
    ``days`` ahead — the staging case, where the command is re-run later in
    the week. ``timezone.now`` is what ``localdate``, ``localtime`` and every
    ``auto_now`` field read, so patching it moves the whole stage's today."""
    shifted = timezone.now() + timedelta(days=days)
    with mock.patch("django.utils.timezone.now", return_value=shifted):
        return run(django_capture_on_commit_callbacks, stages="fees")


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    """Everything the stage may touch, and the things it must not."""
    return {
        "plans": FeePlan.objects.count(),
        "payments": FeePayment.objects.count(),
        "voided": FeePayment.objects.filter(voided_at__isnull=False).count(),
        "with_next_due": FeePlan.objects.filter(next_due_on__isnull=False).count(),
        **{
            f"students_{status}": StudentProfile.objects.filter(fee_status=status).count()
            for status in FeeStatus.values
        },
        **{
            f"enrolments_{status}": Enrollment.objects.filter(status=status).count()
            for status in EnrollmentStatus.values
        },
        "batches": Batch.objects.count(),
        "users": User.objects.count(),
        "fee_audit": AuditLog.objects.filter(resource_type__in=["fee_plan", "fee_payment"]).count(),
        "fee_status_audit": AuditLog.objects.filter(
            action=AuditAction.STUDENT_FEE_STATUS_CHANGED
        ).count(),
    }


def showcase_live() -> Enrollment:
    return Enrollment.objects.filter(batch__description__startswith=MARKER).live()


@pytest.mark.django_db
def test_fees_stage_builds_every_state_and_is_idempotent(django_capture_on_commit_callbacks):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table[label][0] == 0, f"second run created {label}: {table[label]}"
        assert table[label][1] > 0, f"second run found no {label}"
    assert counts() == after_first
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"
    assert "imported batches: none on this database" in first
    assert "imported batches: none on this database" in second
    assert "refreshed" not in second, "a same-day re-run moved a due date"

    today = timezone.localdate()
    now = timezone.now()
    live = showcase_live()
    plans = FeePlan.objects.filter(notes__startswith=MARKER).with_totals()
    payments = FeePayment.objects.filter(note__startswith=TAG_PREFIX)

    # --- Plans: every live showcase enrolment but five; the fee is the course's
    assert live.filter(fee_plan__isnull=True).count() == NO_PLAN
    assert plans.count() == live.count() - NO_PLAN
    assert rows(first)["fee_plan"] == (plans.count(), 0)
    assert not FeePlan.objects.exclude(notes__startswith=MARKER).exists()
    assert not FeePlan.objects.exclude(enrollment__in=live).exists(), "a plan off a live enrolment"
    for plan in plans.select_related("enrollment__batch__course", "enrollment__student"):
        assert plan.agreed_amount == plan.enrollment.batch.course.default_fee, plan.enrollment.code
        assert plan.balance >= 0, f"{plan.enrollment.code} is overpaid"
        assert plan.created_by.email.startswith("admin"), "plans are set by the centre's admin"
        # Backdated to the enrolment, and always the first line of its history.
        assert plan.created_at <= plan.enrollment.enrolled_at, "plan created_at backdated"
        first_payment = plan.payments.order_by("created_at").first()
        if first_payment is not None:
            assert plan.created_at < first_payment.created_at, plan.enrollment.code
            assert first_payment.paid_on >= timezone.localtime(plan.enrollment.enrolled_at).date()
    assert plans.filter(discount_amount__gt=0).count() == DISCOUNTS
    assert not plans.filter(discount_amount__gt=0, discount_reason="").exists()
    waived = [plan for plan in plans if plan.status == FeePlanStatus.WAIVED]
    assert len(waived) == 1
    assert waived[0].discount_amount == waived[0].agreed_amount
    assert waived[0].enrollment.student.fee_status == FeeStatus.WAIVED
    assert not waived[0].payments.exists()
    statuses = {plan.status for plan in plans}
    assert statuses == set(FeePlanStatus.values)

    # --- Payments: every method, round figures, a receipt each, in the last
    # twenty weeks with this week and the far end both populated
    assert set(payments.values_list("method", flat=True)) == set(PaymentMethod.values)
    assert rows(first)["fee_payment"] == (payments.count(), 0)
    assert not FeePayment.objects.exclude(note__startswith=TAG_PREFIX).exists()
    assert not payments.filter(amount__lt=Decimal("1000")).exists(), "an instalment under ₹1,000"
    assert not payments.filter(paid_on__gt=today).exists()
    assert not payments.filter(paid_on__lt=today - timedelta(weeks=WEEKS, days=6)).exists()
    assert payments.filter(paid_on__gte=today - timedelta(days=today.weekday())).exists()
    assert payments.filter(paid_on__lte=today - timedelta(weeks=10)).exists()
    assert payments.filter(paid_on=today).exists()
    receipts = list(payments.values_list("receipt_number", flat=True))
    assert len(receipts) == len(set(receipts))
    assert all(re.fullmatch(r"GRS-R-\d{5}", r) for r in receipts)
    recorders = set(payments.values_list("recorded_by__role", flat=True))
    assert recorders == {"admin", "manager", "counsellor"}
    by_plan: dict = {}
    for payment in payments.order_by("paid_on", "created_at"):
        assert payment.amount % Decimal("100") == 0, "not a round figure"
        # Backdated to the day it was paid (local time), never past now.
        assert timezone.localtime(payment.created_at).date() == payment.paid_on
        assert payment.created_at <= now
        match = TAG_RE.match(payment.note)
        assert match, payment.note
        assert match.group(1) == payment.plan.enrollment.code
        by_plan.setdefault(payment.plan_id, []).append(payment)
    for plan_payments in by_plan.values():
        # The first non-voided instalment is the registration fee, so every
        # instalment is at least ₹1,000; a plan is never paid past its fee.
        live_amounts = [p.amount for p in plan_payments if not p.is_voided]
        assert live_amounts[0] >= Decimal("1000")
    # Cheques, UPI, transfers and cards carry a reference; cash does not.
    for method in (PaymentMethod.UPI, PaymentMethod.CHEQUE, PaymentMethod.BANK_TRANSFER):
        assert not payments.filter(method=method, reference="").exists(), method
    assert not payments.filter(method=PaymentMethod.CASH).exclude(reference="").exists()

    # --- Voids: two mistakes, each with a reason and a correction after it
    voided = list(payments.filter(voided_at__isnull=False))
    assert len(voided) == VOIDS
    assert rows(first)["fee_void"] == (VOIDS, 0)
    for payment in voided:
        assert payment.void_reason.startswith(MARKER)
        assert payment.voided_by is not None
        # The day after the payment, or now when that day is still ahead.
        voided_on = timezone.localtime(payment.voided_at).date()
        assert voided_on == min(payment.paid_on + timedelta(days=1), today)
        n = TAG_RE.match(payment.note).group(2)
        corrected = payments.get(
            note__startswith=f"{MARKER}[fee/{payment.plan.enrollment.code}/{n}r]"
        )
        assert corrected.amount > payment.amount
        assert corrected.paid_on == payment.paid_on
        assert not corrected.is_voided
        assert payment.plan.paid == sum(
            p.amount for p in payment.plan.payments.filter(voided_at__isnull=True)
        )

    # --- Ageing: several plans in every overdue bucket, a few due soon
    owing = [plan for plan in plans if plan.next_due_on and plan.balance > 0]
    for label, oldest, youngest in OVERDUE_BUCKETS:
        window = (today - timedelta(days=oldest), today - timedelta(days=youngest))
        in_bucket = [p for p in owing if window[0] <= p.next_due_on <= window[1]]
        assert len(in_bucket) >= 5, f"bucket {label}: {len(in_bucket)}"
        assert all(p.is_overdue for p in in_bucket)
    due_soon = [p for p in owing if today <= p.next_due_on <= today + timedelta(days=7)]
    assert len(due_soon) >= DUE_SOON
    for plan in owing:
        assert Decimal("0") < plan.next_due_amount <= plan.balance
    assert not plans.filter(next_due_on__isnull=False, next_due_amount__isnull=True).exists()

    # --- The student's derived status: every value, from the ledger alone
    with_plan = StudentProfile.objects.filter(enrollments__fee_plan__in=plans).distinct()
    assert set(with_plan.values_list("fee_status", flat=True)) == set(FeeStatus.values)
    for plan in plans.filter(next_due_on__lt=today):
        if plan.balance > 0:
            assert plan.enrollment.student.fee_status == FeeStatus.OVERDUE, plan.enrollment.code
    # A student with no plan at all was left as they were.
    assert set(
        StudentProfile.objects.exclude(pk__in=with_plan).values_list("fee_status", flat=True)
    ) == {FeeStatus.PENDING}

    # --- The headline student: part paid, paid today, due in five days
    headline = StudentProfile.objects.get(user__email="student@grras.com")
    mine = list(
        plans.filter(enrollment__student=headline).order_by("-enrollment__batch__start_date")
    )
    assert mine, "the headline student has a plan"
    youngest = mine[0]
    assert youngest.status == FeePlanStatus.PARTIAL
    assert youngest.payments.filter(paid_on=today, voided_at__isnull=True).exists()
    assert youngest.next_due_on == today + timedelta(days=5)
    assert headline.fee_status == FeeStatus.PARTIAL

    # --- Audited through the services, never written by hand
    assert AuditLog.objects.filter(action=AuditAction.FEE_PLAN_SET).count() == plans.count()
    assert (
        AuditLog.objects.filter(action=AuditAction.FEE_PAYMENT_RECORDED).count() == payments.count()
    )
    assert AuditLog.objects.filter(action=AuditAction.FEE_PAYMENT_VOIDED).count() == VOIDS
    assert AuditLog.objects.filter(action=AuditAction.FEE_NEXT_DUE_SET).count() == len(owing)
    assert SEED_PASSWORD not in first + second

    # --- Re-run on a later day: the draws do not move with the calendar, so
    # nothing is created; only the next-due dates are refreshed on rows the
    # stage owns. One and two days ahead cross a weekday boundary either way.
    before = counts()
    for days in (1, 2):
        later = run_days_later(django_capture_on_commit_callbacks, days)
        table = rows(later)
        for label in LABELS:
            assert table[label][0] == 0, f"+{days} days created {label}: {table[label]}"
        assert "already paid under other tags" not in later, "the draw moved with the clock"
        assert "refreshed to" in later, "the clock did not move, so the re-run proves nothing"
        after = counts()
        for key in ("plans", "payments", "voided", "with_next_due", "batches", "users"):
            assert after[key] == before[key], f"+{days} days changed {key}"
    assert FeePlan.objects.filter(notes__startswith=MARKER).count() == plans.count()
    assert FeePayment.objects.filter(note__startswith=TAG_PREFIX).count() == payments.count()

    # --- Every fee-status change is a real one: the audit trail for a
    # student never repeats a destination, and each step starts where the
    # last one ended (a stale instance would record "from pending" twice).
    trail: dict = {}
    for entry in AuditLog.objects.filter(action=AuditAction.STUDENT_FEE_STATUS_CHANGED).order_by(
        "created_at", "pk"
    ):
        previous = trail.get(entry.resource_id)
        if previous is not None:
            assert entry.context["from"] == previous, entry.context
            assert entry.context["to"] != previous, entry.context
        trail[entry.resource_id] = entry.context["to"]
