"""Reading the SITP ACE workbooks.

One workbook is one batch: a college cohort taught over a summer. Each carries
the same five sheets, filled in by hand by whichever trainer had the batch, so
the shapes agree in spirit and disagree in detail — a column of emails in one,
none in the next; ``P``/``A`` here, ``PRESENT``/``ABSENT`` there; a date typed
as a date or as ``25-05-2026``. This module turns each workbook into one plain
structure and records everything it could not read, row by row, so the
importer never has to guess and the report never has to say "some rows".

Pure: reads a file, returns data, touches no model. That is what makes it
testable with a workbook built in memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import openpyxl

#: How the trainers wrote attendance. Anything else is reported, not guessed.
ATTENDANCE_VOCABULARY: dict[str, str | None] = {
    "P": "present",
    "PRESENT": "present",
    "OP": "present",  # "online present" — present, joined remotely
    "A": "absent",
    "ABSENT": "absent",
    "LT": "late",
    "L": "late",
    "LATE": "late",
    # No class for anybody that day. Not an absence.
    "SUNDAY": None,
    "SUN": None,
    "MONDAY": None,
    "HOLIDAY": None,
    "H": None,
    "": None,
}

#: Dates the spreadsheet cannot mean. One workbook has a run of 1900 columns
#: from a formula that lost its reference.
EARLIEST_PLAUSIBLE = date(2020, 1, 1)

_DDMMYYYY = re.compile(r"^\s*(\d{1,2})[-/._](\d{1,2})[-/._](\d{2}|\d{4})\s*$")
_DD_MON_YYYY = re.compile(r"^\s*(\d{1,2})[-/. ]+([A-Za-z]+)\.?[-/. ]+(\d{2}|\d{4})\s*$")
_MONTHS = {name.lower(): number for number, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_ASSESSMENT_HEADER = re.compile(
    r"^\s*assess?(?:e)?ment\s*(\d+)\s*(?:\((.*?)\))?\s*(?:out\s*of)?\s*(\d+(?:\.\d+)?)?\s*$",
    re.IGNORECASE,
)
_MARKS_HEADER = re.compile(r"^\s*(.+?)\s*\(\s*(\d+)\s*marks?\s*\)\s*$", re.IGNORECASE)
#: "25EACCE003": two digits of year, a college code, a serial.
_ROLL = re.compile(r"^\d{2}[A-Z]{3,7}\d{2,4}[A-Z]?$")
_FRACTION_MARK = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")
_ONLINE = re.compile(r"(?:onli[nb]e\D{0,3}(\d+))|(?:(\d+)\s*\(?\s*onli[nb]e)", re.IGNORECASE)
_OFFLINE = re.compile(r"(?:offline\D{0,3}(\d+))|(?:(\d+)\s*\(?\s*offline)", re.IGNORECASE)
_OUT_OF = re.compile(r"out\s*of\s*(\d+)", re.IGNORECASE)
_BARE_COUNT = re.compile(r"^\s*(\d+)\s*P?\s*$", re.IGNORECASE)
#: "12 / 0" under a heading that reads "Online Offline": the column's own order.
_PAIR = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
#: "10P + 2OP": ten present in the room, two present online.
_P_PLUS_OP = re.compile(r"^\s*(\d+)\s*P\s*\+\s*(\d+)\s*OP\s*$", re.IGNORECASE)


def parse_counts(raw: str) -> tuple[int | None, int | None, int | None, int | None]:
    """``(online, offline, present, roster)`` from a "Student Count" cell.

    Trainers wrote this a dozen ways — ``Online 5, Offline 0 | out of 11``,
    ``9 (ONLINE)``, ``0 Online``, ``10P``, or simply ``56``. A bare number is
    the number present with no record of how they joined; that is kept as a
    present count and the online/offline split is left unknown rather than
    invented.
    """
    text_value = (raw or "").strip()
    if not text_value or text_value.lower() in ("sunday", "holiday", "-", "na", "n/a"):
        return None, None, None, None
    pair = _PAIR.match(text_value)
    if pair:
        online, offline = int(pair.group(1)), int(pair.group(2))
        return online, offline, online + offline, None
    plus = _P_PLUS_OP.match(text_value)
    if plus:
        offline, online = int(plus.group(1)), int(plus.group(2))
        return online, offline, online + offline, None
    online = offline = None
    match = _ONLINE.search(text_value)
    if match:
        online = int(match.group(1) or match.group(2))
    match = _OFFLINE.search(text_value)
    if match:
        offline = int(match.group(1) or match.group(2))
    roster = int(_OUT_OF.search(text_value).group(1)) if _OUT_OF.search(text_value) else None
    if online is None and offline is None:
        bare = _BARE_COUNT.match(text_value)
        if bare:
            return None, None, int(bare.group(1)), roster
        return None, None, None, roster
    present = (online or 0) + (offline or 0)
    return online, offline, present, roster


@dataclass
class Problem:
    sheet: str
    row: int | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"sheet": self.sheet, "row": self.row, "reason": self.reason}


@dataclass
class Student:
    name: str
    roll_number: str
    email: str = ""
    row: int = 0


@dataclass
class DsrRow:
    row: int
    on: date
    topic: str
    trainer_name: str = ""
    online: int | None = None
    offline: int | None = None
    present: int | None = None
    roster_size: int | None = None
    assignment_given: bool | None = None


@dataclass
class AssessmentColumn:
    index: int
    title: str
    max_marks: Decimal | None
    column: int


@dataclass
class Workbook:
    path: Path
    batch_name: str
    year_label: str
    students: list[Student] = field(default_factory=list)
    class_dates: list[date] = field(default_factory=list)
    #: roll number → date → attendance status
    attendance: dict[str, dict[date, str]] = field(default_factory=dict)
    dsr: list[DsrRow] = field(default_factory=list)
    assessments: list[AssessmentColumn] = field(default_factory=list)
    #: roll number → assessment index → Decimal | "absent" | None
    marks: dict[str, dict[int, Decimal | str | None]] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)
    #: Sheets present but not imported, and why.
    not_imported: dict[str, str] = field(default_factory=dict)
    #: DSR rows that said "Sunday" or "Holiday": not classes, not reported.
    non_class_rows: int = 0

    def problem(self, sheet: str, row: int | None, reason: str) -> None:
        self.problems.append(Problem(sheet, row, reason))

    @property
    def programme_start(self) -> date:
        """The first-year cohort started in June 2026; the others in May."""
        return date(2026, 6, 1) if "1st" in self.year_label else date(2026, 5, 1)


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def as_date(value: Any) -> date | None:
    """A date cell, however it was typed. ``None`` when it is not one."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        match = _DDMMYYYY.match(value)
        if match:
            day, month, year = (int(part) for part in match.groups())
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None
        match = _DD_MON_YYYY.match(value)
        if match:
            day, month_name, year = int(match.group(1)), match.group(2).lower()[:3], int(match.group(3))
            if year < 100:
                year += 2000
            month = _MONTHS.get(month_name)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    return None
    return None


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _days_of_month(days: list[int], *, start: date) -> list[date]:
    """``[25, 26, …, 31, 1, 2, …]`` from ``start``'s month → real dates."""
    out: list[date] = []
    year, month = start.year, start.month
    previous = 0
    for day in days:
        if day < previous:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        previous = day
        try:
            out.append(date(year, month, day))
        except ValueError:
            out.append(out[-1] if out else start)
    return out


#: How far a report may sit from the first or last register and still be a
#: class of the same batch. Reports often start a day or two before the first
#: register, and finish a few days after the last.
WINDOW_SLACK = timedelta(days=10)


def _within_window(when: date, book: Workbook) -> tuple[date | None, bool]:
    """``(date, corrected)``: the date if it belongs to this batch's run.

    Trainers typed last year's year, or next year's, or ``0206``, into a
    handful of rows. A date whose month and day fall inside the batch's window
    once the year is set to the programme's is that date, and the correction
    is reported; a date that fits under no year is refused.
    """
    if not book.class_dates:
        return when, False
    start, end = min(book.class_dates) - WINDOW_SLACK, max(book.class_dates) + WINDOW_SLACK
    if start <= when <= end:
        return when, False
    candidates = []
    try:
        candidates.append(when.replace(year=book.programme_start.year))
    except ValueError:
        pass
    if when.day <= 12:
        # "12/07/2026" typed into a spreadsheet set to month-first became
        # 7 December. Swapping the two lands it in July, inside the window.
        for year in (when.year, book.programme_start.year):
            try:
                candidates.append(date(year, when.day, when.month))
            except ValueError:
                pass
    for candidate in candidates:
        if start <= candidate <= end:
            return candidate, True
    return None, False


def _rows(sheet) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in sheet.iter_rows(values_only=True)]


def _find_sheet(workbook, *prefixes: str):
    for name in workbook.sheetnames:
        lowered = name.strip().lower()
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return workbook[name]
    return None


def _header_index(header: tuple[Any, ...], *names: str) -> int | None:
    wanted = {name.lower() for name in names}
    for index, cell in enumerate(header):
        if text(cell).lower().rstrip(".") in wanted:
            return index
    return None


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------


def _read_attendance(sheet, book: Workbook) -> None:
    rows = _rows(sheet)
    if not rows:
        book.problem(sheet.title, None, "The sheet is empty.")
        return
    header_row = next(
        (i for i, row in enumerate(rows[:6]) if any("roll" in text(c).lower() for c in row)), 0
    )
    header = rows[header_row]
    name_col = _header_index(header, "student name", "name")
    roll_col = _header_index(header, "rtu roll no", "roll no", "roll number", "university roll no")
    email_col = _header_index(header, "student email", "email")
    if name_col is None or roll_col is None:
        book.problem(sheet.title, 1, "No 'Student Name' and 'RTU Roll No.' columns.")
        return

    # The row of dates sits under the header; each date column is one class.
    # The header row itself can carry a few month markers ("2026-05-01",
    # "2026-06-01") above the real dates, so the row with the *most* dates is
    # the one, not the first row with any.
    candidates = [(sum(isinstance(c, datetime) for c in row), i) for i, row in enumerate(rows[:6])]
    best_count, date_row_index = max(candidates, default=(0, None))
    if best_count < 3:
        date_row_index = None
    if date_row_index is None:
        book.problem(sheet.title, None, "No row of class dates found.")
        return
    date_columns: list[tuple[int, date]] = []
    typed = [(column, as_date(cell)) for column, cell in enumerate(rows[date_row_index])]
    typed = [(column, when) for column, when in typed if when is not None]
    day_numbers = [(column, when) for column, when in typed if when < EARLIEST_PLAUSIBLE]
    real = [(column, when) for column, when in typed if when >= EARLIEST_PLAUSIBLE]
    if day_numbers and len(day_numbers) < 5 and len(day_numbers) <= len(real):
        # One or two stray 1900 cells in a row of real dates are a broken
        # formula, not a run of day numbers. Ignore them and say so.
        for column, when in day_numbers:
            book.problem(sheet.title, date_row_index + 1, f"Column {column + 1} is dated {when}; ignored.")
        day_numbers = []
    if day_numbers:
        # "Dates" in 1900 are day numbers (25, 26, …) typed into cells that
        # Excel formatted as dates, and read as days since 1900. Read them as
        # days of the month instead, rolling the month over each time the
        # number drops, from the programme's first month. One sheet mixes
        # the two — day numbers for the first seven weeks, real dates after
        # — so both halves are kept. Reported, because it is a reconstruction
        # rather than a reading.
        decoded = _days_of_month([when.day for _, when in day_numbers], start=book.programme_start)
        reconstructed = [(column, when) for (column, _), when in zip(day_numbers, decoded)]
        book.problem(
            sheet.title,
            date_row_index + 1,
            f"{len(reconstructed)} class dates were typed as day numbers; read as "
            f"{reconstructed[0][1]} to {reconstructed[-1][1]}.",
        )
        date_columns.extend(reconstructed)
    date_columns.extend(real)
    book.class_dates = sorted({when for _, when in date_columns})

    seen_rolls: dict[str, int] = {}
    for offset, row in enumerate(rows[date_row_index + 1 :]):
        line = date_row_index + 2 + offset
        name = text(row[name_col]) if name_col < len(row) else ""
        roll = text(row[roll_col]).upper() if roll_col < len(row) else ""
        if not name and not roll:
            continue
        # The weekday row ("Wed", "Thu") and total rows have no serial number.
        if not isinstance(row[0], (int, float)) and not name:
            continue
        if not roll:
            book.problem(sheet.title, line, f"{name!r} has no roll number; skipped.")
            continue
        if roll in seen_rolls:
            book.problem(sheet.title, line, f"Roll number {roll} repeats line {seen_rolls[roll]}; skipped.")
            continue
        seen_rolls[roll] = line
        email = text(row[email_col]).lower() if email_col is not None and email_col < len(row) else ""
        book.students.append(Student(name=name, roll_number=roll, email=email, row=line))

        register: dict[date, str] = {}
        for column, when in date_columns:
            raw = text(row[column]).upper() if column < len(row) else ""
            if raw not in ATTENDANCE_VOCABULARY:
                book.problem(sheet.title, line, f"{raw!r} on {when} is not an attendance mark; skipped.")
                continue
            status = ATTENDANCE_VOCABULARY[raw]
            if status is not None:
                register[when] = status
        book.attendance[roll] = register

    # A column where nobody has a mark — a Sunday, a holiday, a day nobody
    # filled in — is not a class. Only dates with at least one mark remain.
    marked = {when for register in book.attendance.values() for when in register}
    unmarked = [when for when in book.class_dates if when not in marked]
    if unmarked:
        book.problem(
            sheet.title,
            date_row_index + 1,
            f"{len(unmarked)} dated columns have no marks for anybody (Sundays, holidays); no class created for them.",
        )
    book.class_dates = [when for when in book.class_dates if when in marked]


#: Topics that say the day was not a class at all.
NON_CLASS_TOPICS = frozenset({"sunday", "sun", "holiday", "holi", "no class", "off", "-"})


def _read_dsr(sheet, book: Workbook) -> None:
    rows = _rows(sheet)
    header_index = next(
        (i for i, row in enumerate(rows[:6]) if _header_index(row, "date") is not None), None
    )
    if header_index is None:
        book.problem(sheet.title, None, "No header row with a 'Date' column.")
        return
    header = rows[header_index]
    date_col = _header_index(header, "date")
    topic_col = _header_index(header, "topic cover", "topics covered today", "topic")
    module_col = _header_index(header, "module / topic name")
    counts_col = _header_index(header, "student count online offline")
    trainer_col = _header_index(header, "trainer name")
    assignment_col = _header_index(header, "assignment\ngiven", "assignment given")

    for offset, row in enumerate(rows[header_index + 1 :]):
        line = header_index + 2 + offset
        if not any(text(c) for c in row):
            continue
        topic = text(row[topic_col]) if topic_col is not None and topic_col < len(row) else ""
        if topic.strip().lower() in NON_CLASS_TOPICS:
            book.non_class_rows += 1
            continue
        when = as_date(row[date_col]) if date_col < len(row) else None
        if when is None:
            # A numbered row with nothing in it is the sheet's padding, not a
            # report. Only a row that says something and cannot be dated is
            # worth a line in the report.
            if topic or text(row[date_col] if date_col < len(row) else None):
                book.problem(sheet.title, line, f"{text(row[date_col])!r} is not a date; skipped.")
            continue
        when, corrected = _within_window(when, book)
        if when is None:
            book.problem(sheet.title, line, f"{text(row[date_col])!r} is outside the batch's dates; report skipped.")
            continue
        if corrected:
            book.problem(sheet.title, line, f"{text(row[date_col])!r} read as {when}: the year, or the month and day, were typed the wrong way round.")
        if module_col is not None and module_col < len(row) and text(row[module_col]):
            topic = f"{text(row[module_col])}: {topic}" if topic else text(row[module_col])
        entry = DsrRow(row=line, on=when, topic=topic[:255])
        if trainer_col is not None and trainer_col < len(row):
            entry.trainer_name = text(row[trainer_col])
        if counts_col is not None and counts_col < len(row):
            raw_counts = text(row[counts_col])
            entry.online, entry.offline, entry.present, entry.roster_size = parse_counts(raw_counts)
            if raw_counts and entry.present is None and entry.online is None and entry.offline is None:
                if raw_counts.lower() not in ("sunday", "holiday", "-", "na", "n/a"):
                    book.problem(sheet.title, line, f"Could not read counts from {raw_counts!r}.")
        if assignment_col is not None and assignment_col < len(row):
            given = text(row[assignment_col]).lower()
            entry.assignment_given = True if given == "yes" else False if given == "no" else None
        book.dsr.append(entry)


def _read_assessments(sheet, book: Workbook) -> None:
    rows = _rows(sheet)
    header_index = next(
        (i for i, row in enumerate(rows[:6]) if _header_index(row, "student name") is not None), None
    )
    if header_index is None:
        book.problem(sheet.title, None, "No header row with 'Student Name'.")
        return
    header = rows[header_index]
    roll_col = _header_index(header, "rtu roll no", "roll no", "roll number")
    if roll_col is None:
        book.problem(sheet.title, header_index + 1, "No roll number column; marks cannot be matched.")
        return

    for column, cell in enumerate(header):
        label = text(cell)
        if not label or column == roll_col:
            continue
        match = _ASSESSMENT_HEADER.match(label)
        if match:
            index = int(match.group(1))
            title = (match.group(2) or "").strip()
            maximum = as_decimal(match.group(3))
        else:
            marks = _MARKS_HEADER.match(label)
            if not marks:
                continue
            index = len(book.assessments) + 1
            title = marks.group(1).strip()
            maximum = as_decimal(marks.group(2))
        if not title or title.lower().startswith("topic") or title.lower().startswith("topics name"):
            title = f"Assessment {index}"
        if maximum is None:
            # The header says nothing, but every mark in the column may be
            # written "43/50" — then the column does say what it is out of.
            denominators = {
                _FRACTION_MARK.match(text(r[column])).group(2)
                for r in rows[header_index + 1 :]
                if column < len(r) and _FRACTION_MARK.match(text(r[column]))
            }
            if len(denominators) == 1:
                maximum = as_decimal(denominators.pop())
        if maximum is None:
            book.problem(
                sheet.title, header_index + 1, f"Column {column + 1} ({label[:40]!r}) has no maximum marks; skipped."
            )
            continue
        book.assessments.append(AssessmentColumn(index=index, title=title[:200], max_marks=maximum, column=column))

    name_col = _header_index(header, "student name", "name")
    known = {student.roll_number for student in book.students}
    for offset, raw_row in enumerate(rows[header_index + 1 :]):
        line = header_index + 2 + offset
        row = raw_row
        roll = text(row[roll_col]).upper() if roll_col < len(row) else ""
        shift = 0
        if roll and not _ROLL.match(roll) and roll_col + 1 < len(row) and _ROLL.match(text(row[roll_col + 1]).upper()):
            # The row slid one column left — the name sits where the roll
            # should be and the roll where the first mark should be. Read it
            # one column over rather than treating a name as a roll number.
            shift = 1
            roll = text(row[roll_col + 1]).upper()
        if not roll:
            continue
        name = text(row[(name_col if name_col is not None else roll_col) + shift]) if name_col is not None else ""
        if shift and not name:
            name = text(row[roll_col])
        if roll not in known:
            # On the marks sheet but not the attendance sheet: still a student
            # of this batch, so they join the roster — and it is said. A row
            # with no name at all is known by the roll number until somebody
            # fills it in.
            book.students.append(Student(name=name or f"Student {roll}", roll_number=roll, row=line))
            book.attendance.setdefault(roll, {})
            known.add(roll)
            book.problem(
                sheet.title,
                line,
                f"{roll} is on the marks sheet but not the attendance sheet; enrolled with no attendance"
                + ("" if name else " and no name") + ".",
            )
        marks: dict[int, Decimal | str | None] = {}
        for column_info in book.assessments:
            column = column_info.column + shift
            raw = row[column] if column < len(row) else None
            word = text(raw).upper()
            # "Pending" is a mark not yet given, which is the same fact as an
            # empty cell — not a mark of zero, and not an absence.
            if word in ("", "#N/A", "-", "NA", "N/A", "PENDING", "PENDING.", "LATE ADMISSION", "LATE JOIN"):
                marks[column_info.index] = None
            elif word in ("ABSENT", "AB", "A", "ABS"):
                marks[column_info.index] = "absent"
            else:
                fraction = _FRACTION_MARK.match(text(raw))
                value = as_decimal(fraction.group(1)) if fraction else as_decimal(raw)
                if value is None:
                    book.problem(sheet.title, line, f"{text(raw)!r} is not a mark for assessment {column_info.index}; skipped.")
                    marks[column_info.index] = None
                else:
                    marks[column_info.index] = value
        book.marks[roll] = marks


# ---------------------------------------------------------------------------
# The workbook
# ---------------------------------------------------------------------------


def read_workbook(path: Path) -> Workbook:
    """Everything the importer needs from one file, plus every cell it refused."""
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    parent = path.parent.name
    year = next((label for label in ("1st Year", "2nd Year", "3rd Year") if label in parent), "")
    book = Workbook(path=path, batch_name=path.stem.strip().rstrip("_").strip(), year_label=year)

    attendance = _find_sheet(workbook, "attend")
    if attendance is None:
        book.problem("Attendance", None, "No attendance sheet: without it there is no roster.")
    else:
        _read_attendance(attendance, book)

    dsr = _find_sheet(workbook, "dsr")
    if dsr is not None:
        _read_dsr(dsr, book)

    assessment = _find_sheet(workbook, "assess", "asses")
    if assessment is not None:
        _read_assessments(assessment, book)

    for name in workbook.sheetnames:
        lowered = name.strip().lower()
        if lowered.startswith("course time"):
            book.not_imported[name] = "Planned lecture list; the LMS plans per lesson, and there is no lesson content here to plan against."
        elif lowered.startswith("project"):
            book.not_imported[name] = "Project marks and links; the LMS records project work as reviewed submissions, which these are not."
        elif lowered.startswith("quiz"):
            book.not_imported[name] = "A Microsoft Forms export; the LMS has no importer for it."
    return book
