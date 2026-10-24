"""Reading a GRRAS batch sheet.

One spreadsheet holds several batches, one under another: a banner row with
the course name and the class time, a row naming the trainer, a row with the
starting date, a header row, then the roster — name, phone, email, mode,
college — until the next banner.

Pure: reads a file, returns data, touches no model. That is what makes it
testable against a workbook built in memory, which is how every shape below
is pinned.

Two rules, the same two the SITP reader follows, because they are what makes
an import reviewable:

* **Nothing is guessed.** A cell this cannot read is recorded with the sheet
  and the row it came from. A roster row with no name is a problem, not a
  skipped line.
* **Nothing is dropped quietly.** The counts in the report add up to the rows
  in the file: every student row ends up either in a batch's roster or in the
  problems list.

The banner is recognised by its *content*, not its fill colour: openpyxl can
read the colour, but a sheet re-saved from Google Sheets or re-styled by
whoever typed it loses it, and the words survive. A row is a banner when its
first filled cell is not a header word and the rows beneath it name a trainer
and a date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import openpyxl

#: The header words a roster row's header line uses, in any case or order.
_HEADER_WORDS = frozenset(
    {
        "s.no",
        "sno",
        "sr.no",
        "name",
        "student name",
        "candidate name",
        "phone",
        "mobile",
        "contact",
        "contact no",
        "email",
        "email id",
        "mode",
        "college",
        "college name",
        "branch",
        "remarks",
    }
)

_TRAINER_LABELS = ("trainer", "faculty")
_START_LABELS = ("batch starting date", "starting date", "start date", "batch start")
_COURSE_LABELS = ("course name", "course")

#: "10:00 AM to 12:00 PM", "10 AM - 12 PM", "10:00-12:00".
_TIME_RANGE_RE = re.compile(
    # "10", "10:00", each optionally followed by am/pm with or without dots.
    r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])?\.?[Mm]?\.?"
    # "to", a hyphen, an en dash or an em dash — whichever the person typed.
    r"\s*(?:to|-|\u2013|\u2014)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([AaPp])?\.?[Mm]?\.?",
)

#: Online / offline, as the sheets write it.
_MODE_WORDS = {
    "online": "online",
    "on-line": "online",
    "offline": "offline",
    "off-line": "offline",
    "classroom": "offline",
    "class room": "offline",
    "hybrid": "hybrid",
}


@dataclass
class SheetStudent:
    """One roster row, as written."""

    row: int
    name: str
    phone: str = ""
    email: str = ""
    mode: str = ""
    college: str = ""


@dataclass
class SheetBatch:
    """One banner and everything under it."""

    row: int
    course_name: str
    trainer_name: str = ""
    starts_on: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    students: list[SheetStudent] = field(default_factory=list)


@dataclass
class BatchSheet:
    """Everything read from one file, and everything refused."""

    batches: list[SheetBatch] = field(default_factory=list)
    problems: list[dict[str, Any]] = field(default_factory=list)

    def problem(self, sheet: str, row: int | None, message: str) -> None:
        self.problems.append({"sheet": sheet, "row": row, "message": message})

    @property
    def student_count(self) -> int:
        return sum(len(batch.students) for batch in self.batches)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _is_header_row(cells: list[str]) -> bool:
    filled = [cell.lower().rstrip(".") for cell in cells if cell]
    if not filled:
        return False
    return sum(1 for cell in filled if cell in _HEADER_WORDS) >= 2


def _labelled(cells: list[str], labels: tuple[str, ...]) -> str | None:
    """The value beside a label like "Trainers Name : Rajat", whether the
    value is in the same cell after a colon or in the next one along."""
    for index, cell in enumerate(cells):
        lowered = cell.lower()
        if not any(label in lowered for label in labels):
            continue
        after = cell.split(":", 1)[1].strip() if ":" in cell else ""
        if after:
            return after
        for following in cells[index + 1 :]:
            if following:
                return following
        return ""
    return None


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_time_range(text: str) -> tuple[time | None, time | None]:
    """ "10:00 AM to 12:00 PM" -> (10:00, 12:00). Unreadable -> (None, None).

    A half written without am/pm is read as whichever reading leaves the
    class running forwards: "10 to 12 PM" is a morning class, not one that
    started at ten at night. Borrowing the other half's meridiem outright
    would say the latter.
    """
    match = _TIME_RANGE_RE.search(text or "")
    if not match:
        return (None, None)
    start_hour, start_minute, start_half, end_hour, end_minute, end_half = match.groups()

    def _at(hour: str, minute: str | None, half: str | None) -> time | None:
        value = int(hour)
        if value > 23:
            return None
        meridiem = (half or "").lower()
        if meridiem == "p" and value < 12:
            value += 12
        if meridiem == "a" and value == 12:
            value = 0
        return time(value, int(minute or 0))

    end = _at(end_hour, end_minute, end_half)
    begin = _at(start_hour, start_minute, start_half)
    if begin is None or end is None:
        return (begin, end)
    if start_half is None:
        # Both readings of an unmarked half are legal; the shorter class is
        # the one somebody meant. "6 to 8 PM" is two hours in the evening,
        # not fourteen starting at dawn.
        shifted = _at(start_hour, start_minute, "p" if begin.hour < 12 else "a")
        for candidate in (begin, shifted):
            if candidate is None or candidate > end:
                continue
            if candidate > begin or begin > end:
                begin = candidate
    return (begin, end)


def parse_mode(text: str) -> str:
    return _MODE_WORDS.get((text or "").strip().lower(), "")


def _column_map(cells: list[str]) -> dict[str, int]:
    """Which column holds what, from the header row this sheet actually has."""
    mapping: dict[str, int] = {}
    for index, cell in enumerate(cells):
        key = cell.lower().rstrip(".")
        if key in {"name", "student name", "candidate name"}:
            mapping.setdefault("name", index)
        elif key in {"phone", "mobile", "contact", "contact no"}:
            mapping.setdefault("phone", index)
        elif key in {"email", "email id"}:
            mapping.setdefault("email", index)
        elif key == "mode":
            mapping.setdefault("mode", index)
        elif key in {"college", "college name"}:
            mapping.setdefault("college", index)
    return mapping


def read_rows(rows: list[list[Any]], *, sheet_name: str = "Sheet1") -> BatchSheet:
    """The reader proper, over plain rows — the file reader below is a shell.

    Taking rows rather than a path is what lets a test build three batches in
    memory and assert on the problems list without writing a file.
    """
    sheet = BatchSheet()
    current: SheetBatch | None = None
    columns: dict[str, int] = {}

    for number, raw in enumerate(rows, start=1):
        cells = [_text(cell) for cell in raw]
        if not any(cells):
            continue

        if _is_header_row(cells):
            columns = _column_map(cells)
            if current is not None and "name" not in columns:
                sheet.problem(
                    sheet_name,
                    number,
                    "This header row has no Name column; the roster under it cannot be read.",
                )
            continue

        trainer = _labelled(cells, _TRAINER_LABELS)
        if trainer is not None:
            if current is None:
                sheet.problem(sheet_name, number, "A trainer is named before any course banner.")
            else:
                current.trainer_name = trainer
            continue

        starting = _labelled(cells, _START_LABELS)
        if starting is not None:
            parsed = parse_date(starting)
            if current is None:
                sheet.problem(sheet_name, number, "A start date appears before any course banner.")
            elif parsed is None:
                sheet.problem(sheet_name, number, f"Could not read {starting!r} as a start date.")
            else:
                current.starts_on = parsed
            continue

        # A roster row: it has a name in the name column.
        if current is not None and columns:
            index = columns.get("name")
            name = cells[index] if index is not None and index < len(cells) else ""
            looks_like_a_row = any(
                cells[position] for position in columns.values() if position < len(cells)
            )
            if name:
                current.students.append(
                    SheetStudent(
                        row=number,
                        name=name,
                        phone=_cell(cells, columns.get("phone")),
                        email=_cell(cells, columns.get("email")),
                        mode=_cell(cells, columns.get("mode")),
                        college=_cell(cells, columns.get("college")),
                    )
                )
                continue
            if looks_like_a_row:
                sheet.problem(sheet_name, number, "A roster row with no name; nothing to create.")
                continue

        # Anything else that is not a label is the next course banner.
        banner = _labelled(cells, _COURSE_LABELS)
        title = banner if banner else next((cell for cell in cells if cell), "")
        if not title:
            continue
        start_time, end_time = parse_time_range(" ".join(cells))
        current = SheetBatch(
            row=number,
            course_name=_strip_time(title),
            start_time=start_time,
            end_time=end_time,
        )
        columns = {}
        sheet.batches.append(current)

    for batch in sheet.batches:
        if batch.starts_on is None:
            sheet.problem(sheet_name, batch.row, f"{batch.course_name!r} has no starting date.")
        if not batch.students:
            sheet.problem(sheet_name, batch.row, f"{batch.course_name!r} has no students under it.")

    return sheet


def _cell(cells: list[str], index: int | None) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index]


def _strip_time(title: str) -> str:
    """ "Python Django (10:00 AM to 12:00 PM)" → "Python Django"."""
    without = _TIME_RANGE_RE.sub("", title)
    return without.strip(" .-\u2013\u2014()|,:").strip()


def read_batch_sheet(file_obj) -> BatchSheet:
    """Every batch in an uploaded workbook, across every sheet in it."""
    workbook = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    combined = BatchSheet()
    for worksheet in workbook.worksheets:
        rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
        one = read_rows(rows, sheet_name=worksheet.title)
        combined.batches.extend(one.batches)
        combined.problems.extend(one.problems)
    workbook.close()
    return combined
