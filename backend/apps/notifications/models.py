"""Notifications and outbound email — §7.1 and §7.2.

Three tables, and the separation between them is the design.

``Notification``
    Something a person should know about, in the product. Always written,
    whatever else happens: the in-app record is the notification, and email is
    one way of *delivering* it. If the mail provider is down, the student still
    sees the deadline when they next open the site.

``NotificationPreference``
    One row per person. Which categories they want by email. Absent means the
    defaults apply, so a new user never has to be back-filled.

``EmailMessage``
    The outbox. One row per attempt to send, with its status and — scrubbed —
    why it failed. §7.2 asks for delivery status and failure logging without
    secrets; a table is how you get both, and it is also what makes retry
    possible without a broker.

Provider-agnostic on purpose (§7.1)
-----------------------------------
Nothing above knows how mail is sent. `apps.notifications.channels` holds one
class per channel and a registry; adding SMS or a push service later means one
new class and one line, with no change to any caller.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class NotificationKind(models.TextChoices):
    """Every reason the product speaks to somebody.

    Grouped by the *category* below, which is what a person actually wants to
    control: nobody wants to tick eight boxes, and nobody wants one switch.
    """

    COURSE_UPDATED = "course.updated", _("Course updated")
    BATCH_UPDATED = "batch.updated", _("Batch updated")
    ANNOUNCEMENT = "announcement", _("Announcement")
    ASSIGNMENT_DUE = "assignment.due", _("Assignment deadline")
    ASSIGNMENT_GRADED = "assignment.graded", _("Assignment graded")
    TEST_SCHEDULED = "test.scheduled", _("Weekly test scheduled")
    RESULT_PUBLISHED = "result.published", _("Result published")
    EXAM_REMINDER = "exam.reminder", _("Examination reminder")
    PROJECT_REVIEWED = "project.reviewed", _("Project reviewed")
    ATTENDANCE_WARNING = "attendance.warning", _("Attendance warning")
    COMPLETION_APPROVED = "completion.approved", _("Course completion approved")
    CERTIFICATE_ISSUED = "certificate.issued", _("Certificate issued")


class NotificationCategory(models.TextChoices):
    ACADEMIC = "academic", _("Coursework and results")
    SCHEDULE = "schedule", _("Classes, tests and deadlines")
    ANNOUNCEMENTS = "announcements", _("Announcements")
    ADMINISTRATIVE = "administrative", _("Completion and certificates")


#: Which switch each kind answers to.
KIND_CATEGORY: dict[str, str] = {
    NotificationKind.COURSE_UPDATED: NotificationCategory.ACADEMIC,
    NotificationKind.BATCH_UPDATED: NotificationCategory.SCHEDULE,
    NotificationKind.ANNOUNCEMENT: NotificationCategory.ANNOUNCEMENTS,
    NotificationKind.ASSIGNMENT_DUE: NotificationCategory.SCHEDULE,
    NotificationKind.ASSIGNMENT_GRADED: NotificationCategory.ACADEMIC,
    NotificationKind.TEST_SCHEDULED: NotificationCategory.SCHEDULE,
    NotificationKind.RESULT_PUBLISHED: NotificationCategory.ACADEMIC,
    NotificationKind.EXAM_REMINDER: NotificationCategory.SCHEDULE,
    NotificationKind.PROJECT_REVIEWED: NotificationCategory.ACADEMIC,
    NotificationKind.ATTENDANCE_WARNING: NotificationCategory.SCHEDULE,
    NotificationKind.COMPLETION_APPROVED: NotificationCategory.ADMINISTRATIVE,
    NotificationKind.CERTIFICATE_ISSUED: NotificationCategory.ADMINISTRATIVE,
}


def category_for(kind: str) -> str:
    return KIND_CATEGORY.get(kind, NotificationCategory.ACADEMIC)


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(read_at__isnull=True)

    def for_user(self, user):
        return self.filter(recipient=user)


class Notification(BaseModel):
    """One thing one person should know about."""

    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(_("kind"), max_length=32, choices=NotificationKind.choices)
    category = models.CharField(_("category"), max_length=16, choices=NotificationCategory.choices)

    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("body"), blank=True)
    #: Where the notification points in the product. A relative path, never a
    #: full URL: an absolute link from a database row is a redirect waiting to
    #: be abused.
    link_path = models.CharField(_("link"), max_length=300, blank=True)

    resource_type = models.CharField(_("resource type"), max_length=40, blank=True)
    resource_id = models.CharField(_("resource id"), max_length=64, blank=True)

    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient", "-created_at"], name="notification_recent_idx"),
            models.Index(fields=["recipient", "read_at"], name="notification_unread_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id}: {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class NotificationPreference(BaseModel):
    """Which categories a person wants by email.

    Absent means the defaults, so nobody has to be back-filled when a new user
    is created or a new category is added.
    """

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_preference"
    )
    email_academic = models.BooleanField(_("coursework and results"), default=True)
    email_schedule = models.BooleanField(_("classes, tests and deadlines"), default=True)
    email_announcements = models.BooleanField(_("announcements"), default=True)
    email_administrative = models.BooleanField(_("completion and certificates"), default=True)

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")

    def __str__(self) -> str:
        return str(self.user_id)

    def wants_email(self, category: str) -> bool:
        return bool(getattr(self, f"email_{category}", True))


class EmailStatus(models.TextChoices):
    PENDING = "pending", _("Queued")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    ABANDONED = "abandoned", _("Given up")


class EmailMessage(BaseModel):
    """The outbox — §7.2.

    A row exists before the provider is called, so a crash mid-send leaves
    evidence rather than silence. ``last_error`` is scrubbed by the logging
    helper before it is stored: a provider's error can echo a header, and a
    header can carry a credential.
    """

    to_email = models.EmailField(_("to"), max_length=254)
    subject = models.CharField(_("subject"), max_length=255)
    body = models.TextField(_("body"))
    template = models.CharField(_("template"), max_length=60, blank=True)

    notification = models.ForeignKey(
        Notification,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emails",
    )

    status = models.CharField(
        _("status"), max_length=10, choices=EmailStatus.choices, default=EmailStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    last_error = models.CharField(_("last error"), max_length=500, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    next_attempt_at = models.DateTimeField(_("next attempt"), default=timezone.now)

    class Meta:
        verbose_name = _("email message")
        verbose_name_plural = _("email messages")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="email_pending_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.to_email}: {self.subject}"

    @property
    def is_deliverable(self) -> bool:
        return self.status in (EmailStatus.PENDING, EmailStatus.FAILED)
