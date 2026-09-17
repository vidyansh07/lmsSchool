"""Communication centre models (ERP Phase 19, ADR-12, DATA_MODEL.md §7).

Three tables, and the separation mirrors the forms app on purpose:

``MessageTemplate``
    The named, versioned thing an administrator authors — "batch welcome
    email", "attendance warning WhatsApp message". Soft-deletable: retiring a
    template must not orphan the `Delivery` rows that already point at one of
    its versions.

``TemplateVersion``
    One shape of a template's content. Never soft-deletable itself (nothing
    here restores independently of its template) and, once ``published_at``
    is set, immutable — editing after publishing creates the *next* version,
    the exact discipline `apps.forms.services.publish_version` already
    enforces for `FormVersion`. A version's own ``variables`` column is the
    allowlist D-051 requires: `rendering.render_template` substitutes only
    the paths listed here, never anything a template's body text merely
    mentions.

``Delivery``
    A send log, one row per message per channel (ADR-12's own title) —
    append-only, plain `BaseModel`, never soft-deletable, because a send that
    happened must never become a send that is quietly no longer on the
    record. It wraps `apps.notifications.models.EmailMessage` for the email
    channel rather than duplicating the outbox; WhatsApp and in-app sends
    have no second table because there is nothing else to wrap.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class MessageChannel(models.TextChoices):
    EMAIL = "email", _("Email")
    WHATSAPP = "whatsapp", _("WhatsApp")
    IN_APP = "in_app", _("In-app")


class TemplateStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    APPROVED = "approved", _("Approved")
    PUBLISHED = "published", _("Published")


class DeliveryState(models.TextChoices):
    QUEUED = "queued", _("Queued")
    PROCESSING = "processing", _("Processing")
    SENT = "sent", _("Sent")
    DELIVERED = "delivered", _("Delivered")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class MessageTemplateQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("current_version")


class MessageTemplate(SoftDeleteBaseModel):
    """One named, versioned message. See the module docstring."""

    key = models.CharField(
        _("key"),
        max_length=60,
        help_text=_("Stable identifier a caller (the composer, an automation action) names."),
    )
    name = models.CharField(_("name"), max_length=200)
    channel = models.CharField(_("channel"), max_length=10, choices=MessageChannel.choices)
    #: A `NotificationKind` value (for a template backing the plain
    #: `notify()` path) or an automation-action identifier — validated
    #: loosely in `services.create_template`: any non-blank slug for
    #: email/whatsapp, but a genuine `NotificationKind` for `in_app`, since
    #: the in-app channel dispatches straight through
    #: `apps.notifications.services.notify`, which requires one.
    kind = models.CharField(_("kind"), max_length=60)
    language = models.CharField(_("language"), max_length=8, default="en")
    status = models.CharField(
        _("status"), max_length=10, choices=TemplateStatus.choices, default=TemplateStatus.DRAFT
    )
    current_version = models.ForeignKey(
        "communication.TemplateVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("The currently published version. Null until the first publish."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(MessageTemplateQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("message template")
        verbose_name_plural = _("message templates")
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(
                fields=["key"],
                condition=models.Q(deleted_at__isnull=True),
                name="messagetemplate_key_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.key


class TemplateVersion(BaseModel):
    """One shape of a template's content. Immutable once ``published_at`` is
    set — see `services.publish_version`."""

    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveSmallIntegerField(_("version number"))
    subject = models.CharField(_("subject"), max_length=255, blank=True)
    body_html = models.TextField(_("HTML body"), blank=True)
    body_text = models.TextField(_("text body"), blank=True)
    #: The allowlist D-051 requires: `["student.name", "activity.title"]`.
    #: `rendering.render_template` substitutes only paths listed here.
    variables = models.JSONField(_("variables"), default=list, blank=True)
    #: The WhatsApp Business API's own approved-template id, once one exists.
    provider_template_id = models.CharField(_("provider template id"), max_length=120, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)

    class Meta:
        verbose_name = _("template version")
        verbose_name_plural = _("template versions")
        ordering = ("template", "-number")
        constraints = [
            models.UniqueConstraint(
                fields=["template", "number"], name="templateversion_number_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template_id} v{self.number}"

    @property
    def is_published(self) -> bool:
        return self.published_at is not None


class DeliveryQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "recipient", "template_version", "template_version__template", "requested_by"
        )


class Delivery(BaseModel):
    """A send log row. Append-only — see the module docstring.

    Plain `BaseModel`, deliberately not soft-deletable (`AGENT_PLAYBOOK.md`:
    a send that happened is never made to look like it did not).
    """

    channel = models.CharField(_("channel"), max_length=10, choices=MessageChannel.choices)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="communication_deliveries",
    )
    #: Email address or E.164 phone, whichever the channel needs. Blank for
    #: `in_app`, which has no address concept.
    address = models.CharField(_("address"), max_length=254, blank=True)
    template_version = models.ForeignKey(
        TemplateVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries"
    )
    #: The actual resolved values used for *this* send — for audit/debugging,
    #: never displayed for an OTP-purposed send (see `serializers.py`, and
    #: `services.py`'s module docstring for why one can never exist here in
    #: the first place).
    variables = models.JSONField(_("variables"), default=dict, blank=True)
    state = models.CharField(
        _("state"), max_length=10, choices=DeliveryState.choices, default=DeliveryState.QUEUED
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(_("next attempt"), null=True, blank=True)
    provider_message_id = models.CharField(_("provider message id"), max_length=120, blank=True)
    #: Scrubbed the same way `apps.notifications.models.EmailMessage.last_error`
    #: is — see `services._store_error`, which reuses `apps.common.logging.scrub`.
    error = models.CharField(_("error"), max_length=500, blank=True)
    related_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    related_id = models.UUIDField(null=True, blank=True)
    related_object = GenericForeignKey("related_type", "related_id")
    #: The email channel's actual transport row. `Delivery` wraps it; it
    #: does not replace or duplicate `apps.notifications`'s outbox.
    email_message = models.ForeignKey(
        "notifications.EmailMessage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = DeliveryQuerySet.as_manager()

    class Meta:
        verbose_name = _("delivery")
        verbose_name_plural = _("deliveries")
        indexes = [
            models.Index(fields=["state", "next_attempt_at"], name="delivery_pending_idx"),
            models.Index(fields=["recipient", "-created_at"], name="delivery_recipient_idx"),
            models.Index(fields=["related_type", "related_id"], name="delivery_related_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.channel}:{self.address or self.recipient_id}"
