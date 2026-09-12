"""The fee ledger: what was agreed for a course, and what has been paid.

One plan per enrolment, not per student. A student on two courses has two fees,
agreed at different times, possibly discounted differently, paid down on their
own timetables — putting one number on the student would make "which course
was that ₹5,000 for" a question nobody could answer.

The plan holds what was *agreed*: the course fee, any discount, and an optional
"next ₹N expected by <date>". Payments are appended underneath it, any amount,
whenever they happen — a counsellor's day is a ₹1,000 registration here, ₹8,000
after a salary comes in there, the rest in two months. Nothing here is a
schedule that has to be honoured; the plan says what is owed, the payments say
what has been received, and the balance is the difference.

A payment is never edited or deleted. A mistake is *voided* — kept, marked,
with a reason and a name — because a ledger that can be silently rewritten is
not a ledger. Every change to a plan and every payment is also written to the
audit log by the services, which is where "who changed what, when" is answered.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
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
    CASH = "cash", _("Cash")
    UPI = "upi", _("UPI")
    CARD = "card", _("Card")
    BANK_TRANSFER = "bank_transfer", _("Bank transfer")
    CHEQUE = "cheque", _("Cheque")
    OTHER = "other", _("Other")


class FeePlanStatus(models.TextChoices):
    """Derived, never stored: read off the numbers every time."""

    UNPAID = "unpaid", _("Nothing paid yet")
    PARTIAL = "partial", _("Partly paid")
    PAID = "paid", _("Paid in full")
    WAIVED = "waived", _("Waived")


class FeePlanQuerySet(models.QuerySet):
    def with_totals(self):
        """Annotate what is paid, so a list of plans is one query."""
        return self.annotate(
            paid_total=Coalesce(
                Sum("payments__amount", filter=Q(payments__voided_at__isnull=True)),
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
    discount_reason = models.CharField(
        _("discount reason"),
        max_length=200,
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
        return self.agreed_amount - self.discount_amount

    @property
    def paid(self) -> Decimal:
        """What has actually been received. Voided payments do not count."""
        annotated = getattr(self, "paid_total", None)
        if annotated is not None:
            return Decimal(annotated)
        total = self.payments.filter(voided_at__isnull=True).aggregate(total=Sum("amount"))["total"]
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
    note = models.CharField(
        _("note"), max_length=300, blank=True, validators=[validate_no_control_characters]
    )
    recorded_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="fee_payments_recorded"
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
