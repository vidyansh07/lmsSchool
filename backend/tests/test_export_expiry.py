"""The nightly `reporting.expire_exports` beat task (ERP Phase 20).

`tests/test_export_jobs.py` covers the job lifecycle up to and including
`expires_at` being set on completion; this file covers what happens once
that deadline passes — the file is deleted, the job is marked `EXPIRED`, and
a job that has not yet reached its own `expires_at` (however old the job
row itself is) is left completely alone.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.reporting import tasks
from apps.reporting.models import ExportFormat, ExportJob, ExportStatus

pytestmark = pytest.mark.django_db


def _completed_job(*, requested_by, expires_at, with_file: bool = True) -> ExportJob:
    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=requested_by,
        status=ExportStatus.COMPLETED,
        finished_at=timezone.now(),
        expires_at=expires_at,
        row_count=3,
        checksum="a" * 64,
        size_bytes=42,
    )
    if with_file:
        job.file.save("export.csv", ContentFile(b"student,name\n1,Test\n"), save=True)
    return job


# ---------------------------------------------------------------------------
# The sweep itself
# ---------------------------------------------------------------------------


def test_expires_a_job_past_its_retention_window(admin_user):
    job = _completed_job(requested_by=admin_user, expires_at=timezone.now() - timedelta(days=1))
    file_name = job.file.name
    assert job.file.storage.exists(file_name)

    expired = tasks.expire_exports()

    assert expired == 1
    job.refresh_from_db()
    assert job.status == ExportStatus.EXPIRED
    assert not job.file
    assert not job.file.storage.exists(file_name)


def test_never_touches_a_job_still_within_its_retention_window(admin_user):
    job = _completed_job(requested_by=admin_user, expires_at=timezone.now() + timedelta(days=1))

    expired = tasks.expire_exports()

    assert expired == 0
    job.refresh_from_db()
    assert job.status == ExportStatus.COMPLETED
    assert job.file


def test_never_touches_a_job_with_no_expiry_set(admin_user):
    """A job that somehow never got an `expires_at` (defensive: `run_export`
    always sets one on completion) is left alone rather than treated as
    already-expired."""
    job = _completed_job(requested_by=admin_user, expires_at=None)

    expired = tasks.expire_exports()

    assert expired == 0
    job.refresh_from_db()
    assert job.status == ExportStatus.COMPLETED


@pytest.mark.parametrize(
    "status",
    [ExportStatus.QUEUED, ExportStatus.PROCESSING, ExportStatus.FAILED, ExportStatus.CANCELLED],
)
def test_never_touches_a_job_that_never_completed_however_old(admin_user, status):
    """Only a `COMPLETED` job ever has a file to expire. A `FAILED` or
    `CANCELLED` job with a (spuriously old) `expires_at` must not be swept
    into `EXPIRED` — that status means something different from "this one
    finished and its file's lifetime ran out"."""
    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=admin_user,
        status=status,
        expires_at=timezone.now() - timedelta(days=30),
    )

    expired = tasks.expire_exports()

    assert expired == 0
    job.refresh_from_db()
    assert job.status == status


def test_a_job_already_expired_is_not_swept_again(admin_user):
    job = _completed_job(
        requested_by=admin_user, expires_at=timezone.now() - timedelta(days=10), with_file=False
    )
    job.status = ExportStatus.EXPIRED
    job.save(update_fields=["status"])

    expired = tasks.expire_exports()

    assert expired == 0


def test_sweeps_several_jobs_in_one_run(admin_user):
    jobs = [
        _completed_job(requested_by=admin_user, expires_at=timezone.now() - timedelta(days=i + 1))
        for i in range(3)
    ]
    still_fresh = _completed_job(
        requested_by=admin_user, expires_at=timezone.now() + timedelta(days=5)
    )

    expired = tasks.expire_exports()

    assert expired == 3
    for job in jobs:
        job.refresh_from_db()
        assert job.status == ExportStatus.EXPIRED
    still_fresh.refresh_from_db()
    assert still_fresh.status == ExportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_expiring_a_job_is_audited(admin_user):
    job = _completed_job(requested_by=admin_user, expires_at=timezone.now() - timedelta(days=1))

    tasks.expire_exports()

    actions = set(AuditLog.objects.filter(resource_id=job.pk).values_list("action", flat=True))
    assert AuditAction.EXPORT_EXPIRED in actions


def test_expiring_a_job_with_no_requester_does_not_explode(admin_user):
    """`requested_by` is `SET_NULL`; an orphaned job must still expire
    cleanly rather than the sweep crashing on a null actor."""
    job = _completed_job(requested_by=admin_user, expires_at=timezone.now() - timedelta(days=1))
    job.requested_by = None
    job.save(update_fields=["requested_by"])

    expired = tasks.expire_exports()

    assert expired == 1
    job.refresh_from_db()
    assert job.status == ExportStatus.EXPIRED
