"""The fee ledger: what was agreed for a course, and what has been paid.

One plan per enrolment, not per student. A student on two courses has two fees,
agreed at different times, possibly discounted differently, paid down on their
own timetables — putting one number on the student would make "which course
was that ₹5,000 for" a question nobody could answer.

The plan holds what was *agreed*: the course fee, any discount, and an optional
"next ₹N expected by <date>". Payments are appended underneath it, any amount,
whenever they happen — a counsellor's day is a ₹1,000 registration here, ₹8,000
after a salary comes in there, the rest in two months. The plan says what is owed, the
payments say what has been received, and the balance is the difference.

Since October 2026 a plan also carries an instalment *schedule*: by default
six instalments, the first due the day the fee is agreed and the rest every
thirty days, which the counsellor can reshape before saving. The schedule is
a promise about *when*, not a second ledger: payments are still appended
underneath the plan, any amount, and each instalment's state (paid, pending,
overdue, upcoming) is read off the ledger by covering the instalments in
order with what has actually been received. Nothing about an instalment is
ever "marked paid" by hand.

A payment is never edited or deleted. A mistake is *voided* — kept, marked,
with a reason and a name — because a ledger that can be silently rewritten is
not a ledger. Every change to a plan and every payment is also written to the
audit log by the services, which is where "who changed what, when" is answered.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters

#: The registration payment every student makes. A first payment smaller than
#: this is refused by the service unless the whole fee is smaller.
MIN_FIRST_PAYMENT = Decimal("1000")

ZERO = Decimal("0")


class PaymentMethod(models.TextChoices):
    """How the money arrived.

    The fourteen ways the desk is actually paid, in the order the counsellor
    reads them. `CARD` and `BANK_TRANSFER` were this list's original, vaguer
    names and are migrated to `SWIPE_CARD` and `NET_BANKING`; `OTHER` stays
    for rows imported before anybody recorded a method, and is not offered
    when taking a new payment.
    """

    CASH = "cash", _("Cash")
    CASH_DEPOSIT = "cash_deposit", _("Cash deposit in bank")
    CHEQUE = "cheque", _("Cheque")
    DEMAND_DRAFT = "demand_draft", _("Demand Draft")
    SWIPE_CARD = "swipe_card", _("Swipe Card")
    NET_BANKING = "net_banking", _("Net Banking")
    PAYMENT_GATEWAY = "payment_gateway", _("Payment Gateway")
    EMI_CARD = "emi_card", _("EMI card")
    GOOGLE_PAY = "google_pay", _("Google Pay")
    PAYTM = "paytm", _("Paytm")
    UPI = "upi", _("UPI")
    PAYPAL = "paypal", _("Paypal")
    PHONEPE = "phonepe", _("PhonePe")
    CREDIT_CARD = "credit_card", _("Credit card")
    #: Legacy only. Never offered for a new payment.
    OTHER = "other", _("Other")


#: The methods a counsellor may choose when taking money, in the order the
#: dialog lists them. `OTHER` is deliberately absent: it says nothing, and
#: every real way of paying now has its own name above.
SELECTABLE_PAYMENT_METHODS = (
    PaymentMethod.CASH,
    PaymentMethod.CASH_DEPOSIT,
    PaymentMethod.CHEQUE,
    PaymentMethod.DEMAND_DRAFT,
    PaymentMethod.SWIPE_CARD,
    PaymentMethod.NET_BANKING,
    PaymentMethod.PAYMENT_GATEWAY,
    PaymentMethod.EMI_CARD,
    PaymentMethod.GOOGLE_PAY,
    PaymentMethod.PAYTM,
    PaymentMethod.UPI,
    PaymentMethod.PAYPAL,
    PaymentMethod.PHONEPE,
    PaymentMethod.CREDIT_CARD,
)


class ClearingStatus(models.TextChoices):
    """Whether money taken has actually reached the bank.

    A cheque handed over on Tuesday is money received — the student has paid,
    the balance drops, the receipt prints — but it is not money the institute
    holds until the bank says so. `UNCLEARED` is that gap, and it is a real
    one: the receipt itself says "subject to realisation of cheque".

    `BOUNCED` is terminal here only in the sense that the clearing question
    is answered. What happens to the *money* is the ledger's existing answer:
    the payment is voided with a reason, which takes it out of received, out
    of the balance and out of every total, while leaving the record of it.
    """

    CLEARED = "cleared", _("Cleared")
    UNCLEARED = "uncleared", _("Uncleared")
    BOUNCED = "bounced", _("Bounced")


#: The methods whose money is not in the bank the moment it is taken. Anything
#: else clears as it is recorded — cash is cash, and a UPI transfer has either
#: arrived or not happened at all.
UNCLEARED_ON_ARRIVAL = frozenset(
    {PaymentMethod.CHEQUE, PaymentMethod.DEMAND_DRAFT, PaymentMethod.CASH_DEPOSIT}
)


class PaymentCategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class PaymentCategory(BaseModel):
    """What a payment was for: Fees, Registration, Exam fee.

    An administrator's list (Organization → Payment Categories), not an enum,
    because every institute's list is different and none of them is a code
    change. Exactly one is the default, which is what the payment dialog
    opens with.
    """

    name = models.CharField(
        _("name"), max_length=60, unique=True, validators=[validate_no_control_characters]
    )
    is_default = models.BooleanField(_("default"), default=False, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    objects = PaymentCategoryQuerySet.as_manager()

    class Meta:
        verbose_name = _("payment category")
        verbose_name_plural = _("payment categories")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class TaxGroupQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class TaxGroup(BaseModel):
    """A named tax a payment was taken under — GST, and whatever else.

    Recorded, never computed (owner's decision, 23 October 2026). The amount
    on a payment is the amount that changed hands; this says under which tax
    it was taken, so the receipt and an accountant's export can say so. The
    day somebody wants the split, a rate goes here and the arithmetic goes in
    one service — which is why this is a row with a name rather than a
    boolean on the payment.
    """

    name = models.CharField(
        _("name"), max_length=60, unique=True, validators=[validate_no_control_characters]
    )
    is_default = models.BooleanField(_("default"), default=False, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    objects = TaxGroupQuerySet.as_manager()

    class Meta:
        verbose_name = _("tax group")
        verbose_name_plural = _("tax groups")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class PaymentKind(models.TextChoices):
    """What a payment was taken for.

    ``REGISTRATION`` is the booking amount a counsellor takes when a lead
    becomes a student. It counts against the fee like any other payment; it is
    named because it is the one that sometimes goes back.
    """

    REGISTRATION = "registration", _("Registration")
    INSTALMENT = "instalment", _("Instalment")


class FeePlanStatus(models.TextChoices):
    """Derived, never stored: read off the numbers every time."""

    UNPAID = "unpaid", _("Nothing paid yet")
    PARTIAL = "partial", _("Partly paid")
    PAID = "paid", _("Paid in full")
    WAIVED = "waived", _("Waived")


class InstallmentStatus(models.TextChoices):
    """Derived, never stored: read off the ledger every time."""

    PAID = "paid", _("Paid")
    PENDING = "pending", _("Pending")
    OVERDUE = "overdue", _("Overdue")
    UPCOMING = "upcoming", _("Upcoming")


#: The schedule a fee gets unless the counsellor shapes a different one.
DEFAULT_INSTALLMENT_COUNT = 6
DEFAULT_INSTALLMENT_GAP_DAYS = 30
MAX_INSTALLMENTS = 36


#: Money the institution still holds for a plan: not struck out as a mistake,
#: and not given back.
#:
#: Written once because seven places ask it — two annotations, two subqueries,
#: a first-payment check and two dashboard totals — and a refund that counted
#: towards "paid" in any one of them would quietly overstate a student's
#: payments and understate their balance.
LIVE_PAYMENT = Q(voided_at__isnull=True, refunded_at__isnull=True)

#: The same rule, spelled for a query that reaches payments through a relation.
LIVE_PAYMENT_THROUGH = Q(payments__voided_at__isnull=True, payments__refunded_at__isnull=True)


class FeePlanQuerySet(models.QuerySet):
    def with_totals(self):
        """Annotate what is paid, so a list of plans is one query."""
        return self.annotate(
            paid_total=Coalesce(
                Sum("payments__amount", filter=LIVE_PAYMENT_THROUGH),
                ZERO,
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )


class FeePlan(BaseModel):
    enrollment = models.OneToOneField(
        "enrollments.Enrollment",
        on_delete=models.PROTECT,
        related_name="fee_plan",
        help_text=_("The course this fee is for."),
    )
    agreed_amount = models.DecimalField(
        _("agreed fee"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text=_("The course fee agreed with the student, in rupees, before any discount."),
    )
    discount_amount = models.DecimalField(
        _("discount"),
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    discount_percent = models.DecimalField(
        _("discount percentage"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100"))],
        help_text=_(
            "Set when the discount was given as a percentage of the fee; "
            "`discount_amount` is then worked out from it. Empty for a flat discount."
        ),
    )
    discount_reason = models.CharField(
        _("discount reason"),
        max_length=200,
        blank=True,
        validators=[validate_no_control_characters],
    )
    #: What is owed after an admission is cancelled — the cancellation charge
    #: the institute keeps. ``None`` means the admission was never cancelled.
    #:
    #: Stored rather than derived because it is a decision, not a calculation:
    #: somebody looked at how much of the course had run and agreed a figure.
    #: Deriving it later from a rule would rewrite history every time the rule
    #: changed, which is the thing this ledger does not do.
    #:
    #: Zero is a real answer and a common one — cancelled early, nothing kept —
    #: which is exactly why it is nullable. "Charged nothing" and "never
    #: cancelled" are different facts and a zero cannot tell them apart.
    settled_amount = models.DecimalField(
        _("settled amount"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO)],
        help_text=_("What is owed after cancellation. Empty if not cancelled."),
    )
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_plans_cancelled",
    )
    cancellation_reason = models.CharField(
        _("cancellation reason"),
        max_length=300,
        blank=True,
        validators=[validate_no_control_characters],
    )
    next_due_amount = models.DecimalField(
        _("next amount expected"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    next_due_on = models.DateField(_("expected by"), null=True, blank=True)
    notes = models.TextField(
        _("notes"), max_length=1000, blank=True, validators=[validate_no_control_characters]
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="fee_plans_created"
    )
    updated_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="fee_plans_updated"
    )

    objects = FeePlanQuerySet.as_manager()

    class Meta:
        verbose_name = _("fee plan")
        verbose_name_plural = _("fee plans")
        indexes = [models.Index(fields=["next_due_on"], name="feeplan_next_due_idx")]

    def __str__(self) -> str:
        return f"Fee for {self.enrollment_id}: {self.agreed_amount}"

    # --- the arithmetic, in one place -------------------------------------

    @property
    def payable(self) -> Decimal:
        """What is owed.

        After a cancellation that is the settled amount — the charge agreed at
        the time — and not the original fee. The original is still on the row
        as `agreed_amount`, so what was charged before and what is owed after
        are both answerable; a cancellation that overwrote the fee would lose
        the first.
        """
        if self.settled_amount is not None:
            return self.settled_amount
        return self.agreed_amount - self.discount_amount

    @property
    def gross_payable(self) -> Decimal:
        """What was charged before any cancellation. What the institute said
        was owed, which is the figure a reconciliation starts from."""
        return self.agreed_amount - self.discount_amount

    @property
    def written_off(self) -> Decimal:
        """The part of the original fee the institute decided not to pursue."""
        if self.settled_amount is None:
            return ZERO
        return max(self.gross_payable - self.settled_amount, ZERO)

    @property
    def refund_due(self) -> Decimal:
        """Money held that is no longer the institute's.

        Somebody who paid more than the cancellation charge is owed the
        difference. It is a liability from the moment of cancellation, whether
        or not anybody has got round to paying it back.
        """
        if self.settled_amount is None:
            return ZERO
        return max(self.paid - self.settled_amount, ZERO)

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

    @property
    def paid(self) -> Decimal:
        """What has actually been received. Voided payments do not count."""
        annotated = getattr(self, "paid_total", None)
        if annotated is not None:
            return Decimal(annotated)
        total = self.payments.filter(LIVE_PAYMENT).aggregate(total=Sum("amount"))["total"]
        return Decimal(total or 0)

    @property
    def balance(self) -> Decimal:
        return self.payable - self.paid

    @property
    def status(self) -> str:
        if self.payable <= ZERO:
            return FeePlanStatus.WAIVED
        if self.balance <= ZERO:
            return FeePlanStatus.PAID
        if self.paid > ZERO:
            return FeePlanStatus.PARTIAL
        return FeePlanStatus.UNPAID

    @property
    def is_overdue(self) -> bool:
        """An expected date has passed and money is still owed."""
        return bool(
            self.next_due_on and self.next_due_on < timezone.localdate() and self.balance > ZERO
        )


class FeePayment(BaseModel):
    plan = models.ForeignKey(FeePlan, on_delete=models.PROTECT, related_name="payments")
    receipt_number = models.CharField(
        _("receipt number"), max_length=20, unique=True, editable=False
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    paid_on = models.DateField(_("paid on"), default=timezone.localdate, db_index=True)
    method = models.CharField(
        _("method"), max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    reference = models.CharField(
        _("reference"),
        max_length=100,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("A UPI or bank transaction id, a cheque number."),
    )
    reference_name = models.CharField(
        _("reference name"),
        max_length=120,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("Who made or handled the payment: a parent, the owner, the scanner operator."),
    )
    note = models.CharField(
        _("note"), max_length=300, blank=True, validators=[validate_no_control_characters]
    )
    recorded_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="fee_payments_recorded"
    )

    # --- Where the money went through, and under what heading
    #
    # All four are recorded facts about one payment, never inputs to a
    # calculation: the amount is the amount. `apply_tax`/`tax_group` say what
    # the desk declared at the counter so the receipt and an accountant's
    # export can repeat it (owner's decision, 23 October 2026 — record it,
    # do not compute it).
    bank = models.ForeignKey(
        "organisation.Bank",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("bank"),
        help_text=_("The bank a cheque, draft or deposit went through."),
    )
    category = models.ForeignKey(
        PaymentCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("payment category"),
    )
    apply_tax = models.BooleanField(_("tax applied"), default=False)
    tax_group = models.ForeignKey(
        TaxGroup,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("tax group"),
    )

    # --- Has it reached the bank?
    #
    # A cheque is received the day it is handed over and held the day it
    # clears, and the gap between them is real money nobody has yet. The
    # balance follows *received*, as it always has; `clearing_status` is what
    # the Uncleared figure reads, and what the receipt's "subject to
    # realisation of cheque" refers to.
    clearing_status = models.CharField(
        _("clearing"),
        max_length=10,
        choices=ClearingStatus.choices,
        default=ClearingStatus.CLEARED,
        db_index=True,
    )
    cleared_on = models.DateField(_("cleared on"), null=True, blank=True)
    cleared_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    #: Which instalment this payment was taken against, when it was taken
    #: against one. Optional, and never the source of truth for whether an
    #: instalment is paid: that is still read off the ledger by covering the
    #: schedule in order with what has been received, so a payment made
    #: without naming an instalment still settles the schedule.
    instalment = models.ForeignKey(
        "fees.FeeInstallment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        verbose_name=_("instalment"),
    )

    #: What this payment was for.
    #:
    #: A counsellor turning a lead into a student takes a booking amount —
    #: around a thousand rupees — to hold the seat. It is a real payment that
    #: counts against the fee, so it is a payment row and not a field somewhere
    #: else; what makes it different is that it is sometimes given back.
    kind = models.CharField(
        _("kind"),
        max_length=16,
        choices=PaymentKind.choices,
        default=PaymentKind.INSTALMENT,
        db_index=True,
    )
    #: Whether this one was taken on the understanding it can be returned.
    #: Decided per payment, not per institution: the same booking amount is
    #: refundable for one student and not for another, and only the person who
    #: took it knows which was agreed.
    is_refundable = models.BooleanField(
        _("refundable"),
        default=False,
        help_text=_("Whether this payment was taken on terms that allow it to be returned."),
    )

    # Giving money back is not the same as striking out a mistake. A void says
    # the payment should never have been recorded; a refund says it was correct
    # and the money has since gone back to the student. Both stop it counting
    # towards what has been paid, and the ledger must be able to tell an
    # accountant which happened.
    refunded_at = models.DateTimeField(_("refunded at"), null=True, blank=True)
    refunded_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_payments_refunded",
    )
    refund_reason = models.CharField(
        _("refund reason"), max_length=300, blank=True, validators=[validate_no_control_characters]
    )

    # A mistake is marked, never removed.
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_payments_voided",
    )
    void_reason = models.CharField(
        _("void reason"), max_length=300, blank=True, validators=[validate_no_control_characters]
    )

    class Meta:
        verbose_name = _("fee payment")
        verbose_name_plural = _("fee payments")
        ordering = ("-paid_on", "-created_at")
        indexes = [models.Index(fields=["plan", "voided_at"], name="feepayment_plan_live_idx")]

    def __str__(self) -> str:
        return f"{self.receipt_number}: {self.amount} on {self.paid_on}"

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    @property
    def is_refunded(self) -> bool:
        return self.refunded_at is not None

    @property
    def counts_towards_paid(self) -> bool:
        """Whether this payment still stands as money the institution holds."""
        return self.voided_at is None and self.refunded_at is None


class FeeInstallment(BaseModel):
    """One expected slice of a fee: how much, by when. State is derived."""

    plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name="installments")
    sequence = models.PositiveSmallIntegerField(_("sequence"))
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    due_on = models.DateField(_("due on"), db_index=True)

    class Meta:
        verbose_name = _("fee instalment")
        verbose_name_plural = _("fee instalments")
        ordering = ("plan", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "sequence"], name="feeinstallment_plan_sequence_uniq"
            )
        ]

    def __str__(self) -> str:
        return f"Instalment {self.sequence}: {self.amount} by {self.due_on}"


def installment_rows(plan: FeePlan, installments=None, *, today=None) -> list[dict]:
    """Each instalment with how much of it is covered and what state that makes it.

    Payments are not tied to instalments — a student who pays ₹5,000 against
    two ₹3,000 instalments has simply paid the first and half the second. So
    the plan's `paid` total is poured over the schedule in order: an
    instalment is *paid* once fully covered; the first uncovered one whose
    date has not passed is *pending* (it is the one being collected now);
    anything uncovered and past its date is *overdue*; the rest are *upcoming*.
    """
    today = today or timezone.localdate()
    rows = list(installments if installments is not None else plan.installments.all())
    remaining = plan.paid
    result: list[dict] = []
    pending_taken = False
    for item in rows:
        covered = min(item.amount, max(remaining, ZERO))
        remaining -= covered
        if covered >= item.amount:
            state = InstallmentStatus.PAID
        elif item.due_on < today:
            state = InstallmentStatus.OVERDUE
        elif not pending_taken:
            state = InstallmentStatus.PENDING
            pending_taken = True
        else:
            state = InstallmentStatus.UPCOMING
        result.append(
            {
                "id": item.pk,
                "sequence": item.sequence,
                "amount": item.amount,
                "due_on": item.due_on,
                "paid_amount": covered,
                "balance": item.amount - covered,
                "status": state,
            }
        )
    return result
