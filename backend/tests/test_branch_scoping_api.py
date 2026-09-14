"""The branch wall as a caller actually meets it: over HTTP, with real ids.

`tests/test_branch_scoping.py` proves that the access functions return the right
querysets. That is necessary and it is not sufficient, because a queryset only
protects the endpoints that use it. The leaks worth having are the ones on the
paths where the filter is easiest to forget, and they are all here:

* a **list** whose view builds its own queryset instead of calling `access`;
* an **id from the URL** — the enumeration oracle, where the answer must be a
  404 and not a 403, or guessing a uuid confirms that somebody exists in
  another city;
* a **filter or search parameter**, which must never widen what the caller can
  reach — `?branch=<theirs>` has to come back empty, not helpful;
* an **export**: a report streamed to a file is not a weaker way to read it, and
  a background job runs *after* the request, in a worker, with no request to
  carry the scope;
* an **aggregate** — a dashboard count is still somebody's data, and a total
  that silently includes another centre is the hardest kind of leak to notice
  because the screen looks completely normal;
* the **recycle bin**, where a restore puts a row back into circulation.

Two branches, both populated. Every "sees only A" assertion is paired with the
B row that must be absent, so none of them can be passing because B is empty.

Where a test asserts a status code it asserts the body or the database too: a
403 that still wrote the row is not a refusal.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User, UserRole

TEST_PASSWORD = "correct-horse-battery-staple"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# Centre A is `conftest.py`'s default set (branch MAIN); centre B is the
# `other_branch_*` set (branch PUNE). What follows is only what the API sweep
# needs on top of those.


@pytest.fixture
def counsellor_b(other_branch) -> User:
    return User.objects.create_user(
        email="counsellor@pune.example.test",
        password=TEST_PASSWORD,
        first_name="Chandni",
        last_name="Pune",
        role=UserRole.COUNSELLOR,
        branch=other_branch,
    )


@pytest.fixture
def admin_b(other_branch) -> User:
    """An administrator at the second centre — bounded, per D-127."""
    return User.objects.create_user(
        email="admin@pune.example.test",
        password=TEST_PASSWORD,
        first_name="Anil",
        last_name="Pune",
        role=UserRole.ADMIN,
        branch=other_branch,
        is_staff=True,
    )


@pytest.fixture
def branchless_manager(db) -> User:
    """A manager stamped with no centre — the fail-closed case, as an account."""
    return User.objects.create_user(
        email="nobranch.manager@example.test",
        password=TEST_PASSWORD,
        first_name="Nadia",
        last_name="Nowhere",
        role=UserRole.MANAGER,
        branch=None,
    )


@pytest.fixture
def branchless_admin(db) -> User:
    return User.objects.create_user(
        email="nobranch.admin@example.test",
        password=TEST_PASSWORD,
        first_name="Nilesh",
        last_name="Nowhere",
        role=UserRole.ADMIN,
        branch=None,
        is_staff=True,
    )


@pytest.fixture
def session_a(admin_user, batch):
    from apps.sessions.services import create_session

    return create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Filesystem basics",
    )


@pytest.fixture
def session_b(unbounded_superadmin, other_branch_batch):
    from apps.sessions.services import create_session

    return create_session(
        batch=other_branch_batch,
        actor=unbounded_superadmin,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Cabling",
    )


@pytest.fixture
def dsr_a(admin_user, session_a):
    from apps.dsr.services import start_dsr

    return start_dsr(session=session_a, actor=admin_user)


@pytest.fixture
def dsr_b(unbounded_superadmin, session_b):
    from apps.dsr.services import start_dsr

    return start_dsr(session=session_b, actor=unbounded_superadmin)


@pytest.fixture
def assessment_a(admin_user, batch):
    from apps.assessments.models import AssessmentDelivery
    from apps.assessments.services import create_assessment

    return create_assessment(
        actor=admin_user, batch=batch, title="Week 1 — Jaipur", delivery=AssessmentDelivery.OFFLINE
    )


@pytest.fixture
def assessment_b(unbounded_superadmin, other_branch_batch):
    from apps.assessments.models import AssessmentDelivery
    from apps.assessments.services import create_assessment

    return create_assessment(
        actor=unbounded_superadmin,
        batch=other_branch_batch,
        title="Week 1 — Pune",
        delivery=AssessmentDelivery.OFFLINE,
    )


@pytest.fixture
def exam_a(admin_user, batch):
    from apps.exams.services import create_exam

    return create_exam(actor=admin_user, batch=batch, title="Jaipur final")


@pytest.fixture
def exam_b(unbounded_superadmin, other_branch_batch):
    from apps.exams.services import create_exam

    return create_exam(actor=unbounded_superadmin, batch=other_branch_batch, title="Pune final")


@pytest.fixture
def assignment_a(admin_user, published_course, batch):
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Jaipur exercise",
        instructions="Write a script.",
    )


@pytest.fixture
def assignment_b(unbounded_superadmin, published_course, other_branch_batch):
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=unbounded_superadmin,
        course=published_course,
        batch=other_branch_batch,
        title="Pune exercise",
        instructions="Write a script.",
    )


@pytest.fixture
def project_a(admin_user, published_course, batch):
    from apps.projects.services import create_project

    return create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Jaipur project",
        description="A tool.",
        instructions="Build it.",
        deliverables="Source.",
    )


@pytest.fixture
def project_b(unbounded_superadmin, published_course, other_branch_batch):
    from apps.projects.services import create_project

    return create_project(
        actor=unbounded_superadmin,
        course=published_course,
        batch=other_branch_batch,
        title="Pune project",
        description="A tool.",
        instructions="Build it.",
        deliverables="Source.",
    )


@pytest.fixture
def announcement_a(admin_user, batch):
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=admin_user,
        title="Jaipur lab closed",
        body="The lab is closed on Friday.",
        audience=Audience.BATCH,
        batch=batch,
        course=batch.course,
    )
    return publish(announcement=created, actor=admin_user)


@pytest.fixture
def announcement_b(unbounded_superadmin, other_branch_batch):
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=unbounded_superadmin,
        title="Pune lab closed",
        body="The lab is closed on Friday.",
        audience=Audience.BATCH,
        batch=other_branch_batch,
        course=other_branch_batch.course,
    )
    return publish(announcement=created, actor=unbounded_superadmin)


@pytest.fixture
def institution_wide_announcement(admin_user):
    """Addressed to everyone, which is the one audience that really is."""
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=admin_user,
        title="Holiday on Monday",
        body="Every centre is closed.",
        audience=Audience.EVERYONE,
    )
    return publish(announcement=created, actor=admin_user)


@pytest.fixture
def private_announcement_b(other_branch_manager, other_branch_student):
    """A notice the other centre addressed to *named people*.

    The audience that carries no batch. `announcement_b` above is a batch
    notice, and a batch is stamped with a centre — which is exactly why every
    earlier version of this suite passed while this row was being served to the
    whole institution. The recipient list is one student at the other centre,
    so a headcount of it is itself a fact about their roster.
    """
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=other_branch_manager,
        title="PUNE PRIVATE: fee default follow-up",
        body="Ring these two families about arrears before Friday.",
        audience=Audience.SELECTED,
        recipients=[other_branch_student.user],
    )
    return publish(announcement=created, actor=other_branch_manager)


@pytest.fixture
def draft_announcement_b(other_branch_manager):
    """A notice the other centre has not published yet. Nobody outside it has
    any business reading a sentence somebody is still drafting."""
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement

    return create_announcement(
        actor=other_branch_manager,
        title="DRAFT PUNE: staffing changes",
        body="Not decided yet. Do not circulate.",
        audience=Audience.SELECTED,
    )


@pytest.fixture
def course_announcement_b(other_branch_manager, published_course):
    """A notice the other centre set for a whole course.

    The course catalogue is institution-wide; the notice about it is not. It
    carries no batch either, so it meets the same trap as the private one.
    """
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=other_branch_manager,
        title="PUNE: Linux intake rescheduled",
        body="The Pune sitting moves to the 14th.",
        audience=Audience.COURSE,
        course=published_course,
    )
    return publish(announcement=created, actor=other_branch_manager)


@pytest.fixture
def import_b(other_branch_manager):
    """A pending admissions spreadsheet uploaded at the other centre.

    `report` is the parsed file: names, addresses and phone numbers of people
    who have not been admitted anywhere yet. The sibling of `export_job_b`, and
    it leaked for the same reason — `report.view_any` reads as "everything"
    while the role holding it is bounded to one city.
    """
    from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind

    return BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=other_branch_manager,
        original_filename="pune-intake.csv",
        row_count=1,
        valid_count=1,
        status=BulkImportStatus.PREVIEW,
        report={
            "rows": [
                {
                    "line": 2,
                    "email": "pune.prospect@example.test",
                    "first_name": "Pooja",
                    "last_name": "Deshmukh",
                    "phone": "9999900000",
                }
            ],
            "errors": [],
            "summary": {"read": 1, "valid": 1, "errors": 0},
        },
    )


@pytest.fixture
def import_a(manager_user):
    from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind

    return BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=manager_user,
        original_filename="jaipur-intake.csv",
        row_count=1,
        valid_count=1,
        status=BulkImportStatus.PREVIEW,
        report={"rows": [], "errors": [], "summary": {"read": 0, "valid": 0, "errors": 0}},
    )


@pytest.fixture
def review_b(unbounded_superadmin, other_branch_student):
    from apps.performance.services import create_review

    today = timezone.localdate()
    return create_review(
        actor=unbounded_superadmin,
        student=other_branch_student,
        period_start=today - timedelta(days=30),
        period_end=today,
        rating=3,
        summary="Doing well.",
    )


@pytest.fixture
def feedback_b(unbounded_superadmin, other_branch_student, other_branch_batch):
    from apps.performance.services import create_feedback

    return create_feedback(
        actor=unbounded_superadmin,
        student=other_branch_student,
        batch=other_branch_batch,
        body="Asked a good question.",
    )


@pytest.fixture
def export_job_b(other_branch_manager):
    """A finished export belonging to the other centre's manager.

    Given a file, because the download route is the one that hands over rows
    rather than merely naming them.
    """
    from django.core.files.base import ContentFile

    from apps.reporting.models import ExportFormat, ExportJob, ExportStatus

    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=other_branch_manager,
        status=ExportStatus.COMPLETED,
        queued_at=timezone.now(),
        finished_at=timezone.now(),
        row_count=1,
        original_filename="pune-students.csv",
    )
    job.file.save("pune-students.csv", ContentFile(b"student_id\nPUNE-0001\n"), save=True)
    return job


@pytest.fixture
def export_job_a(manager_user):
    from apps.reporting.models import ExportFormat, ExportJob, ExportStatus

    return ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=manager_user,
        status=ExportStatus.QUEUED,
        queued_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# URL helpers — string literals, one per endpoint
# ---------------------------------------------------------------------------


def _branches_url() -> str:
    return "/api/v1/branches/"


def _branch_url(branch) -> str:
    return f"/api/v1/branches/{branch.id}/"


def _students_url() -> str:
    return "/api/v1/students/"


def _student_url(profile) -> str:
    return f"/api/v1/students/{profile.id}/"


def _student_fee_url(profile) -> str:
    return f"/api/v1/students/{profile.id}/fee-status/"


def _trainers_url() -> str:
    return "/api/v1/trainers/"


def _trainer_url(profile) -> str:
    return f"/api/v1/trainers/{profile.id}/"


def _trainer_overview_url(profile) -> str:
    return f"/api/v1/trainers/{profile.id}/overview/"


def _users_url() -> str:
    return "/api/v1/users/"


def _user_url(user) -> str:
    return f"/api/v1/users/{user.id}/"


def _user_audit_url(user) -> str:
    return f"/api/v1/users/{user.id}/audit/"


def _user_set_active_url(user) -> str:
    return f"/api/v1/users/{user.id}/set-active/"


def _user_branch_url(user) -> str:
    return f"/api/v1/users/{user.id}/branch/"


def _batches_url() -> str:
    return "/api/v1/batches/"


def _batch_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/"


def _batch_overview_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/overview/"


def _batch_students_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/students/"


def _batch_roster_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/roster/"


def _batch_trainer_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/trainer/"


def _enrollments_url() -> str:
    return "/api/v1/enrollments/"


def _enrollment_url(enrollment) -> str:
    return f"/api/v1/enrollments/{enrollment.id}/"


def _enrollment_attendance_url(enrollment) -> str:
    return f"/api/v1/enrollments/{enrollment.id}/attendance/"


def _enrollment_progress_url(enrollment) -> str:
    return f"/api/v1/progress/enrollments/{enrollment.id}/"


def _sessions_url() -> str:
    return "/api/v1/sessions/"


def _session_url(session) -> str:
    return f"/api/v1/sessions/{session.id}/"


def _dsr_list_url() -> str:
    return "/api/v1/dsr/"


def _dsr_url(dsr) -> str:
    return f"/api/v1/dsr/{dsr.id}/"


def _assessments_url() -> str:
    return "/api/v1/assessments/"


def _assessment_url(assessment) -> str:
    return f"/api/v1/assessments/{assessment.id}/"


def _exams_url() -> str:
    return "/api/v1/exams/"


def _exam_url(exam) -> str:
    return f"/api/v1/exams/{exam.id}/"


def _assignments_url() -> str:
    return "/api/v1/assignments/"


def _assignment_url(assignment) -> str:
    return f"/api/v1/assignments/{assignment.id}/"


def _projects_url() -> str:
    return "/api/v1/projects/"


def _project_url(project) -> str:
    return f"/api/v1/projects/{project.id}/"


def _announcements_url() -> str:
    return "/api/v1/announcements/"


def _announcement_url(announcement) -> str:
    return f"/api/v1/announcements/{announcement.id}/"


def _announcement_audience_url(announcement) -> str:
    return f"/api/v1/announcements/{announcement.id}/audience/"


def _announcement_publish_url(announcement) -> str:
    return f"/api/v1/announcements/{announcement.id}/publish/"


def _announcement_archive_url(announcement) -> str:
    return f"/api/v1/announcements/{announcement.id}/archive/"


def _import_url(run) -> str:
    return f"/api/v1/imports/{run.id}/"


def _import_confirm_url(run) -> str:
    return f"/api/v1/imports/{run.id}/confirm/"


def _import_reject_url(run) -> str:
    return f"/api/v1/imports/{run.id}/reject/"


def _reviews_url() -> str:
    return "/api/v1/performance/reviews/"


def _review_url(review) -> str:
    return f"/api/v1/performance/reviews/{review.id}/"


def _feedback_list_url() -> str:
    return "/api/v1/performance/feedback/"


def _feedback_url(feedback) -> str:
    return f"/api/v1/performance/feedback/{feedback.id}/"


def _export_jobs_url() -> str:
    return "/api/v1/reports/exports/"


def _export_job_url(job) -> str:
    return f"/api/v1/reports/exports/{job.id}/"


def _export_job_download_url(job) -> str:
    return f"/api/v1/reports/exports/{job.id}/download/"


def _export_job_cancel_url(job) -> str:
    return f"/api/v1/reports/exports/{job.id}/cancel/"


def _report_url(key: str) -> str:
    return f"/api/v1/reports/{key}/"


def _report_export_url(key: str) -> str:
    return f"/api/v1/reports/{key}/export/"


def _manager_dashboard_url() -> str:
    return "/api/v1/dashboards/manager/"


def _admin_dashboard_url() -> str:
    return "/api/v1/dashboards/admin/"


def _batch_summaries_url() -> str:
    return "/api/v1/dashboards/batches/"


def _calendar_url() -> str:
    return "/api/v1/calendar/"


def _recycle_bin_url(label: str) -> str:
    return f"/api/v1/recovery/{label}/"


def _restore_url(label: str, record_id) -> str:
    return f"/api/v1/recovery/{label}/{record_id}/restore/"


def _rows(response) -> list:
    """The rows in a response, paginated or not."""
    body = response.json()
    if isinstance(body, dict) and "results" in body:
        return body["results"]
    return body


def _row_ids(response) -> set[str]:
    return {str(row["id"]) for row in _rows(response)}


# ---------------------------------------------------------------------------
# List endpoints — the four questions, over HTTP
# ---------------------------------------------------------------------------
#
# One parametrised sweep instead of forty near-identical tests. The parameter is
# carried into every assertion message, so a failure names the endpoint.

#: (path, fixture holding the row that must appear, fixture that must not)
_SCOPED_LISTS = [
    ("/api/v1/branches/", "branch", "other_branch"),
    ("/api/v1/batches/", "batch", "other_branch_batch"),
    ("/api/v1/students/", "student_profile", "other_branch_student"),
    ("/api/v1/trainers/", "trainer_profile", "other_branch_trainer"),
    ("/api/v1/enrollments/", "enrollment", "other_branch_enrollment"),
    ("/api/v1/sessions/", "session_a", "session_b"),
    ("/api/v1/dsr/", "dsr_a", "dsr_b"),
    ("/api/v1/assessments/", "assessment_a", "assessment_b"),
    ("/api/v1/exams/", "exam_a", "exam_b"),
    ("/api/v1/assignments/", "assignment_a", "assignment_b"),
    ("/api/v1/projects/", "project_a", "project_b"),
    ("/api/v1/announcements/", "announcement_a", "announcement_b"),
]


def test_the_list_endpoint_sweep_covers_every_scoped_list():
    """Vacuity guard: a sweep over an empty list passes without asserting anything."""
    assert len(_SCOPED_LISTS) >= 12
    assert len({path for path, _, _ in _SCOPED_LISTS}) == len(_SCOPED_LISTS)


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "mine", "theirs"), _SCOPED_LISTS)
def test_a_manager_lists_their_own_centres_rows_and_not_the_other_centres(
    path, mine, theirs, api_client_no_csrf, manager_user, request
):
    ours = request.getfixturevalue(mine)
    theirs_row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(path)

    assert response.status_code == 200, (path, response.data)
    ids = _row_ids(response)
    assert str(ours.id) in ids, path
    assert str(theirs_row.id) not in ids, path


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "mine", "theirs"), _SCOPED_LISTS)
def test_a_platform_operator_lists_both_centres_rows(
    path, mine, theirs, api_client_no_csrf, unbounded_superadmin, request
):
    """The positive half of the sweep: the rule is a filter, not a denial."""
    ours = request.getfixturevalue(mine)
    theirs_row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get(path)

    assert response.status_code == 200, (path, response.data)
    ids = _row_ids(response)
    assert {str(ours.id), str(theirs_row.id)} <= ids, path


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "mine", "theirs"), _SCOPED_LISTS)
def test_a_manager_with_no_centre_lists_nothing(
    path, mine, theirs, api_client_no_csrf, branchless_manager, request
):
    """Fail closed, at the boundary. The account still authenticates, still
    holds every manager capability, and still sees no rows."""
    ours = request.getfixturevalue(mine)
    theirs_row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(branchless_manager)
    response = api_client_no_csrf.get(path)

    assert response.status_code == 200, (path, response.data)
    ids = _row_ids(response)
    assert str(ours.id) not in ids, path
    assert str(theirs_row.id) not in ids, path


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "mine", "theirs"), _SCOPED_LISTS)
def test_an_anonymous_caller_is_refused_rather_than_erroring(
    path, mine, theirs, api_client_no_csrf, request
):
    """The scoping helpers are called above the authenticated guard, so a
    missing first line in `is_unbounded` shows up here as a 500."""
    request.getfixturevalue(mine)
    request.getfixturevalue(theirs)

    response = api_client_no_csrf.get(path)
    assert response.status_code in (401, 403), (path, response.status_code)


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "mine", "theirs"), _SCOPED_LISTS)
def test_a_deactivated_manager_is_refused_rather_than_erroring(
    path, mine, theirs, api_client_no_csrf, manager_user, request
):
    request.getfixturevalue(mine)
    request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(manager_user)
    manager_user.is_active = False
    manager_user.save(update_fields=["is_active"])

    response = api_client_no_csrf.get(path)
    assert response.status_code in (401, 403), (path, response.status_code)


@pytest.mark.django_db
def test_a_counsellor_lists_their_own_centres_admissions_and_nothing_else(
    api_client_no_csrf,
    counsellor_user,
    student_profile,
    other_branch_student,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
):
    """Admissions is the counsellor's whole job, so their student list is the
    one where another centre's names would do the most damage."""
    api_client_no_csrf.force_login(counsellor_user)

    students = api_client_no_csrf.get(_students_url())
    assert students.status_code == 200, students.data
    assert str(student_profile.id) in _row_ids(students)
    assert str(other_branch_student.id) not in _row_ids(students)

    batches = api_client_no_csrf.get(_batches_url())
    assert batches.status_code == 200, batches.data
    assert str(batch.id) in _row_ids(batches)
    assert str(other_branch_batch.id) not in _row_ids(batches)

    enrollments = api_client_no_csrf.get(_enrollments_url())
    assert enrollments.status_code == 200, enrollments.data
    assert str(enrollment.id) in _row_ids(enrollments)
    assert str(other_branch_enrollment.id) not in _row_ids(enrollments)


@pytest.mark.django_db
def test_the_other_centres_manager_sees_the_mirror_image(
    api_client_no_csrf, other_branch_manager, batch, other_branch_batch
):
    """Neither direction is privileged; "A sees only A" must not be passing
    because B happens to be invisible to everybody."""
    api_client_no_csrf.force_login(other_branch_manager)
    response = api_client_no_csrf.get(_batches_url())

    assert response.status_code == 200, response.data
    assert _row_ids(response) == {str(other_branch_batch.id)}


@pytest.mark.django_db
def test_the_account_list_shows_a_manager_only_their_own_centres_people(
    api_client_no_csrf, manager_user, admin_user, other_branch_manager, unbounded_superadmin
):
    """Listing every account in the institution while seeing none of their
    batches is the inconsistency people report as a data leak."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_users_url())

    assert response.status_code == 200, response.data
    ids = _row_ids(response)
    assert str(manager_user.id) in ids
    assert str(admin_user.id) in ids
    assert str(other_branch_manager.id) not in ids
    # A superadmin carries no centre, so a bounded caller cannot see them either.
    assert str(unbounded_superadmin.id) not in ids


@pytest.mark.django_db
def test_the_certificate_list_is_scoped_through_the_batch_hub(
    api_client_no_csrf, manager_user, enrollment, other_branch_enrollment
):
    from apps.certificates.models import Certificate
    from apps.progress.models import CourseCompletion

    def _certificate(enrolment):
        completion = CourseCompletion.objects.create(enrollment=enrolment)
        return Certificate.objects.create(
            completion=completion,
            number=f"CERT-{str(completion.pk)[:8]}",
            student_name=enrolment.student.user.get_full_name(),
            student_code=enrolment.student.student_id,
            course_title=enrolment.batch.course.title,
            batch_code=enrolment.batch.code,
            completion_date=timezone.localdate(),
            verification_code=str(completion.pk)[:12],
        )

    mine = _certificate(enrollment)
    theirs = _certificate(other_branch_enrollment)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get("/api/v1/certificates/")

    assert response.status_code == 200, response.data
    ids = _row_ids(response)
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids


# ---------------------------------------------------------------------------
# Ids from the URL — 404, never 403
# ---------------------------------------------------------------------------
#
# 403 would confirm the id names a real record. That is the whole difference
# between "there is nothing here" and "there is something here you may not
# have", and for a record in another city only the first is true.

#: (label, url helper, fixture holding the other centre's record)
_CROSS_BRANCH_DETAIL_ROUTES = [
    ("branch", _branch_url, "other_branch"),
    ("batch", _batch_url, "other_branch_batch"),
    ("batch overview", _batch_overview_url, "other_branch_batch"),
    ("batch students", _batch_students_url, "other_branch_batch"),
    ("batch roster", _batch_roster_url, "other_branch_batch"),
    ("student", _student_url, "other_branch_student"),
    ("trainer", _trainer_url, "other_branch_trainer"),
    ("trainer overview", _trainer_overview_url, "other_branch_trainer"),
    ("user", _user_url, "other_branch_manager"),
    ("user audit", _user_audit_url, "other_branch_manager"),
    ("enrolment", _enrollment_url, "other_branch_enrollment"),
    ("enrolment attendance", _enrollment_attendance_url, "other_branch_enrollment"),
    ("enrolment progress", _enrollment_progress_url, "other_branch_enrollment"),
    ("session", _session_url, "session_b"),
    ("dsr", _dsr_url, "dsr_b"),
    ("assessment", _assessment_url, "assessment_b"),
    ("exam", _exam_url, "exam_b"),
    ("assignment", _assignment_url, "assignment_b"),
    ("project", _project_url, "project_b"),
    ("announcement", _announcement_url, "announcement_b"),
    # Three announcements, not one, because the batch notice above is the only
    # audience that carries a batch — and a batch is the thing stamped with a
    # centre. The other three audiences are all `batch IS NULL`, which is the
    # shape that was being read as "institution-wide" and served everywhere.
    ("private announcement", _announcement_url, "private_announcement_b"),
    ("private announcement audience", _announcement_audience_url, "private_announcement_b"),
    ("course announcement", _announcement_url, "course_announcement_b"),
    ("draft announcement", _announcement_url, "draft_announcement_b"),
    ("review", _review_url, "review_b"),
    ("export job", _export_job_url, "export_job_b"),
    ("export download", _export_job_download_url, "export_job_b"),
    ("bulk import", _import_url, "import_b"),
]


def test_the_detail_route_sweep_covers_every_id_taking_endpoint():
    """Vacuity guard."""
    assert len(_CROSS_BRANCH_DETAIL_ROUTES) >= 28


@pytest.mark.django_db
@pytest.mark.parametrize(("label", "url_for", "theirs"), _CROSS_BRANCH_DETAIL_ROUTES)
def test_an_administrator_cannot_fetch_another_centres_record_by_its_real_id(
    label, url_for, theirs, api_client_no_csrf, admin_user, request
):
    """An administrator, because they hold the widest capability set that is
    still bounded — if anybody reaches across, it is them."""
    row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(url_for(row))

    assert response.status_code == 404, (label, response.status_code, response.data)


@pytest.mark.django_db
@pytest.mark.parametrize(("label", "url_for", "theirs"), _CROSS_BRANCH_DETAIL_ROUTES)
def test_a_platform_operator_can_fetch_either_centres_record_by_id(
    label, url_for, theirs, api_client_no_csrf, unbounded_superadmin, request
):
    """The positive half: a 404 everywhere would also pass the test above."""
    row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get(url_for(row))

    assert response.status_code != 404, (label, response.status_code)


#: Sub-resources reached through *another* record's id in the URL. Listed
#: separately from the detail routes above because the id being guessed is the
#: parent's: a leak here hands over a whole batch's register, marks or reports
#: rather than one row.
_CROSS_BRANCH_SUBRESOURCE_ROUTES = [
    ("batch sessions", "/api/v1/batches/{id}/sessions/", "other_branch_batch"),
    ("batch dsr", "/api/v1/batches/{id}/dsr/", "other_branch_batch"),
    ("batch timeline", "/api/v1/batches/{id}/timeline/", "other_branch_batch"),
    ("batch schedules", "/api/v1/batches/{id}/schedules/", "other_branch_batch"),
    ("batch performance", "/api/v1/batches/{id}/performance/", "other_branch_batch"),
    ("batch trainer history", "/api/v1/batches/{id}/trainer-history/", "other_branch_batch"),
    ("session register", "/api/v1/sessions/{id}/register/", "session_b"),
    ("session dsr", "/api/v1/sessions/{id}/dsr/", "session_b"),
    ("assessment marks", "/api/v1/assessments/{id}/marks/", "assessment_b"),
    ("assignment submissions", "/api/v1/assignments/{id}/submissions/", "assignment_b"),
    ("exam attempts", "/api/v1/exams/{id}/attempts/", "exam_b"),
    ("exam readiness", "/api/v1/exams/{id}/readiness/", "exam_b"),
    ("project submissions", "/api/v1/projects/{id}/submissions/", "project_b"),
]


def test_the_sub_resource_sweep_covers_the_drill_downs():
    """Vacuity guard."""
    assert len(_CROSS_BRANCH_SUBRESOURCE_ROUTES) >= 13


@pytest.mark.django_db
@pytest.mark.parametrize(("label", "template", "theirs"), _CROSS_BRANCH_SUBRESOURCE_ROUTES)
def test_a_drill_down_through_another_centres_id_finds_nothing(
    label, template, theirs, api_client_no_csrf, admin_user, request
):
    """The parent id is the one being guessed here, so a 200 does not leak one
    record — it leaks a register, a mark sheet or a batch's reports."""
    row = request.getfixturevalue(theirs)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(template.format(id=row.id))

    assert response.status_code == 404, (label, response.status_code, response.data)


#: The same drill-downs that only accept a write. Creating a record *on* another
#: centre's batch is the write half of the same leak: the id is the parent's,
#: and a 201 both confirms the class exists and files a record onto it.
_CROSS_BRANCH_CREATE_ROUTES = [
    (
        "assessment on a batch",
        "/api/v1/batches/{id}/assessments/",
        {"title": "Planted test", "delivery": "offline"},
        "assessments.Assessment",
    ),
    (
        "exam on a batch",
        "/api/v1/batches/{id}/exams/",
        {"title": "Planted exam"},
        "exams.Exam",
    ),
    (
        "discussion thread on a batch",
        "/api/v1/batches/{id}/threads/",
        {"title": "Planted thread", "body": "Anybody there?"},
        "discussions.Thread",
    ),
]


def test_the_create_sweep_covers_the_writes_onto_another_centres_batch():
    """Vacuity guard."""
    assert len(_CROSS_BRANCH_CREATE_ROUTES) >= 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("label", "template", "payload", "model_label"), _CROSS_BRANCH_CREATE_ROUTES
)
def test_a_record_cannot_be_created_on_another_centres_batch(
    label, template, payload, model_label, api_client_no_csrf, admin_user, other_branch_batch
):
    from django.apps import apps as django_apps

    model = django_apps.get_model(model_label)
    before = model.objects.filter(batch=other_branch_batch).count()

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        template.format(id=other_branch_batch.id), payload, format="json"
    )

    assert response.status_code == 404, (label, response.status_code, response.data)
    assert model.objects.filter(batch=other_branch_batch).count() == before, label


@pytest.mark.django_db
def test_the_same_id_is_reachable_from_its_own_centre(
    api_client_no_csrf, other_branch_manager, other_branch_batch
):
    """Proves the 404s above are about the *caller*, not about a record that is
    broken or unreachable by anybody."""
    api_client_no_csrf.force_login(other_branch_manager)
    response = api_client_no_csrf.get(_batch_url(other_branch_batch))
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_setting_a_fee_status_on_another_centres_student_is_a_404_and_writes_nothing(
    api_client_no_csrf, manager_user, other_branch_student
):
    from apps.students.models import FeeStatus

    before = other_branch_student.fee_status
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _student_fee_url(other_branch_student),
        {"fee_status": FeeStatus.PAID, "reason": "Cleared."},
        format="json",
    )

    assert response.status_code == 404, response.data
    other_branch_student.refresh_from_db()
    assert other_branch_student.fee_status == before


@pytest.mark.django_db
def test_deactivating_an_account_at_another_centre_is_a_404_and_writes_nothing(
    api_client_no_csrf, admin_user, other_branch_manager
):
    """A 403 here would tell an administrator in Jaipur that a uuid they
    guessed names a real account in Pune — the enumeration oracle the 404
    discipline exists to close."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _user_set_active_url(other_branch_manager),
        {"is_active": False, "reason": "Left."},
        format="json",
    )

    assert response.status_code == 404, response.data
    other_branch_manager.refresh_from_db()
    assert other_branch_manager.is_active is True


@pytest.mark.django_db
def test_moving_an_account_to_a_centre_the_caller_cannot_see_is_a_404(
    api_client_no_csrf, admin_user, manager_user, other_branch
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _user_branch_url(manager_user),
        {"branch_id": str(other_branch.id), "reason": "Relocating."},
        format="json",
    )

    assert response.status_code == 404, response.data
    manager_user.refresh_from_db()
    assert manager_user.branch_id != other_branch.id


@pytest.mark.django_db
def test_staffing_a_class_with_a_trainer_from_another_centre_is_a_404(
    api_client_no_csrf, admin_user, batch, other_branch_trainer, trainer_profile
):
    """The trainer is resolved out of the caller's own visible trainers, so an
    id they cannot see is not found rather than refused after the fetch."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _batch_trainer_url(batch), {"trainer_id": str(other_branch_trainer.id)}, format="json"
    )

    assert response.status_code == 404, response.data
    batch.refresh_from_db()
    assert batch.trainer_id == trainer_profile.pk


@pytest.mark.django_db
def test_enrolling_a_student_onto_another_centres_class_is_a_404_and_writes_nothing(
    api_client_no_csrf, counsellor_user, student_profile, other_branch_batch
):
    from apps.enrollments.models import Enrollment

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        _enrollments_url(),
        {"student_id": str(student_profile.id), "batch_id": str(other_branch_batch.id)},
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not Enrollment.objects.filter(batch=other_branch_batch, student=student_profile).exists()


@pytest.mark.django_db
def test_enrolling_another_centres_student_is_a_404_and_writes_nothing(
    api_client_no_csrf, counsellor_user, other_branch_student, batch
):
    from apps.enrollments.models import Enrollment

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        _enrollments_url(),
        {"student_id": str(other_branch_student.id), "batch_id": str(batch.id)},
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not Enrollment.objects.filter(batch=batch, student=other_branch_student).exists()


@pytest.mark.django_db
def test_a_project_cannot_be_marked_by_a_trainer_from_another_centre(
    api_client_no_csrf, manager_user, published_course, batch, other_branch_trainer
):
    """The reviewer is an id in the body rather than in the URL, which is the
    same enumeration oracle wearing different clothes — and a project whose
    marker works in another city is a project whose marks leave the centre."""
    from apps.projects.models import Project

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/projects/",
        {
            "title": "Planted reviewer",
            "description": "A tool.",
            "instructions": "Build it.",
            "deliverables": "Source.",
            "batch": str(batch.id),
            "reviewer": str(other_branch_trainer.id),
        },
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not Project.objects.filter(reviewer=other_branch_trainer).exists()


@pytest.mark.django_db
def test_a_performance_review_cannot_be_written_about_another_centres_student(
    api_client_no_csrf, manager_user, other_branch_student
):
    """A write is a read too: a 201 here confirms the person exists, and files a
    review against them that their own centre would then see appear."""
    from apps.performance.models import PerformanceReview

    today = timezone.localdate()
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _reviews_url(),
        {
            "student": str(other_branch_student.id),
            "period_start": str(today - timedelta(days=30)),
            "period_end": str(today),
            "rating": 3,
            "summary": "Filed from another city.",
        },
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not PerformanceReview.objects.filter(student=other_branch_student).exists()


@pytest.mark.django_db
def test_withdrawing_another_centres_feedback_is_a_404_and_leaves_it_in_place(
    api_client_no_csrf, admin_user, feedback_b
):
    """`FeedbackDetailView` takes only DELETE, so it sits outside the GET sweep
    above and needs its own assertion — including that nothing was written."""
    from apps.performance.models import Feedback

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.delete(
        _feedback_url(feedback_b), {"reason": "Withdrawn."}, format="json"
    )

    assert response.status_code == 404, response.data
    assert Feedback.objects.filter(pk=feedback_b.pk).exists()


@pytest.mark.django_db
def test_feedback_cannot_be_written_about_another_centres_trainer(
    api_client_no_csrf, manager_user, other_branch_trainer
):
    from apps.performance.models import Feedback

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _feedback_list_url(),
        {"trainer": str(other_branch_trainer.id), "body": "Filed from another city."},
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not Feedback.objects.filter(trainer=other_branch_trainer).exists()


# ---------------------------------------------------------------------------
# The noticeboard — the audiences that carry no batch
# ---------------------------------------------------------------------------
#
# An announcement's `batch` is null for three of its four audiences, and the
# model's own CheckConstraint says so: `everyone`, `course` and `selected` all
# require it. Only `everyone` is genuinely institution-wide. Reading the other
# two as "belongs to no centre, therefore to all of them" put a notice
# addressed to two named families in Pune on the board of every manager in the
# institution — and, because the same expression backs the manage queryset, let
# them edit it and take it down.


@pytest.mark.django_db
def test_a_notice_addressed_to_another_centres_people_is_not_on_this_boards_list(
    api_client_no_csrf, manager_user, private_announcement_b
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_announcements_url())

    assert response.status_code == 200, response.data
    assert str(private_announcement_b.id) not in _row_ids(response)
    assert "fee default follow-up" not in response.content.decode()


@pytest.mark.django_db
def test_a_notice_another_centre_set_for_a_course_is_not_on_this_boards_list(
    api_client_no_csrf, manager_user, course_announcement_b
):
    """The course is shared; the notice about one centre's sitting of it is not."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_announcements_url())

    assert response.status_code == 200, response.data
    assert str(course_announcement_b.id) not in _row_ids(response)


@pytest.mark.django_db
def test_another_centres_unpublished_draft_is_not_on_this_boards_list(
    api_client_no_csrf, manager_user, draft_announcement_b
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_announcements_url())

    assert response.status_code == 200, response.data
    assert str(draft_announcement_b.id) not in _row_ids(response)


@pytest.mark.django_db
def test_a_notice_addressed_to_everyone_really_does_reach_the_other_centre(
    api_client_no_csrf, other_branch_manager, institution_wide_announcement
):
    """The positive half, and the reason the rule is about the *audience*
    rather than about the null batch: `everyone` means everyone, so narrowing
    it to its author's centre would be a different bug in the other direction."""
    api_client_no_csrf.force_login(other_branch_manager)
    response = api_client_no_csrf.get(_announcements_url())

    assert response.status_code == 200, response.data
    assert str(institution_wide_announcement.id) in _row_ids(response)


@pytest.mark.django_db
def test_editing_another_centres_private_notice_is_a_404_and_changes_nothing(
    api_client_no_csrf, manager_user, private_announcement_b
):
    before = private_announcement_b.title

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.patch(
        _announcement_url(private_announcement_b), {"title": "Hijacked"}, format="json"
    )

    assert response.status_code == 404, response.data
    private_announcement_b.refresh_from_db()
    assert private_announcement_b.title == before


@pytest.mark.django_db
def test_taking_another_centres_private_notice_off_their_board_is_a_404(
    api_client_no_csrf, manager_user, private_announcement_b
):
    from apps.announcements.models import AnnouncementStatus

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _announcement_archive_url(private_announcement_b), {}, format="json"
    )

    assert response.status_code == 404, response.data
    private_announcement_b.refresh_from_db()
    assert private_announcement_b.status == AnnouncementStatus.PUBLISHED


@pytest.mark.django_db
def test_publishing_another_centres_draft_is_a_404_and_leaves_it_a_draft(
    api_client_no_csrf, manager_user, draft_announcement_b
):
    from apps.announcements.models import AnnouncementStatus

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _announcement_publish_url(draft_announcement_b), {}, format="json"
    )

    assert response.status_code == 404, response.data
    draft_announcement_b.refresh_from_db()
    assert draft_announcement_b.status == AnnouncementStatus.DRAFT


@pytest.mark.django_db
def test_a_notice_cannot_be_addressed_to_a_person_at_another_centre(
    api_client_no_csrf, manager_user, other_branch_student
):
    """The write-side twin. Resolving recipients from `User.objects` put a
    notice from one city's manager into another city's student's tray — and
    made the create an existence oracle for account ids, because only a real
    active account survived the filter."""
    from apps.announcements.models import Announcement

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _announcements_url(),
        {
            "title": "Reaching across",
            "body": "You should not be reading this.",
            "audience": "selected",
            "recipients": [str(other_branch_student.user_id)],
        },
        format="json",
    )

    assert response.status_code == 404, response.data
    assert not Announcement.objects.filter(title="Reaching across").exists()


@pytest.mark.django_db
def test_a_notice_can_still_be_addressed_to_a_person_at_the_callers_own_centre(
    api_client_no_csrf, manager_user, student_profile
):
    """The positive half: scoping the recipient lookup must not break the
    endpoint it protects."""
    from apps.announcements.models import Announcement

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _announcements_url(),
        {
            "title": "Fee reminder",
            "body": "Please settle the second instalment.",
            "audience": "selected",
            "recipients": [str(student_profile.user_id)],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    created = Announcement.objects.get(title="Fee reminder")
    assert list(created.recipients.values_list("id", flat=True)) == [student_profile.user_id]


@pytest.mark.django_db
def test_publishing_a_course_notice_tells_only_the_authors_own_centre(
    api_client_no_csrf,
    manager_user,
    enrollment,
    other_branch_enrollment,
    published_course,
):
    """Delivery has to agree with the board. A course notice is readable only
    at the centre that wrote it, so notifying the whole course's students
    everywhere would have handed the other city the message the board withheld."""
    from apps.announcements.models import Audience
    from apps.announcements.services import audience_for, create_announcement, publish
    from apps.notifications.models import Notification

    created = create_announcement(
        actor=manager_user,
        title="Jaipur sitting rescheduled",
        body="The Jaipur sitting moves to the 14th.",
        audience=Audience.COURSE,
        course=published_course,
    )
    reached = audience_for(created)
    publish(announcement=created, actor=manager_user)

    assert enrollment.student.user in reached
    assert other_branch_enrollment.student.user not in reached
    assert not Notification.objects.filter(
        recipient=other_branch_enrollment.student.user, resource_id=str(created.pk)
    ).exists()


# ---------------------------------------------------------------------------
# Bulk imports — a spreadsheet of people who are not students yet
# ---------------------------------------------------------------------------
#
# `report.view_any` sits on the manager and administrator rungs, and both are
# bounded to a centre. `BulkImport` was gated on that capability alone while
# its sibling `ExportJob` one screen away was scoped, so "everything" still
# meant every import in the institution — a parsed admissions file, with names,
# addresses and phone numbers, plus the two buttons that discard it or apply it.


@pytest.mark.django_db
def test_reading_another_centres_import_preview_is_a_404(
    api_client_no_csrf, manager_user, import_b
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_import_url(import_b))

    assert response.status_code == 404, response.data
    assert "pune.prospect@example.test" not in response.content.decode()


@pytest.mark.django_db
def test_rejecting_another_centres_import_is_a_404_and_leaves_it_pending(
    api_client_no_csrf, manager_user, import_b
):
    from apps.reporting.models import BulkImportStatus

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(_import_reject_url(import_b), {}, format="json")

    assert response.status_code == 404, response.data
    import_b.refresh_from_db()
    assert import_b.status == BulkImportStatus.PREVIEW


@pytest.mark.django_db
def test_confirming_another_centres_import_is_a_404_and_admits_nobody(
    api_client_no_csrf, manager_user, import_b
):
    """The worst of the three: confirmation runs `create_student(actor=...)`,
    so another centre's intake list would have been admitted as this centre's
    students, stamped with this centre's branch."""
    from apps.accounts.models import User as UserModel
    from apps.reporting.models import BulkImportStatus

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(_import_confirm_url(import_b), {}, format="json")

    assert response.status_code == 404, response.data
    import_b.refresh_from_db()
    assert import_b.status == BulkImportStatus.PREVIEW
    assert not UserModel.objects.filter(email="pune.prospect@example.test").exists()


@pytest.mark.django_db
def test_a_manager_can_still_open_their_own_centres_import(
    api_client_no_csrf, manager_user, import_a
):
    """The positive half — a 404 for everybody would pass the three above."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_import_url(import_a))

    assert response.status_code == 200, response.data
    assert response.json()["id"] == str(import_a.id)


@pytest.mark.django_db
def test_a_platform_operator_can_open_either_centres_import(
    api_client_no_csrf, unbounded_superadmin, import_a, import_b
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    for run in (import_a, import_b):
        response = api_client_no_csrf.get(_import_url(run))
        assert response.status_code == 200, (run.original_filename, response.data)


@pytest.mark.django_db
def test_an_import_whose_uploader_is_gone_belongs_to_no_centre(
    api_client_no_csrf, manager_user, import_a
):
    """`uploaded_by` is SET_NULL, and the join through it therefore drops the
    orphans. That is the intended answer and the same one `ExportJob` gives: a
    run nobody owns belongs to nobody's centre, rather than to everybody's."""
    import_a.uploaded_by = None
    import_a.save(update_fields=["uploaded_by"])

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_import_url(import_a))

    assert response.status_code == 404, response.data


@pytest.mark.django_db
def test_confirming_an_import_cannot_enrol_into_a_batch_the_confirmer_cannot_open(
    api_client_no_csrf, unbounded_superadmin, manager_user, other_branch_batch
):
    """The stored preview carries a batch id, and it was resolved from
    `Batch.objects`. A preview taken by an operator who can see both centres,
    confirmed by a manager who can see one, must not enrol into the other."""
    from apps.enrollments.models import Enrollment
    from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind

    run = BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=manager_user,
        original_filename="mixed.csv",
        row_count=1,
        valid_count=1,
        status=BulkImportStatus.PREVIEW,
        report={
            "rows": [
                {
                    "line": 2,
                    "email": "new.starter@example.test",
                    "first_name": "Nina",
                    "last_name": "Nayak",
                    "phone": "",
                }
            ],
            "errors": [],
            "summary": {"read": 1, "valid": 1, "errors": 0},
            "batch": {"id": str(other_branch_batch.pk), "code": other_branch_batch.code},
        },
    )
    before = Enrollment.objects.filter(batch=other_branch_batch).count()

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(_import_confirm_url(run), {}, format="json")

    assert response.status_code == 200, response.data
    assert Enrollment.objects.filter(batch=other_branch_batch).count() == before


# ---------------------------------------------------------------------------
# The write half for the one unbounded role
# ---------------------------------------------------------------------------
#
# Every `other_branch_*` fixture in this suite is built by calling the service
# layer directly, because that is the only way to put a record at a centre the
# API would not let the caller name. That convenience hid a hole: no create
# serializer accepted a `branch`, so `resolve_branch_for_new_record` refused
# every write by the one role that is supposed to run more than one centre. A
# suite that only proves refusals passes on a system where nothing works.


@pytest.mark.django_db
def test_a_platform_operator_can_create_a_user_at_a_named_centre(
    api_client_no_csrf, unbounded_superadmin, other_branch
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _users_url(),
        {
            "email": "new.manager@pune.example.test",
            "first_name": "Nikhil",
            "last_name": "Pune",
            "role": UserRole.MANAGER,
            "branch": str(other_branch.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    created = User.objects.get(email="new.manager@pune.example.test")
    assert created.branch_id == other_branch.id


@pytest.mark.django_db
def test_a_platform_operator_creating_a_user_without_naming_a_centre_is_refused(
    api_client_no_csrf, unbounded_superadmin
):
    """The refusal is the point of the field being optional rather than absent:
    a branchless staff account is one that can see nothing."""
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _users_url(),
        {
            "email": "nowhere.manager@example.test",
            "first_name": "Nadia",
            "last_name": "Nowhere",
            "role": UserRole.MANAGER,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "branch" in response.json()["error"]["details"]
    assert not User.objects.filter(email="nowhere.manager@example.test").exists()


@pytest.mark.django_db
def test_a_platform_operator_can_create_a_student_at_a_named_centre(
    api_client_no_csrf, unbounded_superadmin, other_branch
):
    from apps.students.models import StudentProfile

    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _students_url(),
        {
            "email": "new.student@pune.example.test",
            "first_name": "Neha",
            "last_name": "Pune",
            "branch": str(other_branch.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    profile = StudentProfile.objects.get(user__email="new.student@pune.example.test")
    assert profile.branch_id == other_branch.id
    assert profile.user.branch_id == other_branch.id


@pytest.mark.django_db
def test_a_platform_operator_can_create_a_trainer_at_a_named_centre(
    api_client_no_csrf, unbounded_superadmin, other_branch
):
    from apps.trainers.models import TrainerProfile

    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _trainers_url(),
        {
            "email": "new.trainer@pune.example.test",
            "first_name": "Nitin",
            "last_name": "Pune",
            "branch": str(other_branch.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    profile = TrainerProfile.objects.get(user__email="new.trainer@pune.example.test")
    assert profile.branch_id == other_branch.id
    assert profile.user.branch_id == other_branch.id


@pytest.mark.django_db
def test_a_platform_operator_can_create_a_batch_at_a_named_centre(
    api_client_no_csrf, unbounded_superadmin, other_branch, published_course
):
    from apps.batches.models import Batch

    today = timezone.localdate()
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _batches_url(),
        {
            "name": "Linux Essentials — Pune Morning",
            "course": str(published_course.id),
            "start_date": str(today + timedelta(days=7)),
            "end_date": str(today + timedelta(days=90)),
            "capacity": 10,
            "branch": str(other_branch.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    created = Batch.objects.get(name="Linux Essentials — Pune Morning")
    assert created.branch_id == other_branch.id


@pytest.mark.django_db
def test_a_manager_naming_another_centre_on_a_new_record_still_gets_their_own(
    api_client_no_csrf, admin_user, branch, other_branch
):
    """Forced, not validated. A bounded caller who sends a branch id is not
    refused — the worst a wrong id can do is be silently right — because
    refusing would leak which ids name a real centre."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _users_url(),
        {
            "email": "planted@example.test",
            "first_name": "Priya",
            "last_name": "Planted",
            "role": UserRole.MANAGER,
            "branch": str(other_branch.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert User.objects.get(email="planted@example.test").branch_id == branch.id


# ---------------------------------------------------------------------------
# Filters, search and pagination — a parameter must never widen the reach
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_filtering_by_another_centres_branch_id_returns_nothing_rather_than_helping(
    api_client_no_csrf, manager_user, student_profile, other_branch, other_branch_student
):
    """The filter runs *inside* the scoped queryset, so naming the other centre
    intersects to empty. If it ever ran outside one, this is the request an
    attacker would send first — it is one query parameter away from the whole
    institution."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_students_url()}?branch={other_branch.id}")

    assert response.status_code == 200, response.data
    assert _rows(response) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/api/v1/students/", "/api/v1/trainers/", "/api/v1/batches/", "/api/v1/users/"]
)
def test_no_list_can_be_widened_by_naming_the_other_centre(
    path,
    api_client_no_csrf,
    manager_user,
    other_branch,
    other_branch_batch,
    other_branch_student,
    other_branch_trainer,
    other_branch_manager,
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{path}?branch={other_branch.id}")

    assert response.status_code == 200, (path, response.data)
    assert _rows(response) == [], path


@pytest.mark.django_db
def test_filtering_by_the_callers_own_centre_still_returns_their_rows(
    api_client_no_csrf, manager_user, branch, student_profile
):
    """The positive half: the parameter works, it simply cannot reach outward."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_students_url()}?branch={branch.id}")

    assert response.status_code == 200, response.data
    assert str(student_profile.id) in _row_ids(response)


@pytest.mark.django_db
def test_searching_for_a_student_at_another_centre_by_name_finds_nothing(
    api_client_no_csrf, manager_user, other_branch_student
):
    """Search is the parameter most likely to be applied to an unscoped base:
    it is written to be generous."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_students_url()}?search=Pooja")

    assert response.status_code == 200, response.data
    assert _rows(response) == []


@pytest.mark.django_db
def test_searching_a_batch_roster_cannot_reach_another_centres_batch(
    api_client_no_csrf, manager_user, other_branch_batch, other_branch_enrollment
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_batch_students_url(other_branch_batch)}?search=Pooja")
    assert response.status_code == 404, response.data


@pytest.mark.django_db
def test_the_paginated_count_counts_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, batch, other_branch_batch
):
    """The count is computed from a second query against the same queryset. A
    count that included the other centre would leak *how many* classes it runs
    even with every row filtered out of the page."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_batches_url()}?page_size=100")

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["count"] == 1
    assert _row_ids(response) == {str(batch.id)}


@pytest.mark.django_db
def test_walking_every_page_never_turns_up_the_other_centre(
    api_client_no_csrf, manager_user, batch, other_branch_batch
):
    """A page size of one is the cheapest way to prove the filter is on the
    queryset rather than on the page that happened to be returned."""
    api_client_no_csrf.force_login(manager_user)
    seen: set[str] = set()
    page = 1
    while True:
        response = api_client_no_csrf.get(f"{_batches_url()}?page_size=1&page={page}")
        assert response.status_code == 200, response.data
        seen |= _row_ids(response)
        if response.json().get("next") is None:
            break
        page += 1
        assert page < 10, "pagination did not terminate"

    assert seen == {str(batch.id)}


# ---------------------------------------------------------------------------
# Reports, downloads and background export jobs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_report_read_on_screen_covers_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, enrollment, other_branch_enrollment
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_report_url("student_progress"))

    assert response.status_code == 200, response.data
    rendered = str(response.json())
    assert "Pooja" not in rendered
    assert "Enrolled" in rendered


@pytest.mark.django_db
def test_the_csv_download_of_a_report_covers_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, enrollment, other_branch_enrollment
):
    """A file is not a weaker way to read something. The export shares
    `_queryset_for_user` with the screen precisely so the two cannot diverge —
    asserted, because sharing a helper is a claim about today's code."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_report_export_url("student_progress"))

    assert response.status_code == 200
    body = b"".join(response.streaming_content).decode()
    assert "Enrolled" in body
    assert "Pooja" not in body


@pytest.mark.django_db
def test_a_trainer_activity_report_covers_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, trainer_profile, other_branch_trainer
):
    """The trainer source builds its own queryset rather than deriving one, so
    it needs its own assertion: a report naming who works where is a report
    about the institution's staffing."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_report_export_url("trainer_activity"))

    assert response.status_code == 200
    body = b"".join(response.streaming_content).decode()
    assert "Prakash" not in body


@pytest.mark.django_db
def test_a_report_filtered_to_another_centres_batch_is_a_404(
    api_client_no_csrf, manager_user, other_branch_batch
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"{_report_url('attendance')}?batch={other_branch_batch.id}")
    assert response.status_code == 404, response.data


@pytest.mark.django_db
def test_the_export_job_list_shows_only_the_callers_own_centres_jobs(
    api_client_no_csrf, admin_user, export_job_a, export_job_b
):
    """`export.view_any` is an administrator capability, and an administrator is
    bounded to a centre. Without a branch narrowing here it means "every job in
    the institution", which is a list of what every other centre has exported.
    """
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_export_jobs_url())

    assert response.status_code == 200, response.data
    ids = _row_ids(response)
    assert str(export_job_a.id) in ids
    assert str(export_job_b.id) not in ids


@pytest.mark.django_db
def test_a_platform_operator_sees_export_jobs_from_both_centres(
    api_client_no_csrf, unbounded_superadmin, export_job_a, export_job_b
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get(_export_jobs_url())

    assert response.status_code == 200, response.data
    assert {str(export_job_a.id), str(export_job_b.id)} <= _row_ids(response)


@pytest.mark.django_db
def test_an_export_job_whose_requester_is_gone_belongs_to_no_centre(
    api_client_no_csrf, admin_user, unbounded_superadmin, export_job_a
):
    """A job's centre is its requester's, so clearing the requester leaves a
    file that belongs to nobody — and whose rows were rendered from an access
    the system can no longer reconstruct. Bounded callers stop reaching it; a
    platform operator still can, so the row is recoverable rather than lost.
    """
    export_job_a.requested_by = None
    export_job_a.save(update_fields=["requested_by"])

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(_export_job_url(export_job_a)).status_code == 404
    assert str(export_job_a.id) not in _row_ids(api_client_no_csrf.get(_export_jobs_url()))

    api_client_no_csrf.force_login(unbounded_superadmin)
    assert api_client_no_csrf.get(_export_job_url(export_job_a)).status_code == 200


@pytest.mark.django_db
def test_downloading_another_centres_finished_export_is_a_404(
    api_client_no_csrf, admin_user, export_job_b
):
    """The file is already rendered and sitting in storage; this route is the
    one that would hand it over."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_export_job_download_url(export_job_b))
    assert response.status_code == 404, response.status_code


@pytest.mark.django_db
def test_cancelling_another_centres_export_is_a_404_and_leaves_it_alone(
    api_client_no_csrf, admin_user, other_branch_manager
):
    from apps.reporting.models import ExportFormat, ExportJob, ExportStatus

    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=other_branch_manager,
        status=ExportStatus.QUEUED,
        queued_at=timezone.now(),
    )

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(_export_job_cancel_url(job), {}, format="json")

    assert response.status_code == 404, response.data
    job.refresh_from_db()
    assert job.status == ExportStatus.QUEUED


@pytest.mark.django_db
def test_a_background_export_renders_only_the_requesters_own_centre(
    manager_user, enrollment, other_branch_enrollment
):
    """The worker has no request, so it re-derives the scope from the requesting
    user. That re-derivation is the whole of the branch rule on this path: if it
    read a global queryset, the file would be written correctly-looking and
    quietly contain another city."""
    from apps.reporting.models import ExportFormat, ExportJob, ExportStatus
    from apps.reporting.tasks import run_export

    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=manager_user,
        status=ExportStatus.QUEUED,
        queued_at=timezone.now(),
    )

    assert run_export(str(job.id)) is True
    job.refresh_from_db()
    assert job.status == ExportStatus.COMPLETED, job.error

    with job.file.open("rb") as handle:
        body = handle.read().decode()
    assert "Enrolled" in body
    assert "Pooja" not in body


@pytest.mark.django_db
def test_a_background_export_for_an_account_with_no_centre_renders_nothing(
    branchless_manager, enrollment, other_branch_enrollment
):
    """Fail closed in the worker as well as in the request."""
    from apps.reporting.models import ExportFormat, ExportJob, ExportStatus
    from apps.reporting.tasks import run_export

    job = ExportJob.objects.create(
        report_key="student_progress",
        format=ExportFormat.CSV,
        requested_by=branchless_manager,
        status=ExportStatus.QUEUED,
        queued_at=timezone.now(),
    )

    assert run_export(str(job.id)) is True
    job.refresh_from_db()
    assert job.row_count == 0

    with job.file.open("rb") as handle:
        body = handle.read().decode()
    assert "Enrolled" not in body
    assert "Pooja" not in body


# ---------------------------------------------------------------------------
# Dashboards — an aggregate is still somebody's data
# ---------------------------------------------------------------------------
#
# The hardest leak to notice, because the screen looks entirely normal: nobody
# audits a total. `scope_for` was fixed for exactly this reason, and these
# assert the plain counts that sit beside its metrics.


@pytest.mark.django_db
def test_the_manager_dashboard_counts_only_the_callers_own_centre(
    api_client_no_csrf,
    manager_user,
    batch,
    other_branch_batch,
    student_profile,
    other_branch_student,
    trainer_profile,
    other_branch_trainer,
    enrollment,
    other_branch_enrollment,
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_manager_dashboard_url())

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["batches"]["total"] == 1, body["batches"]
    assert body["batches"]["active"] == 1, body["batches"]
    assert body["students"]["total"] == 1, body["students"]
    assert body["trainers"]["total"] == 1, body["trainers"]


@pytest.mark.django_db
def test_scoping_the_manager_dashboard_did_not_turn_it_into_a_query_per_row(
    api_client_no_csrf,
    manager_user,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
    student_profile,
    other_branch_student,
    django_assert_max_num_queries,
):
    """A budget, because the obvious way to scope a set of counts is to walk
    them. 35 is the measured cost plus headroom; it is a ceiling on a fixed set
    of grouped counts, not a licence for one query per batch. `test_performance`
    holds the growth half of this for the admin dashboard through `assert_flat`.
    """
    api_client_no_csrf.force_login(manager_user)
    with django_assert_max_num_queries(35):
        response = api_client_no_csrf.get(_manager_dashboard_url())
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_the_manager_dashboard_of_the_other_centre_counts_its_own(
    api_client_no_csrf,
    other_branch_manager,
    batch,
    other_branch_batch,
    student_profile,
    other_branch_student,
    trainer_profile,
    other_branch_trainer,
):
    api_client_no_csrf.force_login(other_branch_manager)
    response = api_client_no_csrf.get(_manager_dashboard_url())

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["batches"]["total"] == 1, body["batches"]
    assert body["students"]["total"] == 1, body["students"]
    assert body["trainers"]["total"] == 1, body["trainers"]


@pytest.mark.django_db
def test_the_manager_dashboard_shows_a_platform_operator_the_whole_institution(
    api_client_no_csrf,
    unbounded_superadmin,
    batch,
    other_branch_batch,
    student_profile,
    other_branch_student,
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get(_manager_dashboard_url())

    assert response.status_code == 200, response.data
    assert response.json()["batches"]["total"] == 2


@pytest.mark.django_db
def test_the_manager_dashboard_of_an_account_with_no_centre_counts_nothing(
    api_client_no_csrf, branchless_manager, batch, other_branch_batch, student_profile
):
    api_client_no_csrf.force_login(branchless_manager)
    response = api_client_no_csrf.get(_manager_dashboard_url())

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["batches"]["total"] == 0, body["batches"]
    assert body["students"]["total"] == 0, body["students"]
    assert body["trainers"]["total"] == 0, body["trainers"]


@pytest.mark.django_db
def test_the_admin_dashboard_counts_only_the_callers_own_centre(
    api_client_no_csrf,
    admin_user,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
    trainer_profile,
    other_branch_trainer,
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_admin_dashboard_url())

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["active_batches"] == 1, body
    assert body["active_students"] == 1, body
    assert body["active_trainers"] == 1, body


@pytest.mark.django_db
def test_the_admin_dashboard_shows_a_platform_operator_both_centres(
    api_client_no_csrf,
    unbounded_superadmin,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get(_admin_dashboard_url())

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["active_batches"] == 2, body
    assert body["active_students"] == 2, body


@pytest.mark.django_db
def test_the_batch_summaries_hub_lists_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, batch, other_branch_batch
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_batch_summaries_url())

    assert response.status_code == 200, response.data
    codes = {row["code"] for row in _rows(response)}
    assert batch.code in codes
    assert other_branch_batch.code not in codes


@pytest.mark.django_db
def test_the_calendar_shows_only_the_callers_own_centres_classes(
    api_client_no_csrf, manager_user, batch, other_branch_batch, schedule
):
    """Every calendar source resolves through the access layer rather than
    reading its model directly — which is a property of six functions, and only
    a test notices when a seventh is added that does not."""
    api_client_no_csrf.force_login(manager_user)
    start = timezone.localdate()
    end = start + timedelta(days=30)
    response = api_client_no_csrf.get(f"{_calendar_url()}?start={start}&end={end}")

    assert response.status_code == 200, response.data
    events = response.json()["events"]
    batch_ids = {event["batch_id"] for event in events if event.get("batch_id")}
    assert str(batch.id) in batch_ids
    assert str(other_branch_batch.id) not in batch_ids


@pytest.mark.django_db
def test_the_trainer_workload_dashboard_counts_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, batch, other_branch_batch
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get("/api/v1/dashboards/workload/")

    assert response.status_code == 200, response.data
    assert response.json()["batches"] == 1


# ---------------------------------------------------------------------------
# The recycle bin and restore
# ---------------------------------------------------------------------------
#
# The bin itself is deliberately *not* branch-scoped — a deleted record is
# already invisible on every normal screen, and somebody looking for a batch
# that vanished should not have to know which centre it was filed under.
# Restoring is a write that puts a row back into circulation, and is bounded.


@pytest.mark.django_db
def test_restoring_another_centres_batch_is_refused_and_leaves_it_deleted(
    api_client_no_csrf, admin_user, unbounded_superadmin, other_branch_batch
):
    from apps.batches.models import Batch
    from apps.common.deletion import soft_delete

    soft_delete(instance=other_branch_batch, actor=unbounded_superadmin, reason="Closed.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _restore_url("batches.batch", other_branch_batch.id), {}, format="json"
    )

    assert response.status_code == 403, response.data
    assert response.json()["error"]["code"] == "permission_denied"
    # And it says nothing about which centre, which would confirm one exists.
    assert "centre" not in response.json()["error"]["message"].lower()
    assert not Batch.objects.filter(pk=other_branch_batch.pk).exists()


@pytest.mark.django_db
def test_restoring_another_centres_batch_is_audited_as_a_refusal(
    api_client_no_csrf, admin_user, unbounded_superadmin, other_branch_batch
):
    from apps.audit.models import AuditAction, AuditLog, AuditResult
    from apps.common.deletion import soft_delete

    soft_delete(instance=other_branch_batch, actor=unbounded_superadmin, reason="Closed.")

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(_restore_url("batches.batch", other_branch_batch.id), {}, format="json")

    entry = AuditLog.objects.filter(action=AuditAction.PERMISSION_DENIED).latest("created_at")
    assert entry.result == AuditResult.DENIED
    assert entry.context["refused"] == "outside_branch"
    assert entry.context["label"] == "batches.batch"


@pytest.mark.django_db
def test_restoring_the_callers_own_centres_batch_still_works(api_client_no_csrf, admin_user, batch):
    """The positive half, so the guard cannot be satisfied by refusing everybody."""
    from apps.batches.models import Batch
    from apps.common.deletion import soft_delete

    soft_delete(instance=batch, actor=admin_user, reason="Mistake.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(_restore_url("batches.batch", batch.id), {}, format="json")

    assert response.status_code == 200, response.data
    assert Batch.objects.filter(pk=batch.pk).exists()


@pytest.mark.django_db
def test_restoring_another_centres_export_job_is_refused(
    api_client_no_csrf, admin_user, unbounded_superadmin, export_job_b
):
    """An export job's centre is its requester's, since that is whose access the
    worker re-derives its rows from."""
    from apps.common.deletion import soft_delete
    from apps.reporting.models import ExportJob

    soft_delete(instance=export_job_b, actor=unbounded_superadmin, reason="Tidying.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _restore_url("reporting.exportjob", export_job_b.id), {}, format="json"
    )

    assert response.status_code == 403, response.data
    assert not ExportJob.objects.filter(pk=export_job_b.pk).exists()


@pytest.mark.django_db
def test_restoring_another_centres_dsr_is_refused(
    api_client_no_csrf, admin_user, unbounded_superadmin, dsr_b
):
    from apps.common.deletion import soft_delete
    from apps.dsr.models import DSR

    soft_delete(instance=dsr_b, actor=unbounded_superadmin, reason="Filed wrongly.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(_restore_url("dsr.dsr", dsr_b.id), {}, format="json")

    assert response.status_code == 403, response.data
    assert not DSR.objects.filter(pk=dsr_b.pk).exists()


@pytest.mark.django_db
def test_restoring_another_centres_enrolment_is_refused(
    api_client_no_csrf, admin_user, unbounded_superadmin, other_branch_enrollment
):
    from apps.common.deletion import soft_delete
    from apps.enrollments.models import Enrollment

    soft_delete(instance=other_branch_enrollment, actor=unbounded_superadmin, reason="Withdrawn.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _restore_url("enrollments.enrollment", other_branch_enrollment.id), {}, format="json"
    )

    assert response.status_code == 403, response.data
    assert not Enrollment.objects.filter(pk=other_branch_enrollment.pk).exists()


@pytest.mark.django_db
def test_restoring_another_centres_performance_review_is_refused(
    api_client_no_csrf, admin_user, unbounded_superadmin, review_b
):
    """A review hangs off a person, not a batch, so its centre is reached
    through whichever of student or trainer is set — the one entry in
    `BRANCH_PATHS` that is a callable rather than a dotted path."""
    from apps.common.deletion import soft_delete
    from apps.performance.models import PerformanceReview

    soft_delete(instance=review_b, actor=unbounded_superadmin, reason="Superseded.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _restore_url("performance.performancereview", review_b.id), {}, format="json"
    )

    assert response.status_code == 403, response.data
    assert not PerformanceReview.objects.filter(pk=review_b.pk).exists()


@pytest.mark.django_db
def test_an_administrator_with_no_centre_may_restore_nothing(
    api_client_no_csrf, branchless_admin, admin_user, batch
):
    from apps.batches.models import Batch
    from apps.common.deletion import soft_delete

    soft_delete(instance=batch, actor=admin_user, reason="Mistake.")

    api_client_no_csrf.force_login(branchless_admin)
    response = api_client_no_csrf.post(_restore_url("batches.batch", batch.id), {}, format="json")

    assert response.status_code == 403, response.data
    assert not Batch.objects.filter(pk=batch.pk).exists()


@pytest.mark.django_db
def test_a_platform_operator_may_restore_either_centres_record(
    api_client_no_csrf, unbounded_superadmin, other_branch_batch
):
    from apps.batches.models import Batch
    from apps.common.deletion import soft_delete

    soft_delete(instance=other_branch_batch, actor=unbounded_superadmin, reason="Closed.")

    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.post(
        _restore_url("batches.batch", other_branch_batch.id), {}, format="json"
    )

    assert response.status_code == 200, response.data
    assert Batch.objects.filter(pk=other_branch_batch.pk).exists()


@pytest.mark.django_db
def test_the_recycle_bin_deliberately_lists_records_from_every_centre(
    api_client_no_csrf, admin_user, unbounded_superadmin, other_branch_batch
):
    """Recorded as a test because it is a decision, not an omission: a deleted
    record is already invisible on every ordinary screen, and somebody hunting a
    batch that vanished should not need to know which centre it was filed under
    to learn that it was deleted. Restoring it is what stays bounded — see the
    refusals above. If this rule is ever reversed, this test is the one that
    says it was on purpose the first time.
    """
    from apps.common.deletion import soft_delete

    soft_delete(instance=other_branch_batch, actor=unbounded_superadmin, reason="Closed.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_recycle_bin_url("batches.batch"))

    assert response.status_code == 200, response.data
    assert str(other_branch_batch.id) in {str(row["id"]) for row in _rows(response)}


# ---------------------------------------------------------------------------
# Notifications and the signed-in caller's own record
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notifications_reach_only_their_own_recipient(
    api_client_no_csrf, manager_user, other_branch_manager
):
    """Scoped per recipient rather than per centre, which is stricter — recorded
    here so that "notifications are not branch-scoped" reads as a fact somebody
    checked rather than as something nobody looked at."""
    from apps.notifications.models import Notification, NotificationCategory

    theirs = Notification.objects.create(
        recipient=other_branch_manager,
        category=NotificationCategory.ADMINISTRATIVE,
        title="Pune only",
        body="For Pune.",
    )

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get("/api/v1/notifications/")

    assert response.status_code == 200, response.data
    assert str(theirs.id) not in _row_ids(response)


@pytest.mark.django_db
def test_the_signed_in_caller_is_told_which_centre_they_are_in(
    api_client_no_csrf, manager_user, branch
):
    """The screen has to be able to name the place somebody works, and it reads
    it from here."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get("/api/v1/auth/me/")

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["branch_id"] == str(branch.id)
    assert body["branch_code"] == branch.code
    assert body["branch_name"] == branch.name


@pytest.mark.django_db
def test_a_platform_operator_is_told_they_are_in_no_particular_centre(
    api_client_no_csrf, unbounded_superadmin
):
    """`source="branch.id"` on a null relation raises `AttributeError`, so this
    is a 500 on the very first superadmin login if the defaults are ever lost."""
    api_client_no_csrf.force_login(unbounded_superadmin)
    response = api_client_no_csrf.get("/api/v1/auth/me/")

    assert response.status_code == 200, response.data
    body = response.json()
    assert body["branch_id"] is None
    assert body["branch_code"] is None
    assert body["branch_name"] is None


@pytest.mark.django_db
def test_an_administrators_view_of_a_user_names_their_centre(
    api_client_no_csrf, admin_user, manager_user, branch
):
    """The user record shows the centre — the Centre card on that screen is
    built from it — not only the signed-in user's own ``me`` payload."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/users/{manager_user.pk}/")
    assert response.status_code == 200
    assert response.json()["branch_id"] == str(branch.pk)
    assert response.json()["branch_code"] == branch.code
    assert response.json()["branch_name"] == branch.name
