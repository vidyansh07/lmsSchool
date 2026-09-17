"""The activity engine (ERP Phase 9).

Two things share the app's namespace potential collision with
``apps.activity`` — the pre-existing audit/activity-feed app — is
deliberate and documented in ADR-08 (`docs/erp/ARCHITECTURE_DECISIONS.md`):
that app is unrelated (a feed of "who did what"), so this one is named
``apps.work`` and mounted at ``/api/v1/activities/``, leaving
``/api/v1/activity/`` exactly where it was.

``ActivityType`` is the seeded catalog (`docs/erp/ACTIVITY_CATALOG.md`) plus
whatever an administrator adds; ``Activity`` is one scheduled/worked/reviewed
instance of a type, moving through the twelve-status lifecycle described in
``apps/work/transitions.py``; ``ActivityHistory`` is its append-only audit
trail, kept separate from the general ``AuditLog`` so a person's timeline for
one activity is a single cheap query rather than a filter over every audit
row in the system.

Several fields exist only for later phases to fill in, on purpose, so their
migration is additive rather than introduced fresh when those phases land:
``performance_weight``/``risk_effect`` (Phase 12/13 read them),
``next_action`` (Phase 14 dispatches it), ``parent``/``automation_run``
provenance (Phase 14 populates ``parent``; the ``automation_run`` FK itself
does not exist yet — Phase 14 adds it additively when ``AutomationRun`` is
built). Nothing in this app writes any of those beyond storing what it is
given.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class ActivityCategory(models.TextChoices):
    INTERVIEW = "interview", _("Interview")
    MENTORING = "mentoring", _("Mentoring")
    COUNSELLING = "counselling", _("Counselling")
    REVIEW = "review", _("Review")
    PLACEMENT = "placement", _("Placement")
    FEEDBACK = "feedback", _("Feedback")
    WARNING = "warning", _("Warning")
    FOLLOW_UP = "follow_up", _("Follow-up")
    OTHER = "other", _("Other")


class RiskEffect(models.TextChoices):
    """Whether a low score on this type feeds the activity-risk rule.

    Store-only in this phase — there is no reader yet. Phase 13 (ADR-11)
    consumes it against the policy key ``risk.activity_score_below``. The
    catalog names a few richer rules in prose ("placement rule", "yes
    (count)") that do not fit this two-value enum; those types are seeded
    with ``none`` here and the richer rule stays documented in
    ``ACTIVITY_CATALOG.md`` for Phase 13 to read when it extends this
    enum — a deliberate simplification, not a bug (see the seed migration's
    docstring for the exact list).
    """

    NONE = "none", _("No effect")
    SCORE_BELOW_THRESHOLD = "score_below_threshold", _("Low score raises risk")


class ActivityTypeQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("form")


class ActivityTypeStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    DISABLED = "disabled", _("Disabled")


class ActivityType(SoftDeleteBaseModel):
    """One kind of activity ("Mock Interview", "Counselling"). The 18 seeded
    rows (`is_system=True`) come from ``migrations/0002_seed_catalog.py``;
    an administrator may add more, disable any of them, or change any column
    except ``slug``."""

    slug = models.CharField(_("slug"), max_length=60)
    name = models.CharField(_("name"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    category = models.CharField(_("category"), max_length=30, choices=ActivityCategory.choices)
    # Role *slugs* (``apps.accounts.roles.UserRole`` values), plus the literal
    # string ``"automation"`` for the handful of catalog rows an automation
    # rule creates (Phase 14). This is a narrowing on top of the
    # ``activity.create``/``activity.assign`` capabilities, never a
    # replacement for them — see ``services.create_activity``.
    allowed_creator_roles = models.JSONField(_("allowed creator roles"), default=list, blank=True)
    allowed_assignee_roles = models.JSONField(_("allowed assignee roles"), default=list, blank=True)
    # Fails closed: a freshly-created custom type shows to nobody until an
    # administrator opts it in, rather than leaking a half-configured type's
    # notes to a student by default.
    visible_to_student = models.BooleanField(_("visible to student"), default=False)
    default_duration_minutes = models.PositiveIntegerField(
        _("default duration (minutes)"), null=True, blank=True
    )
    form = models.ForeignKey(
        "forms.FormDefinition",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_types",
    )
    requires_review = models.BooleanField(_("requires review"), default=False)
    #: 0 = no effect on the performance component. Store only — Phase 12 reads
    #: it as one term of a weighted mean (`apps.performance.engine`), which
    #: assumes every weight is non-negative; a negative value would flip the
    #: sign of that mean or drive its denominator through zero, so it is
    #: rejected here (`MinValueValidator`, both write serializers) and by the
    #: matching `CheckConstraint` below rather than left for the engine to
    #: mishandle silently.
    performance_weight = models.DecimalField(
        _("performance weight"),
        max_digits=4,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    risk_effect = models.CharField(
        _("risk effect"), max_length=30, choices=RiskEffect.choices, default=RiskEffect.NONE
    )
    reminder_minutes_before = models.PositiveIntegerField(
        _("remind before (minutes)"), null=True, blank=True
    )
    #: Verbatim shape from `DATA_MODEL.md` §5: ``{when, threshold,
    #: create_type, assign_to, notify}``. Store only — Phase 14 dispatches it.
    next_action = models.JSONField(_("next action"), null=True, blank=True)
    is_system = models.BooleanField(_("seeded by the catalog"), default=False)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=ActivityTypeStatus.choices,
        default=ActivityTypeStatus.ACTIVE,
    )

    objects, all_objects = soft_delete_managers(ActivityTypeQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("activity type")
        verbose_name_plural = _("activity types")
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="activity_type_slug_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(performance_weight__gte=0),
                name="activity_type_performance_weight_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.slug


class ActivityStatus(models.TextChoices):
    """The twelve statuses (§25). See ``apps/work/transitions.py`` for the
    legal moves between them and who may make each one."""

    DRAFT = "draft", _("Draft")
    PLANNED = "planned", _("Planned")
    ASSIGNED = "assigned", _("Assigned")
    IN_PROGRESS = "in_progress", _("In progress")
    COMPLETED = "completed", _("Completed")
    MISSED = "missed", _("Missed")
    OVERDUE = "overdue", _("Overdue")
    CANCELLED = "cancelled", _("Cancelled")
    REOPENED = "reopened", _("Reopened")
    UNDER_REVIEW = "under_review", _("Under review")
    APPROVED = "approved", _("Approved")
    REQUIRES_ACTION = "requires_action", _("Requires action")


#: Statuses in which an activity still has open work ahead of it — used by
#: the calendar source and by ``mark_overdue_and_missed`` to pick candidates.
#: Not "every status the transition table allows a move out of": REOPENED,
#: UNDER_REVIEW and REQUIRES_ACTION are mid-workflow but never themselves
#: what a due-date reminder is about.
OPEN_STATUSES = frozenset(
    {
        ActivityStatus.DRAFT,
        ActivityStatus.PLANNED,
        ActivityStatus.ASSIGNED,
        ActivityStatus.IN_PROGRESS,
        ActivityStatus.OVERDUE,
        ActivityStatus.REQUIRES_ACTION,
    }
)


class ActivityPriority(models.TextChoices):
    LOW = "low", _("Low")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("High")
    URGENT = "urgent", _("Urgent")


class ActivityResult(models.TextChoices):
    PASS = "pass", _("Pass")
    FAIL = "fail", _("Fail")
    MIXED = "mixed", _("Mixed")
    N_A = "n/a", _("Not applicable")


class ActivityQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "student",
            "student__user",
            "enrollment",
            "batch",
            "branch",
            "activity_type",
            "created_by",
            "assigned_to",
            "performed_by",
            "reviewed_by",
            "form_version",
            "form_response",
            "parent",
        )


class Activity(SoftDeleteBaseModel):
    """One scheduled/worked/reviewed instance of an :class:`ActivityType`."""

    student = models.ForeignKey(
        "students.StudentProfile", on_delete=models.PROTECT, related_name="activities"
    )
    enrollment = models.ForeignKey(
        "enrollments.Enrollment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activities",
    )
    #: Denormalised from ``enrollment`` at creation time so a query never has
    #: to join through it just to scope by batch.
    batch = models.ForeignKey(
        "batches.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="activities"
    )
    branch = models.ForeignKey(
        "organisation.Branch", on_delete=models.PROTECT, related_name="activities"
    )
    activity_type = models.ForeignKey(
        ActivityType, on_delete=models.PROTECT, related_name="activities"
    )
    title = models.CharField(_("title"), max_length=160)
    status = models.CharField(
        _("status"), max_length=16, choices=ActivityStatus.choices, default=ActivityStatus.DRAFT
    )
    priority = models.CharField(
        _("priority"),
        max_length=10,
        choices=ActivityPriority.choices,
        default=ActivityPriority.NORMAL,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_activities",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_activities",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="performed_activities",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_activities",
    )
    planned_at = models.DateTimeField(_("planned at"), null=True, blank=True)
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    due_at = models.DateTimeField(_("due at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    #: Set by ``send_activity_reminders`` the moment a reminder is queued, so
    #: a re-run of the same beat tick — or one running slightly late — does
    #: not send the same reminder twice.
    reminder_sent_at = models.DateTimeField(_("reminder sent at"), null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(_("duration (minutes)"), null=True, blank=True)
    form_version = models.ForeignKey(
        "forms.FormVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("Pinned at creation. Never changes after."),
    )
    form_response = models.ForeignKey(
        "forms.FormResponse",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    result = models.CharField(
        _("result"), max_length=20, choices=ActivityResult.choices, default=ActivityResult.N_A
    )
    score = models.DecimalField(_("score"), max_digits=5, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(
        _("max score"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    summary = models.TextField(_("summary"), blank=True)
    review_note = models.TextField(_("review note"), blank=True)
    student_visible = models.BooleanField(_("visible to student"), default=True)
    #: The activity that generated this one (Phase 14's `next_action`
    #: dispatch). Nothing populates this yet.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    #: Set by `apps.automation.actions.create_activity` (ERP Phase 14,
    #: ADR-13) on the activity a rule created — provenance, never read by
    #: this app itself. Additive: `AutomationRun` did not exist when `parent`
    #: above was added, per this model's own module docstring.
    automation_run = models.ForeignKey(
        "automation.AutomationRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_activities",
    )
    #: Idempotency key for POST /activities/: a retry with the same
    #: (created_by, client_key) within 24h returns the original row instead
    #: of creating a duplicate. See `services.create_activity`. Blank, not
    #: null: "no client key" is a real answer, spelled as the empty string
    #: so the column stays a plain CharField (DJ001 — the same choice
    #: `FormField.performance_key` makes).
    client_key = models.CharField(_("client key"), max_length=100, blank=True, default="")

    objects, all_objects = soft_delete_managers(ActivityQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("activity")
        verbose_name_plural = _("activities")
        indexes = [
            models.Index(fields=["student", "-created_at"], name="activity_student_created_idx"),
            models.Index(
                fields=["assigned_to", "status", "due_at"], name="activity_assignee_status_idx"
            ),
            models.Index(fields=["branch", "status"], name="activity_branch_status_idx"),
            models.Index(fields=["created_by", "client_key"], name="activity_client_key_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.activity_type_id}:{self.pk}"


class ActivityHistory(BaseModel):
    """Append-only. No soft delete, no ``objects``/``all_objects`` split —
    a history log with a delete button is not a history log."""

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="history")
    #: Null for a system-driven transition (OVERDUE, MISSED) — there is no
    #: person to attribute it to.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_status = models.CharField(_("from"), max_length=16, choices=ActivityStatus.choices)
    to_status = models.CharField(_("to"), max_length=16, choices=ActivityStatus.choices)
    note = models.TextField(_("note"), blank=True)
    changes = models.JSONField(_("changes"), default=dict, blank=True)

    class Meta:
        verbose_name = _("activity history entry")
        verbose_name_plural = _("activity history")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.activity_id}: {self.from_status} -> {self.to_status}"
