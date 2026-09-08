"""Student profile.

Kept separate from ``accounts.User`` on purpose: authentication data changes
rarely and is read on every request, while student detail is large, optional and
read on profile screens. Splitting them keeps the auth table small and means a
new student field never touches the login path.

Field selection follows data minimisation — only what Grras actually needs to
run admissions and contact a student. Deliberately **not** collected: gender,
national identity numbers, caste/religion, and any medical detail. Nothing in
the LMS makes a decision from them, and data not collected cannot leak.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.common.validators import validate_no_control_characters, validate_phone_number


class FeeStatus(models.TextChoices):
    """Coarse fee state, maintained by administrators.

    Scope note: this is a *status flag*, not an accounting system. There are no
    transactions or receipts here by design — a fee ledger belongs with the
    payments module in a later phase, and putting half of one here would create
    a second source of truth about money.

    The one figure that does live here is ``fee_amount``: the fee agreed with
    the student at registration, which the counsellor or manager decides case
    by case. It is a *quoted* amount, not a balance — what was agreed, not what
    has been paid — and it exists so that the status above has a number to be
    a status *of*.
    """

    PENDING = "pending", _("Pending")
    PARTIAL = "partial", _("Partially paid")
    PAID = "paid", _("Paid")
    WAIVED = "waived", _("Waived")
    OVERDUE = "overdue", _("Overdue")


class InstitutionKind(models.TextChoices):
    """What the ``institution`` field names: where the student studies, or
    where they work. Most people registering are one or the other, and the
    label a counsellor sees ("College" / "Employer") is the same fact from the
    other side."""

    COLLEGE = "college", _("College")
    EMPLOYER = "employer", _("Employer")


#: The least a course fee can be, in rupees. A quoted fee below this is a typo
#: or a test, not a decision, so the service refuses it rather than storing it.
MIN_FEE_AMOUNT = Decimal("1000")


class Qualification(models.TextChoices):
    SECONDARY = "secondary", _("Secondary (10th)")
    HIGHER_SECONDARY = "higher_secondary", _("Higher secondary (12th)")
    DIPLOMA = "diploma", _("Diploma")
    BACHELORS = "bachelors", _("Bachelor's degree")
    MASTERS = "masters", _("Master's degree")
    OTHER = "other", _("Other")


class StudentProfile(UUIDPrimaryKeyModel, TimeStampedModel):
    #: Fields a student may edit on their own record. Everything else is
    #: administrator-only. The serializer layer reads this list, so adding a
    #: field does not silently become self-editable.
    SELF_EDITABLE_FIELDS = (
        "date_of_birth",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "country",
        "postal_code",
        "qualification",
        "institution",
        "institution_kind",
        "graduation_year",
        "emergency_contact_name",
        "emergency_contact_phone",
        "emergency_contact_relationship",
        "guardian_name",
        "guardian_phone",
    )

    #: Fields counted towards the completion percentage shown in the UI.
    COMPLETION_FIELDS = (
        "date_of_birth",
        "address_line1",
        "city",
        "state",
        "country",
        "qualification",
        "institution",
        "emergency_contact_name",
        "emergency_contact_phone",
    )

    student_id = models.CharField(
        _("student ID"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human-readable identifier, e.g. GRS-S-00042. Allocated by the system."),
    )
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="student_profile",
        help_text=_("Deleting the account removes the profile; accounts are deactivated instead."),
    )

    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)

    address_line1 = models.CharField(
        _("address line 1"), max_length=200, blank=True, validators=[validate_no_control_characters]
    )
    address_line2 = models.CharField(
        _("address line 2"), max_length=200, blank=True, validators=[validate_no_control_characters]
    )
    city = models.CharField(_("city"), max_length=100, blank=True)
    state = models.CharField(_("state"), max_length=100, blank=True)
    country = models.CharField(_("country"), max_length=100, blank=True, default="India")
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)

    qualification = models.CharField(
        _("highest qualification"), max_length=32, choices=Qualification.choices, blank=True
    )
    institution = models.CharField(
        _("college or employer"),
        max_length=200,
        blank=True,
        validators=[validate_no_control_characters],
    )
    institution_kind = models.CharField(
        _("institution kind"),
        max_length=16,
        choices=InstitutionKind.choices,
        blank=True,
        help_text=_("Whether the institution named is where the student studies or works."),
    )
    graduation_year = models.PositiveSmallIntegerField(_("graduation year"), null=True, blank=True)

    emergency_contact_name = models.CharField(
        _("emergency contact name"), max_length=150, blank=True
    )
    emergency_contact_phone = models.CharField(
        _("emergency contact phone"), max_length=20, blank=True, validators=[validate_phone_number]
    )
    emergency_contact_relationship = models.CharField(_("relationship"), max_length=50, blank=True)

    guardian_name = models.CharField(_("parent or guardian name"), max_length=150, blank=True)
    guardian_phone = models.CharField(
        _("parent or guardian phone"), max_length=20, blank=True, validators=[validate_phone_number]
    )

    fee_status = models.CharField(
        _("fee status"),
        max_length=16,
        choices=FeeStatus.choices,
        default=FeeStatus.PENDING,
        db_index=True,
        help_text=_("Administrator-maintained. Students see it but cannot change it."),
    )
    fee_status_updated_at = models.DateTimeField(_("fee status updated at"), null=True, blank=True)
    fee_status_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_status_updates",
        help_text=_("Administrator who last changed the fee status."),
    )

    # The fee agreed at registration. Null means "not yet decided" — every
    # student registered before this field existed, and any registered without
    # a counsellor quoting one. Never zero: zero would be a claim.
    fee_amount = models.DecimalField(
        _("agreed fee"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(MIN_FEE_AMOUNT)],
        help_text=_("In rupees. Decided by the counsellor or manager; students see it but cannot change it."),
    )
    fee_amount_updated_at = models.DateTimeField(_("fee amount updated at"), null=True, blank=True)
    fee_amount_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fee_amount_updates",
        help_text=_("Who last set the agreed fee."),
    )

    notes = models.TextField(
        _("internal notes"),
        blank=True,
        help_text=_("Administrator-only. Never returned to the student."),
    )

    # Who brought this student in. A working professional who joins to learn a
    # new skill is also a channel — colleagues follow — and the institute wants
    # to be able to credit that later. Recorded by the counsellor, never by the
    # student, and kept if the referrer's record is later removed: the fact of
    # the referral does not stop being true.
    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
        help_text=_("The existing student who referred this one, if any."),
    )

    def clean(self) -> None:
        super().clean()
        if self.referred_by_id is not None and self.referred_by_id == self.pk:
            raise ValidationError({"referred_by": _("A student cannot refer themselves.")})

    class Meta:
        verbose_name = _("student profile")
        verbose_name_plural = _("student profiles")
        ordering = ("student_id",)
        indexes = [
            # The admin list filters by fee status and orders by newest first.
            models.Index(fields=["fee_status", "-created_at"], name="student_fee_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} ({self.user.email})"

    @property
    def completion_percent(self) -> int:
        """How much of the optional detail has been filled in."""
        filled = sum(1 for field in self.COMPLETION_FIELDS if getattr(self, field, None))
        return round(filled * 100 / len(self.COMPLETION_FIELDS))

    @property
    def is_profile_complete(self) -> bool:
        return self.completion_percent == 100
