"""Reports, analytics, dashboards and bulk data tools — §8.3 to §8.7.

§8.7 asks specifically for report authorization, filters, exports, import
failures, large datasets and dashboard query performance, and each has a test
below saying which it is.
"""

from __future__ import annotations

import csv
import io
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


def _csv(rows: list[list[str]], name: str = "people.csv") -> SimpleUploadedFile:
    body = "\n".join(",".join(cell for cell in row) for row in rows).encode("utf-8")
    return SimpleUploadedFile(name, body, content_type="text/csv")


@pytest.fixture
def marked_session(admin_user, trainer_profile, batch, schedule, enrollment, other_enrollment):
    """A class with a register already taken, so reports have something to read."""
    from apps.attendance.services import mark_attendance
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Reported class",
    )
    mark_attendance(
        session=session,
        actor=trainer_profile.user,
        entries=[
            {"enrollment_id": str(enrollment.pk), "status": "present"},
            {"enrollment_id": str(other_enrollment.pk), "status": "absent"},
        ],
    )
    return session


# ---------------------------------------------------------------------------
# §8.7 — report authorization
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_read_any_report(api_client_no_csrf, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)

    assert api_client_no_csrf.get("/api/v1/reports/").status_code == 403
    assert api_client_no_csrf.get("/api/v1/reports/attendance/").status_code == 403
    assert api_client_no_csrf.get("/api/v1/reports/metrics/").status_code == 403


@pytest.mark.django_db
def test_an_administrator_sees_the_catalogue(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/").json()

    keys = {row["key"] for row in body}
    for expected in (
        "student_progress",
        "attendance",
        "assignments",
        "test_results",
        "project_results",
        "exam_results",
        "completion",
        "batch_performance",
        "trainer_activity",
        "certificates",
    ):
        assert expected in keys, expected
    # Every report declares its columns, which is what a screen renders from.
    assert all(row["columns"] for row in body)


@pytest.mark.django_db
def test_a_trainer_sees_only_their_own_batches_in_a_report(
    api_client_no_csrf,
    trainer_profile,
    trainer_profile_two,
    marked_session,
    upcoming_batch,
    admin_user,
    other_student_profile,
):
    """A report is built from a scoped queryset, not filtered afterwards."""
    from apps.enrollments.services import enrol_student

    enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    api_client_no_csrf.force_login(trainer_profile.user)
    mine = api_client_no_csrf.get("/api/v1/reports/attendance/").json()
    batches = {row["batch_code"] for row in mine["rows"]}
    assert upcoming_batch.code not in batches

    api_client_no_csrf.force_login(trainer_profile_two.user)
    theirs = api_client_no_csrf.get("/api/v1/reports/attendance/").json()
    theirs_batches = {row["batch_code"] for row in theirs["rows"]}
    assert marked_session.batch.code not in theirs_batches


@pytest.mark.django_db
def test_an_unknown_report_is_a_plain_not_found(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get("/api/v1/reports/not-a-report/").status_code == 404


# ---------------------------------------------------------------------------
# §8.7 — filters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_report_can_be_filtered_to_one_batch(
    api_client_no_csrf, admin_user, marked_session, batch, upcoming_batch, other_student_profile
):
    from apps.enrollments.services import enrol_student

    enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    api_client_no_csrf.force_login(admin_user)
    everything = api_client_no_csrf.get("/api/v1/reports/attendance/").json()
    filtered = api_client_no_csrf.get(f"/api/v1/reports/attendance/?batch={batch.id}").json()

    assert len(filtered["rows"]) < len(everything["rows"])
    assert {row["batch_code"] for row in filtered["rows"]} == {batch.code}


@pytest.mark.django_db
def test_filtering_by_a_batch_the_caller_cannot_see_is_a_not_found(
    api_client_no_csrf, trainer_profile, upcoming_batch
):
    """A filter must not become a way to widen access."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/reports/attendance/?batch={upcoming_batch.id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_the_attendance_report_carries_the_configured_requirement(
    api_client_no_csrf, admin_user, marked_session
):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/attendance/").json()

    row = next(row for row in body["rows"] if row["total_sessions"] > 0)
    assert row["required_percent"]
    assert row["meets_requirement"] in (True, False, None)


# ---------------------------------------------------------------------------
# §8.7 — exports
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_export_streams_the_same_report_as_csv(api_client_no_csrf, admin_user, marked_session):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get("/api/v1/reports/attendance/export/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Content-Type-Options"] == "nosniff"

    body = b"".join(response.streaming_content).decode("utf-8")
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0][0] == "Student"
    assert len(rows) > 1


@pytest.mark.django_db
def test_exporting_needs_its_own_capability(api_client_no_csrf, trainer_profile, marked_session):
    """Reading a page and walking out with the institution are different acts."""
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.get("/api/v1/reports/attendance/").status_code == 200
    assert api_client_no_csrf.get("/api/v1/reports/attendance/export/").status_code == 403


@pytest.mark.django_db
def test_an_export_neutralises_spreadsheet_formulas(
    api_client_no_csrf, admin_user, trainer_profile, batch, schedule, enrollment
):
    """A cell starting `=` runs in Excel on the machine that opens the file."""
    from apps.attendance.services import mark_attendance
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=2),
        start_time=time(14, 0),
        end_time=time(16, 0),
        topic="=cmd|'/c calc'!A1",
    )
    mark_attendance(
        session=session,
        actor=trainer_profile.user,
        entries=[{"enrollment_id": str(enrollment.pk), "status": "present"}],
    )

    from apps.reporting.exports import sanitise

    assert sanitise("=cmd|'/c calc'!A1").startswith("'=")
    assert sanitise("+1234").startswith("'+")
    assert sanitise("plain") == "plain"
    assert sanitise(None) == ""
    assert sanitise(True) == "yes"


@pytest.mark.django_db
def test_an_export_is_audited(api_client_no_csrf, admin_user, marked_session):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get("/api/v1/reports/attendance/export/")
    b"".join(response.streaming_content)

    entry = AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED).first()
    assert entry is not None
    assert entry.resource_id == "attendance"


# ---------------------------------------------------------------------------
# §8.6 — metrics, each with its definition
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_metric_carries_a_definition(api_client_no_csrf, admin_user, marked_session):
    """§8.6: 'Every metric must have a documented definition.'"""
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/metrics/").json()

    assert len(body) == 9
    for metric in body:
        assert metric["definition"].strip(), metric["key"]
        assert len(metric["definition"]) > 40, metric["key"]
        assert metric["unit"] in ("percent", "count")


@pytest.mark.django_db
def test_a_rate_over_nothing_is_null_rather_than_zero(admin_user, published_course):
    """'0% of nothing' reads as failure when it means there was nothing."""
    from apps.reporting import metrics

    result = metrics.attendance_rate({"course": published_course.pk})
    assert result["value"] is None


@pytest.mark.django_db
def test_the_attendance_metric_matches_the_report(api_client_no_csrf, admin_user, marked_session):
    api_client_no_csrf.force_login(admin_user)
    metric = next(
        row
        for row in api_client_no_csrf.get("/api/v1/reports/metrics/").json()
        if row["key"] == "attendance_rate"
    )
    # One present, one absent, on the one marked class.
    assert metric["numerator"] == 1
    assert metric["denominator"] == 2
    assert metric["value"] == 50.0


@pytest.mark.django_db
def test_the_attendance_trend_is_grouped_by_week(
    api_client_no_csrf, admin_user, marked_session, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(12):
        body = api_client_no_csrf.get("/api/v1/reports/metrics/attendance-trend/").json()

    assert body
    assert body[0]["counted"] >= 1
    assert "percent" in body[0]


# ---------------------------------------------------------------------------
# §8.4 — dashboards, and §8.7's query-performance requirement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_admin_dashboard_answers_in_a_bounded_number_of_queries(
    api_client_no_csrf, admin_user, marked_session, django_assert_max_num_queries
):
    """§8.7 dashboard query performance."""
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(45):
        body = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()

    assert body["active_batches"] >= 1
    assert len(body["metrics"]) == 5
    assert all(metric["definition"] for metric in body["metrics"])


@pytest.mark.django_db
def test_a_trainer_cannot_open_the_admin_dashboard(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get("/api/v1/dashboards/admin/").status_code == 403


@pytest.mark.django_db
def test_the_trainer_workload_counts_what_is_outstanding(
    api_client_no_csrf, trainer_profile, marked_session, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(trainer_profile.user)
    with django_assert_max_num_queries(30):
        body = api_client_no_csrf.get("/api/v1/dashboards/workload/").json()

    assert body["batches"] >= 1
    assert "submissions_to_mark" in body
    assert "registers_outstanding" in body


@pytest.mark.django_db
def test_batch_summaries_do_not_grow_a_query_per_batch(
    api_client_no_csrf, admin_user, marked_session, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(10):
        body = api_client_no_csrf.get("/api/v1/dashboards/batches/").json()

    assert body
    assert "attendance_percent" in body[0]


# ---------------------------------------------------------------------------
# §8.5 — bulk import
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_import_previews_without_writing(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {
            "file": _csv(
                [
                    ["email", "first name", "last name"],
                    ["asha.new@example.test", "Asha", "Rao"],
                    ["bilal.new@example.test", "Bilal", "Khan"],
                ]
            )
        },
        format="multipart",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == BulkImportStatus.PREVIEW
    assert body["valid_count"] == 2
    assert body["error_count"] == 0

    from apps.accounts.models import User

    assert not User.objects.filter(email="asha.new@example.test").exists()


@pytest.mark.django_db
def test_confirming_creates_the_accounts_and_enrols_them(api_client_no_csrf, admin_user, batch):
    from apps.accounts.models import User
    from apps.enrollments.models import Enrollment

    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {
            "file": _csv(
                [["email", "first name", "last name"], ["chen.new@example.test", "Chen", "Wu"]]
            ),
            "batch": str(batch.id),
        },
        format="multipart",
    ).json()

    confirmed = api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/confirm/", format="json")

    assert confirmed.status_code == 200
    assert confirmed.json()["created_count"] == 1
    student = User.objects.get(email="chen.new@example.test")
    assert student.role == "student"
    assert Enrollment.objects.filter(student__user=student, batch=batch).exists()


@pytest.mark.django_db
def test_an_existing_account_is_reported_not_silently_changed(
    api_client_no_csrf, admin_user, student_profile
):
    """A bulk file must never quietly rename somebody or change their role."""
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {
            "file": _csv(
                [["email", "first name"], [student_profile.user.email, "Completely Different"]]
            )
        },
        format="multipart",
    ).json()

    assert body["error_count"] == 1
    assert "already exists" in body["report"]["errors"][0]["problem"]

    student_profile.user.refresh_from_db()
    assert student_profile.user.first_name != "Completely Different"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rows,fragment",
    [
        ([["name", "town"], ["Asha", "Jaipur"]], "missing required column"),
        ([["email", "first name"], ["not-an-email", "Asha"]], "valid email"),
        ([["email", "first name"], ["a@example.test", ""]], "No first name"),
        (
            [["email", "first name"], ["a@example.test", "A"], ["A@EXAMPLE.TEST", "B"]],
            "Duplicate",
        ),
        ([["email", "first name"], ["=cmd|calc", "A"]], "formula"),
    ],
)
def test_a_bad_student_file_is_reported(api_client_no_csrf, admin_user, rows, fragment):
    """§8.7 import failures."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/imports/students/", {"file": _csv(rows)}, format="multipart"
    )

    if response.status_code == 400:
        assert fragment.lower() in str(response.json()).lower()
    else:
        body = response.json()
        assert body["error_count"] >= 1
        assert fragment.lower() in str(body["report"]["errors"]).lower()


@pytest.mark.django_db
def test_a_file_with_errors_cannot_be_confirmed(api_client_no_csrf, admin_user):
    from apps.accounts.models import User

    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {"file": _csv([["email", "first name"], ["good@example.test", "Good"], ["bad", "Bad"]])},
        format="multipart",
    ).json()

    response = api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/confirm/", format="json")

    assert response.status_code == 409
    assert not User.objects.filter(email="good@example.test").exists()


@pytest.mark.django_db
def test_an_address_registered_between_preview_and_confirm_rolls_it_all_back(
    api_client_no_csrf, admin_user
):
    from apps.accounts.models import User
    from apps.students.services import create_student

    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {
            "file": _csv(
                [
                    ["email", "first name"],
                    ["first@example.test", "First"],
                    ["second@example.test", "Second"],
                ]
            )
        },
        format="multipart",
    ).json()

    create_student(
        email="second@example.test",
        first_name="Somebody",
        last_name="Else",
        actor=admin_user,
        password=None,
        send_invitation=False,
    )

    response = api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/confirm/", format="json")

    assert response.status_code == 409
    # Not one of two: all or nothing.
    assert not User.objects.filter(email="first@example.test").exists()


@pytest.mark.django_db
def test_an_attendance_file_marks_the_register(
    api_client_no_csrf, admin_user, trainer_profile, batch, schedule, enrollment, other_enrollment
):
    from apps.attendance.models import AttendanceRecord
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=3),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Taken on paper",
    )

    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        f"/api/v1/imports/sessions/{session.id}/attendance/",
        {
            "file": _csv(
                [
                    ["student id", "status"],
                    [enrollment.student.student_id, "present"],
                    [other_enrollment.student.student_id, "absent"],
                ]
            )
        },
        format="multipart",
    ).json()

    assert preview["error_count"] == 0
    confirmed = api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/confirm/", format="json")

    assert confirmed.status_code == 200
    assert AttendanceRecord.objects.filter(session=session).count() == 2


@pytest.mark.django_db
def test_an_attendance_file_cannot_mark_somebody_not_in_the_room(
    api_client_no_csrf, admin_user, batch, schedule, enrollment
):
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=4),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Guarded",
    )

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.post(
        f"/api/v1/imports/sessions/{session.id}/attendance/",
        {"file": _csv([["student id", "status"], ["GRS-S-99999", "present"]])},
        format="multipart",
    ).json()

    assert body["error_count"] == 1
    assert "register" in body["report"]["errors"][0]["problem"]


@pytest.mark.django_db
def test_a_trainer_cannot_bulk_import(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {"file": _csv([["email", "first name"], ["x@example.test", "X"]])},
        format="multipart",
    )

    assert response.status_code == 403
    assert BulkImport.objects.count() == 0


@pytest.mark.django_db
def test_an_import_can_be_discarded(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {"file": _csv([["email", "first name"], ["discard@example.test", "D"]])},
        format="multipart",
    ).json()

    rejected = api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/reject/", format="json")

    assert rejected.status_code == 200
    assert rejected.json()["status"] == BulkImportStatus.REJECTED
    assert (
        api_client_no_csrf.post(
            f"/api/v1/imports/{preview['id']}/confirm/", format="json"
        ).status_code
        == 409
    )


@pytest.mark.django_db
def test_an_import_is_audited(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    preview = api_client_no_csrf.post(
        "/api/v1/imports/students/",
        {"file": _csv([["email", "first name"], ["audited@example.test", "A"]])},
        format="multipart",
    ).json()
    api_client_no_csrf.post(f"/api/v1/imports/{preview['id']}/confirm/", format="json")

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.BULK_IMPORT_PREVIEWED in actions
    assert AuditAction.BULK_IMPORT_CONFIRMED in actions

    run = BulkImport.objects.get()
    assert run.kind == ImportKind.STUDENTS
    assert len(run.checksum) == 64


# ---------------------------------------------------------------------------
# §8.7 — larger datasets
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_report_page_is_bounded_and_says_so(
    api_client_no_csrf, admin_user, published_course, batch
):
    """A screen gets a page; the export gets everything."""
    from apps.reporting.views import PAGE_LIMIT

    assert PAGE_LIMIT <= 1000

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/student_progress/").json()
    assert body["row_count"] <= PAGE_LIMIT
    assert "truncated" in body


@pytest.mark.django_db
def test_a_large_export_streams_rather_than_buffering(admin_user, batch, published_course):
    """The response is a generator, so nothing holds the whole set in memory."""
    from apps.reporting import exports, reports

    definition = reports.ATTENDANCE
    produced = ({"student_code": f"GRS-S-{index:05d}"} for index in range(5000))
    stream = exports.stream_csv(definition.column_dicts(), produced)

    import types

    assert isinstance(stream, types.GeneratorType)
    first = next(stream)
    assert first.startswith("Student")
    # Pulling one row does not consume the rest.
    assert next(stream).startswith("GRS-S-00000")


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf):
    for url in (
        "/api/v1/reports/",
        "/api/v1/reports/metrics/",
        "/api/v1/dashboards/admin/",
        "/api/v1/imports/students/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403, 405), url


# ---------------------------------------------------------------------------
# Every report actually runs
# ---------------------------------------------------------------------------


@pytest.fixture
def a_bit_of_everything(
    admin_user,
    trainer_profile,
    student_profile,
    published_course,
    batch,
    enrollment,
    marked_session,
):
    """One record of each kind, so every report has something to produce.

    Reports are the place a schema change breaks quietly: a renamed field
    surfaces as an empty column rather than an error, so each one is run against
    real rows rather than an empty table.
    """
    from apps.assessments.models import AssessmentDelivery, AssessmentStatus
    from apps.assessments.services import create_assessment, record_result, set_assessment_status
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )
    from apps.certificates.services import issue_certificate, save_template
    from apps.exams.models import ExamStatus
    from apps.exams.services import create_exam, set_exam_status, start_attempt, submit_attempt
    from apps.progress.services import approve_completion
    from apps.projects.models import ProjectStatus, WorkStatus
    from apps.projects.services import (
        create_project,
        review_project,
        set_project_status,
        student_project_for,
        submit_project,
    )
    from apps.questions.models import QuestionType
    from apps.questions.services import create_question

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Reported assignment",
        max_marks=Decimal("100.00"),
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
    submission = submit_assignment(
        assignment=work,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("a.py", b"pass\n")],
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("77.00"))

    test = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Reported test",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )
    set_assessment_status(assessment=test, actor=admin_user, status=AssessmentStatus.PUBLISHED)
    record_result(assessment=test, enrollment=enrollment, actor=admin_user, marks=Decimal("16.00"))

    project = create_project(
        actor=admin_user, course=published_course, batch=batch, title="Reported project"
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)
    student_work = student_project_for(project=project, student=student_profile)
    submit_project(
        work=student_work,
        actor=student_profile.user,
        files=[SimpleUploadedFile("p.py", b"pass\n")],
    )
    review_project(
        work=student_work,
        actor=trainer_profile.user,
        outcome=WorkStatus.APPROVED,
        marks=Decimal("81.00"),
    )

    for index in range(2):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.MCQ,
            text=f"R{index}?",
            marks=Decimal("5.00"),
            options=[{"text": "a", "is_correct": True}, {"text": "b"}],
        )
    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Reported exam",
        opens_at=timezone.now() - timedelta(minutes=5),
        sections=[{"title": "A", "question_count": 2, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)
    attempt = start_attempt(exam=exam, enrollment=enrollment, actor=student_profile.user)
    submit_attempt(attempt=attempt, actor=student_profile.user)

    save_template(actor=admin_user, name="Reported", is_default=True)
    completion = approve_completion(
        enrollment=enrollment, actor=admin_user, override=True, note="For the report."
    )
    issue_certificate(completion=completion, actor=admin_user)
    return enrollment


@pytest.mark.django_db
@pytest.mark.parametrize("key", list(__import__("apps.reporting.reports", fromlist=["x"]).REPORTS))
def test_every_report_runs_and_matches_its_columns(
    api_client_no_csrf, admin_user, a_bit_of_everything, key
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/reports/{key}/")

    assert response.status_code == 200, key
    body = response.json()
    assert body["key"] == key
    assert body["rows"], f"{key} produced no rows"

    declared = {column["key"] for column in body["columns"]}
    for row in body["rows"]:
        assert set(row) == declared, f"{key} row does not match its columns"


@pytest.mark.django_db
@pytest.mark.parametrize("key", list(__import__("apps.reporting.reports", fromlist=["x"]).REPORTS))
def test_every_report_exports(api_client_no_csrf, admin_user, a_bit_of_everything, key):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/reports/{key}/export/")

    assert response.status_code == 200, key
    rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode("utf-8"))))
    assert len(rows) >= 2, key


@pytest.mark.django_db
def test_grades_come_from_the_configured_bands(api_client_no_csrf, admin_user, a_bit_of_everything):
    """A report letters a score with the institution's bands, not a constant."""
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.request_context import clear_scope

    api_client_no_csrf.force_login(admin_user)
    before = api_client_no_csrf.get("/api/v1/reports/test_results/").json()
    assert before["rows"][0]["grade"] == "A"  # 16 of 20 is 80%

    update_policy(
        policy=get_or_create_policy(),
        actor=admin_user,
        grade_bands=[
            {"label": "Distinction", "min_percent": "85.00"},
            {"label": "Merit", "min_percent": "70.00"},
            {"label": "Pass", "min_percent": "40.00"},
            {"label": "Fail", "min_percent": "0.00"},
        ],
    )
    clear_scope()

    after = api_client_no_csrf.get("/api/v1/reports/test_results/").json()
    assert after["rows"][0]["grade"] == "Merit"


@pytest.mark.django_db
def test_grade_bands_must_reach_zero(admin_user):
    """A score falling through every band would have no grade at all."""
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        update_policy(
            policy=get_or_create_policy(),
            actor=admin_user,
            grade_bands=[{"label": "A", "min_percent": "50.00"}],
        )


@pytest.mark.django_db
def test_grade_bands_must_descend(admin_user):
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        update_policy(
            policy=get_or_create_policy(),
            actor=admin_user,
            grade_bands=[
                {"label": "Low", "min_percent": "0.00"},
                {"label": "High", "min_percent": "80.00"},
            ],
        )
