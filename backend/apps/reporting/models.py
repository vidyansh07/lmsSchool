"""The bulk-import audit record — §8.5.

Same shape and the same reasoning as the result importer in §4.6: a row exists
from the moment a file is uploaded, before anything is written, so the workflow
is *preview → validate → confirm* rather than "upload and hope". Storing the
parsed rows is what lets an operator see exactly what would happen and decide.

A separate model from `assessments.ResultImport` rather than a shared one:
they validate different things against different tables, and the one thing they
would share — a status field — is not worth coupling two workflows over.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class ImportKind(models.TextChoices):
    STUDENTS = "students", _("Students")
    ATTENDANCE = "attendance", _("Attendance")


class BulkImportStatus(models.TextChoices):
    PREVIEW = "preview", _("Awaiting confirmation")
    CONFIRMED = "confirmed", _("Applied")
    REJECTED = "rejected", _("Discarded")
    FAILED = "failed", _("Failed validation")


class BulkImport(BaseModel):
    """One attempt to import a file."""

    kind = models.CharField(_("kind"), max_length=12, choices=ImportKind.choices)
    uploaded_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="bulk_imports"
    )

    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True)

    row_count = models.PositiveIntegerField(_("rows read"), default=0)
    valid_count = models.PositiveIntegerField(_("rows that would apply"), default=0)
    error_count = models.PositiveIntegerField(_("rows with problems"), default=0)
    created_count = models.PositiveIntegerField(_("records created"), default=0)
    updated_count = models.PositiveIntegerField(_("records updated"), default=0)

    status = models.CharField(
        _("status"),
        max_length=10,
        choices=BulkImportStatus.choices,
        default=BulkImportStatus.PREVIEW,
    )
    report = models.JSONField(_("report"), default=dict, blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)

    #: Attendance imports are scoped to one class; student imports are not.
    session = models.ForeignKey(
        "class_sessions.ClassSession",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="imports",
    )

    class Meta:
        verbose_name = _("bulk import")
        verbose_name_plural = _("bulk imports")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["kind", "status"], name="bulkimport_kind_status_idx")]

    def __str__(self) -> str:
        return f"{self.kind}: {self.original_filename or self.pk}"


# ---------------------------------------------------------------------------
# Background export jobs — the worker-side sibling of `ReportExportView`
# ---------------------------------------------------------------------------


class ExportFormat(models.TextChoices):
    CSV = "csv", _("CSV")
    XLSX = "xlsx", _("Excel")
    PDF = "pdf", _("PDF")


class ExportStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    PROCESSING = "processing", _("Running")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


#: Terminal states. Once here, a job does not move again — `run_export` refuses
#: to touch a job that is not `QUEUED`, and cancellation refuses one that is not
#: `QUEUED` or `PROCESSING`.
TERMINAL_EXPORT_STATUSES = frozenset(
    {ExportStatus.COMPLETED, ExportStatus.FAILED, ExportStatus.CANCELLED}
)

#: How long a finished file is kept downloadable. An export is a copy of
#: institutional data sitting in a bucket rather than behind the access rules
#: that governed it when it was produced — a scope narrowed the day after an
#: export completes does not retract the file. A short, stated lifetime is the
#: mitigation: `expires_at` is set the moment a job completes, the download view
#: honours it, and nothing keeps a five-year-old spreadsheet of students
#: reachable forever just because nobody deleted the row.
EXPORT_RETENTION = timedelta(days=14)


def export_upload_to(instance: ExportJob, filename: str) -> str:
    """Stored path for a finished export.

    Sharded by a fresh UUID rather than the job's own id or the caller's
    filename, for the same reason `apps.common.uploads.submission_upload_to`
    does it: the stored path must be a function of server-side randomness
    alone, never of anything a client supplied or anything guessable from the
    record it belongs to.
    """
    import uuid
    from pathlib import PurePosixPath

    suffix = PurePosixPath(filename or "").suffix.lower() or ".bin"
    name = uuid.uuid4().hex
    return f"exports/{name[:2]}/{name[2:4]}/{name}{suffix}"


def validate_report_key(value: str) -> None:
    """Defence in depth: `ExportJobQueueView` already refuses an unknown key
    before a row is ever created. This is what stops the admin site, a
    management command, or a future caller from writing one anyway.
    """
    from . import reports

    if value not in reports.REPORTS:
        raise ValidationError(_("%(value)s is not a known report."), params={"value": value})


class ExportJobQuerySet(SoftDeleteQuerySet):
    def for_user(self, user) -> ExportJobQuerySet:
        return self.filter(requested_by=user)

    def with_related(self) -> ExportJobQuerySet:
        return self.select_related("requested_by")


class ExportJob(SoftDeleteBaseModel):
    """One request to render a report to a file, off the request/response cycle.

    `BulkImport` above is the closest sibling: both are a row that exists
    before the expensive work happens, so the workflow has something to point
    at while it runs and something to show for it afterwards. The difference is
    direction — an import turns a file into database rows; this turns database
    rows into a file — and that a real worker does the work here rather than a
    synchronous confirm.

    **Scope is never trusted from the past.** `filters` records what the job
    *asked* for (a batch, a course) so a finished file can say what it
    contains, and so a person deciding whether to open it knows before they do.
    It is not what `run_export` reads to build the queryset: the task re-derives
    the caller's *current* visibility from their user record at the moment it
    runs, never from anything stored here or passed on the queue. A capability
    granted and revoked, a trainer moved off a batch, an account deactivated —
    all of it must be caught between queueing and running, and the only way to
    catch it is to ask again rather than remember the answer.
    """

    report_key = models.CharField(_("report"), max_length=40, validators=[validate_report_key])
    format = models.CharField(_("format"), max_length=4, choices=ExportFormat.choices)
    #: What the job was scoped to when it was queued — for display only. See
    #: the class docstring for why this is never read back to build a queryset.
    filters = models.JSONField(_("filters"), default=dict, blank=True)

    requested_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="export_jobs"
    )

    status = models.CharField(
        _("status"), max_length=10, choices=ExportStatus.choices, default=ExportStatus.QUEUED
    )
    queued_at = models.DateTimeField(_("queued at"), auto_now_add=True)
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    row_count = models.PositiveIntegerField(_("rows written"), default=0)

    file = models.FileField(_("file"), upload_to=export_upload_to, max_length=255, blank=True)
    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"), default=0)

    #: Scrubbed before it is stored — see `apps.common.logging.scrub` — and
    #: never a traceback: an unexpected failure is logged in full server-side
    #: and this field gets a fixed, user-facing sentence instead. A known,
    #: expected refusal (scope narrowed, row cap exceeded) writes its own
    #: message here directly, because that message was written for a user in
    #: the first place.
    error = models.CharField(_("error"), max_length=500, blank=True)

    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)

    objects, all_objects = soft_delete_managers(ExportJobQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("export job")
        verbose_name_plural = _("export jobs")
        indexes = [
            models.Index(fields=["requested_by", "-created_at"], name="exportjob_owner_idx"),
            models.Index(fields=["status", "-created_at"], name="exportjob_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.report_key} ({self.format}): {self.status}"
