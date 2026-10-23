"""An admission: the act of putting a student on one or more courses at once.

Until now the record of that act was implicit. A counsellor enrolled a student
on a course, set a fee against the enrolment, and did it again for the second
course — two enrolments, two fees, and nothing saying they were one
conversation on one afternoon for one agreed total. "What did this student
sign up for in October" had no row to point at, and a discount agreed across
two courses had nowhere to live.

`Admission` is that row. It carries the date, the academic year, the note and
the discount, and it holds one `AdmissionLine` per thing being charged for.

**Money stays where it was** (owner's decision, 23 October 2026). Each course
line still creates its own `Enrollment` and its own `FeePlan`, so "which
course was that ₹5,000 for" keeps the answer it has always had, the fee
ledger, the cancellation and the reconciliation are untouched, and this app
groups rather than replaces. What the admission adds on top is the grouping,
the one agreed total and the one discount — which it *splits* across those
plans rather than holding centrally, so no figure exists in two places.

An additional-fee line (an exam fee, a kit) names the course line it belongs
to, and its amount is charged on that course's plan. It has to belong
somewhere: a fee with no course has no enrolment, and an enrolment is where a
`FeePlan` hangs. Keeping the line here as well means the breakdown survives —
the receipt can still say "Data Analytics 30,000, exam fee 2,000" — while the
ledger keeps one plan per course and the totals keep adding up.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers
from apps.common.validators import validate_no_control_characters

ZERO = Decimal("0")


class AdmissionStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    CANCELLED = "cancelled", _("Cancelled")


class DiscountKind(models.TextChoices):
    """How the discount was agreed — the Flat/Percent toggle on the form.

    Both are stored: the percentage because it is what was agreed and what
    somebody will ask about later, and the amount because it is what was
    actually taken off and must not move when a fee is edited afterwards.
    """

    FLAT = "flat", _("Flat")
    PERCENT = "percent", _("Percent")


class AdmissionQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "student", "student__user", "branch", "academic_year", "created_by"
        ).prefetch_related(
            "lines",
            "lines__course",
            # Through to the payments: `money()` reads them for every line, and
            # without this an admission list is a query per course per row.
            "lines__enrollment__fee_plan__payments",
        )

    def live(self):
        return self.filter(status=AdmissionStatus.ACTIVE)


class Admission(SoftDeleteBaseModel):
    """One student signing up for one or more courses, on one date."""

    student = models.ForeignKey(
        "students.StudentProfile",
        on_delete=models.PROTECT,
        related_name="admissions",
        verbose_name=_("student"),
    )
    #: Denormalised from the student when the admission is made, so scoping a
    #: list or a report to a centre never joins through the student.
    branch = models.ForeignKey(
        "organisation.Branch",
        on_delete=models.PROTECT,
        related_name="admissions",
        verbose_name=_("centre"),
    )
    #: Nullable because 657 admissions already existed when years became a
    #: record. A report filtered by year shows those under "no year" rather
    #: than hiding them.
    academic_year = models.ForeignKey(
        "organisation.AcademicYear",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="admissions",
        verbose_name=_("academic year"),
    )
    admission_date = models.DateField(_("admission date"), default=timezone.localdate)
    status = models.CharField(
        _("status"),
        max_length=12,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.ACTIVE,
        db_index=True,
    )

    # --- What was agreed overall
    #
    # `discount_amount` is the rupees taken off the whole admission, and it is
    # what gets split across the course plans. `discount_percent` is kept only
    # when that is how it was agreed — see `DiscountKind`.
    discount_kind = models.CharField(
        _("discount kind"), max_length=8, choices=DiscountKind.choices, default=DiscountKind.FLAT
    )
    discount_amount = models.DecimalField(
        _("discount"),
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    discount_percent = models.DecimalField(
        _("discount percent"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    note = models.TextField(_("note"), blank=True, validators=[validate_no_control_characters])

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_admissions",
    )
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    cancellation_reason = models.CharField(
        _("cancellation reason"),
        max_length=300,
        blank=True,
        validators=[validate_no_control_characters],
    )

    objects, all_objects = soft_delete_managers(AdmissionQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("admission")
        verbose_name_plural = _("admissions")
        ordering = ("-admission_date", "-created_at")
        indexes = [
            models.Index(fields=["student", "-admission_date"], name="admission_student_idx"),
            models.Index(fields=["branch", "status"], name="admission_branch_status_idx"),
            models.Index(fields=["academic_year", "-admission_date"], name="admission_year_idx"),
        ]

    def __str__(self) -> str:
        return f"Admission {self.pk} on {self.admission_date}"

    @property
    def is_cancelled(self) -> bool:
        return self.status == AdmissionStatus.CANCELLED

    @property
    def gross_total(self) -> Decimal:
        """What the lines come to before the discount."""
        return sum((line.line_total for line in self.lines.all()), ZERO)

    @property
    def total_fees(self) -> Decimal:
        """What was agreed: the lines less the discount, never below zero."""
        return max(self.gross_total - self.discount_amount, ZERO)

    def money(self) -> dict[str, Decimal]:
        """The five figures the admission list shows: Total, Paid, Uncleared,
        Refund, Balance.

        Read from the fee ledger — each course line's own plan — rather than
        held here. The admission says what was *agreed*; what has actually
        been received is the ledger's answer and must have exactly one source.
        A line with no enrolment yet (no batch chosen) contributes its agreed
        figure and nothing else, which is the truth about it.

        `uncleared` is money taken that the bank has not confirmed: a cheque
        handed over on Tuesday. It is part of `paid` — the student has paid,
        the balance has dropped, the receipt has printed — and is reported
        beside it so somebody can see how much of the balance is a promise.
        """
        from apps.fees.models import ClearingStatus

        total = self.total_fees
        paid = uncleared = refunded = ZERO
        for line in self.lines.all():
            if line.kind != LineKind.COURSE or line.enrollment_id is None:
                continue
            plan = getattr(line.enrollment, "fee_plan", None)
            if plan is None:
                continue
            for payment in plan.payments.all():
                if payment.voided_at is not None:
                    continue
                if payment.refunded_at is not None:
                    refunded += payment.amount
                    continue
                paid += payment.amount
                if payment.clearing_status == ClearingStatus.UNCLEARED:
                    uncleared += payment.amount
        return {
            "total": total,
            "paid": paid,
            "uncleared": uncleared,
            "refund": refunded,
            "balance": max(total - paid, ZERO),
        }


class LineKind(models.TextChoices):
    COURSE = "course", _("Course")
    ADDITIONAL_FEE = "additional_fee", _("Additional Fee")


class AdmissionLine(SoftDeleteBaseModel):
    """One charged thing on an admission: a course, or a fee beside one."""

    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name="lines", verbose_name=_("admission")
    )
    kind = models.CharField(
        _("kind"), max_length=16, choices=LineKind.choices, default=LineKind.COURSE
    )
    #: Set on a course line, never on an additional fee.
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="admission_lines",
        verbose_name=_("course"),
    )
    #: What an additional fee is called ("Exam fee", "Kit"). Blank on a course
    #: line, which is named by its course.
    label = models.CharField(
        _("label"), max_length=120, blank=True, validators=[validate_no_control_characters]
    )
    #: The course line an additional fee is charged on. An additional fee has
    #: to belong to a course, because a course is what has an enrolment and an
    #: enrolment is what has a fee plan — see this module's docstring.
    charged_on = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="additional_fees",
        verbose_name=_("charged on"),
    )
    quantity = models.PositiveSmallIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)]
    )
    #: What one of this line costs, as agreed on the day. Copied from the
    #: course's price at the time and then frozen: a later price change never
    #: moves what this student was charged.
    unit_fee = models.DecimalField(
        _("unit fee"),
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    #: This line's share of the admission's discount, in rupees. Written by
    #: `services.create_admission`, which splits the whole discount across the
    #: course lines so the parts add back to exactly the whole.
    discount_share = models.DecimalField(
        _("discount share"),
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    #: The enrolment this course line created. Set only on course lines.
    enrollment = models.OneToOneField(
        "enrollments.Enrollment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="admission_line",
        verbose_name=_("enrolment"),
    )

    objects, all_objects = soft_delete_managers(SoftDeleteQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("admission line")
        verbose_name_plural = _("admission lines")
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="course", course__isnull=False)
                    | models.Q(kind="additional_fee", course__isnull=True)
                ),
                name="admissionline_course_matches_kind",
            )
        ]

    def __str__(self) -> str:
        return self.label or (self.course.title if self.course_id else "line")

    @property
    def line_total(self) -> Decimal:
        """Quantity times the agreed unit fee. The discount is not taken off
        here: it belongs to the admission, and each line's share of it is
        recorded separately so the two can be read apart."""
        return (self.unit_fee or ZERO) * self.quantity

    @property
    def name(self) -> str:
        return self.label or (self.course.title if self.course_id else "")
