"""Trainer result import — §4.6.

A trainer hands the LMS a spreadsheet that came out of Google Forms, or out of
a colleague's laptop, or off a USB stick. §4.6's instruction is blunt: *never
trust spreadsheet values blindly*. So nothing here treats a cell as data until
it has been proved to be data.

The workflow is **preview → validate → confirm**:

1. ``preview_import`` reads the file, validates every row against the live
   database and stores a :class:`ResultImport` describing exactly what would
   happen. **Nothing is written to the results table.**
2. The trainer reads the report — matched students, unknown ids, duplicates,
   bad marks — and decides.
3. ``confirm_import`` applies it **inside one transaction**, re-validating from
   the file's stored rows against the database as it goes. Either every row
   lands or none does, so a bad import cannot leave half a class marked.

What is defended against, and how
---------------------------------
``formula cells``      Workbooks are opened ``data_only=True``, so a formula
                       yields its cached value and is never evaluated. A cell
                       whose *text* begins ``= + - @`` is refused outright
                       rather than stored, because that string re-exported into
                       a CSV is a spreadsheet-injection payload in somebody
                       else's Excel.
``zip bombs``          ``.xlsx`` is a ZIP container. The upload is size-capped
                       before it is opened, the sheet is read row by row in
                       read-only mode, and the row count is capped — so a
                       sheet claiming a million rows stops at the cap instead
                       of exhausting memory.
``unknown students``   A student id that matches nobody, or matches somebody
                       who is not in this assessment's cohort, is an error row.
                       It is never created, and never silently skipped.
``duplicates``         The same student twice in one file is an error on the
                       second occurrence; the first is not quietly overwritten.
``invalid marks``      Parsed as a Decimal and bounded by the assessment's own
                       maximum through the same ``validate_mark`` the API uses.
``stale previews``     Confirmation re-resolves every student against the
                       database. An enrolment cancelled between preview and
                       confirm fails the row rather than writing to it.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.uploads import checksum_of

from .models import Assessment, ImportStatus, ResultImport, ResultSource
from .services import cohort_for, record_result

#: Hard ceilings. A result file for one batch is tens of rows; anything of a
#: different order of magnitude is a mistake or an attack, not a class list.
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 2000
MAX_CELL_LENGTH = 500

ALLOWED_IMPORT_EXTENSIONS = frozenset({".csv", ".xlsx"})

#: Accepted spellings for each column, lower-cased and stripped. Trainers do not
#: all name their columns the same way, and rejecting a file over "Student ID"
#: versus "student_id" would push people back to marking on paper.
COLUMN_ALIASES: dict[str, frozenset[str]] = {
    "student_id": frozenset({"student_id", "student id", "studentid", "roll", "roll no", "id"}),
    "marks": frozenset({"marks", "mark", "score", "marks obtained", "marks_obtained", "result"}),
    "absent": frozenset({"absent", "is_absent", "attendance", "present"}),
    "remarks": frozenset({"remarks", "remark", "comment", "comments", "note", "notes"}),
}

REQUIRED_COLUMNS = ("student_id", "marks")

#: A cell whose text starts with one of these is a spreadsheet formula. Refused
#: rather than stored, because a stored one becomes an injection payload the
#: moment this data is exported again.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t=", "\r=")

_TRUE_WORDS = frozenset({"yes", "y", "true", "1", "absent", "a"})
_FALSE_WORDS = frozenset({"no", "n", "false", "0", "present", "p", ""})


class ImportError_(ApplicationError):
    """A problem with the file itself, as opposed to with a row inside it."""

    default_detail = "The file could not be read."
    default_code = "import_failed"


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------


def _normalise_header(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _map_columns(header: list[Any]) -> dict[str, int]:
    """Map our field names onto the file's column positions."""
    normalised = [_normalise_header(cell) for cell in header]
    mapping: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        accepted = {alias.replace("_", " ") for alias in aliases}
        for index, name in enumerate(normalised):
            if name in accepted:
                mapping[field] = index
                break

    missing = [field for field in REQUIRED_COLUMNS if field not in mapping]
    if missing:
        raise ImportError_(
            {
                "file": [
                    "The file is missing required column(s): "
                    + ", ".join(missing)
                    + ". Expected a header row with at least 'student_id' and 'marks'."
                ]
            }
        )
    return mapping


def _cell(row: list[Any], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()[:MAX_CELL_LENGTH]


def _read_csv(uploaded_file) -> list[list[str]]:
    uploaded_file.seek(0)
    raw = uploaded_file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_({"file": ["The file is not valid UTF-8 text."]}) from exc
    if "\x00" in text:
        raise ImportError_({"file": ["The file does not look like a CSV."]})

    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    for row in reader:
        rows.append([str(cell) for cell in row])
        if len(rows) > MAX_IMPORT_ROWS + 1:  # +1 for the header
            raise ImportError_({"file": [f"The file has more than {MAX_IMPORT_ROWS} rows."]})
    return rows


def _read_xlsx(uploaded_file) -> list[list[Any]]:
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    uploaded_file.seek(0)
    try:
        # `data_only` returns the cached value of a formula instead of the
        # formula, and `read_only` streams the sheet rather than building the
        # whole workbook in memory.
        workbook = load_workbook(io.BytesIO(uploaded_file.read()), data_only=True, read_only=True)
    except (InvalidFileException, OSError, ValueError, KeyError) as exc:
        raise ImportError_({"file": ["The file could not be opened as a spreadsheet."]}) from exc

    try:
        sheet = workbook.worksheets[0]
        rows: list[list[Any]] = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
            if len(rows) > MAX_IMPORT_ROWS + 1:
                raise ImportError_({"file": [f"The file has more than {MAX_IMPORT_ROWS} rows."]})
        return rows
    finally:
        workbook.close()


def read_rows(uploaded_file) -> list[list[Any]]:
    """Validate the file's type and size, then read it into rows."""
    name = getattr(uploaded_file, "name", "") or ""
    suffix = PurePosixPath(name).suffix.lower()

    size = getattr(uploaded_file, "size", None)
    if not size:
        raise ImportError_({"file": ["The uploaded file is empty."]})
    if size > MAX_IMPORT_BYTES:
        raise ImportError_(
            {"file": [f"The file must be {MAX_IMPORT_BYTES // (1024 * 1024)} MB or smaller."]}
        )
    if suffix not in ALLOWED_IMPORT_EXTENSIONS:
        raise ImportError_({"file": ["Upload a .csv or .xlsx file."]})

    rows = _read_csv(uploaded_file) if suffix == ".csv" else _read_xlsx(uploaded_file)
    if len(rows) < 2:
        raise ImportError_({"file": ["The file has a header but no result rows."]})
    return rows


# ---------------------------------------------------------------------------
# Validating the rows
# ---------------------------------------------------------------------------


def _parse_absent(text: str, column_is_present_style: bool) -> bool:
    lowered = text.strip().lower()
    if column_is_present_style:
        # A column headed "present" means the opposite of what we store.
        if lowered in _TRUE_WORDS - {"absent", "a"}:
            return False
        if lowered in _FALSE_WORDS - {""}:
            return True
        return False
    if lowered in _TRUE_WORDS:
        return True
    if lowered in _FALSE_WORDS:
        return False
    raise ValueError(f"'{text}' is not a yes/no value")


def validate_rows(*, assessment: Assessment, rows: list[list[Any]]) -> dict[str, Any]:
    """Check every row against the live database. Writes nothing.

    Returns the report stored on the :class:`ResultImport`: the rows that would
    apply, and one entry per problem with the line number a trainer can find in
    their spreadsheet.
    """
    header, *body = rows
    mapping = _map_columns(header)
    absent_column_name = _normalise_header(header[mapping["absent"]] if "absent" in mapping else "")
    present_style = absent_column_name in {"present", "attendance"}

    # The cohort, keyed by the identifier a trainer would type.
    cohort = {
        enrollment.student.student_id.upper(): enrollment for enrollment in cohort_for(assessment)
    }
    already = set(assessment.results.values_list("enrollment_id", flat=True))

    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    for offset, raw_row in enumerate(body):
        line = offset + 2  # 1-indexed, and the header is line 1
        row = [raw_row] if not isinstance(raw_row, list) else raw_row
        student_id = _cell(row, mapping.get("student_id"))
        marks_text = _cell(row, mapping.get("marks"))
        absent_text = _cell(row, mapping.get("absent"))
        remarks = _cell(row, mapping.get("remarks"))

        if not student_id and not marks_text and not absent_text:
            continue  # a blank trailing line, not a problem

        for label, text in (("student_id", student_id), ("remarks", remarks)):
            if text.startswith(FORMULA_PREFIXES):
                errors.append(
                    {
                        "line": line,
                        "student_id": student_id,
                        "problem": f"The {label} cell looks like a spreadsheet formula.",
                    }
                )
                break
        else:
            key = student_id.upper()
            if not key:
                errors.append({"line": line, "student_id": "", "problem": "No student id."})
                continue
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

            enrollment = cohort.get(key)
            if enrollment is None:
                errors.append(
                    {
                        "line": line,
                        "student_id": student_id,
                        "problem": "Not a student in this assessment's cohort.",
                    }
                )
                continue

            try:
                is_absent = _parse_absent(absent_text, present_style)
            except ValueError as exc:
                errors.append({"line": line, "student_id": student_id, "problem": str(exc)})
                continue

            marks: Decimal | None = None
            if not is_absent:
                if marks_text == "":
                    errors.append(
                        {"line": line, "student_id": student_id, "problem": "No mark given."}
                    )
                    continue
                try:
                    marks = Decimal(marks_text)
                except (InvalidOperation, ValueError):
                    errors.append(
                        {
                            "line": line,
                            "student_id": student_id,
                            "problem": f"'{marks_text}' is not a number.",
                        }
                    )
                    continue
                if marks < 0 or marks > assessment.max_marks:
                    errors.append(
                        {
                            "line": line,
                            "student_id": student_id,
                            "problem": (
                                f"{marks} is outside the range 0 to {assessment.max_marks}."
                            ),
                        }
                    )
                    continue
            elif marks_text not in ("", "0"):
                errors.append(
                    {
                        "line": line,
                        "student_id": student_id,
                        "problem": "An absent student cannot also have a mark.",
                    }
                )
                continue

            valid.append(
                {
                    "line": line,
                    "student_id": student_id,
                    "enrollment_id": str(enrollment.pk),
                    "student_name": enrollment.student.user.get_full_name(),
                    "marks": None if marks is None else str(marks),
                    "is_absent": is_absent,
                    "remarks": remarks,
                    "replaces_existing": enrollment.pk in already,
                }
            )

    missing = [
        {"student_id": student_id, "student_name": enrollment.student.user.get_full_name()}
        for student_id, enrollment in cohort.items()
        if student_id not in seen
    ]

    return {
        "columns": {
            field: header[index] for field, index in mapping.items() if index < len(header)
        },
        "rows": valid,
        "errors": errors,
        "not_in_file": missing,
        "summary": {
            "read": len(body),
            "valid": len(valid),
            "errors": len(errors),
            "would_create": sum(1 for row in valid if not row["replaces_existing"]),
            "would_update": sum(1 for row in valid if row["replaces_existing"]),
            "cohort_size": len(cohort),
            "not_in_file": len(missing),
        },
    }


# ---------------------------------------------------------------------------
# The two-step workflow
# ---------------------------------------------------------------------------


@transaction.atomic
def preview_import(*, assessment: Assessment, actor: User, uploaded_file) -> ResultImport:
    """Step one: read, validate, store the report. Writes no results."""
    rows = read_rows(uploaded_file)
    report = validate_rows(assessment=assessment, rows=rows)

    run = ResultImport.objects.create(
        assessment=assessment,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
        original_filename=(getattr(uploaded_file, "name", "") or "")[:255],
        checksum=checksum_of(uploaded_file),
        row_count=report["summary"]["read"],
        valid_count=report["summary"]["valid"],
        error_count=report["summary"]["errors"],
        status=ImportStatus.PREVIEW if report["rows"] else ImportStatus.FAILED,
        report=report,
    )

    record(
        action=AuditAction.RESULT_IMPORT_PREVIEWED,
        actor=actor,
        resource_type="result_import",
        resource_id=run.pk,
        context={
            "assessment": assessment.code,
            "filename": run.original_filename,
            "checksum": run.checksum,
            **report["summary"],
        },
        durable=False,
    )
    return run


@transaction.atomic
def confirm_import(*, run: ResultImport, actor: User) -> ResultImport:
    """Step two: apply the previewed rows, all or nothing.

    Every row is re-resolved against the database. The preview's own
    ``enrollment_id`` is used as a lookup key, never as proof — an enrolment
    cancelled since the preview fails here rather than being written to.
    """
    if run.status != ImportStatus.PREVIEW:
        raise ConflictError({"import": [f"This import is already {run.get_status_display()}."]})
    if run.error_count:
        raise ConflictError(
            {"import": ["Fix the rows listed in the preview and upload the file again."]}
        )

    rows = run.report.get("rows", [])
    if not rows:
        raise ConflictError({"import": ["There is nothing to apply."]})

    assessment = run.assessment
    cohort = {str(enrollment.pk): enrollment for enrollment in cohort_for(assessment)}

    created = updated = 0
    for row in rows:
        enrollment = cohort.get(row["enrollment_id"])
        if enrollment is None:
            # The class list changed between preview and confirm. Rolling the
            # whole import back is the safe answer: a partially applied result
            # sheet is worse than none.
            raise ConflictError(
                {
                    "import": [
                        f"{row['student_id']} is no longer in this cohort. "
                        "Upload the file again to see a fresh preview."
                    ]
                }
            )
        _, was_created = record_result(
            assessment=assessment,
            enrollment=enrollment,
            actor=actor,
            marks=None if row["marks"] is None else Decimal(row["marks"]),
            is_absent=row["is_absent"],
            remarks=row["remarks"],
            source=ResultSource.IMPORT,
            import_run=run,
        )
        created += int(was_created)
        updated += int(not was_created)

    run.status = ImportStatus.CONFIRMED
    run.created_count = created
    run.updated_count = updated
    run.confirmed_at = timezone.now()
    run.save(
        update_fields=["status", "created_count", "updated_count", "confirmed_at", "updated_at"]
    )

    record(
        action=AuditAction.RESULT_IMPORT_CONFIRMED,
        actor=actor,
        resource_type="result_import",
        resource_id=run.pk,
        context={
            "assessment": assessment.code,
            "created": created,
            "updated": updated,
            "checksum": run.checksum,
        },
        durable=False,
    )
    return run


@transaction.atomic
def reject_import(*, run: ResultImport, actor: User) -> ResultImport:
    """Discard a preview without applying it."""
    if run.status != ImportStatus.PREVIEW:
        raise ConflictError({"import": [f"This import is already {run.get_status_display()}."]})
    run.status = ImportStatus.REJECTED
    run.save(update_fields=["status", "updated_at"])
    record(
        action=AuditAction.RESULT_IMPORT_REJECTED,
        actor=actor,
        resource_type="result_import",
        resource_id=run.pk,
        context={"assessment": run.assessment.code},
        durable=False,
    )
    return run
