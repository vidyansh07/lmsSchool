"""Enquiries — the leads a counsellor works before anyone is a student.

An `Enquiry` is the Meritto-style lead record: who asked, about which course,
through which source, at which stage of the admissions pipeline, and which
counsellor owns it. It is created when the enquiry form is submitted (or
filled in directly by a counsellor), updated when a follow-up form or a
counselling call's form is answered about it, and moved along by people and
automation rules. Activities (calls, demo classes) hang off it the same way
they hang off a student.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers


class EnquiryStage(models.TextChoices):
    """Meritto's standard lead pipeline, in the order a lead moves through it."""

    NEW = "new", _("New")
    CONTACTED = "contacted", _("Contacted")
    INTERESTED = "interested", _("Interested")
    COUNSELLING_BOOKED = "counselling_booked", _("Counselling booked")
    DEMO_BOOKED = "demo_booked", _("Demo class booked")
    REGISTERED = "registered", _("Registered")
    NOT_INTERESTED = "not_interested", _("Not interested")
    NOT_ELIGIBLE = "not_eligible", _("Not eligible")


#: Stages that end the pipeline — won or lost.
CLOSED_STAGES = frozenset(
    {EnquiryStage.REGISTERED, EnquiryStage.NOT_INTERESTED, EnquiryStage.NOT_ELIGIBLE}
)


class LeadChannel(models.TextChoices):
    """Where the lead came from, coarsely: over the internet, or in the world."""

    ONLINE = "online", _("Online")
    OFFLINE = "offline", _("Offline")


#: The sources the enquiry form offers (`apps/forms` migration 0004), and the
#: channel each one implies. A source not listed here is offline.
SOURCE_CHOICES: tuple[tuple[str, str], ...] = (
    ("walk_in", "Walk-in"),
    ("phone_call", "Phone call"),
    ("website", "Website"),
    ("google", "Google"),
    ("facebook_instagram", "Facebook / Instagram"),
    ("linkedin", "LinkedIn"),
    ("whatsapp", "WhatsApp"),
    ("referral", "Referral"),
    ("college_seminar", "College seminar"),
    ("other", "Other"),
)
ONLINE_SOURCES = frozenset({"website", "google", "facebook_instagram", "linkedin", "whatsapp"})


def channel_for_source(source: str) -> str:
    return LeadChannel.ONLINE if source in ONLINE_SOURCES else LeadChannel.OFFLINE


class EnquiryQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("owner", "branch", "created_by", "student", "student__user")

    def open(self):
        return self.exclude(stage__in=list(CLOSED_STAGES))


class Enquiry(SoftDeleteBaseModel):
    full_name = models.CharField(_("full name"), max_length=120)
    mobile = models.CharField(_("mobile"), max_length=20)
    #: The last ten digits of `mobile`: how a repeat enquiry is recognised.
    mobile_key = models.CharField(_("mobile key"), max_length=10, db_index=True)
    email = models.EmailField(_("email"), blank=True)
    whatsapp_number = models.CharField(_("WhatsApp number"), max_length=20, blank=True)
    state = models.CharField(_("state"), max_length=60, blank=True)
    city = models.CharField(_("city"), max_length=60, blank=True)
    course = models.CharField(_("course"), max_length=60, blank=True)
    track = models.CharField(_("track"), max_length=60, blank=True)
    preferred_centre = models.CharField(_("preferred centre"), max_length=30, blank=True)
    mode = models.CharField(_("mode of study"), max_length=20, blank=True)
    batch_timing = models.CharField(_("batch timing"), max_length=20, blank=True)
    qualification = models.CharField(_("qualification"), max_length=40, blank=True)
    source = models.CharField(_("source"), max_length=40, blank=True)
    channel = models.CharField(
        _("channel"),
        max_length=10,
        choices=LeadChannel.choices,
        default=LeadChannel.OFFLINE,
        db_index=True,
        help_text=_("Online or offline lead. Follows the source unless set by hand."),
    )
    #: Where the lead came from when another system sent it (`meritto`, or
    #: `key:<prefix>` for a generic API key) and that system's own id for it,
    #: so a second post about the same lead updates it rather than duplicating.
    external_system = models.CharField(_("external system"), max_length=30, blank=True)
    external_id = models.CharField(_("external id"), max_length=100, blank=True)
    utm_source = models.CharField(_("UTM source"), max_length=200, blank=True)
    utm_medium = models.CharField(_("UTM medium"), max_length=200, blank=True)
    utm_campaign = models.CharField(_("UTM campaign"), max_length=200, blank=True)
    remarks = models.TextField(_("remarks"), blank=True)

    stage = models.CharField(
        _("stage"), max_length=30, choices=EnquiryStage.choices, default=EnquiryStage.NEW
    )
    stage_changed_at = models.DateTimeField(_("stage changed at"), null=True, blank=True)
    lost_reason = models.CharField(_("lost reason"), max_length=40, blank=True)
    lead_quality = models.PositiveSmallIntegerField(_("lead quality"), null=True, blank=True)
    next_follow_up_at = models.DateTimeField(_("next follow-up"), null=True, blank=True)
    last_contacted_at = models.DateTimeField(_("last contacted"), null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_enquiries",
    )
    branch = models.ForeignKey(
        "organisation.Branch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    #: The student this enquiry became, once registered.
    student = models.ForeignKey(
        "students.StudentProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries",
    )

    objects, all_objects = soft_delete_managers(EnquiryQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("enquiry")
        verbose_name_plural = _("enquiries")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["branch", "stage"], name="enquiry_branch_stage_idx"),
            models.Index(fields=["owner", "stage"], name="enquiry_owner_stage_idx"),
            models.Index(
                fields=["external_system", "external_id"], name="enquiry_external_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.mobile})"
