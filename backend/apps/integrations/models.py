"""Connections to systems outside the LMS.

Two directions, kept apart because they trust different things:

- **In** — an `ApiKey` lets another system (Meritto, a website form, an ad
  platform's lead webhook) post leads to `POST /api/v1/integrations/leads/`.
  The key is shown once and stored only as a hash; it can do one thing,
  create or update an enquiry at one centre, and every request is logged as
  a `LeadIntake` row whether it was accepted or not.
- **Out** — a `Webhook` is a URL an automation rule's `send_webhook` action
  posts to: a lead created here pushed back into Meritto, a payment told to
  an accounts system. Each request is signed, and logged as a
  `WebhookDelivery`.

A preset ("meritto", "generic") only pre-fills field names and headers; it
grants nothing.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class Preset(models.TextChoices):
    GENERIC = "generic", _("Generic JSON")
    MERITTO = "meritto", _("Meritto")


class ApiKey(BaseModel):
    name = models.CharField(_("name"), max_length=80, validators=[validate_no_control_characters])
    preset = models.CharField(
        _("preset"), max_length=20, choices=Preset.choices, default=Preset.GENERIC
    )
    #: The visible part of the key, `grk_<prefix>`: how a person tells two keys
    #: apart in the list, and how a request's key is found without a scan.
    prefix = models.CharField(_("prefix"), max_length=16, unique=True, editable=False)
    #: SHA-256 of the whole key. The key itself is shown once, at creation.
    key_hash = models.CharField(_("key hash"), max_length=64, editable=False)
    branch = models.ForeignKey(
        "organisation.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("The centre leads from this key land at. Empty: no centre."),
    )
    #: Where a lead says it came from when the payload does not say, or says
    #: something the pipeline has no source for (`enquiries.models.SOURCE_CHOICES`).
    default_source = models.CharField(_("default source"), max_length=40, default="website")
    #: Payload field → enquiry field, on top of the preset's own names.
    field_map = models.JSONField(_("field map"), default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_used_at = models.DateTimeField(_("last used"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("API key")
        verbose_name_plural = _("API keys")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} (grk_{self.prefix})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class IntakeStatus(models.TextChoices):
    CREATED = "created", _("New enquiry")
    UPDATED = "updated", _("Matched an open enquiry")
    REJECTED = "rejected", _("Refused")


class LeadIntake(BaseModel):
    """One request to the lead endpoint, kept so "why did my lead not arrive"
    has an answer an administrator can read."""

    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="intakes")
    status = models.CharField(_("status"), max_length=10, choices=IntakeStatus.choices)
    enquiry = models.ForeignKey(
        "enquiries.Enquiry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    external_id = models.CharField(_("external id"), max_length=100, blank=True)
    #: What was sent, trimmed and scrubbed — never more than a few KB.
    payload = models.JSONField(_("payload"), default=dict, blank=True)
    errors = models.JSONField(_("errors"), default=dict, blank=True)

    class Meta:
        verbose_name = _("lead intake")
        verbose_name_plural = _("lead intakes")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["api_key", "-created_at"], name="leadintake_key_idx")]


class Webhook(BaseModel):
    name = models.CharField(_("name"), max_length=80, validators=[validate_no_control_characters])
    preset = models.CharField(
        _("preset"), max_length=20, choices=Preset.choices, default=Preset.GENERIC
    )
    url = models.URLField(_("URL"), max_length=500)
    #: Fernet-encrypted (`crypto.py`): the HMAC signing secret, and any extra
    #: headers a receiver needs (Meritto's access and secret keys). Never
    #: returned by the API once saved; the screen shows only that one is set.
    secret_encrypted = models.TextField(_("signing secret"), blank=True)
    headers_encrypted = models.TextField(_("headers"), blank=True)
    header_names = models.JSONField(_("header names"), default=list, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("webhook")
        verbose_name_plural = _("webhooks")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class WebhookDelivery(BaseModel):
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(_("event"), max_length=60)
    rule = models.ForeignKey(
        "automation.AutomationRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    ok = models.BooleanField(_("delivered"), default=False)
    status_code = models.PositiveSmallIntegerField(_("status code"), null=True, blank=True)
    error = models.CharField(_("error"), max_length=500, blank=True)
    response_excerpt = models.CharField(_("response"), max_length=500, blank=True)
    duration_ms = models.PositiveIntegerField(_("duration (ms)"), default=0)

    class Meta:
        verbose_name = _("webhook delivery")
        verbose_name_plural = _("webhook deliveries")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["webhook", "-created_at"], name="webhookdelivery_hook_idx")]
