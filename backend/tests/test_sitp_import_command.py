"""The SITP import, end to end, on a workbook built in memory.

What matters is not that rows arrive but *how*: through the same services a
person would use, so every record is validated and audited; without inventing
anything for a cell the reader could not understand; and without duplicating
anything when run a second time.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.assessments.models import Assessment, AssessmentResult
from apps.attendance.models import AttendanceRecord
from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import Batch
from apps.dsr.models import DSR, DSRStatus
from apps.enrollments.models import Enrollment
from apps.sessions.models import ClassSession
from apps.students.models import StudentProfile
from tests.test_sitp_reader import build_workbook


@pytest.fixture
def workbook(tmp_path):
    folder = tmp_path / "SITP ACE 2026 1st Year"
    folder.mkdir()
    return build_workbook(folder / "Group A.xlsx")


def run(workbook, actor_email, *, dry_run=False, report=None):
    out = StringIO()
    args = [str(workbook), "--actor", actor_email]
    if dry_run:
        args.append("--dry-run")
    if report:
        args += ["--report", str(report)]
    call_command("import_sitp_workbooks", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
def test_one_workbook_becomes_one_batch_with_its_roster_classes_registers_reports_and_marks(
    workbook, admin_user, tmp_path
):
    report_path = tmp_path / "report.json"
    run(workbook, admin_user.email, report=report_path)

    batch = Batch.objects.get(name__contains="Group A")
    assert batch.kind == "internship"
    assert batch.start_date == date(2026, 6, 10)
    assert batch.end_date == date(2026, 6, 14)

    # Three students had roll numbers; "No Roll" did not and was reported.
    rolls = set(StudentProfile.objects.exclude(roll_number="").values_list("roll_number", flat=True))
    assert rolls == {"25EACEE003", "25EACCE026", "25EACCE099"}
    assert Enrollment.objects.filter(batch=batch).count() == 3

    # One with an email keeps it; the others get an address that cannot receive mail.
    with_email = StudentProfile.objects.get(roll_number="25EACEE003")
    assert with_email.user.email == "arjit@example.test"
    placeholder = StudentProfile.objects.get(roll_number="25EACCE026")
    assert placeholder.user.email.endswith("@sitp.grras.invalid")
    assert not placeholder.user.has_usable_password()
    assert placeholder.institution == "Arya College of Engineering"

    # A class per dated column (the 1900 column was refused).
    assert set(ClassSession.objects.filter(batch=batch).values_list("session_date", flat=True)) == {
        date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 14)
    }
    # Registers as marked, with the vocabulary normalised.
    first_day = ClassSession.objects.get(batch=batch, session_date=date(2026, 6, 10))
    statuses = dict(
        AttendanceRecord.objects.filter(session=first_day).values_list("enrollment__student__roll_number", "status")
    )
    assert statuses == {"25EACEE003": "present", "25EACCE026": "present", "25EACCE099": "present"}
    second_day = ClassSession.objects.get(batch=batch, session_date=date(2026, 6, 11))
    assert dict(
        AttendanceRecord.objects.filter(session=second_day).values_list("enrollment__student__roll_number", "status")
    ) == {"25EACEE003": "absent", "25EACCE026": "late"}

    # Two DSR rows matched classes; the "not a date" row was reported.
    assert DSR.objects.filter(batch=batch, status=DSRStatus.SUBMITTED).count() == 2
    intro = DSR.objects.get(session=first_day)
    assert intro.actual_topic == "INTRO"
    assert (intro.online_count, intro.offline_count, intro.student_count) == (5, 0, 11)

    # Two assessment columns had maximums; the marks landed, absence as absence.
    assert Assessment.objects.filter(batch=batch).count() == 2
    python = Assessment.objects.get(batch=batch, title__startswith="1.")
    assert python.max_marks == Decimal("30")
    result = AssessmentResult.objects.get(assessment=python, enrollment__student__roll_number="25EACEE003")
    assert result.marks_obtained == Decimal("25")
    html = Assessment.objects.get(batch=batch, title__startswith="2.")
    absent = AssessmentResult.objects.get(assessment=html, enrollment__student__roll_number="25EACEE003")
    assert absent.is_absent and absent.marks_obtained is None

    # The report names what was left out, by sheet and row.
    report = json.loads(report_path.read_text())
    problems = report["files"][0]["problems"]
    reasons = " | ".join(p["reason"] for p in problems)
    assert "'No Roll' has no roll number" in reasons
    assert "'X' on 2026-06-11 is not an attendance mark" in reasons
    assert "'not a date' is not a date" in reasons
    assert "has no maximum marks" in reasons
    assert "'ninety' is not a mark" in reasons
    assert set(report["files"][0]["not_imported"]) == {"Course Timeline", "Project"}


@pytest.mark.django_db
def test_every_imported_record_is_in_the_audit_log_under_the_importer(workbook, admin_user):
    run(workbook, admin_user.email)

    actions = set(AuditLog.objects.filter(actor=admin_user).values_list("action", flat=True))
    for expected in (
        AuditAction.STUDENT_CREATED,
        AuditAction.BATCH_CREATED,
        AuditAction.SESSION_CREATED,
        AuditAction.DSR_CREATED,
        AuditAction.DSR_SUBMITTED,
        AuditAction.ASSESSMENT_CREATED,
    ):
        assert expected in actions, expected


@pytest.mark.django_db
def test_running_it_twice_changes_nothing(workbook, admin_user):
    run(workbook, admin_user.email)
    before = {
        model: model.objects.count()
        for model in (StudentProfile, Batch, Enrollment, ClassSession, AttendanceRecord, DSR, Assessment, AssessmentResult)
    }

    out = run(workbook, admin_user.email)

    after = {model: model.objects.count() for model in before}
    assert after == before
    assert "students already present 3" in out
    assert "registers unchanged" in out


@pytest.mark.django_db
def test_a_dry_run_reports_everything_and_writes_nothing(workbook, admin_user, tmp_path):
    report_path = tmp_path / "dry.json"
    out = run(workbook, admin_user.email, dry_run=True, report=report_path)

    assert "Dry run: nothing was written." in out
    assert StudentProfile.objects.exclude(roll_number="").count() == 0
    assert Batch.objects.filter(name__contains="Group A").count() == 0
    report = json.loads(report_path.read_text())
    assert report["dry_run"] is True
    assert report["files"][0]["counts"]["students created"] == 3


@pytest.mark.django_db
def test_it_refuses_to_run_as_nobody(workbook):
    from django.core.management import CommandError

    with pytest.raises(CommandError):
        run(workbook, "ghost@example.test")
