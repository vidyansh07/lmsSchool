"""Importing the batch sheet a centre already keeps.

One spreadsheet holds several batches, one under another: a banner with the
course name and the class time, the trainer, the starting date, a header
row, then the roster. This suite pins the two halves separately — the reader,
which refuses to guess, and the import, which refuses to write anything the
services would not accept.

The rules each half is held to:

* nothing is guessed: an unreadable date, a nameless roster row and a course
  the catalogue does not have are each a problem with the row it came from;
* nothing is dropped quietly: every roster row ends up in a batch or in the
  problems list;
* a re-run of a corrected sheet adds what was added and duplicates nothing;
* a dry run is the real run, rolled back — so its report is the report the
  import would print.
"""

from __future__ import annotations

from datetime import date, time
from io import BytesIO

import openpyxl
import pytest

from apps.batches.importing import PLACEHOLDER_DOMAIN, import_batch_sheet
from apps.batches.models import Batch
from apps.batches.sheets import parse_time_range, read_batch_sheet, read_rows
from apps.common.exceptions import AuthorityError
from apps.enrollments.models import Enrollment
from apps.students.models import StudentProfile

pytestmark = pytest.mark.django_db


def _rows(course_title: str = "Linux Essentials", *, starts: str = "01-11-2026") -> list[list]:
    return [
        [f"{course_title} (10:00 AM to 12:00 PM)", None, None],
        ["Trainers Name : Rajat Goyal", None, None],
        [f"Batch Starting Date : {starts}", None, None],
        ["S.No", "Name", "Phone", "Email", "Mode", "College"],
        [1, "Himanshu Verma", "7073060025", "himanshu@example.test", "Offline", "Arya College"],
        [2, "Asha Rao", "9876543210", "", "Online", "JECRC"],
    ]


def _workbook(rows: list[list]) -> BytesIO:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Batches"
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def test_a_banner_its_trainer_its_date_and_its_roster():
    sheet = read_rows(_rows())

    assert len(sheet.batches) == 1
    batch = sheet.batches[0]
    assert batch.course_name == "Linux Essentials"
    assert batch.trainer_name == "Rajat Goyal"
    assert batch.starts_on == date(2026, 11, 1)
    assert (batch.start_time, batch.end_time) == (time(10, 0), time(12, 0))
    assert [student.name for student in batch.students] == ["Himanshu Verma", "Asha Rao"]
    assert sheet.problems == []


def test_several_batches_one_under_another():
    rows = _rows("Linux Essentials") + _rows("Python Django", starts="15-11-2026")
    sheet = read_rows(rows)

    assert [batch.course_name for batch in sheet.batches] == ["Linux Essentials", "Python Django"]
    assert [len(batch.students) for batch in sheet.batches] == [2, 2]


def test_an_unreadable_date_is_a_problem_with_its_row():
    rows = _rows(starts="whenever")
    sheet = read_rows(rows)

    assert sheet.batches[0].starts_on is None
    assert any("whenever" in problem["message"] for problem in sheet.problems)
    # And the row it came from, so somebody can go and fix that cell.
    assert any(problem["row"] == 3 for problem in sheet.problems)


def test_a_roster_row_with_no_name_is_reported_rather_than_skipped():
    rows = _rows()
    rows.append([3, "", "9000000000", "", "Online", ""])
    sheet = read_rows(rows)

    assert len(sheet.batches[0].students) == 2
    assert any("no name" in problem["message"] for problem in sheet.problems)


def test_a_batch_with_nobody_under_it_says_so():
    sheet = read_rows(_rows()[:4])
    assert any("no students" in problem["message"] for problem in sheet.problems)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10:00 AM to 12:00 PM", (time(10, 0), time(12, 0))),
        ("10 AM - 12 PM", (time(10, 0), time(12, 0))),
        ("2:30 PM to 4:30 PM", (time(14, 30), time(16, 30))),
        # No meridiem on the first half: it takes the second's.
        ("10 to 12 PM", (time(10, 0), time(12, 0))),
        # Both readings are legal; the shorter class is the one meant.
        ("6 to 8 PM", (time(18, 0), time(20, 0))),
        ("sometime", (None, None)),
    ],
)
def test_the_class_time_as_people_write_it(text, expected):
    assert parse_time_range(text) == expected


def test_a_real_file_reads_the_same_as_rows():
    sheet = read_batch_sheet(_workbook(_rows()))
    assert len(sheet.batches) == 1
    assert sheet.batches[0].trainer_name == "Rajat Goyal"


# ---------------------------------------------------------------------------
# The import
# ---------------------------------------------------------------------------


def test_an_import_opens_the_batch_and_enrols_its_roster(admin_user, published_course):
    sheet = read_rows(_rows(published_course.title))

    report = import_batch_sheet(actor=admin_user, sheet=sheet, dry_run=False)

    assert report.batches_created == 1
    assert report.students_created == 2
    assert report.enrolments_created == 2
    batch = Batch.objects.get(course=published_course, start_date=date(2026, 11, 1))
    assert batch.enrollments.count() == 2
    # The sheet says the mode per student; a mixed roster is hybrid, which is
    # a real answer rather than a tie-break.
    assert batch.delivery_mode == "hybrid"


def test_somebody_with_no_address_gets_one_that_cannot_receive_mail(admin_user, published_course):
    sheet = read_rows(_rows(published_course.title))
    import_batch_sheet(actor=admin_user, sheet=sheet, dry_run=False)

    asha = StudentProfile.objects.get(user__first_name="Asha")
    assert asha.user.email.endswith(f"@{PLACEHOLDER_DOMAIN}")
    assert "9876543210" in asha.user.email


def test_a_course_the_catalogue_does_not_have_is_a_problem_not_a_new_course(admin_user):
    from apps.courses.models import Course

    sheet = read_rows(_rows("Phyton Djano"))
    before = Course.objects.count()

    report = import_batch_sheet(actor=admin_user, sheet=sheet, dry_run=False)

    assert Course.objects.count() == before
    assert report.batches_created == 0
    assert any("No course in the catalogue" in problem["message"] for problem in report.problems)


def test_re_importing_a_corrected_sheet_duplicates_nothing(admin_user, published_course):
    rows = _rows(published_course.title)
    import_batch_sheet(actor=admin_user, sheet=read_rows(rows), dry_run=False)

    rows.append([3, "Nikhil Jain", "9000000001", "nikhil@example.test", "Offline", "Arya College"])
    report = import_batch_sheet(actor=admin_user, sheet=read_rows(rows), dry_run=False)

    assert report.batches_matched == 1
    assert report.batches_created == 0
    assert report.students_created == 1
    assert report.enrolments_existing == 2
    assert Batch.objects.filter(course=published_course).count() == 1
    assert Enrollment.objects.filter(batch__course=published_course).count() == 3


def test_a_student_already_on_the_system_is_matched_by_email(
    admin_user, published_course, student_profile
):
    rows = _rows(published_course.title)
    rows[4][3] = student_profile.user.email
    sheet = read_rows(rows)

    report = import_batch_sheet(actor=admin_user, sheet=sheet, dry_run=False)

    assert report.students_matched == 1
    assert report.students_created == 1


def test_a_dry_run_reports_what_it_would_do_and_writes_nothing(admin_user, published_course):
    sheet = read_rows(_rows(published_course.title))
    before = (Batch.objects.count(), StudentProfile.objects.count())

    report = import_batch_sheet(actor=admin_user, sheet=sheet, dry_run=True)

    assert report.batches_created == 1
    assert report.students_created == 2
    assert (Batch.objects.count(), StudentProfile.objects.count()) == before


def test_importing_needs_both_rights_it_uses(trainer, published_course):
    sheet = read_rows(_rows(published_course.title))
    with pytest.raises(AuthorityError):
        import_batch_sheet(actor=trainer, sheet=sheet, dry_run=True)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_previews_by_default(api_client_no_csrf, admin_user, published_course):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(admin_user)
    upload = SimpleUploadedFile(
        "batches.xlsx",
        _workbook(_rows(published_course.title)).read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response = api_client_no_csrf.post(
        "/api/v1/batches/import/", {"file": upload}, format="multipart"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["batches_created"] == 1
    assert body["students_created"] == 2
    # Previewed, not written: the default is deliberate.
    assert Batch.objects.filter(course=published_course).count() == 0


def test_the_endpoint_writes_when_asked(api_client_no_csrf, admin_user, published_course):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(admin_user)
    upload = SimpleUploadedFile(
        "batches.xlsx",
        _workbook(_rows(published_course.title)).read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response = api_client_no_csrf.post(
        "/api/v1/batches/import/", {"file": upload, "dry_run": "false"}, format="multipart"
    )

    assert response.status_code == 200, response.content
    assert Batch.objects.filter(course=published_course).count() == 1


def test_a_file_that_is_not_a_spreadsheet_is_refused_without_echoing_it(
    api_client_no_csrf, admin_user
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(admin_user)
    upload = SimpleUploadedFile(
        "roster.xlsx", b"not a spreadsheet at all", content_type="text/plain"
    )

    response = api_client_no_csrf.post(
        "/api/v1/batches/import/", {"file": upload}, format="multipart"
    )

    assert response.status_code == 400
    assert "not a spreadsheet" not in response.content.decode()


def test_a_csv_is_refused_by_name(api_client_no_csrf, admin_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(admin_user)
    upload = SimpleUploadedFile("roster.csv", b"name,phone\n", content_type="text/csv")

    response = api_client_no_csrf.post(
        "/api/v1/batches/import/", {"file": upload}, format="multipart"
    )
    assert response.status_code == 400
    assert ".xlsx" in response.content.decode()


def test_a_trainer_cannot_import(api_client_no_csrf, trainer):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(trainer)
    upload = SimpleUploadedFile(
        "batches.xlsx",
        _workbook(_rows()).read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    response = api_client_no_csrf.post(
        "/api/v1/batches/import/", {"file": upload}, format="multipart"
    )
    assert response.status_code == 403
