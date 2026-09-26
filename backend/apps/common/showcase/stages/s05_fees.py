"""Stage 5 — fee plans, payments, dues and the derived fee status.

Creates, through ``apps.fees.services`` and idempotently, a fee ledger for
every enrolment stage 4 left behind, so every fee tile, filter, chart and
warning has a number on it:

* **Plans** via ``set_fee_plan`` — as the centre's admin
  (``ctx.actor_for(branch_code)``, who holds ``fee.manage_any``) — on every
  live showcase enrolment except :data:`NO_PLAN` of them, left without one
  so the *no fee agreed* warning keeps a few rows, and on **every**
  enrolment of the imported SITP batches, live or completed: the service
  takes any enrolment, and only the derived student status is limited to
  live ones. The agreed amount is the course's ``default_fee``; the SITP
  courses have none, so those draw ₹12,000-25,000. :data:`DISCOUNTS`
  showcase plans carry a discount with a reason, and one of them is
  **waived** — discount equal to the fee — on a student with no other
  showcase enrolment, so the student's own status reads *waived*. The plan
  is always set before any payment, because payable can never drop below
  what is paid.
* **Payments** via ``record_payment``: of the imported plans roughly 60 %
  are paid in full, 25 % in part and 15 % not at all (the showcase plans
  lean towards open balances, which feed the ageing), in one to three
  instalments each. The first instalment is never below the ₹1,000
  registration fee and every instalment is a round figure. ``paid_on`` is
  spread over the last :data:`WEEKS` weeks, weighted towards recent weeks
  so the collections trend climbs, and week zero is placed inside the
  current Monday-based week so the "collected this week" tile is never
  empty. A showcase payment is never dated before the enrolment it pays
  for; an imported one is floored at the batch start, because the import
  stamped every SITP ``enrolled_at`` with the day it ran. Every method
  appears, with a UPI id, UTR, cheque or card reference where the method
  has one; the receipt number comes from the service. :data:`VOIDS`
  showcase payments are **voided** through ``void_payment`` with a reason
  and re-entered under the next receipt, so a ledger shows a crossed-out
  line and its correction. Money is taken by the centre's admin, manager or
  counsellor in turn, so "collected per actor" has several bars.
* **Ageing** via ``set_next_due`` on showcase plans that still owe money
  (imported ones only when the showcase has too few): several each at 1-7,
  8-30, 31-90 and 90+ days overdue — the last on the batches that started
  earliest, so a due date is not months before the cohort existed — and a
  few *due soon* (within the next week). The headline student's youngest
  plan is part paid — its second instalment dated today — with the next
  due in five days. ``set_next_due`` does not derive the student's status,
  so ``sync_student_fee_status`` is then called for **every** student
  touched, on a freshly loaded profile, which lands
  ``StudentProfile.fee_status`` on pending, partial, paid, waived or
  overdue from the ledger alone.
* **Backdating**, last of all and only on rows this run created: a plan's
  ``created_at`` to the enrolment's ``enrolled_at`` or, when a payment is
  dated earlier than that (the imported enrolments), to the morning of the
  first payment; a payment's ``created_at`` to its ``paid_on``; a void's
  ``voided_at`` to the day after the payment — so a fee history reads in
  the order it happened.

Idempotent by enrolment for plans (a plan already there is *found* — and
when its notes do not carry the marker it was somebody else's, so nothing is
recorded against it), by the tag ``[showcase][fee/<enrolment code>/<n>]`` in
the note for payments (``note__startswith``), by the same tag plus
``voided_at`` for voids, and by the plan for next-dues.

**Every draw is per enrolment.** Each plan's figures — the fee, the
outcome, the instalments, their dates, methods and recorders — come from a
generator seeded with the enrolment's code (:func:`_seed`), and the picks
that single some enrolments out (left without a plan, discounted, voided,
put in an ageing bucket) take the lowest-scoring codes under a seed of
their own. So no enrolment's ledger depends on any other enrolment, on the
order the rows come back in, or on the day the command runs: a re-run
draws the same ledger for the same enrolment whether it is the same
Monday, a later Saturday, or after stage 7 has completed some enrolments
(a showcase enrolment that has a plan stays in the set whether it is live
or completed, so the set does not shrink when that happens; the five left
without a plan can only dwindle, never be replaced). ``ctx.rng`` is not
used at all. Dates
are the one thing that move between days — a payment's ``paid_on`` is
relative to today, and so is ``next_due_on`` — but a payment is looked up
by its tag, not its date, and a next-due on a later day is refreshed on a
row this stage owns, counted as *found*, which is what keeps the buckets
live. Should a plan this stage owns nonetheless carry tagged payments while
the tag for one of its drawn instalments is missing, the plan is reported
and skipped rather than paid twice. On a database with no SITP import the
imported part is a no-op, and says so.

Leaves in ``ctx``: nothing new; later stages read the ledger from the DB.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from time import perf_counter
from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.enrollments.models import LIVE_STATUSES, Enrollment, EnrollmentStatus
from apps.fees.models import FeePayment, FeePlan, PaymentMethod
from apps.fees.services import (
    record_payment,
    set_fee_plan,
    set_next_due,
    sync_student_fee_status,
    void_payment,
)
from apps.students.models import StudentProfile

from ..context import MARKER, RUN_SEED, Context
from ..roster import MAIN

STAGE = "fees"

#: How far back payments are spread. The trend chart reads twelve weeks; a
#: longer tail means the chart's first week is not also the ledger's.
WEEKS = 20
#: A batch that starts further ahead than this still has its payments spread
#: over the last fortnight, rather than all clamped to today.
RECENT_DAYS = 14
#: Live showcase enrolments deliberately left without a fee plan.
NO_PLAN = 5
#: Showcase plans given a discount (one of them the waived plan).
DISCOUNTS = 10
#: Showcase payments voided and re-entered.
VOIDS = 2
#: The overdue buckets — (label, oldest days ago, youngest days ago) — how
#: many plans land in each, and how many fall due within the next week.
OVERDUE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1-7", 7, 1),
    ("8-30", 30, 8),
    ("31-90", 90, 31),
    ("90+", 150, 91),
)
OVERDUE_PER_BUCKET = 7
DUE_SOON = 6

#: The registration fee: the floor for the first instalment, and for every one.
MIN_INSTALMENT = Decimal("1000")
STEP = Decimal("500")
ZERO = Decimal("0")
#: The SITP courses have no ``default_fee``; these are the plausible figures.
SITP_FEES = [Decimal(n) for n in range(12000, 25001, 500)]

#: (weight, method). UPI first, because that is how an Indian institute is paid.
METHODS: tuple[tuple[int, str], ...] = (
    (40, PaymentMethod.UPI),
    (25, PaymentMethod.CASH),
    (15, PaymentMethod.BANK_TRANSFER),
    (10, PaymentMethod.CARD),
    (7, PaymentMethod.CHEQUE),
    (3, PaymentMethod.OTHER),
)
BANKS = ("SBI", "HDFC Bank", "ICICI Bank", "Bank of Baroda", "Axis Bank", "PNB")
#: Who takes the money at the desk. Counsellors twice: it is mostly their job.
RECORDERS = ("admin", "manager", "counsellor", "counsellor")

#: (share of the fee, or a fixed amount, reason). The reason is kept with the
#: record, so it reads like something a counsellor wrote.
DISCOUNT_KINDS: tuple[tuple[Decimal | None, Decimal | None, str], ...] = (
    (Decimal("0.10"), None, "Early-bird: enrolled before the batch was announced."),
    (None, Decimal("2000"), "Referred by an alumnus; referral discount."),
    (Decimal("0.15"), None, "Grras alumni discount (second course)."),
    (Decimal("0.25"), None, "Merit scholarship on the entrance test."),
    (None, Decimal("5000"), "Corporate sponsorship; the employer pays the balance directly."),
)
WAIVER_REASON = "Full scholarship (Grras Foundation); fee waived."

PLAN_NOTE = "Agreed at admission; instalments as the student can manage."
VOID_REASON = "Amount entered wrong; re-entered under the next receipt."

PAID, PARTIAL, UNPAID = "paid", "partial", "unpaid"
#: (weight, outcome): the owner's 60/25/15 for the imported plans; the
#: showcase plans keep more balances open, which is what the ageing needs.
SITP_OUTCOMES: tuple[tuple[int, str], ...] = ((60, PAID), (25, PARTIAL), (15, UNPAID))
SHOWCASE_OUTCOMES: tuple[tuple[int, str], ...] = ((40, PAID), (45, PARTIAL), (15, UNPAID))

#: The tag prefix every payment note starts with; the re-run's lookup key.
TAG_PREFIX = f"{MARKER}[fee/"


# ---------------------------------------------------------------------------
# What the stage creates: drawn once, then applied
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentSpec:
    """One instalment. ``n`` is the tag suffix (``"2"``, or ``"2r"`` for the
    re-entry after ``"2"`` is voided); ``void_reason`` set means the payment
    is recorded and then voided, in that order."""

    n: str
    amount: Decimal
    paid_on: date
    method: str
    reference: str
    text: str
    recorder: str
    void_reason: str = ""


@dataclass
class PlanSpec:
    enrollment: Enrollment
    branch_code: str
    agreed: Decimal
    discount: Decimal
    discount_reason: str
    payments: list[PaymentSpec] = field(default_factory=list)
    #: (amount, on, bucket label) once the ageing pass has picked this plan.
    next_due: tuple[Decimal, date, str] | None = None
    imported: bool = False

    @property
    def payable(self) -> Decimal:
        return self.agreed - self.discount

    @property
    def paid(self) -> Decimal:
        return sum((p.amount for p in self.payments if not p.void_reason), ZERO)

    @property
    def balance(self) -> Decimal:
        return self.payable - self.paid

    @property
    def is_live(self) -> bool:
        return self.enrollment.status in LIVE_STATUSES

    @property
    def code(self) -> str:
        return self.enrollment.code


@dataclass
class Plan:
    specs: list[PlanSpec] = field(default_factory=list)
    #: Showcase enrolments deliberately left without a plan.
    without_plan: list[Enrollment] = field(default_factory=list)
    #: Rows this run created, for the backdating pass at the end.
    created_plans: list[tuple[FeePlan, PlanSpec]] = field(default_factory=list)
    created_payments: list[tuple[FeePayment, PaymentSpec]] = field(default_factory=list)
    voided: list[FeePayment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _seed(*parts: Any) -> random.Random:
    """A generator of its own for one thing — a plan, a pick — so no draw
    depends on what was drawn before it or on the calendar. Same pattern as
    stage 6."""
    return random.Random(":".join([str(RUN_SEED), STAGE, *(str(p) for p in parts)]))  # noqa: S311


def _score(kind: str, code: str) -> float:
    """Where an enrolment ranks for a pick: the lowest scores are taken."""
    return _seed(kind, code).random()


def _lowest(kind: str, rows: list, count: int) -> list:
    """The ``count`` rows (enrolments or specs — both have a ``code``) with
    the lowest score under ``kind``. Each row's score is its own, so the
    pick only moves when the rows themselves do."""
    return sorted(rows, key=lambda row: _score(kind, row.code))[:count]


def _enrolments(batches: list, statuses: list[str]) -> list[Enrollment]:
    """Enrolments on ``batches`` in the wanted statuses, in an order that is
    the same on every database (batch name, student email, code), with one
    ``StudentProfile`` instance per student: the services derive the
    student's status onto the instance they are handed, and two instances
    of one student would let a later call compare against a stale copy."""
    if not batches:
        return []
    rows = list(
        Enrollment.objects.filter(batch__in=batches, status__in=statuses)
        .select_related("student__user", "batch__course", "batch__branch")
        .order_by("batch__name", "student__user__email", "code")
    )
    students: dict[Any, StudentProfile] = {}
    for row in rows:
        row.student = students.setdefault(row.student_id, row.student)
    return rows


def _showcase_enrolments(ctx: Context) -> list[Enrollment]:
    """Every live or completed enrolment on a showcase batch. Only the live
    ones get a plan; the completed ones (stage 4 completes whole batches,
    stage 7 single students) are read so a plan set while an enrolment was
    live is still found — and its ledger still checked — after it completed."""
    batches = [ctx.showcase_batches[key] for key in sorted(ctx.showcase_batches)]
    return _enrolments(batches, [*LIVE_STATUSES, EnrollmentStatus.COMPLETED])


def _imported_enrolments(ctx: Context) -> list[Enrollment]:
    """Every live or completed enrolment on an imported SITP batch. Cancelled
    and transferred ones owe nothing and get no ledger."""
    batches = [ctx.imported_batches[key] for key in sorted(ctx.imported_batches)]
    return _enrolments(batches, [*LIVE_STATUSES, EnrollmentStatus.COMPLETED])


def _round_step(amount: Decimal) -> Decimal:
    """To the nearest ₹500: a counsellor's desk does not take ₹4,237."""
    return (amount / STEP).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * STEP


def _share(draw: random.Random, low: float, high: float) -> Decimal:
    """A fraction drawn to three places, as a Decimal the money arithmetic
    can take."""
    return Decimal(str(round(draw.uniform(low, high), 3)))


def _weighted(draw: random.Random, table: tuple[tuple[int, Any], ...]) -> Any:
    return draw.choices([value for _, value in table], weights=[w for w, _ in table], k=1)[0]


def _paid_on(ctx: Context, draw: random.Random, floor: date) -> date:
    """A day in the last :data:`WEEKS` weeks, recent weeks heavier.

    Week zero is the current Monday-based week — the one the "collected this
    week" tile counts — so its days run from Monday to today rather than a
    week back from today. The offset inside a week is always drawn from 0-6
    and clamped afterwards, never drawn from a range that depends on the
    weekday: ``randint`` takes a different number of bits for a different
    range, and a draw that depended on the weekday would leave every later
    draw for the plan different on a different day. Never later than today
    (the service refuses a future date) and never earlier than ``floor``.
    """
    weights = [WEEKS + 1 - week for week in range(WEEKS)]
    week = draw.choices(range(WEEKS), weights=weights, k=1)[0]
    offset = draw.randint(0, 6)
    if week == 0:
        day = ctx.today - timedelta(days=min(offset, ctx.today.weekday()))
    else:
        day = ctx.weeks_ago(week) - timedelta(days=offset)
    return min(max(day, floor), ctx.today)


def _reference(draw: random.Random, method: str) -> str:
    if method == PaymentMethod.UPI:
        return f"UPI {draw.randrange(10**11, 10**12)}"
    if method == PaymentMethod.BANK_TRANSFER:
        return f"UTR {draw.choice(BANKS).split()[0].upper()}N{draw.randrange(10**10, 10**11)}"
    if method == PaymentMethod.CHEQUE:
        return f"Cheque {draw.randint(100000, 999999)}, {draw.choice(BANKS)}"
    if method == PaymentMethod.CARD:
        return f"Card ending {draw.randint(1000, 9999)}"
    if method == PaymentMethod.OTHER:
        return "Paid by the employer"
    return ""


def _split(draw: random.Random, total: Decimal, parts: int) -> list[Decimal]:
    """``total`` as ``parts`` round instalments, each at least the
    registration fee. Fewer parts when the amount will not stretch."""
    amounts: list[Decimal] = []
    remaining = total
    for index in range(parts - 1):
        slots_left = parts - index - 1
        upper = remaining - MIN_INSTALMENT * slots_left
        if upper < MIN_INSTALMENT:
            break
        share = max(MIN_INSTALMENT, min(_round_step(remaining * _share(draw, 0.25, 0.6)), upper))
        amounts.append(share)
        remaining -= share
    amounts.append(remaining)
    return amounts


def _instalment(draw: random.Random, n: str, amount: Decimal, day: date, text: str) -> PaymentSpec:
    method = _weighted(draw, METHODS)
    return PaymentSpec(
        n=n,
        amount=amount,
        paid_on=day,
        method=method,
        reference=_reference(draw, method),
        text=text,
        recorder=draw.choice(RECORDERS),
    )


def _draw_payments(
    ctx: Context, draw: random.Random, spec: PlanSpec, outcome: str, floor: date
) -> None:
    """Fill ``spec.payments`` for the outcome. Amounts are drawn before
    dates, so what a plan owes never depends on the calendar; dates are
    drawn per instalment and sorted, so instalment two never precedes
    instalment one."""
    payable = spec.payable
    if outcome == UNPAID or payable <= ZERO:
        return
    if outcome == PAID:
        total = payable
        parts = draw.choice((1, 2, 2, 3))
    else:
        total = _round_step(payable * _share(draw, 0.25, 0.7))
        total = min(max(total, MIN_INSTALMENT), payable - MIN_INSTALMENT)
        if total < MIN_INSTALMENT:
            return
        parts = draw.choice((1, 1, 2))
    amounts = _split(draw, total, parts)
    days = sorted(_paid_on(ctx, draw, floor) for _ in amounts)
    for index, (amount, day) in enumerate(zip(amounts, days, strict=True), start=1):
        if len(amounts) == 1:
            text = "Paid in full" if outcome == PAID else "Registration fee"
        elif index == 1:
            text = "Registration fee"
        else:
            text = f"Instalment {index} of {len(amounts)}"
        spec.payments.append(_instalment(draw, str(index), amount, day, text))


def _headline_payments(ctx: Context, draw: random.Random, spec: PlanSpec) -> None:
    """The headline student: a registration fee a month ago and a second
    instalment **today**, so the ledger has history and today's tile a row."""
    first = _instalment(
        draw, "1", _round_step(spec.payable * Decimal("0.3")), ctx.weeks_ago(4), "Registration fee"
    )
    second = _instalment(
        draw, "2", _round_step(spec.payable * Decimal("0.2")), ctx.today, "Instalment 2 of 4"
    )
    spec.payments = [first, second]


def _with_void(ctx: Context, spec: PlanSpec) -> None:
    """Turn the second instalment into a mistake and its correction: the
    wrong (smaller) amount is recorded, voided with a reason, and the right
    amount re-entered under the next receipt with the same date."""
    original = spec.payments[1]
    wrong = original.amount - STEP
    if wrong < MIN_INSTALMENT:
        wrong = original.amount - Decimal("100")
    mistake = PaymentSpec(
        n=original.n,
        amount=wrong,
        paid_on=original.paid_on,
        method=original.method,
        reference=original.reference,
        text=original.text,
        recorder=original.recorder,
        void_reason=ctx.note(VOID_REASON),
    )
    corrected = PaymentSpec(
        n=f"{original.n}r",
        amount=original.amount,
        paid_on=original.paid_on,
        method=original.method,
        reference=original.reference,
        text=f"{original.text}; re-entered after the voided receipt",
        recorder=original.recorder,
    )
    spec.payments[1:2] = [mistake, corrected]


def _headline_enrolment(ctx: Context, rows: list[Enrollment]) -> Enrollment | None:
    """The headline student's youngest showcase enrolment."""
    headline = (ctx.students.get(MAIN) or [None])[0]
    if headline is None:
        return None
    mine = [row for row in rows if row.student_id == headline.pk]
    return max(mine, key=lambda row: (row.batch.start_date, row.code), default=None)


def _agreed(draw: random.Random, row: Enrollment) -> Decimal:
    fee = row.batch.course.default_fee
    return Decimal(fee) if fee else draw.choice(SITP_FEES)


def _due_amount(draw: random.Random, spec: PlanSpec) -> Decimal:
    """Part or all of the balance, rounded, never more than is owed."""
    amount = _round_step(spec.balance * _share(draw, 0.3, 1.0))
    return min(max(amount, MIN_INSTALMENT), spec.balance)


def _floor(ctx: Context, row: Enrollment, *, imported: bool) -> date:
    """The earliest day a payment on ``row`` may be dated.

    Three weeks before the batch starts — the fee is usually paid before the
    first class — but never later than a fortnight ago, so a batch that
    starts next month has a fortnight of payments rather than a pile dated
    today. A showcase enrolment is never paid before it exists; an imported
    one keeps the batch floor, because the import stamped ``enrolled_at``
    with the day it ran, months after the cohort paid.
    """
    floor = min(row.batch.start_date - timedelta(days=21), ctx.days_ago(RECENT_DAYS))
    if not imported and row.enrolled_at is not None:
        floor = max(floor, timezone.localtime(row.enrolled_at).date())
    return floor


def _plan(ctx: Context) -> Plan:
    """Every draw, per enrolment, before a single write."""
    plan = Plan()

    # --- showcase --------------------------------------------------------
    showcase = _showcase_enrolments(ctx)
    planned = set(
        FeePlan.objects.filter(enrollment__in=showcase).values_list("enrollment_id", flat=True)
    )
    headline = _headline_enrolment(ctx, showcase)
    # Left without a plan: the lowest-scoring *live* enrolments that have
    # none. A row that has a plan is always a spec — found on a re-run,
    # whether it is still live or stage 7 has completed it since — and a
    # completed row without one never gets one. So a re-run's specs are the
    # first run's exactly, and the five can only dwindle as they complete.
    unplanned = [
        row
        for row in showcase
        if row is not headline and row.pk not in planned and row.status in LIVE_STATUSES
    ]
    without = set(_lowest("without", unplanned, NO_PLAN))
    plan.without_plan = [row for row in showcase if row in without]
    rows = [
        row
        for row in showcase
        if row not in without and (row.pk in planned or row.status in LIVE_STATUSES)
    ]

    discounted = _lowest("discount", [row for row in rows if row is not headline], DISCOUNTS)
    # The waived plan goes to a student with only this showcase enrolment,
    # so the derived status on the student reads *waived* too.
    per_student: dict[Any, int] = {}
    for row in showcase:
        per_student[row.student_id] = per_student.get(row.student_id, 0) + 1
    waived = next((row for row in discounted if per_student[row.student_id] == 1), None)
    if waived is None and discounted:
        waived = discounted[0]

    for row in rows:
        draw = _seed("plan", row.code)
        agreed = _agreed(draw, row)
        discount, reason = ZERO, ""
        if row is waived:
            discount, reason = agreed, WAIVER_REASON
        elif row in discounted:
            share, fixed, reason = draw.choice(DISCOUNT_KINDS)
            discount = min(_round_step(agreed * share) if share is not None else fixed, agreed)
        spec = PlanSpec(row, row.batch.branch.code, agreed, discount, reason)
        if row is headline:
            _headline_payments(ctx, draw, spec)
        else:
            outcome = _weighted(draw, SHOWCASE_OUTCOMES)
            _draw_payments(ctx, draw, spec, outcome, _floor(ctx, row, imported=False))
        plan.specs.append(spec)

    voidable = [s for s in plan.specs if len(s.payments) >= 2 and s.enrollment is not headline]
    for spec in _lowest("void", voidable, VOIDS):
        _with_void(ctx, spec)

    # --- imported SITP ------------------------------------------------------
    for row in _imported_enrolments(ctx):
        draw = _seed("plan", row.code)
        spec = PlanSpec(row, row.batch.branch.code, _agreed(draw, row), ZERO, "", imported=True)
        outcome = _weighted(draw, SITP_OUTCOMES)
        _draw_payments(ctx, draw, spec, outcome, _floor(ctx, row, imported=True))
        plan.specs.append(spec)

    # --- ageing ----------------------------------------------------------
    _draw_ageing(ctx, plan, headline)
    return plan


def _draw_ageing(ctx: Context, plan: Plan, headline: Enrollment | None) -> None:
    """Which plans owe something overdue, and since when.

    The candidates are the showcase plans with a balance, in the order of
    their own scores — the reviewer opens those by name — and the imported
    *live* ones after them, only reached when the showcase has too few.
    The buckets are dealt in turn off that order, except 90+, which takes
    the plans whose batches started earliest (the oldest start dates, not
    "started more than N days ago": that would move with the calendar), so
    a due date months ago belongs to a cohort that was there months ago.
    """
    ordered = [
        s
        for s in plan.specs
        if s.balance >= MIN_INSTALMENT
        and s.enrollment is not headline
        and (s.is_live or not s.imported)
    ]

    def by_score(spec: PlanSpec) -> tuple:
        return (spec.imported, _score("ageing", spec.code))

    def by_start(spec: PlanSpec) -> tuple:
        return (spec.imported, spec.enrollment.batch.start_date, _score("ageing", spec.code))

    ordered.sort(key=by_score)
    for label, oldest, youngest in OVERDUE_BUCKETS:
        ordered.sort(key=by_start if label == "90+" else by_score)
        picked, ordered = ordered[:OVERDUE_PER_BUCKET], ordered[OVERDUE_PER_BUCKET:]
        for spec in picked:
            draw = _seed("ageing", spec.code)
            on = ctx.days_ago(draw.randint(youngest, oldest))
            spec.next_due = (_due_amount(draw, spec), on, label)
    ordered.sort(key=by_score)
    for spec in ordered[:DUE_SOON]:
        draw = _seed("ageing", spec.code)
        on = ctx.days_ahead(draw.randint(1, 7))
        spec.next_due = (_due_amount(draw, spec), on, "due soon")
    if headline is not None:
        spec = next(s for s in plan.specs if s.enrollment is headline)
        if spec.balance >= MIN_INSTALMENT:
            draw = _seed("ageing", spec.code)
            spec.next_due = (_due_amount(draw, spec), ctx.days_ahead(5), "due soon")


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    if not ctx.showcase_batches and not ctx.imported_batches:
        raise RuntimeError("No showcase or imported batches: run the batches stage first.")
    if not ctx.imported_batches:
        ctx.out("imported batches: none on this database")

    plan = _plan(ctx)
    showcase = sum(1 for s in plan.specs if not s.imported)
    ctx.out(
        f"fees/plan: {showcase} showcase plans ({len(plan.without_plan)} enrolments left "
        f"without), {len(plan.specs) - showcase} imported plans, "
        f"{sum(len(s.payments) for s in plan.specs)} payments"
    )
    for row in plan.without_plan:
        ctx.out(f"no plan on purpose: {row.code} ({row.student.user.email})")

    plans = _timed(ctx, "plans", lambda: _ensure_plans(ctx, plan))
    _timed(ctx, "payments", lambda: _ensure_payments(ctx, plan, plans))
    _timed(ctx, "ageing", lambda: _ensure_next_dues(ctx, plan, plans))
    _timed(ctx, "status sync", lambda: _sync_statuses(ctx, plan, plans))
    _timed(ctx, "backdating", lambda: _backdate(ctx, plan))


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> Any:
    started = perf_counter()
    result = step()
    ctx.out(f"fees/{what}: {perf_counter() - started:.1f}s")
    return result


def _recorder(ctx: Context, branch_code: str, who: str) -> User:
    """The staff member who took the money: the centre's admin, manager or
    counsellor, falling back to the centre's actor where it has fewer."""
    slots = {"admin": ctx.admins, "manager": ctx.managers, "counsellor": ctx.counsellors}
    return slots[who].get(branch_code) or ctx.actor_for(branch_code)


def _ensure_plans(ctx: Context, plan: Plan) -> dict[Any, FeePlan]:
    """One ``set_fee_plan`` per enrolment without a plan. Returns the plans
    this stage may write against, by enrolment pk: a plan whose notes lack
    the marker was somebody else's and is left exactly as found."""
    ids = [s.enrollment.pk for s in plan.specs]
    existing = {
        row.enrollment_id: row
        for row in FeePlan.objects.filter(enrollment_id__in=ids).select_related(
            "enrollment__student__user", "enrollment__batch"
        )
    }
    ours: dict[Any, FeePlan] = {}
    made = found = foreign = 0
    for spec in plan.specs:
        row = existing.get(spec.enrollment.pk)
        if row is not None:
            ctx.found_existing("fee_plan")
            found += 1
            if row.notes.startswith(MARKER):
                ours[spec.enrollment.pk] = row
            else:
                foreign += 1
                ctx.out(f"plan {spec.code}: found, not ours; left alone")
            continue
        row = set_fee_plan(
            enrollment=spec.enrollment,
            actor=ctx.actor_for(spec.branch_code),
            agreed_amount=spec.agreed,
            discount_amount=spec.discount,
            discount_reason=spec.discount_reason,
            notes=ctx.note(PLAN_NOTE),
        )
        ctx.created("fee_plan")
        plan.created_plans.append((row, spec))
        ours[spec.enrollment.pk] = row
        made += 1
    ctx.out(f"plans: {made} created, {found} found ({foreign} not ours)")
    return ours


def _tag_of(note: str) -> str:
    """``[showcase][fee/GRS-E-00012/2]`` out of the note it starts."""
    end = note.find("]", len(MARKER) + 1)
    return note[: end + 1] if end > 0 else note


def _ensure_payments(ctx: Context, plan: Plan, plans: dict[Any, FeePlan]) -> None:
    """Every instalment, in order, then the void where the spec says so.

    Order matters twice: a payment cannot exceed the balance, so the wrong
    amount is voided before its correction is recorded; and a re-run finds
    each by its tag, so nothing is recorded twice. A plan that already
    carries tagged payments from an earlier run but lacks the tag for one
    of the instalments drawn now was drawn differently then — which the
    per-enrolment seeds are there to prevent — and is skipped whole, with
    a line saying so, rather than paid past its balance.
    """
    existing = {
        _tag_of(row.note): row for row in FeePayment.objects.filter(note__startswith=TAG_PREFIX)
    }
    tagged_plans = {row.plan_id for row in existing.values()}
    made = found = voided = kept = skipped = 0
    for spec in plan.specs:
        fee_plan = plans.get(spec.enrollment.pk)
        if fee_plan is None or not spec.payments:
            continue
        tags = [ctx.tag(f"fee/{spec.code}/{instalment.n}") for instalment in spec.payments]
        if fee_plan.pk in tagged_plans and any(tag not in existing for tag in tags):
            missing = ", ".join(tag for tag in tags if tag not in existing)
            ctx.out(f"payments {spec.code}: plan already paid under other tags; skipped {missing}")
            skipped += 1
            continue
        for instalment, tag in zip(spec.payments, tags, strict=True):
            payment = existing.get(tag)
            if payment is None:
                payment = record_payment(
                    plan=fee_plan,
                    actor=_recorder(ctx, spec.branch_code, instalment.recorder),
                    amount=instalment.amount,
                    paid_on=instalment.paid_on,
                    method=instalment.method,
                    reference=instalment.reference,
                    note=ctx.tag(f"fee/{spec.code}/{instalment.n}", instalment.text),
                )
                ctx.created("fee_payment")
                plan.created_payments.append((payment, instalment))
                made += 1
            else:
                ctx.found_existing("fee_payment")
                found += 1
            if not instalment.void_reason:
                continue
            if payment.is_voided:
                ctx.found_existing("fee_void")
                kept += 1
            else:
                void_payment(
                    payment=payment,
                    actor=ctx.actor_for(spec.branch_code),
                    reason=instalment.void_reason,
                )
                ctx.created("fee_void")
                plan.voided.append(payment)
                voided += 1
    ctx.out(
        f"payments: {made} created, {found} found; voids: {voided} created, {kept} found"
        + (f"; {skipped} plans skipped" if skipped else "")
    )


def _ensure_next_dues(ctx: Context, plan: Plan, plans: dict[Any, FeePlan]) -> None:
    """``set_next_due`` on the picked plans. Dates are relative to today, so
    on a later day the same plan is *found* and its date refreshed; a plan
    whose ledger no longer owes anything (somebody paid) is skipped."""
    made = found = skipped = 0
    buckets: dict[str, int] = {}
    for spec in plan.specs:
        fee_plan = plans.get(spec.enrollment.pk)
        if spec.next_due is None or fee_plan is None:
            continue
        amount, on, label = spec.next_due
        balance = fee_plan.balance
        if balance <= ZERO:
            skipped += 1
            ctx.out(f"next due {spec.code}: nothing owed any more, skipped")
            continue
        before = (fee_plan.next_due_amount, fee_plan.next_due_on)
        set_next_due(
            plan=fee_plan,
            actor=ctx.actor_for(spec.branch_code),
            amount=min(amount, balance),
            on=on,
        )
        if before[1] is not None:
            ctx.found_existing("fee_next_due")
            found += 1
            if before != (fee_plan.next_due_amount, fee_plan.next_due_on):
                ctx.out(f"next due {spec.code}: refreshed to {on:%d %b} ({label})")
        else:
            ctx.created("fee_next_due")
            made += 1
        buckets[label] = buckets.get(label, 0) + 1
    detail = ", ".join(f"{label}: {n}" for label, n in buckets.items())
    ctx.out(f"next dues: {made} created, {found} found, {skipped} skipped — {detail}")


def _sync_statuses(ctx: Context, plan: Plan, plans: dict[Any, FeePlan]) -> None:
    """Derive ``fee_status`` for every student whose ledger this stage owns —
    the plan and payment services did it as they went, but ``set_next_due``
    does not, and *overdue* only exists after it.

    The profiles are loaded afresh first: the instances on the specs were
    read before any write, and the service compares the derived status
    with the instance it is handed — a stale one would make it record a
    change "from pending" on a student the ledger had long moved on.
    """
    actors: dict[Any, User] = {}
    for spec in plan.specs:
        if spec.enrollment.pk in plans:
            actors.setdefault(spec.enrollment.student_id, ctx.actor_for(spec.branch_code))
    fresh = StudentProfile.objects.in_bulk(list(actors))
    for student_id, actor in actors.items():
        sync_student_fee_status(fresh[student_id], actor=actor)
    ctx.out(f"fee status derived for {len(actors)} students")


def _backdate(ctx: Context, plan: Plan) -> None:
    """Only rows this run created, and only after their last service call.

    A plan is dated at the enrolment — or, when its first payment is dated
    earlier than that, at half past nine on the morning of that payment, so
    the plan is always the first line of its history. Payments are stamped
    between ten and six on the day they were paid.
    """
    for fee_plan, spec in plan.created_plans:
        when = spec.enrollment.enrolled_at or spec.enrollment.created_at or ctx.now
        first_paid = min((p.paid_on for p in spec.payments), default=None)
        if first_paid is not None:
            when = min(when, ctx.at(first_paid, 9, 30))
        ctx.backdate(fee_plan, created_at=min(when, ctx.now))
    for payment, instalment in plan.created_payments:
        # The desk is open ten to six; the uuid spreads the minutes.
        hour, minute = 10 + payment.pk.int % 8, (payment.pk.int >> 4) % 60
        stamped = min(ctx.at(instalment.paid_on, hour, minute), ctx.now)
        ctx.backdate(payment, created_at=stamped, updated_at=stamped)
    for payment in plan.voided:
        stamped = min(ctx.at(payment.paid_on + timedelta(days=1), 11, 15), ctx.now)
        ctx.backdate(payment, voided_at=stamped, updated_at=stamped)
    ctx.out(
        f"backdated {len(plan.created_plans)} plans, {len(plan.created_payments)} payments, "
        f"{len(plan.voided)} voids"
    )
