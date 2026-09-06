"""Rendering a report to a file — the three formats `ExportJob` can produce.

`apps.reporting.exports` already solved streaming CSV straight into an HTTP
response. A background job cannot stream into anything — there is no request
to write bytes onto — so every writer here returns the finished file as
``bytes`` for `apps.reporting.tasks.run_export` to hand to storage. That is a
real trade-off, not an oversight: it means a writer holds one rendered file in
memory rather than one row, which is why `PDF_MAX_ROW_LIMIT` exists below and
why XLSX uses openpyxl's write-only mode rather than the ordinary one.

**Formula injection applies to every format that Excel can open, not only
CSV.** `apps.reporting.exports.sanitise` is reused as-is for XLSX cell values,
and matters *more* there than in CSV: openpyxl inspects a plain string starting
with ``=`` and stores it as a formula (data type ``f``) rather than text,
before Excel ever sees the file. Feeding raw values to a cell would mean the
export tool itself creates the formula the sanitiser exists to prevent, not
just fail to strip one. Prefixing with an apostrophe first — exactly what
`sanitise` already does — keeps the leading character `'`, not `=`, so
openpyxl stores it as an ordinary string.

**A PDF is not a spreadsheet.** It has no formula engine, so injection is not
the concern; scale is. A landscape A4 page holds a few dozen rows, so ten
thousand of them is fifty-plus pages nobody asked to print. Rather than
silently handing back a truncated document that looks complete, exceeding
`PDF_MAX_ROW_LIMIT` fails the job outright with a message that says why —
CSV or XLSX are the shapes to choose for anything that large.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.utils import timezone

from .exports import sanitise, stream_csv

#: A landscape A4 page fits roughly 35-40 data rows under a title block and a
#: repeating header. This is comfortably past "an operator will actually
#: print or skim this", not a technical ceiling reportlab enforces.
PDF_MAX_ROW_LIMIT = 2_000

#: Content type for the finished file, keyed by `ExportFormat`.
CONTENT_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


class RowLimitExceeded(Exception):
    """Raised by `write_pdf` when the row cap is exceeded.

    The message is written for the person who queued the export, not for a
    log: `apps.reporting.tasks.run_export` stores `str(exc)` directly in
    `ExportJob.error`.
    """

    def __init__(self, limit: int):
        super().__init__(
            f"This report has more than {limit:,} rows, which is too many for a PDF. "
            "Export it as CSV or Excel instead."
        )
        self.limit = limit


def filename_for(key: str, fmt: str) -> str:
    """A safe download name. Never built from anything user-supplied."""
    stem = re.sub(r"[^a-z0-9_-]+", "-", key.lower()).strip("-") or "report"
    return f"{stem}-{timezone.localdate().isoformat()}.{fmt}"


def _display(value: Any) -> str:
    """Render one value for a spreadsheet or PDF cell, dates included.

    `sanitise` handles the injection concern for every type; this only adds a
    consistent, readable rendering for the temporal types the report producers
    hand back as native `date`/`datetime` objects rather than strings.
    """
    if isinstance(value, datetime):
        value = timezone.localtime(value) if timezone.is_aware(value) else value
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return sanitise(value)


def write_csv(
    columns: Iterable[dict[str, str]], rows: Iterable[dict[str, Any]]
) -> tuple[bytes, int]:
    """The same CSV `ReportExportView` streams, materialised as one blob.

    Reuses `stream_csv` line for line rather than re-implementing it, so a
    queued CSV export and an on-demand one can never disagree about what
    "safe" means for a cell.
    """
    row_count = 0

    def counted() -> Iterator[dict[str, Any]]:
        nonlocal row_count
        for row in rows:
            row_count += 1
            yield row

    content = "".join(stream_csv(columns, counted())).encode("utf-8")
    return content, row_count


def write_xlsx(
    columns: Iterable[dict[str, str]], rows: Iterable[dict[str, Any]]
) -> tuple[bytes, int]:
    """Excel, written in openpyxl's write-only mode.

    Write-only mode never builds a `Cell`/`Row` object graph for the sheet —
    each call to ``append`` streams a row straight into the underlying zip —
    so an export of the whole institution costs one row of memory while it is
    being written, the same property `stream_csv` has. The finished archive is
    still assembled in the buffer `save()` is given; that is the one place a
    whole file's bytes exist at once, by design (see the module docstring).
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    columns = list(columns)
    keys = [column["key"] for column in columns]

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title="Export")
    sheet.append([column["label"] for column in columns])
    # Metadata only; write-only mode still tracks dimensions and panes even
    # though it never materialises the cells they describe.
    sheet.freeze_panes = "A2"
    for index in range(len(columns)):
        sheet.column_dimensions[get_column_letter(index + 1)].width = 22

    row_count = 0
    for row in rows:
        sheet.append([_display(row.get(key)) for key in keys])
        row_count += 1

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), row_count


def _filters_line(filters: dict[str, Any]) -> str:
    """One human-readable line describing the scope a job was run with."""
    parts = []
    if filters.get("batch_label"):
        parts.append(f"Batch: {filters['batch_label']}")
    if filters.get("course_label"):
        parts.append(f"Course: {filters['course_label']}")
    return " · ".join(parts) if parts else "No batch or course filter."


def write_pdf(
    columns: Iterable[dict[str, str]],
    rows: Iterable[dict[str, Any]],
    *,
    title: str,
    filters: dict[str, Any],
) -> tuple[bytes, int]:
    """Landscape PDF with a repeating header row and page numbers.

    Raises `RowLimitExceeded` the moment the (`PDF_MAX_ROW_LIMIT` + 1)th row is
    reached, without draining whatever remains of `rows` — an oversized report
    is refused as soon as it is known to be oversized, not after the whole
    queryset has been walked for nothing.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    columns = list(columns)
    keys = [column["key"] for column in columns]
    header = [column["label"] for column in columns]

    data = [header]
    row_count = 0
    for row in rows:
        if row_count >= PDF_MAX_ROW_LIMIT:
            raise RowLimitExceeded(PDF_MAX_ROW_LIMIT)
        data.append([_display(row.get(key)) for key in keys])
        row_count += 1

    page_size = landscape(A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(_filters_line(filters), styles["Normal"]),
        Paragraph(
            f"Generated {timezone.localtime().strftime('%Y-%m-%d %H:%M')} · {row_count} rows",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)

    def _stamp(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(page_size[0] - 20, 15, f"Page {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        title=title,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
    )
    document.build(story, onFirstPage=_stamp, onLaterPages=_stamp)
    return buffer.getvalue(), row_count


def write(
    fmt: str,
    columns: Iterable[dict[str, str]],
    rows: Iterable[dict[str, Any]],
    *,
    title: str,
    filters: dict[str, Any],
) -> tuple[bytes, int]:
    """Dispatch to the writer for `fmt`. `fmt` is an `ExportFormat` value."""
    if fmt == "csv":
        return write_csv(columns, rows)
    if fmt == "xlsx":
        return write_xlsx(columns, rows)
    if fmt == "pdf":
        return write_pdf(columns, rows, title=title, filters=filters)
    raise ValueError(f"Unknown export format: {fmt!r}")
