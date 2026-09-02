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

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


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
