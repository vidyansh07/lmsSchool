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

from django.contrib.postgres.fields import ArrayField
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


class ClassTime(models.TextChoices):
    """When a student can actually attend.

    Asked because it decides something: a batch scheduled at a time most of its
    students cannot make empties out in the second week, and the institute only
    found out after it had happened.
    """

    MORNING = "morning", _("Morning")
    AFTERNOON = "afternoon", _("Afternoon")
    EVENING = "evening", _("Evening")
    WEEKEND = "weekend", _("Weekend")


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
        "job_title",
        "roll_number",
        "graduation_year",
        "emergency_contact_name",
        "emergency_contact_phone",
        "emergency_contact_relationship",
        "guardian_name",
        "guardian_phone",
        # What the student says about themselves. Self-edited by definition:
        # nobody else can answer "what do you want to do".
        "about",
        "career_goal",
        "interests",
        "skills",
        "languages",
        "preferred_class_time",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "open_to_placement",
        "willing_to_relocate",
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

    # An identifier issued by somebody else — a university roll number, an
    # employer's staff id — that the student is known by outside this system.
    # For a college batch it is often the *only* identifier a spreadsheet
    # carries, so it is indexed and searchable.
    roll_number = models.CharField(
        _("roll number"),
        max_length=32,
        blank=True,
        db_index=True,
        validators=[validate_no_control_characters],
        help_text=_("The student's roll or registration number at their college, if any."),
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
    branch = models.ForeignKey(
        "organisation.Branch",
        on_delete=models.PROTECT,
        related_name="students",
        verbose_name=_("branch"),
        help_text=_(
            "The centre this student was admitted to. A later transfer may put "
            "their class at another one; this is where their record is kept."
        ),
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
    # For a working professional: what they do there. The one field that makes
    # "working professional" a category rather than a label, and the first
    # thing a corporate-training conversation asks.
    job_title = models.CharField(
        _("designation"),
        max_length=120,
        blank=True,
        validators=[validate_no_control_characters],
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
        help_text=_(
            "In rupees. Decided by the counsellor or manager; students see it but cannot change it."
        ),
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

    # --- What the student says about themselves ---------------------------
    #
    # Everything above this line is a fact the institute records about a
    # student: their address, their fee status, who referred them. Everything
    # below is what the student says about themselves, and it is here rather
    # than in a separate table for the reason the rest of this model exists —
    # it is the same person, and a profile split across two records is one
    # nobody keeps up to date.
    #
    # It is asked for because it is used. A placement officer looking for
    # somebody to put in front of an employer needs to know what they want to
    # do and what they can already do; a batch planner needs to know when they
    # can attend. Without this, both were guesses made from a course code.
    #
    # Every field is optional and self-edited. A student who fills in nothing
    # has a complete profile in the sense that matters: the institute has no
    # business insisting on their LinkedIn.

    about = models.TextField(
        _("about"),
        max_length=1000,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("A few lines in the student's own words."),
    )
    career_goal = models.CharField(
        _("career goal"),
        max_length=200,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("The job or field the student is aiming for."),
    )
    #: Favourite subjects and topics, as the student names them. Free text in a
    #: list rather than a fixed vocabulary: "Linux", "cloud", "cyber security"
    #: and "networking" are what people actually say, and a dropdown built from
    #: the course catalogue would miss everything the institute does not teach
    #: yet — which is exactly the signal worth having.
    interests = ArrayField(
        models.CharField(max_length=60, validators=[validate_no_control_characters]),
        verbose_name=_("interests"),
        default=list,
        blank=True,
        size=20,
    )
    skills = ArrayField(
        models.CharField(max_length=60, validators=[validate_no_control_characters]),
        verbose_name=_("skills"),
        default=list,
        blank=True,
        size=30,
    )
    languages = ArrayField(
        models.CharField(max_length=40, validators=[validate_no_control_characters]),
        verbose_name=_("languages"),
        default=list,
        blank=True,
        size=10,
    )
    preferred_class_time = models.CharField(
        _("preferred class time"),
        max_length=16,
        choices=ClassTime.choices,
        blank=True,
    )
    linkedin_url = models.URLField(_("LinkedIn"), max_length=200, blank=True)
    github_url = models.URLField(_("GitHub"), max_length=200, blank=True)
    portfolio_url = models.URLField(_("portfolio"), max_length=200, blank=True)
    #: Whether the student wants to be put forward for jobs. A placement
    #: officer should not be ringing somebody who is not looking, and a student
    #: who is looking should not have to hope they get noticed.
    open_to_placement = models.BooleanField(
        _("open to placement"),
        default=False,
        help_text=_("Whether the student wants to be put forward for jobs."),
    )
    willing_to_relocate = models.BooleanField(_("willing to relocate"), default=False)

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
