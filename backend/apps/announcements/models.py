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

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class Audience(models.TextChoices):
    EVERYONE = "everyone", _("Everyone")
    COURSE = "course", _("A course")
    BATCH = "batch", _("A batch")
    SELECTED = "selected", _("Selected people")


class AnnouncementStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class AnnouncementQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("course", "batch", "created_by")

    def live(self):
        """Published, and not past its expiry."""
        from django.utils import timezone

        return self.filter(status=AnnouncementStatus.PUBLISHED).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
        )


class Announcement(BaseModel):
    """Something the institution wants people to read."""

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

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
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
                    models.Q(audience="everyone", course__isnull=True, batch__isnull=True)
                    | models.Q(audience="course", course__isnull=False, batch__isnull=True)
                    | models.Q(audience="batch", batch__isnull=False)
                    | models.Q(audience="selected", course__isnull=True, batch__isnull=True)
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
