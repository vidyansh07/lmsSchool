"""Bulk import — §8.5.

    "Imports must use validation + preview + transaction-safe execution."

The file-reading and the never-trust-a-cell rules already exist in
:mod:`apps.assessments.importers` for §4.6, and are reused here rather than
written twice: the same size cap, the same row cap, the same formula refusal,
the same UTF-8 and spreadsheet handling. What differs is what each row means and
what it is validated against.

Two importers:

``students``
    Creates student accounts and, optionally, enrols them on a batch. The
    dangerous one: it makes accounts. A duplicate email matches the existing
    person rather than creating a second, and an existing student is *never*
    silently modified — a row that would change somebody is reported, not
    applied.

``attendance``
    Marks a register from a file, for the case where a class was taken on paper.
    Validated against the same roster the API uses, so an import cannot mark
    somebody who is not in the room.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.assessments.importers import FORMULA_PREFIXES, _cell, _normalise_header, read_rows
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.uploads import checksum_of

from .models import BulkImport, BulkImportStatus, ImportKind

#: Accepted spellings per column, as in §4.6: trainers do not all name their
#: columns the same way, and refusing a file over "Full Name" versus "name"
#: pushes people back to typing records in by hand.
STUDENT_COLUMNS: dict[str, frozenset[str]] = {
    "email": frozenset({"email", "email address", "e mail"}),
    "first_name": frozenset({"first name", "firstname", "given name", "name"}),
    "last_name": frozenset({"last name", "lastname", "surname", "family name"}),
    "phone": frozenset({"phone", "mobile", "contact", "phone number"}),
}
STUDENT_REQUIRED = ("email", "first_name")

ATTENDANCE_COLUMNS: dict[str, frozenset[str]] = {
    "student_id": frozenset({"student id", "studentid", "roll", "roll no", "id"}),
    "status": frozenset({"status", "attendance", "present"}),
    "note": frozenset({"note", "notes", "remark", "remarks"}),
}
ATTENDANCE_REQUIRED = ("student_id", "status")


def _map_columns(header: list[Any], aliases: dict[str, frozenset[str]], required) -> dict[str, int]:
    normalised = [_normalise_header(cell) for cell in header]
    mapping: dict[str, int] = {}
    for field, spellings in aliases.items():
        accepted = {name.replace("_", " ") for name in spellings}
        for index, name in enumerate(normalised):
            if name in accepted:
                mapping[field] = index
                break

    missing = [field for field in required if field not in mapping]
    if missing:
        raise ApplicationError(
            {
                "file": [
                    "The file is missing required column(s): "
                    + ", ".join(name.replace("_", " ") for name in missing)
                    + "."
                ]
            }
        )
    return mapping


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


def validate_students(rows: list[list[Any]]) -> dict[str, Any]:
    """Check every row against the live database. Writes nothing."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.core.validators import validate_email

    header, *body = rows
    mapping = _map_columns(header, STUDENT_COLUMNS, STUDENT_REQUIRED)

    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    for offset, raw in enumerate(body):
        line = offset + 2
        row = raw if isinstance(raw, list) else [raw]
        email = _cell(row, mapping.get("email")).lower()
        first_name = _cell(row, mapping.get("first_name"))
        last_name = _cell(row, mapping.get("last_name"))
        phone = _cell(row, mapping.get("phone"))

        if not any((email, first_name, last_name)):
            continue

        if any(text.startswith(FORMULA_PREFIXES) for text in (email, first_name, last_name, phone)):
            errors.append({"line": line, "email": email, "problem": "A cell looks like a formula."})
            continue
        if not email:
            errors.append({"line": line, "email": "", "problem": "No email address."})
            continue
        try:
            validate_email(email)
        except DjangoValidationError:
            errors.append({"line": line, "email": email, "problem": "Not a valid email address."})
            continue
        if not first_name:
            errors.append({"line": line, "email": email, "problem": "No first name."})
            continue
        if email in seen:
            errors.append(
                {"line": line, "email": email, "problem": f"Duplicate of line {seen[email]}."}
            )
            continue
        seen[email] = line

        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            # Deliberately not an update: a bulk file must never quietly rename
            # somebody or change their role. Matching is fine; editing is not.
            errors.append(
                {
                    "line": line,
                    "email": email,
                    "problem": "An account with this address already exists.",
                }
            )
            continue

        valid.append(
            {
                "line": line,
                "email": email,
                "first_name": first_name[:150],
                "last_name": last_name[:150],
                "phone": phone[:20],
            }
        )

    return {
        "columns": {
            field: header[index] for field, index in mapping.items() if index < len(header)
        },
        "rows": valid,
        "errors": errors,
        "summary": {
            "read": len(body),
            "valid": len(valid),
            "errors": len(errors),
            "would_create": len(valid),
            "would_update": 0,
        },
    }


@transaction.atomic
def preview_students(*, actor: User, uploaded_file, batch=None) -> BulkImport:
    rows = read_rows(uploaded_file)
    report = validate_students(rows)
    if batch is not None:
        report["batch"] = {"id": str(batch.pk), "code": batch.code}

    run = BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
        original_filename=(getattr(uploaded_file, "name", "") or "")[:255],
        checksum=checksum_of(uploaded_file),
        row_count=report["summary"]["read"],
        valid_count=report["summary"]["valid"],
        error_count=report["summary"]["errors"],
        status=BulkImportStatus.PREVIEW if report["rows"] else BulkImportStatus.FAILED,
        report=report,
    )
    record(
        action=AuditAction.BULK_IMPORT_PREVIEWED,
        actor=actor,
        resource_type="bulk_import",
        resource_id=run.pk,
        context={"kind": run.kind, "checksum": run.checksum, **report["summary"]},
        durable=False,
    )
    return run


@transaction.atomic
def confirm_students(*, run: BulkImport, actor: User) -> BulkImport:
    """Create the accounts, all or nothing.

    Every row is re-checked against the database: an address registered between
    the preview and the confirmation fails the import rather than colliding.
    """
    _check_confirmable(run)

    from apps.students.services import create_student

    batch = None
    if run.report.get("batch"):
        from apps.batches.models import Batch

        batch = Batch.objects.filter(pk=run.report["batch"]["id"]).first()

    created = 0
    for row in run.report.get("rows", []):
        if User.objects.filter(email__iexact=row["email"]).exists():
            raise ConflictError(
                {
                    "import": [
                        f"{row['email']} was registered since the preview. "
                        "Upload the file again to see a fresh preview."
                    ]
                }
            )
        student = create_student(
            email=row["email"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            actor=actor,
            password=None,
            send_invitation=False,
            profile_fields={"phone": row["phone"]} if row["phone"] else None,
        )
        created += 1

        if batch is not None:
            from apps.enrollments.services import enrol_student

            enrol_student(student=student, batch=batch, actor=actor)

    return _finish(run=run, actor=actor, created=created, updated=0)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

_STATUS_WORDS = {
    "present": "present",
    "p": "present",
    "yes": "present",
    "y": "present",
    "absent": "absent",
    "a": "absent",
    "no": "absent",
    "n": "absent",
    "late": "late",
    "l": "late",
    "excused": "excused",
    "e": "excused",
}


def validate_attendance(*, session, rows: list[list[Any]]) -> dict[str, Any]:
    from apps.attendance.services import roster_for

    header, *body = rows
    mapping = _map_columns(header, ATTENDANCE_COLUMNS, ATTENDANCE_REQUIRED)

    roster = {
        enrollment.student.student_id.upper(): enrollment for enrollment in roster_for(session)
    }

    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    for offset, raw in enumerate(body):
        line = offset + 2
        row = raw if isinstance(raw, list) else [raw]
        student_id = _cell(row, mapping.get("student_id"))
        status_text = _cell(row, mapping.get("status")).lower()
        note = _cell(row, mapping.get("note"))

        if not student_id and not status_text:
            continue
        if student_id.startswith(FORMULA_PREFIXES) or note.startswith(FORMULA_PREFIXES):
            errors.append(
                {"line": line, "student_id": student_id, "problem": "A cell looks like a formula."}
            )
            continue

        key = student_id.upper()
        if key in seen:
            errors.append(
                {
                    "line": line,
                    "student_id": student_id,
                    "problem": f"Duplicate of line {seen[key]}.",
                }
            )
            continue
        seen[key] = line

        enrollment = roster.get(key)
        if enrollment is None:
            errors.append(
                {
                    "line": line,
                    "student_id": student_id,
                    "problem": "Not on this class's register.",
                }
            )
            continue

        status = _STATUS_WORDS.get(status_text)
        if status is None:
            errors.append(
                {
                    "line": line,
                    "student_id": student_id,
                    "problem": f"'{status_text}' is not present, absent, late or excused.",
                }
            )
            continue

        valid.append(
            {
                "line": line,
                "student_id": student_id,
                "enrollment_id": str(enrollment.pk),
                "student_name": enrollment.student.user.get_full_name(),
                "status": status,
                "note": note[:255],
            }
        )

    missing = [
        {"student_id": code, "student_name": row.student.user.get_full_name()}
        for code, row in roster.items()
        if code not in seen
    ]

    return {
        "columns": {
            field: header[index] for field, index in mapping.items() if index < len(header)
        },
        "session": {"id": str(session.pk), "date": session.session_date.isoformat()},
        "rows": valid,
        "errors": errors,
        "not_in_file": missing,
        "summary": {
            "read": len(body),
            "valid": len(valid),
            "errors": len(errors),
            "would_create": len(valid),
            "would_update": 0,
            "not_in_file": len(missing),
        },
    }


@transaction.atomic
def preview_attendance(*, actor: User, session, uploaded_file) -> BulkImport:
    rows = read_rows(uploaded_file)
    report = validate_attendance(session=session, rows=rows)

    run = BulkImport.objects.create(
        kind=ImportKind.ATTENDANCE,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
        session=session,
        original_filename=(getattr(uploaded_file, "name", "") or "")[:255],
        checksum=checksum_of(uploaded_file),
        row_count=report["summary"]["read"],
        valid_count=report["summary"]["valid"],
        error_count=report["summary"]["errors"],
        status=BulkImportStatus.PREVIEW if report["rows"] else BulkImportStatus.FAILED,
        report=report,
    )
    record(
        action=AuditAction.BULK_IMPORT_PREVIEWED,
        actor=actor,
        resource_type="bulk_import",
        resource_id=run.pk,
        context={"kind": run.kind, "checksum": run.checksum, **report["summary"]},
        durable=False,
    )
    return run


@transaction.atomic
def confirm_attendance(*, run: BulkImport, actor: User) -> BulkImport:
    """Mark the register, through the same service the API uses.

    Not a bulk write of its own: the register service owns the rules about which
    classes can be marked and what a re-mark means, and an importer that wrote
    rows directly would be a second place for those rules to be wrong.
    """
    _check_confirmable(run)

    from apps.attendance.services import mark_attendance

    entries = [
        {"enrollment_id": row["enrollment_id"], "status": row["status"], "note": row["note"]}
        for row in run.report.get("rows", [])
    ]
    result = mark_attendance(session=run.session, actor=actor, entries=entries)
    return _finish(run=run, actor=actor, created=result["created"], updated=result["updated"])


# ---------------------------------------------------------------------------
# Shared workflow
# ---------------------------------------------------------------------------


def _check_confirmable(run: BulkImport) -> None:
    if run.status != BulkImportStatus.PREVIEW:
        raise ConflictError({"import": [f"This import is already {run.get_status_display()}."]})
    if run.error_count:
        raise ConflictError(
            {"import": ["Fix the rows listed in the preview and upload the file again."]}
        )
    if not run.report.get("rows"):
        raise ConflictError({"import": ["There is nothing to apply."]})


def _finish(*, run: BulkImport, actor: User, created: int, updated: int) -> BulkImport:
    run.status = BulkImportStatus.CONFIRMED
    run.created_count = created
    run.updated_count = updated
    run.confirmed_at = timezone.now()
    run.save(
        update_fields=["status", "created_count", "updated_count", "confirmed_at", "updated_at"]
    )
    record(
        action=AuditAction.BULK_IMPORT_CONFIRMED,
        actor=actor,
        resource_type="bulk_import",
        resource_id=run.pk,
        context={
            "kind": run.kind,
            "created": created,
            "updated": updated,
            "checksum": run.checksum,
        },
        durable=False,
    )
    return run


@transaction.atomic
def reject(*, run: BulkImport, actor: User) -> BulkImport:
    if run.status != BulkImportStatus.PREVIEW:
        raise ConflictError({"import": [f"This import is already {run.get_status_display()}."]})
    run.status = BulkImportStatus.REJECTED
    run.save(update_fields=["status", "updated_at"])
    record(
        action=AuditAction.BULK_IMPORT_REJECTED,
        actor=actor,
        resource_type="bulk_import",
        resource_id=run.pk,
        context={"kind": run.kind},
        durable=False,
    )
    return run
