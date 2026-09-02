"""§14.9 — the query count must not grow with the data.

Absolute query budgets (``django_assert_max_num_queries(20)``) catch a gross
regression but pass an N+1 happily: on a fixture with two students, one query
per student is two queries. The bug only appears in production, where there are
four hundred.

So every test here measures the *same* endpoint twice, against a small dataset
and a larger one, and asserts the number of queries is identical. That is a
direct statement of the property that matters — the endpoint's cost is
independent of how many rows it returns — and it fails loudly the moment
somebody drops a `select_related`.

The second half checks the other half of §14.9: that no endpoint can be asked
for an unbounded result set.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User, UserRole
from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultSource,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.common.identifiers import next_enrolment_code, next_student_id
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.sessions.models import ClassSession, SessionStatus
from apps.students.models import StudentProfile

SMALL = 3
LARGE = 15


def _add_students(batch, count: int, *, start: int = 0) -> list[Enrollment]:
    """Enrol `count` extra students into `batch`, with attendance and a result."""
    users = User.objects.bulk_create(
        User(
            email=f"perf-{start + index:03d}@perf.grras.invalid",
            first_name="Perf",
            last_name=f"Student {start + index}",
            role=UserRole.STUDENT,
            is_active=True,
        )
        for index in range(count)
    )
    profiles = StudentProfile.objects.bulk_create(
        StudentProfile(user=user, student_id=next_student_id()) for user in users
    )
    enrollments = Enrollment.objects.bulk_create(
        Enrollment(
            code=next_enrolment_code(),
            student=profile,
            batch=batch,
            course=batch.course,
            status=EnrollmentStatus.ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )
        for profile in profiles
    )

    for session in ClassSession.objects.filter(batch=batch, status=SessionStatus.COMPLETED):
        AttendanceRecord.objects.bulk_create(
            AttendanceRecord(
                session=session, enrollment=enrollment, status=AttendanceStatus.PRESENT
            )
            for enrollment in enrollments
        )
    for assessment in Assessment.objects.filter(batch=batch):
        AssessmentResult.objects.bulk_create(
            AssessmentResult(
                assessment=assessment,
                enrollment=enrollment,
                marks_obtained=40,
                source=ResultSource.MANUAL,
            )
            for enrollment in enrollments
        )
    return enrollments


@pytest.fixture
def loaded_batch(admin_user, batch, enrollment):
    """A batch with completed classes and a published test to report on."""
    session = ClassSession.objects.create(
        batch=batch,
        session_date=date.today() - timedelta(days=3),
        start_time="10:00",
        end_time="12:00",
        topic="Recorded class",
        status=SessionStatus.COMPLETED,
        created_by=admin_user,
    )
    assessment = Assessment.objects.create(
        batch=batch,
        course=batch.course,
        title="Weekly Test 1",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.OFFLINE,
        status=AssessmentStatus.PUBLISHED,
        max_marks=50,
        passing_marks=20,
        created_by=admin_user,
    )
    AttendanceRecord.objects.create(
        session=session, enrollment=enrollment, status=AttendanceStatus.PRESENT
    )
    AssessmentResult.objects.create(
        assessment=assessment, enrollment=enrollment, marks_obtained=40, source=ResultSource.MANUAL
    )
    return {"batch": batch, "session": session, "assessment": assessment}


def _count_queries(client, url: str) -> tuple[int, int]:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200, f"{url} -> {response.status_code}"
    return len(captured.captured_queries), response.status_code


def assert_flat(client, url: str, batch) -> None:
    """The heart of this module: same endpoint, five times the data, same cost."""
    _add_students(batch, SMALL)
    small, _ = _count_queries(client, url)

    _add_students(batch, LARGE, start=100)
    large, _ = _count_queries(client, url)

    assert large == small, (
        f"{url} issued {small} queries for {SMALL} students and {large} for "
        f"{SMALL + LARGE}. The cost grows with the data — an N+1."
    )


# ---------------------------------------------------------------------------
# The endpoints that read a whole cohort
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_batch_roster_does_not_query_per_student(api_client_no_csrf, admin_user, loaded_batch):
    api_client_no_csrf.force_login(admin_user)
    batch = loaded_batch["batch"]
    assert_flat(api_client_no_csrf, f"/api/v1/batches/{batch.id}/roster/", batch)


@pytest.mark.django_db
def test_the_attendance_register_does_not_query_per_student(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    session = loaded_batch["session"]
    assert_flat(
        api_client_no_csrf,
        f"/api/v1/sessions/{session.id}/register/",
        loaded_batch["batch"],
    )


@pytest.mark.django_db
def test_the_attendance_listing_does_not_query_per_record(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    session = loaded_batch["session"]
    assert_flat(
        api_client_no_csrf,
        f"/api/v1/sessions/{session.id}/attendance/",
        loaded_batch["batch"],
    )


@pytest.mark.django_db
def test_the_student_progress_report_does_not_query_per_student(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/reports/student_progress/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_attendance_report_does_not_query_per_record(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/reports/attendance/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_test_results_report_does_not_query_per_result(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/reports/test_results/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_admin_dashboard_does_not_query_per_student(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/dashboards/admin/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_batch_summary_does_not_query_per_batch_member(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/dashboards/batches/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_metrics_endpoint_does_not_query_per_enrolment(
    api_client_no_csrf, admin_user, loaded_batch
):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/reports/metrics/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_batch_list_does_not_query_per_batch(api_client_no_csrf, admin_user, loaded_batch):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/batches/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_student_list_does_not_query_per_student(api_client_no_csrf, admin_user, loaded_batch):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/students/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_user_list_does_not_query_per_user(api_client_no_csrf, admin_user, loaded_batch):
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/users/", loaded_batch["batch"])


# ---------------------------------------------------------------------------
# Nothing may be asked for unbounded
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/students/",
        "/api/v1/users/",
        "/api/v1/batches/",
        "/api/v1/courses/",
        "/api/v1/enrollments/",
    ],
)
def test_a_caller_cannot_ask_for_every_row(api_client_no_csrf, admin_user, batch, url):
    """A page size the caller chooses is a denial-of-service parameter."""
    _add_students(batch, 12)
    api_client_no_csrf.force_login(admin_user)

    body = api_client_no_csrf.get(f"{url}?page_size=100000").json()
    from apps.common.pagination import DefaultPagination

    assert len(body["results"]) <= DefaultPagination.max_page_size


@pytest.mark.django_db
def test_a_report_page_is_capped(api_client_no_csrf, admin_user, loaded_batch):
    from apps.reporting.views import PAGE_LIMIT

    _add_students(loaded_batch["batch"], 12)
    api_client_no_csrf.force_login(admin_user)

    body = api_client_no_csrf.get("/api/v1/reports/student_progress/").json()
    assert len(body["rows"]) <= PAGE_LIMIT


@pytest.mark.django_db
def test_an_export_streams_rather_than_buffering(api_client_no_csrf, admin_user, loaded_batch):
    """§8.5: an export must not load the whole institution into memory."""
    _add_students(loaded_batch["batch"], 12)
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.get("/api/v1/reports/student_progress/export/")
    assert response.status_code == 200
    assert response.streaming is True


# ---------------------------------------------------------------------------
# The bulk path must not become a second progress calculation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_cohort_report_agrees_with_the_single_student_report(loaded_batch, enrollment):
    """The guarantee that makes the bulk path safe.

    `progress_reports` exists to make a cohort cheap. If it ever computed
    anything differently from `progress_report`, two screens would disagree
    about whether a student has finished — the exact failure §6 was written to
    prevent. So they are compared, row by row, on data with real progress in it.
    """
    from apps.progress.reports import progress_report, progress_reports

    _add_students(loaded_batch["batch"], 4)
    cohort = list(Enrollment.objects.filter(batch=loaded_batch["batch"]))
    assert len(cohort) >= 5

    for row, (bulk_enrollment, bulk_report) in zip(cohort, progress_reports(cohort), strict=True):
        assert bulk_enrollment.pk == row.pk
        assert bulk_report == progress_report(row)


@pytest.mark.django_db
def test_the_cohort_report_cost_is_flat(loaded_batch):
    from apps.progress.reports import progress_reports

    def measure() -> tuple[int, int]:
        cohort = Enrollment.objects.filter(batch=loaded_batch["batch"])
        with CaptureQueriesContext(connection) as captured:
            rows = list(progress_reports(cohort))
        return len(rows), len(captured.captured_queries)

    _add_students(loaded_batch["batch"], SMALL)
    small_size, small = measure()

    _add_students(loaded_batch["batch"], LARGE, start=200)
    large_size, large = measure()

    assert large_size > small_size
    assert large == small, f"{small} queries for {small_size} students, {large} for {large_size}"


@pytest.mark.django_db
def test_a_single_student_report_stays_cheap(enrollment, django_assert_max_num_queries):
    """The bulk path must not have made one student's own screen slower."""
    from apps.progress.reports import progress_report

    with django_assert_max_num_queries(14):
        progress_report(enrollment)


# ---------------------------------------------------------------------------
# Batch and trainer reports
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_batch_report_does_not_query_per_batch(
    api_client_no_csrf, admin_user, loaded_batch, published_course, trainer_profile
):
    """Adding batches, not students: this report's row is a batch."""
    from apps.batches.models import Batch, BatchStatus

    api_client_no_csrf.force_login(admin_user)

    def measure() -> int:
        with CaptureQueriesContext(connection) as captured:
            response = api_client_no_csrf.get("/api/v1/reports/batch_performance/")
        assert response.status_code == 200
        return len(captured.captured_queries)

    small = measure()
    Batch.objects.bulk_create(
        Batch(
            code=f"PERF-{index:03d}",
            name=f"Perf batch {index}",
            course=published_course,
            trainer=trainer_profile,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
            capacity=50,
            status=BatchStatus.ACTIVE,
        )
        for index in range(10)
    )
    assert measure() == small


@pytest.mark.django_db
def test_the_trainer_report_does_not_query_per_trainer(
    api_client_no_csrf, admin_user, trainer_profile
):
    from apps.common.identifiers import next_trainer_id
    from apps.trainers.models import TrainerProfile

    api_client_no_csrf.force_login(admin_user)

    def measure() -> int:
        with CaptureQueriesContext(connection) as captured:
            response = api_client_no_csrf.get("/api/v1/reports/trainer_activity/")
        assert response.status_code == 200
        return len(captured.captured_queries)

    small = measure()
    users = User.objects.bulk_create(
        User(
            email=f"perf-trainer-{index}@perf.grras.invalid",
            first_name="Perf",
            last_name=f"Trainer {index}",
            role=UserRole.TRAINER,
            is_active=True,
        )
        for index in range(10)
    )
    TrainerProfile.objects.bulk_create(
        TrainerProfile(user=user, trainer_id=next_trainer_id()) for user in users
    )
    assert measure() == small


@pytest.mark.django_db
def test_the_grouped_metrics_agree_with_the_scalar_ones(loaded_batch):
    """The guarantee that makes `metrics.by_batch` safe.

    A batch report showing 71% attendance while the metrics page shows 68% for
    the same batch would be worse than either number being wrong: nobody would
    know which to believe.
    """
    from apps.reporting import metrics

    _add_students(loaded_batch["batch"], 5)
    batch = loaded_batch["batch"]

    grouped = metrics.by_batch([batch.pk])[batch.pk]
    scope = {"batch": batch.pk}

    assert grouped["attendance_percent"] == metrics.attendance_rate(scope)["value"]
    assert grouped["completion_percent"] == metrics.completion_rate(scope)["value"]
    assert grouped["pending_marking"] == metrics.pending_marking(scope)["value"]


@pytest.mark.django_db
def test_the_enrolment_list_does_not_query_per_row(api_client_no_csrf, admin_user, loaded_batch):
    """Every row renders the trainer's name; the join must come from the queryset."""
    api_client_no_csrf.force_login(admin_user)
    assert_flat(api_client_no_csrf, "/api/v1/enrollments/", loaded_batch["batch"])


@pytest.mark.django_db
def test_the_batch_summary_counts_without_a_join_explosion(
    api_client_no_csrf, admin_user, loaded_batch
):
    """Guards a slow query that no query *count* would catch.

    Annotating the student count and the attendance counts onto one queryset
    made the database count rows in the product of enrolments, sessions and
    attendance records — eight queries, four seconds. The counts are now taken
    separately, so the work grows with the records rather than with their
    product. Asserted by checking the rows are still right after the data has
    been multiplied in both dimensions at once.
    """
    batch = loaded_batch["batch"]
    _add_students(batch, 6)
    for day in range(6):
        session = ClassSession.objects.create(
            batch=batch,
            session_date=date.today() - timedelta(days=10 + day),
            start_time="14:00",
            end_time="16:00",
            topic=f"Extra class {day}",
            status=SessionStatus.COMPLETED,
            created_by=admin_user,
        )
        AttendanceRecord.objects.bulk_create(
            AttendanceRecord(
                session=session, enrollment=enrollment, status=AttendanceStatus.PRESENT
            )
            for enrollment in Enrollment.objects.filter(batch=batch)
        )

    api_client_no_csrf.force_login(admin_user)
    with CaptureQueriesContext(connection) as captured:
        body = api_client_no_csrf.get("/api/v1/dashboards/batches/").json()

    row = next(entry for entry in body if entry["id"] == str(batch.pk))
    # Seven students, all present at every counted class.
    assert row["students"] == Enrollment.objects.filter(batch=batch).count()
    assert row["attendance_percent"] == 100.0
    assert len(captured.captured_queries) <= 12


# ---------------------------------------------------------------------------
# Pagination must not lose or duplicate a row
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_paging_through_tied_rows_shows_each_one_exactly_once(
    api_client_no_csrf, admin_user, loaded_batch
):
    """Rows that tie on the sort column must still paginate deterministically.

    Every student here is created in one bulk insert, so they share a
    `created_at` to the microsecond — which is the ordering the student list
    uses. Without a unique tiebreaker the database is free to return tied rows
    in a different order for page one and page two, and the result is a student
    who appears twice and another who is never listed at all.
    """
    _add_students(loaded_batch["batch"], 30)
    api_client_no_csrf.force_login(admin_user)

    seen: list[str] = []
    page = 1
    while True:
        body = api_client_no_csrf.get(f"/api/v1/students/?page={page}&page_size=10").json()
        seen.extend(row["id"] for row in body["results"])
        if not body["next"]:
            break
        page += 1

    assert len(seen) == len(set(seen)), "a row appeared on more than one page"
    assert len(seen) == body["count"], f"{body['count']} rows exist but paging returned {len(seen)}"


@pytest.mark.django_db
def test_the_ordering_is_stable_across_identical_requests(
    api_client_no_csrf, admin_user, loaded_batch
):
    _add_students(loaded_batch["batch"], 20)
    api_client_no_csrf.force_login(admin_user)

    first = [row["id"] for row in api_client_no_csrf.get("/api/v1/students/").json()["results"]]
    second = [row["id"] for row in api_client_no_csrf.get("/api/v1/students/").json()["results"]]
    assert first == second


@pytest.mark.django_db
def test_a_nullable_sort_column_still_paginates_completely(
    api_client_no_csrf, student_profile, enrollment, admin_user, batch
):
    """The case that found this: projects sorted by a due date most of them lack."""
    from apps.common.identifiers import next_project_code
    from apps.projects.models import Project, ProjectStatus

    Project.objects.bulk_create(
        Project(
            code=next_project_code(),
            course=batch.course,
            title=f"Undated project {index}",
            description="No due date, like most of them.",
            instructions="Build something.",
            deliverables="Source.",
            status=ProjectStatus.PUBLISHED,
            max_marks=100,
            is_required=False,
            created_by=admin_user,
        )
        for index in range(30)
    )

    api_client_no_csrf.force_login(student_profile.user)
    seen: list[str] = []
    page = 1
    while True:
        body = api_client_no_csrf.get(f"/api/v1/projects/mine/?page={page}&page_size=10").json()
        seen.extend(row["id"] for row in body["results"])
        if not body["next"]:
            break
        page += 1

    assert len(seen) == len(set(seen))
    assert len(seen) == body["count"]
