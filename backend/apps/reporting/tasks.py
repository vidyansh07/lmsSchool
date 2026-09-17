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
from .models import ExportJob, ExportStatus

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

    extra = {
        key: value
        for key, value in filters.items()
        if key in ("student", "since", "until", "actor", "kind", "role") and value
    }
    queryset = _queryset_for_user(user, source, batch, course, extra)
    return definition, queryset


def _tell(job: ExportJob, *, ready: bool, label: str) -> None:
    """ "Your export is ready" — or that it failed — in the requester's inbox.

    In-app always, by email when their preferences allow; the person asked for
    a file and walked away, and a notification is how they find out it exists.
    """
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    if job.requested_by is None:
        return
    notify(
        recipient=job.requested_by,
        kind=NotificationKind.EXPORT_READY if ready else NotificationKind.EXPORT_FAILED,
        title=f"Your {label} export is ready" if ready else f"Your {label} export failed",
        body=(
            f"{job.row_count} rows as {job.get_format_display()}. Download it from Reports."
            if ready
            else (job.error or "The export could not be produced.")
        ),
        link_path="/admin/reports#exports",
        resource_type="export_job",
        resource_id=str(job.pk),
    )


@shared_task(name="reporting.run_export", ignore_result=True)
def run_export(job_id: str) -> bool:
    """Render one queued job to a file in private storage.

    Re-reads the job and checks its status before doing anything, exactly as
    `notifications.tasks.send_queued_email` does: `task_acks_late` makes
    redelivery possible, and a job already moved past `QUEUED` — by a previous
    delivery of this same task, or by a cancellation racing it — must be a
    no-op rather than a second attempt or a resurrected cancelled job.
    """
    # Cross-app imports inside the function on purpose.
    from apps.configuration.settings_resolver import export_retention, forget_resolved_settings

    # The settings memo is scoped to a request, and a worker has none:
    # `RequestContextMiddleware` is what calls `request_context.reset()`, and it
    # never runs here, so the first job a worker process handles would pin the
    # retention window for the life of that process. An operator who shortened
    # "keep exports for" would then see no change until the next deploy.
    forget_resolved_settings()

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
        # How long a file stays reachable is an operator's decision, not a
        # release's. `EXPORT_RETENTION` stays as the code default that
        # `DEFAULT_SETTINGS["export_retention_days"]` mirrors, for a system
        # nobody has configured yet.
        job.expires_at = job.finished_at + export_retention()
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
        _tell(job, ready=True, label=definition.label)
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
    _tell(job, ready=False, label=job.report_key)
    record(
        action=AuditAction.EXPORT_FAILED,
        actor=job.requested_by,
        resource_type="export_job",
        resource_id=job.pk,
        result="failure",
        context={"report": job.report_key, "error": job.error},
    )
    return False


@shared_task(name="reporting.expire_exports", ignore_result=True)
def expire_exports() -> int:
    """Nightly (`CELERY_BEAT_SCHEDULE`): delete the file behind every export
    job whose own `expires_at` has passed, and mark the job `EXPIRED`.

    `expires_at` is set once, at completion time, from
    `SystemSetting.export_retention_days` as it stood then (`run_export`
    above) — this task only acts on that stored deadline; it never
    recomputes it against today's setting, so shortening the retention
    window does not retroactively expire a file that was promised a longer
    life when it was produced.

    Idempotent and safe to redeliver, the same as every other task in this
    module: the queryset only ever matches `COMPLETED` jobs, so a job this
    sweep has already moved to `EXPIRED` is not matched again, and a job
    that never completed (`QUEUED`/`PROCESSING`/`FAILED`/`CANCELLED`) is
    never touched regardless of how old it is.
    """
    from apps.configuration.settings_resolver import forget_resolved_settings

    # Same reasoning as `run_export`'s own call: a worker process has no
    # per-request settings memo to reset, so the first job it ever touches
    # would otherwise pin a stale reading for the life of the process.
    forget_resolved_settings()

    candidates = ExportJob.objects.filter(
        status=ExportStatus.COMPLETED,
        expires_at__isnull=False,
        expires_at__lte=timezone.now(),
    )
    expired = 0
    for job in candidates.iterator(chunk_size=200):
        if job.file:
            job.file.delete(save=False)
        job.status = ExportStatus.EXPIRED
        job.save(update_fields=["status", "file", "updated_at"])
        record(
            action=AuditAction.EXPORT_EXPIRED,
            actor=job.requested_by,
            resource_type="export_job",
            resource_id=job.pk,
            context={"report": job.report_key, "expired_at": str(job.expires_at)},
            durable=False,
        )
        expired += 1
    return expired
