"""Reading the SITP ACE workbooks.

The sheets were filled in by hand by a dozen trainers, so the reader's job is
less to parse a format than to survive its variations without ever guessing:
``P``/``A`` and ``PRESENT``/``ABSENT``, dates typed as dates or as
``25-05-2026``, a roll number where the email should be. Every cell it cannot
read is reported with its row, which is what lets the import say exactly what
it left out.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest

from apps.reporting.sitp import as_date, read_workbook


def build_workbook(path, *, with_email=True, dsr_style="classic"):
    wb = openpyxl.Workbook()
    att = wb.active
    att.title = "Attendance"
    head = ["S NO"] + (["Student Email"] if with_email else []) + [
        "Student Name", "RTU Roll No.", "Total Present", "Total Absent", "Total Class", "Attendance Percent",
    ]
    dates = [datetime(2026, 6, 10), datetime(2026, 6, 11), datetime(2026, 6, 14), datetime(1900, 1, 25)]
    att.append(head + [dates[0]])
    att.append([None] * len(head) + dates)
    att.append([None] * len(head) + ["Wed", "Thu", "Sun", "?"])
    base = [1] + (["arjit@example.test"] if with_email else []) + ["Arjit Kaushik", "25EACEE003", 2, 1, 3, 66.6]
    att.append(base + ["P", "A", "SUNDAY", "P"])
    base2 = [2] + ([""] if with_email else []) + ["Somya Gupta", "25eacce026", 1, 0, 1, 100]
    att.append(base2 + ["OP", "LT", None, None])
    base3 = [3] + ([""] if with_email else []) + ["No Roll", "", 0, 0, 0, 0]
    att.append(base3 + ["P", "P", None, None])
    base4 = [4] + ([""] if with_email else []) + ["Odd Mark", "25EACCE099", 0, 0, 0, 0]
    att.append(base4 + ["P", "X", None, None])

    dsr = wb.create_sheet("DSR")
    if dsr_style == "classic":
        dsr.append(["SNO", "Date", "Topic Cover", "Student Count Online Offline", "Trainer Name"])
        dsr.append([1, datetime(2026, 6, 10), "INTRO", "Online 5, Offline 0 | out of 11", "Kapil Jangid"])
        dsr.append([2, "11-06-2026", "VARIABLES", "Online 9, Offline 1", "Kapil Jangid"])
        dsr.append([3, "not a date", "LOST", "", "Kapil Jangid"])
    else:
        dsr.append(["DAILY STATUS REPORT | SITP 2026"])
        dsr.append(["Day #", "Date", "Module / Topic Name", "Topics Covered Today", "Assignment\nGiven"])
        dsr.append([1, "10-06-2026", "Cloud Intro", "Deployment types", "No"])
        dsr.append([2, datetime(2026, 6, 11), "AWS Intro", "Account creation", "Yes"])

    marks = wb.create_sheet("Assessment")
    marks.append([None, None, None, 1, 2, 3])
    marks.append([
        "S NO", "Student Name", "RTU Roll No.",
        "Assesment 1 (Intro to python) Out of 30",
        "Assesment 2 (Topics Name ) Out of ",
        "HTML(20 marks)",
    ])
    marks.append([1, "Arjit Kaushik", "25EACEE003", 25, 10, "Absent"])
    marks.append([2, "Somya Gupta", "25EACCE026", "#N/A", None, "ninety"])

    wb.create_sheet("Course Timeline").append(["Lecture No.", "BLOWN UP TOPICS", "Status"])
    wb.create_sheet("Project").append(["S NO", "Student Name", "RTU Roll No.", "PROJECT 1 () Out of"])
    wb.save(path)
    return path


@pytest.fixture
def classic(tmp_path):
    folder = tmp_path / "SITP ACE 2026 1st Year"
    folder.mkdir()
    return read_workbook(build_workbook(folder / "Group A.xlsx"))


def test_the_batch_is_named_from_the_file_and_folder(classic):
    assert classic.batch_name == "Group A"
    assert classic.year_label == "1st Year"


def test_students_come_from_the_attendance_sheet_with_upper_case_roll_numbers(classic):
    rolls = [student.roll_number for student in classic.students]
    assert rolls == ["25EACEE003", "25EACCE026", "25EACCE099"]
    assert classic.students[0].email == "arjit@example.test"
    assert classic.students[1].email == ""


def test_a_student_without_a_roll_number_is_reported_not_guessed(classic):
    reasons = [p.reason for p in classic.problems]
    assert any("'No Roll' has no roll number" in reason for reason in reasons)


def test_the_attendance_vocabulary_is_normalised_and_non_days_are_skipped(classic):
    register = classic.attendance["25EACEE003"]
    assert register == {date(2026, 6, 10): "present", date(2026, 6, 11): "absent"}
    second = classic.attendance["25EACCE026"]
    assert second == {date(2026, 6, 10): "present", date(2026, 6, 11): "late"}


def test_an_unknown_mark_is_reported_with_its_row(classic):
    assert any("'X' on 2026-06-11 is not an attendance mark" in p.reason for p in classic.problems)
    assert date(2026, 6, 11) not in classic.attendance["25EACCE099"]


def test_an_impossible_date_column_is_ignored_and_reported(classic):
    assert date(1900, 1, 25) not in classic.class_dates
    # June 14 was a Sunday for everybody, so it is not a class either.
    assert classic.class_dates == [date(2026, 6, 10), date(2026, 6, 11)]
    assert any("dated 1900-01-25" in p.reason for p in classic.problems)


def test_dsr_rows_read_either_date_style_and_the_counts(classic):
    assert [(row.on, row.online, row.offline, row.roster_size) for row in classic.dsr] == [
        (date(2026, 6, 10), 5, 0, 11),
        (date(2026, 6, 11), 9, 1, None),
    ]
    assert classic.dsr[0].trainer_name == "Kapil Jangid"
    assert any("'not a date' is not a date" in p.reason for p in classic.problems)


def test_the_other_dsr_layout_is_read_too(tmp_path):
    folder = tmp_path / "SITP ACE 2026 3rd Year"
    folder.mkdir()
    book = read_workbook(build_workbook(folder / "AWS.xlsx", with_email=False, dsr_style="modern"))
    assert [(row.on, row.topic, row.assignment_given) for row in book.dsr] == [
        (date(2026, 6, 10), "Cloud Intro: Deployment types", False),
        (date(2026, 6, 11), "AWS Intro: Account creation", True),
    ]
    assert book.students[0].email == ""


def test_assessment_columns_need_a_maximum_to_exist(classic):
    titles = [(a.index, a.title, a.max_marks) for a in classic.assessments]
    assert titles == [(1, "Intro to python", Decimal("30")), (2, "HTML", Decimal("20"))]
    assert any("has no maximum marks" in p.reason for p in classic.problems)


def test_marks_absent_blank_and_nonsense_are_told_apart(classic):
    assert classic.marks["25EACEE003"] == {1: Decimal("25"), 2: "absent"}
    assert classic.marks["25EACCE026"] == {1: None, 2: None}
    assert any("'ninety' is not a mark" in p.reason for p in classic.problems)


def test_sheets_the_lms_cannot_hold_are_named_with_a_reason(classic):
    assert set(classic.not_imported) == {"Course Timeline", "Project"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (datetime(2026, 5, 25, 10), date(2026, 5, 25)),
        ("25-05-2026", date(2026, 5, 25)),
        ("25/05/2026", date(2026, 5, 25)),
        ("31-02-2026", None),
        ("May 25", None),
        (None, None),
    ],
)
def test_as_date(raw, expected):
    assert as_date(raw) == expected


# ---------------------------------------------------------------------------
# The formats the trainers actually used, found by dry-running all sixteen
# ---------------------------------------------------------------------------

from apps.reporting.sitp import parse_counts  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Online 5, Offline 0 | out of 11", (5, 0, 5, 11)),
        ("0 Online, 0 Offline", (0, 0, 0, None)),
        ("9 (ONLINE)", (9, None, 9, None)),
        ("0 Online", (0, None, 0, None)),
        ("Online 24", (24, None, 24, None)),
        ("56", (None, None, 56, None)),
        ("10P", (None, None, 10, None)),
        ("sunday", (None, None, None, None)),
        ("", (None, None, None, None)),
    ],
)
def test_parse_counts_reads_every_spelling_and_keeps_a_head_count_honest(raw, expected):
    # A bare number is a head count with no online/offline split — kept as
    # present, never split by guesswork.
    assert parse_counts(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("13-07-26", date(2026, 7, 13)),
        ("15-7-26", date(2026, 7, 15)),
        ("14_07_2026", date(2026, 7, 14)),
        ("16/June./2026", date(2026, 6, 16)),
        ("#VALUE!", None),
    ],
)
def test_as_date_reads_the_hand_typed_variants(raw, expected):
    assert as_date(raw) == expected


def build_fraction_workbook(path):
    wb = openpyxl.Workbook()
    att = wb.active
    att.title = "Attendence"
    head = ["S NO", "Student Name", "RTU Roll No.", "Total Present", "Total Absent", "Total Class", "Attendance Percent"]
    # Month markers in the header row, the real dates beneath — and typed as
    # day numbers, which Excel stored as dates in 1900.
    att.append(head + [datetime(2026, 5, 1), None, None, datetime(2026, 6, 1)])
    att.append([None] * len(head) + [datetime(1900, 1, 30), datetime(1900, 1, 31), datetime(1900, 1, 1), datetime(1900, 1, 2)])
    att.append([None] * len(head) + ["Sat", "Sun", "Mon", "Tue"])
    att.append([1, "Ruchi Raj", "24EACCS668", 3, 0, 3, 100, "p", "SUNDAY", "P", "a"])

    marks = wb.create_sheet("Assesment")
    marks.append([None, None, None, 1, 2])
    marks.append(["S NO", "Student Name", "RTU Roll No.", "Assesment 1 (Networking) 50", "Assessment 2 (All AWS Services)"])
    marks.append([1, "Ruchi Raj", "24EACCS668", "43/50", "29 / 30"])
    marks.append([2, "Only In Marks", "24EACAD002", "Absent", "30/30"])

    dsr = wb.create_sheet("DSR")
    dsr.append(["SNO", "Date", "Topic Cover", "Student Count Online Offline", "Trainer Name"])
    dsr.append([1, datetime(2026, 5, 30), "INTRO", "56", "Mohit"])
    wb.save(path)
    return path


@pytest.fixture
def fraction_book(tmp_path):
    folder = tmp_path / "SITP ACE 2026 3rd Year"
    folder.mkdir()
    return read_workbook(build_fraction_workbook(folder / "AWS ML Engineer.xlsx"))


def test_day_numbers_typed_as_dates_are_read_as_days_of_the_programme_month(fraction_book):
    # 30, 31, 1, 2 from a May start: 30 May, 31 May, 1 June, 2 June.
    assert fraction_book.class_dates == [date(2026, 5, 30), date(2026, 6, 1), date(2026, 6, 2)]
    assert any("typed as day numbers" in p.reason for p in fraction_book.problems)
    assert fraction_book.attendance["24EACCS668"] == {
        date(2026, 5, 30): "present", date(2026, 6, 1): "present", date(2026, 6, 2): "absent"
    }


def test_the_header_row_is_found_below_the_month_markers(fraction_book):
    assert [s.roll_number for s in fraction_book.students][0] == "24EACCS668"


def test_marks_written_as_a_fraction_carry_their_own_maximum(fraction_book):
    columns = {a.index: (a.title, a.max_marks) for a in fraction_book.assessments}
    assert columns == {1: ("Networking", Decimal("50")), 2: ("All AWS Services", Decimal("30"))}
    assert fraction_book.marks["24EACCS668"] == {1: Decimal("43"), 2: Decimal("29")}


def test_a_student_only_on_the_marks_sheet_joins_the_roster_and_is_reported(fraction_book):
    rolls = [s.roll_number for s in fraction_book.students]
    assert rolls == ["24EACCS668", "24EACAD002"]
    assert fraction_book.attendance["24EACAD002"] == {}
    assert fraction_book.marks["24EACAD002"] == {1: "absent", 2: Decimal("30")}
    assert any("on the marks sheet but not the attendance sheet" in p.reason for p in fraction_book.problems)


def test_a_bare_head_count_in_the_dsr_is_kept_as_present_only(fraction_book):
    row = fraction_book.dsr[0]
    assert (row.online, row.offline, row.present) == (None, None, 56)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12 / 0", (12, 0, 12, None)),
        ("10P + 2OP", (2, 10, 12, None)),
        ("86 onlibe", (86, None, 86, None)),
    ],
)
def test_parse_counts_reads_the_last_three_spellings(raw, expected):
    assert parse_counts(raw) == expected


def test_a_marks_row_that_slid_one_column_left_is_read_one_column_over(tmp_path):
    folder = tmp_path / "SITP ACE 2026 1st Year"
    folder.mkdir()
    wb = openpyxl.Workbook()
    att = wb.active
    att.title = "Attendance"
    att.append(["S NO", "Student Email", "Student Name", "RTU Roll No.", "Total Present", "Total Absent", "Total Class", "Attendance Percent", datetime(2026, 6, 10)])
    att.append([None] * 8 + [datetime(2026, 6, 10), datetime(2026, 6, 11), datetime(2026, 6, 12)])
    att.append([None] * 8 + ["Wed", "Thu", "Fri"])
    att.append([1, "", "Harshit", "25EACCC020", 1, 0, 1, 100, "P", "P", "P"])
    marks = wb.create_sheet("Assessment")
    marks.append(["S NO", "Student Name", "RTU Roll No.", "Assesment 1 (Loops) Out of 30", "Assesment 2 (Sets) Out of 30"])
    # The row slid one cell to the right: the name sits under "RTU Roll No."
    # and the roll number under the first assessment.
    marks.append([1, "", "Harshit", "25EACCC020", "Absent", "29 / 30"])
    marks.append([2, "Late Joiner", "25EACCS119", "Late Admission", 20])
    wb.save(folder / "Group B.xlsx")

    book = read_workbook(folder / "Group B.xlsx")

    assert book.marks["25EACCC020"] == {1: "absent", 2: Decimal("29")}
    # Joined after the first test: no mark, not an absence.
    assert book.marks["25EACCS119"] == {1: None, 2: Decimal("20")}
    assert any("25EACCS119 is on the marks sheet but not the attendance sheet" in p.reason for p in book.problems)


def build_window_workbook(path):
    wb = openpyxl.Workbook()
    att = wb.active
    att.title = "Attendance"
    head = ["S NO", "Student Email", "Student Name", "RTU Roll No.", "Total Present", "Total Absent", "Total Class", "Attendance Percent"]
    att.append(head + [datetime(2026, 6, 1)])
    att.append([None] * len(head) + [datetime(2026, 6, 10), datetime(2026, 6, 11), datetime(2026, 6, 14), datetime(2026, 6, 15)])
    att.append([None] * len(head) + ["Wed", "Thu", "Sun", "Mon"])
    att.append([1, "", "Arjit Kaushik", "25EACEE003", 2, 1, 3, 66.6, "P", "A", "SUNDAY", "P"])
    dsr = wb.create_sheet("DSR")
    dsr.append(["SNO", "Date", "Topic Cover", "Student Count Online Offline", "Trainer Name"])
    dsr.append([1, datetime(2026, 6, 10), "INTRO", "Online 1, Offline 0", "Kapil Jangid"])
    dsr.append([2, datetime(2025, 6, 11), "VARIABLES", "Online 1, Offline 0", "Kapil Jangid"])   # last year's year
    dsr.append([3, datetime(2026, 6, 14), "SUNDAY", "", "Kapil Jangid"])                         # not a class
    dsr.append([4, datetime(2028, 5, 27), "FAR AWAY", "Online 1, Offline 0", "Kapil Jangid"])   # fits no year
    dsr.append([5, datetime(2026, 6, 16), "WRAP-UP", "Online 1, Offline 0", "Kapil Jangid"])    # just after the last register
    wb.save(path)
    return path


@pytest.fixture
def window_book(tmp_path):
    folder = tmp_path / "SITP ACE 2026 1st Year"
    folder.mkdir()
    return read_workbook(build_window_workbook(folder / "Group A.xlsx"))


def test_a_dated_column_with_no_marks_for_anybody_is_not_a_class(window_book):
    # June 14 was a Sunday for everyone; June 10, 11 and 15 had marks.
    assert window_book.class_dates == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 15)]
    assert any("no marks for anybody" in p.reason for p in window_book.problems)


def test_a_report_dated_with_the_wrong_year_is_read_as_this_years_date_and_reported(window_book):
    dates = {row.topic: row.on for row in window_book.dsr}
    assert dates["VARIABLES"] == date(2026, 6, 11)
    assert any("typed the wrong way round" in p.reason for p in window_book.problems)


def test_a_report_that_fits_no_year_is_refused(window_book):
    assert "FAR AWAY" not in {row.topic for row in window_book.dsr}
    assert any("outside the batch's dates" in p.reason for p in window_book.problems)


def test_a_sunday_row_is_not_a_report(window_book):
    assert "SUNDAY" not in {row.topic for row in window_book.dsr}
    assert window_book.non_class_rows == 1


def test_a_report_a_day_or_two_after_the_last_register_still_belongs(window_book):
    assert date(2026, 6, 16) in {row.on for row in window_book.dsr}



def test_a_report_with_month_and_day_swapped_is_read_the_right_way_round(tmp_path):
    folder = tmp_path / "SITP ACE 2026 3rd Year"
    folder.mkdir()
    path = build_window_workbook(folder / "SOC.xlsx")
    wb = openpyxl.load_workbook(path)
    # 12 June typed month-first became 6 December.
    wb["DSR"].append([6, datetime(2026, 12, 6), "SIEM", "Online 1, Offline 0", "Sachin"])
    wb.save(path)

    book = read_workbook(path)

    assert {row.topic: row.on for row in book.dsr}["SIEM"] == date(2026, 6, 12)
