"""Trainer result import — §4.6.

The rule under test throughout: *never trust spreadsheet values blindly*, and
never let a bad file leave a class half-marked.
"""

from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.assessments.models import (
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ImportStatus,
    ResultImport,
    ResultSource,
)
from apps.audit.models import AuditAction, AuditLog


@pytest.fixture
def weekly_test(admin_user, batch):
    from apps.assessments.services import create_assessment, set_assessment_status

    created = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Week 1 test",
        delivery=AssessmentDelivery.EXTERNAL_LINK,
        external_url="https://forms.example.test/week1",
        scheduled_for=timezone.now() - timedelta(days=1),
        max_marks=Decimal("20.00"),
        passing_marks=Decimal("8.00"),
    )
    return set_assessment_status(
        assessment=created, actor=admin_user, status=AssessmentStatus.PUBLISHED
    )


def _csv(rows: list[list[str]], name: str = "results.csv") -> SimpleUploadedFile:
    body = "\n".join(",".join(cell for cell in row) for row in rows).encode("utf-8")
    return SimpleUploadedFile(name, body, content_type="text/csv")


def _xlsx(rows: list[list], name: str = "results.xlsx") -> SimpleUploadedFile:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _preview(client, assessment, upload):
    return client.post(
        f"/api/v1/assessments/{assessment.id}/imports/", {"file": upload}, format="multipart"
    )


@pytest.fixture
def cohort(enrollment, other_enrollment):
    """Two enrolled students, keyed by their public student id."""
    return {
        enrollment.student.student_id: enrollment,
        other_enrollment.student.student_id: other_enrollment,
    }


# ---------------------------------------------------------------------------
# The happy path is still two steps
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_preview_writes_no_results(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    """Step one is a dry run. That is the whole point of it."""
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    response = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [codes[0], "15"], [codes[1], "9"]]),
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == ImportStatus.PREVIEW
    assert body["report"]["summary"]["valid"] == 2
    assert body["report"]["summary"]["would_create"] == 2
    assert body["error_count"] == 0
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_confirming_applies_every_row(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    preview = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [codes[0], "15"], [codes[1], "9"]]),
    ).json()

    confirmed = api_client_no_csrf.post(
        f"/api/v1/results/imports/{preview['id']}/confirm/", format="json"
    )

    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["status"] == ImportStatus.CONFIRMED
    assert body["created_count"] == 2
    assert AssessmentResult.objects.count() == 2
    assert {str(row.marks_obtained) for row in AssessmentResult.objects.all()} == {
        "15.00",
        "9.00",
    }
    assert all(row.source == ResultSource.IMPORT for row in AssessmentResult.objects.all())


@pytest.mark.django_db
def test_an_xlsx_file_is_read_the_same_way(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    preview = _preview(
        api_client_no_csrf,
        weekly_test,
        _xlsx([["Student ID", "Marks", "Remarks"], [codes[0], 17, "Good"], [codes[1], 4, ""]]),
    ).json()

    assert preview["error_count"] == 0
    api_client_no_csrf.post(f"/api/v1/results/imports/{preview['id']}/confirm/", format="json")

    assert AssessmentResult.objects.count() == 2
    assert AssessmentResult.objects.filter(remarks="Good").exists()


@pytest.mark.django_db
def test_column_names_do_not_have_to_be_exact(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    """'Roll No' and 'Score' are what real trainer files say."""
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    response = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["Roll No", "Score"], [codes[0], "12"], [codes[1], "13"]]),
    )

    assert response.status_code == 201
    assert response.json()["report"]["summary"]["valid"] == 2


@pytest.mark.django_db
def test_re_importing_updates_rather_than_duplicates(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))

    for mark in ("10", "14"):
        preview = _preview(
            api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, mark]])
        ).json()
        api_client_no_csrf.post(f"/api/v1/results/imports/{preview['id']}/confirm/", format="json")

    assert AssessmentResult.objects.count() == 1
    assert AssessmentResult.objects.get().marks_obtained == Decimal("14.00")


# ---------------------------------------------------------------------------
# What the validator catches
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_unknown_student_is_reported_not_created(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    body = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [code, "10"], ["GRS-S-99999", "20"]]),
    ).json()

    problems = body["report"]["errors"]
    assert len(problems) == 1
    assert problems[0]["student_id"] == "GRS-S-99999"
    assert "cohort" in problems[0]["problem"]
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_a_duplicate_row_is_reported(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    body = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [code, "10"], [code, "20"]]),
    ).json()

    problems = body["report"]["errors"]
    assert len(problems) == 1
    assert "Duplicate of line 2" in problems[0]["problem"]


@pytest.mark.django_db
@pytest.mark.parametrize("value,fragment", [("abc", "not a number"), ("99", "outside")])
def test_an_invalid_mark_is_reported(
    api_client_no_csrf, trainer_profile, weekly_test, cohort, value, fragment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    body = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, value]])
    ).json()

    assert body["error_count"] == 1
    assert fragment in body["report"]["errors"][0]["problem"]


@pytest.mark.django_db
def test_a_formula_cell_is_refused(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    """A stored `=cmd|...` becomes an injection payload the next time this data
    is exported. It never gets stored."""
    api_client_no_csrf.force_login(trainer_profile.user)
    body = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], ['=cmd|"/c calc"!A1', "10"]]),
    ).json()

    assert body["error_count"] == 1
    assert "formula" in body["report"]["errors"][0]["problem"]


@pytest.mark.django_db
def test_an_absence_column_is_understood(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    preview = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks", "absent"], [codes[0], "12", "no"], [codes[1], "", "yes"]]),
    ).json()

    assert preview["error_count"] == 0
    api_client_no_csrf.post(f"/api/v1/results/imports/{preview['id']}/confirm/", format="json")

    absent = AssessmentResult.objects.get(is_absent=True)
    assert absent.marks_obtained is None
    assert absent.is_passing is False


@pytest.mark.django_db
def test_students_missing_from_the_file_are_listed(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    """Silence about a missing student is how a class ends up half-marked."""
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    body = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [codes[0], "10"]])
    ).json()

    assert body["report"]["summary"]["not_in_file"] == 1
    assert body["report"]["not_in_file"][0]["student_id"] == codes[1]


# ---------------------------------------------------------------------------
# Bad files
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_file_without_the_required_columns_is_refused(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _preview(api_client_no_csrf, weekly_test, _csv([["name", "grade"], ["Asha", "A"]]))

    assert response.status_code == 400
    assert "missing required column" in str(response.json())
    assert ResultImport.objects.count() == 0


@pytest.mark.django_db
def test_a_wrong_file_type_is_refused(api_client_no_csrf, trainer_profile, weekly_test):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _preview(
        api_client_no_csrf,
        weekly_test,
        SimpleUploadedFile("results.pdf", b"%PDF-1.4\n", content_type="application/pdf"),
    )

    assert response.status_code == 400
    assert ".csv or .xlsx" in str(response.json())


@pytest.mark.django_db
def test_a_header_with_no_rows_is_refused(api_client_no_csrf, trainer_profile, weekly_test):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _preview(api_client_no_csrf, weekly_test, _csv([["student_id", "marks"]]))

    assert response.status_code == 400
    assert "no result rows" in str(response.json())


@pytest.mark.django_db
def test_an_oversized_file_is_refused(api_client_no_csrf, trainer_profile, weekly_test):
    from apps.assessments.importers import MAX_IMPORT_BYTES

    api_client_no_csrf.force_login(trainer_profile.user)
    padding = b"x" * (MAX_IMPORT_BYTES + 1)
    response = _preview(
        api_client_no_csrf,
        weekly_test,
        SimpleUploadedFile("big.csv", padding, content_type="text/csv"),
    )

    assert response.status_code == 400
    assert "MB or smaller" in str(response.json())


@pytest.mark.django_db
def test_a_file_with_too_many_rows_is_refused(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    from apps.assessments.importers import MAX_IMPORT_ROWS

    api_client_no_csrf.force_login(trainer_profile.user)
    rows = [["student_id", "marks"]] + [[f"GRS-S-{i:05d}", "1"] for i in range(MAX_IMPORT_ROWS + 5)]
    response = _preview(api_client_no_csrf, weekly_test, _csv(rows))

    assert response.status_code == 400
    assert "more than" in str(response.json())


@pytest.mark.django_db
def test_a_binary_pretending_to_be_a_csv_is_refused(
    api_client_no_csrf, trainer_profile, weekly_test
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = _preview(
        api_client_no_csrf,
        weekly_test,
        SimpleUploadedFile("results.csv", b"\x00\x01\x02binary", content_type="text/csv"),
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Nothing is applied by halves
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_file_with_errors_cannot_be_confirmed(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    preview = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [codes[0], "10"], ["GRS-S-99999", "5"]]),
    ).json()

    response = api_client_no_csrf.post(
        f"/api/v1/results/imports/{preview['id']}/confirm/", format="json"
    )

    assert response.status_code == 409
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_a_cohort_change_between_preview_and_confirm_rolls_the_whole_thing_back(
    api_client_no_csrf, admin_user, trainer_profile, weekly_test, cohort, other_enrollment
):
    """The preview is a report, not a promise. Confirmation re-checks."""
    api_client_no_csrf.force_login(trainer_profile.user)
    codes = list(cohort)
    preview = _preview(
        api_client_no_csrf,
        weekly_test,
        _csv([["student_id", "marks"], [codes[0], "10"], [codes[1], "12"]]),
    ).json()

    from apps.enrollments.models import EnrollmentStatus
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=other_enrollment,
        target=EnrollmentStatus.CANCELLED,
        actor=admin_user,
        note="Withdrew.",
    )

    response = api_client_no_csrf.post(
        f"/api/v1/results/imports/{preview['id']}/confirm/", format="json"
    )

    assert response.status_code == 409
    # Not one row of a two-row file. All or nothing.
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_an_import_cannot_be_confirmed_twice(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    preview = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "10"]])
    ).json()
    url = f"/api/v1/results/imports/{preview['id']}/confirm/"

    assert api_client_no_csrf.post(url, format="json").status_code == 200
    assert api_client_no_csrf.post(url, format="json").status_code == 409
    assert AssessmentResult.objects.count() == 1


@pytest.mark.django_db
def test_a_preview_can_be_discarded(api_client_no_csrf, trainer_profile, weekly_test, cohort):
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    preview = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "10"]])
    ).json()

    rejected = api_client_no_csrf.post(
        f"/api/v1/results/imports/{preview['id']}/reject/", format="json"
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == ImportStatus.REJECTED
    assert (
        api_client_no_csrf.post(
            f"/api/v1/results/imports/{preview['id']}/confirm/", format="json"
        ).status_code
        == 409
    )


# ---------------------------------------------------------------------------
# Who may import, and what gets recorded about it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_another_trainer_cannot_import_into_this_assessment(
    api_client_no_csrf, trainer_profile_two, weekly_test, cohort
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    code = next(iter(cohort))
    response = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "20"]])
    )

    assert response.status_code == 404
    assert ResultImport.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_import_results(api_client_no_csrf, student_profile, weekly_test, cohort):
    api_client_no_csrf.force_login(student_profile.user)
    code = next(iter(cohort))
    response = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "20"]])
    )

    assert response.status_code == 404
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_read_somebody_elses_import_report(
    api_client_no_csrf, trainer_profile, student_profile, weekly_test, cohort
):
    """The report names every student in the cohort — it is staff data."""
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    preview = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "10"]])
    ).json()

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/results/imports/{preview['id']}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_every_import_leaves_an_audit_record(
    api_client_no_csrf, trainer_profile, weekly_test, cohort
):
    """§4.6 asks for an import audit record. It is the `ResultImport` row plus
    the audit entries either side of it."""
    api_client_no_csrf.force_login(trainer_profile.user)
    code = next(iter(cohort))
    preview = _preview(
        api_client_no_csrf, weekly_test, _csv([["student_id", "marks"], [code, "10"]])
    ).json()
    api_client_no_csrf.post(f"/api/v1/results/imports/{preview['id']}/confirm/", format="json")

    run = ResultImport.objects.get()
    assert run.checksum and len(run.checksum) == 64
    assert run.original_filename == "results.csv"
    assert run.uploaded_by_id == trainer_profile.user.pk

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.RESULT_IMPORT_PREVIEWED in actions
    assert AuditAction.RESULT_IMPORT_CONFIRMED in actions

    confirmed = AuditLog.objects.filter(action=AuditAction.RESULT_IMPORT_CONFIRMED).first()
    assert confirmed.context["created"] == 1
    assert confirmed.context["checksum"] == run.checksum
