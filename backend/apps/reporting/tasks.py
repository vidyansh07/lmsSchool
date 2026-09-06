"""Background tasks for report exports.

``run_export`` is the whole surface: one task that takes a job id and moves it
``QUEUED → PROCESSING → COMPLETED`` or ``FAILED``. It is declared here, in
``apps/reporting/tasks.py``, purely so Celery's ``autodiscover_tasks()`` (see
``config.celery``) finds it — the same mechanism that already picks up
``apps.notifications.tasks``. Nothing in ``config/settings`` or
``config/celery.py`` needed to change for a new task to exist.

**The queryset is re-derived here, never carried on the job.** `ExportJob`
stores what a job was *asked* for — a report key, a batch, a course — as
display metadata. It is not read back to decide what the file contains. This
task rebuilds the scoped queryset from the requesting user's access exactly as
it stands *right now*, using the identical `_queryset_for_user` the on-screen
report and the synchronous CSV download use. That is deliberate and it is the
whole point of the design: a job queued while a role held wide access must not
still export at that width after the role was narrowed, a batch reassignment
happened, or the account was switched off, all of which can happen in the
(possibly considerable) time between a job being queued and a worker
picking it up. Trusting anything captured at queue time would turn "export
what I can see" into "export what I could see once," and nobody reviewing an
export three days later can tell those apart from the file alone.

**This task never raises.** Every branch that can fail — an unknown key, a
scope that has narrowed to nothing the caller can no longer reach, a row cap,
an unexpected exception from a writer — is caught here and turned into a
``FAILED`` job with a clean, user-facing ``error``. `notifications.tasks` sets
the same rule for the same reason: with ``CELERY_TASK_EAGER_PROPAGATES`` on in
tests and ``task_acks_late`` in production, a task that raises either breaks
the request that queued it (eager) or gets silently redelivered and retried
against a job already marked failed (broker). Both are worse than a status
field with a message in it.
"""

from __future__ import annotations

import hashlib
import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.logging import scrub_text
from apps.courses import access as course_access

from . import access, reports, writers
from .models import EXPORT_RETENTION, ExportJob, ExportStatus

logger = logging.getLogger("grras.reporting")

#: Shown to the caller for any failure that is not one of the specific,
#: already-friendly messages raised below (a scope problem, the PDF row cap).
#: The real cause is always logged server-side with `logger.exception`, in full
#: — this field is what a user sees, and a traceback is not written for a user.
GENERIC_FAILURE_MESSAGE = (
    "This export could not be completed. Try again, or contact support if it keeps happening."
)


class ExportScopeError(Exception):
    """The caller's access will no longer produce this file.

    Covers every way "queued, then the world changed" can happen: the account
    was deactivated, the role lost `data.export` or `report.view_any`, the
    report key stopped existing, or the batch/course the job was scoped to is
    no longer visible to whoever queued it.
    """


def _rescope(job: ExportJob):
    """Re-derive `(definition, queryset)` from the requester's *current* access.

    Raises `ExportScopeError` for every reason that access might have
    narrowed. Nothing here reads `job.filters` as authorization — only as the
    ids to look up, which are then checked against a *freshly* resolved
    visible set.
    """
    from .views import _queryset_for_user

    user = job.requested_by
    if user is None or not user.is_active:
        raise ExportScopeError("The account that queued this export is no longer active.")
    if not access.can_read_reports(user) or not has_capability(user, Capability.DATA_EXPORT):
        raise ExportScopeError("You no longer have permission to export this report.")
    if job.report_key not in reports.REPORTS:
        raise ExportScopeError("This report no longer exists.")

    definition, _producer, source = reports.REPORTS[job.report_key]
    filters = job.filters or {}

    batch = course = None
    batch_id = filters.get("batch_id")
    course_id = filters.get("course_id")
    if batch_id:
        batch = batch_access.visible_batches(user).filter(pk=batch_id).first()
        if batch is None:
            raise ExportScopeError(
                "The batch this export was scoped to is no longer visible to you."
            )
    if course_id:
        course = course_access.visible_courses(user).filter(pk=course_id).first()
        if course is None:
            raise ExportScopeError(
                "The course this export was scoped to is no longer visible to you."
            )

    queryset = _queryset_for_user(user, source, batch, course)
    return definition, queryset


@shared_task(name="reporting.run_export", ignore_result=True)
def run_export(job_id: str) -> bool:
    """Render one queued job to a file in private storage.

    Re-reads the job and checks its status before doing anything, exactly as
    `notifications.tasks.send_queued_email` does: `task_acks_late` makes
    redelivery possible, and a job already moved past `QUEUED` — by a previous
    delivery of this same task, or by a cancellation racing it — must be a
    no-op rather than a second attempt or a resurrected cancelled job.
    """
    job = ExportJob.objects.select_related("requested_by").filter(pk=job_id).first()
    if job is None:
        return False
    if job.status != ExportStatus.QUEUED:
        return False

    job.status = ExportStatus.PROCESSING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])

    error_message: str | None = None
    try:
        definition, queryset = _rescope(job)
        _report, produced = reports.run(job.report_key, queryset)

        content, row_count = writers.write(
            job.format,
            definition.column_dicts(),
            produced,
            title=definition.label,
            filters=job.filters or {},
        )

        checksum = hashlib.sha256(content).hexdigest()
        filename = writers.filename_for(job.report_key, job.format)

        job.file.save(filename, ContentFile(content), save=False)
        job.original_filename = filename
        job.checksum = checksum
        job.size_bytes = len(content)
        job.row_count = row_count
        job.status = ExportStatus.COMPLETED
        job.finished_at = timezone.now()
        job.expires_at = job.finished_at + EXPORT_RETENTION
        job.error = ""
        job.save(
            update_fields=[
                "file",
                "original_filename",
                "checksum",
                "size_bytes",
                "row_count",
                "status",
                "finished_at",
                "expires_at",
                "error",
                "updated_at",
            ]
        )
        record(
            action=AuditAction.EXPORT_COMPLETED,
            actor=job.requested_by,
            resource_type="export_job",
            resource_id=job.pk,
            context={"report": job.report_key, "format": job.format, "rows": row_count},
            durable=False,
        )
        return True

    except (ExportScopeError, writers.RowLimitExceeded) as exc:
        error_message = scrub_text(str(exc))
    except Exception:
        logger.exception(
            "Export job failed unexpectedly",
            extra={"context": {"job": str(job.pk), "report": job.report_key}},
        )
        error_message = GENERIC_FAILURE_MESSAGE

    job.status = ExportStatus.FAILED
    job.finished_at = timezone.now()
    job.error = error_message[:500]
    job.save(update_fields=["status", "finished_at", "error", "updated_at"])
    record(
        action=AuditAction.EXPORT_FAILED,
        actor=job.requested_by,
        resource_type="export_job",
        resource_id=job.pk,
        result="failure",
        context={"report": job.report_key, "error": job.error},
    )
    return False
