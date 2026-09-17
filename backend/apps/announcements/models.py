"""Announcements — §7.3.

One message, one audience, published once.

The audience is a *rule* (everyone, a course, a batch, named people) rather than
a stored list of recipients, so an announcement to a batch reaches a student who
joins the next day — and a student who leaves stops seeing it. Publishing also
fans out notifications, which is a separate, historical record: the notification
says what somebody was told at the time, and the announcement says what is
currently on the noticeboard.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers
from apps.common.validators import validate_no_control_characters


class Audience(models.TextChoices):
    EVERYONE = "everyone", _("Everyone")
    COURSE = "course", _("A course")
    BATCH = "batch", _("A batch")
    SELECTED = "selected", _("Selected people")
    # The teaching staff of the writer's centre — a manager telling the
    # trainers something, without naming each one (owner's call, 14 September
    # 2026). Resolved at publication like the others, see `audience_for`.
    TRAINERS = "trainers", _("Trainers at my centre")
    # ERP Phase 19: two more rule-shaped audiences, the same "resolved at
    # publication, never a stored list" design as every other one here.
    # `ROLE` generalises `TRAINERS` to any role, not just the trainer kind;
    # `BRANCH` generalises `EVERYONE` to one named centre instead of the
    # whole institution.
    ROLE = "role", _("Everyone holding a role")
    BRANCH = "branch", _("Everyone at a centre")


class AnnouncementStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")
    # ERP Phase 19 (announcements scheduling).
    SCHEDULED = "scheduled", _("Scheduled")
    CANCELLED = "cancelled", _("Cancelled")


class AnnouncementQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("course", "batch", "created_by")

    def live(self):
        """Published, and not past its expiry."""
        from django.utils import timezone

        return self.filter(status=AnnouncementStatus.PUBLISHED).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
        )


class Announcement(SoftDeleteBaseModel):
    """Something the institution wants people to read.

    Soft-deletable (Phase 7): removal by an administrator is distinct from
    :func:`apps.announcements.services.archive`. Archiving is an editorial
    state the ``AnnouncementStatus`` enum already carries — a notice taken
    off the board on purpose, still on the record, restorable by publishing
    it again. Soft delete is the recovery-bin kind of removal: something
    that should not have existed, gone from every normal query, and brought
    back (or purged) only through the bin. The two stay separate rather than
    collapsing into one "gone" concept, because an archived notice is not in
    the bin and a deleted one is not still archivable.
    """

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    body = models.TextField(_("body"))

    audience = models.CharField(
        _("audience"), max_length=10, choices=Audience.choices, default=Audience.BATCH
    )
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    batch = models.ForeignKey(
        "batches.Batch",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
    )
    recipients = models.ManyToManyField(
        "accounts.User",
        blank=True,
        related_name="announcements_addressed",
        help_text=_("Only for the 'selected people' audience."),
    )
    role = models.ForeignKey(
        "authorization.Role",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
        help_text=_("Only for the 'role' audience. Matched by the role's kind, not its id."),
    )
    branch = models.ForeignKey(
        "organisation.Branch",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
        help_text=_("Only for the 'branch' audience: everyone at this one centre."),
    )

    is_pinned = models.BooleanField(
        _("pinned"), default=False, help_text=_("Kept at the top of the noticeboard.")
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=AnnouncementStatus.choices,
        default=AnnouncementStatus.DRAFT,
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    #: ERP Phase 19: when a `SCHEDULED` announcement should publish itself.
    #: `apps.announcements.tasks.publish_due` (beat, every minute) is what
    #: actually acts on it.
    publish_at = models.DateTimeField(
        _("publish at"),
        null=True,
        blank=True,
        help_text=_("When a scheduled announcement is published automatically."),
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True,
        help_text=_("After this it drops off the noticeboard. Leave empty to keep it."),
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcements_created",
    )

    objects, all_objects = soft_delete_managers(AnnouncementQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("announcement")
        verbose_name_plural = _("announcements")
        ordering = ("-is_pinned", "-published_at", "-created_at")
        indexes = [
            models.Index(fields=["status", "-published_at"], name="announcement_live_idx"),
        ]
        constraints = [
            # The audience and its target must agree, or an announcement to "a
            # batch" with no batch reaches either everybody or nobody, and which
            # one is an implementation detail.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        audience="everyone",
                        course__isnull=True,
                        batch__isnull=True,
                        role__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="course",
                        course__isnull=False,
                        role__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="batch",
                        batch__isnull=False,
                        role__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="selected",
                        course__isnull=True,
                        batch__isnull=True,
                        role__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="trainers",
                        course__isnull=True,
                        batch__isnull=True,
                        role__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="role",
                        role__isnull=False,
                        course__isnull=True,
                        batch__isnull=True,
                        branch__isnull=True,
                    )
                    | models.Q(
                        audience="branch",
                        branch__isnull=False,
                        course__isnull=True,
                        batch__isnull=True,
                        role__isnull=True,
                    )
                ),
                name="announcement_audience_matches_target",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_live(self) -> bool:
        from django.utils import timezone

        if self.status != AnnouncementStatus.PUBLISHED:
            return False
        return not (self.expires_at and timezone.now() > self.expires_at)
