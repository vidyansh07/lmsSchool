"""The automation engine's two tables (ERP Phase 14, ADR-13).

``AutomationRule`` is data, never code a person typed: a trigger name, a
list of ``{path, op, value}`` conditions ANDed together, and a list of
``{type, params}`` actions executed in order when the conditions hold. See
``docs/erp/AUTOMATION_CATALOG.md`` for the fixed vocabulary this data is
checked against at save time (``services.py``) — the model itself does not
validate a condition's path or an action's params; nothing here trusts a
JSON blob to be internally consistent.

``AutomationRun`` is the append-only log a dispatch writes one row to for
every rule it evaluates and decides to act on (or explicitly skip/fail).
It is deliberately plain ``BaseModel``, not soft-deletable — a run record is
provenance, the same reasoning ``ActivityHistory`` gives for skipping soft
delete on an append-only-by-nature table. Its
``UniqueConstraint(rule, occurrence_key)`` *is* the idempotency guard the
catalog's "Guards" section describes: a second attempt to run the same rule
against the same occurrence hits this constraint at the database level, not
a race-prone "check then create" in Python.
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


class AutomationTrigger(models.TextChoices):
    """The seven values ``AUTOMATION_CATALOG.md``'s "Triggers and their
    context" table names. Nothing else is a legal ``AutomationRule.trigger``
    — enforced in ``services.py`` at save time, not here, the same split
    ``apps.forms`` draws between "what shape can this column hold" and "what
    value is actually allowed right now"."""

    ACTIVITY_COMPLETED = "ACTIVITY_COMPLETED", _("Activity completed")
    ACTIVITY_OVERDUE = "ACTIVITY_OVERDUE", _("Activity overdue")
    ASSESSMENT_FAILED = "ASSESSMENT_FAILED", _("Assessment failed")
    ATTENDANCE_THRESHOLD = "ATTENDANCE_THRESHOLD", _("Attendance crossed threshold")
    PROJECT_OVERDUE = "PROJECT_OVERDUE", _("Project overdue")
    ASSIGNMENT_OVERDUE = "ASSIGNMENT_OVERDUE", _("Assignment overdue")
    RISK_CHANGED = "RISK_CHANGED", _("Risk level or triggered rules changed")


class AutomationRuleStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")


class AutomationRunStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    RAN = "ran", _("Ran")
    SKIPPED = "skipped", _("Skipped")
    FAILED = "failed", _("Failed")


class AutomationRuleQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("branch", "created_by", "updated_by")

    def active(self):
        return self.filter(status=AutomationRuleStatus.ACTIVE)

    def for_trigger(self, trigger: str):
        return self.filter(trigger=trigger)


class AutomationRule(SoftDeleteBaseModel):
    """One row of the builder (`docs/erp/AUTOMATION_CATALOG.md`).

    ``version`` is bumped by `services.update_rule` on every edit made
    *after* the rule has left `draft` at least once (ADR-13: "a run carries
    the rule version") — a draft is still being written and edits to it are
    not a new "version" of anything a run has ever referenced yet.

    ``is_system`` is meant to mark provenance only — never to lock a rule,
    since the catalog is explicit that an administrator may edit, pause or
    delete any seeded rule from the builder exactly like their own, and this
    field is never read by an authorization check. It is not actually set
    anywhere today: `0002_seed_rules` creates the 9 seeded rows with
    ``is_system=False``, matching ``AUTOMATION_CATALOG.md``'s own "Seeded
    rules (`is_system=False`, editable, all `active`)" heading — so right
    now this column is simply always `False` for every rule, seeded or not.
    """

    name = models.CharField(_("name"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    trigger = models.CharField(_("trigger"), max_length=40, choices=AutomationTrigger.choices)
    conditions = models.JSONField(
        _("conditions"),
        default=list,
        blank=True,
        help_text=_("A list of {path, op, value}, ANDed together."),
    )
    actions = models.JSONField(
        _("actions"),
        default=list,
        blank=True,
        help_text=_("A list of {type, params}, executed in order when conditions hold."),
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=AutomationRuleStatus.choices,
        default=AutomationRuleStatus.DRAFT,
    )
    version = models.PositiveIntegerField(_("version"), default=1)
    branch = models.ForeignKey(
        "organisation.Branch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="automation_rules",
        help_text=_("Null applies the rule at every centre."),
    )
    is_system = models.BooleanField(
        _("system rule"),
        default=False,
        help_text=_(
            "Provenance only — never locked, always editable. Not currently set anywhere "
            "(the seeded rows are created with this False); reserved for future use."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(AutomationRuleQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("automation rule")
        verbose_name_plural = _("automation rules")
        ordering = ("name",)
        indexes = [
            models.Index(fields=["trigger", "status"], name="autorule_trigger_status_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class AutomationRunQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("rule", "content_type")

    def today(self):
        from django.utils import timezone

        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=start)


class AutomationRun(BaseModel):
    """One evaluation of one rule against one occurrence. Append-only — a
    run is never edited or soft-deleted once written."""

    rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name="runs")
    trigger = models.CharField(_("trigger"), max_length=40, choices=AutomationTrigger.choices)
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")
    occurrence_key = models.CharField(_("occurrence key"), max_length=80)
    depth = models.SmallIntegerField(_("depth"), default=0)
    status = models.CharField(_("status"), max_length=10, choices=AutomationRunStatus.choices)
    result = models.JSONField(_("result"), default=dict, blank=True)
    error = models.TextField(_("error"), blank=True)
    rule_version = models.PositiveIntegerField(
        _("rule version"),
        default=1,
        help_text=_("The rule's version at the moment this run happened (ADR-13)."),
    )

    objects = models.Manager.from_queryset(AutomationRunQuerySet)()

    class Meta:
        verbose_name = _("automation run")
        verbose_name_plural = _("automation runs")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "occurrence_key"], name="automation_run_rule_occurrence_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="autorun_owner_idx"),
            models.Index(fields=["rule", "created_at"], name="autorun_rule_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rule_id}:{self.occurrence_key}"
