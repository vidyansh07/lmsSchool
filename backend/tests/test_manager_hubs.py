"""The manager hubs — Batches and Trainers.

    "What a manager here wants is two pages that drill all the way down:
    Batches ... Trainers."

Four endpoints, tested in the order a manager would actually use them: the
landing summary (`/dashboards/manager/`), a batch's full picture
(`/batches/<id>/overview/`), its roster
(`/batches/<id>/students/`), and a trainer's full picture
(`/trainers/<id>/overview/`).

Three things every section below returns to, because they are the ones a
rollup gets wrong first: every numeric field is a real number or `None`,
never an absent key or a lying zero; every endpoint is reached through a
scoped queryset, so a trainer's own batch and somebody else's resolve
differently; and the roster and batch-overview query counts are asserted
flat against the number of students, the same discipline
`tests/test_performance.py` holds the rest of the reporting surface to.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.common.identifiers import next_enrolment_code, next_student_id
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.students.models import StudentProfile

MANAGER_URL = "/api/v1/dashboards/manager/"


def _overview_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/overview/"


def _students_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/students/"


def _trainer_url(trainer) -> str:
    return f"/api/v1/trainers/{trainer.id}/overview/"


def _add_students(batch, count: int, *, start: int = 0) -> list[Enrollment]:
    """Enrol `count` more students directly, bypassing capacity and services.

    Mirrors `tests/test_performance.py`'s own helper: the point of a
    flat-query-cost test is data volume without a matching query cost, and a
    bulk insert is how that volume is produced without also producing the
    N+1 the test exists to catch.
    """
    users = User.objects.bulk_create(
        User(
            email=f"hub-perf-{start + index:04d}@perf.grras.invalid",
            first_name="Hub",
            last_name=f"Student {start + index}",
            role=UserRole.STUDENT,
            is_active=True,
        )
        for index in range(count)
    )
    profiles = StudentProfile.objects.bulk_create(
        StudentProfile(user=user, student_id=next_student_id()) for user in users
    )
    return Enrollment.objects.bulk_create(
        Enrollment(
            code=next_enrolment_code(),
            student=profile,
            batch=batch,
            course=batch.course,
            status=EnrollmentStatus.ACTIVE,
            start_date=date.today() - timedelta(days=10),
        )
        for profile in profiles
    )


def _query_count(client, url: str) -> int:
    """The query cost of one GET, measured from a steady state.

    `apps.academics.policies.policy_for` memoises per request, not across
    them — correctly, since a rule change must take effect on the very next
    request. A fixture that calls a service directly (grading a submission,
    say) can warm that memo before the first request of a test ever fires,
    which would make a "small" measurement artificially cheaper than a
    "large" one that runs after the memo has already been reset by the first
    request's own middleware. One throwaway call first means every measured
    call starts from the same place: a freshly reset request scope, exactly
    like a real request that is not the first one of a warm process.
    """
    client.get(url)
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200, (
        f"{url} -> {response.status_code}: {response.content[:500]!r}"
    )
    return len(captured.captured_queries)


def _active_batch(admin_user, course, *, trainer=None, start_date, end_date, capacity=10):
    """An active batch, or — with no trainer — the upcoming one `create_batch`
    leaves behind: `set_batch_status` refuses to activate a batch nobody is
    assigned to teach, so a trainerless batch used to exercise a null
    `trainer` field stays `UPCOMING` rather than being forced active."""
    from apps.batches.models import BatchStatus
    from apps.batches.services import create_batch, set_batch_status

    created = create_batch(
        actor=admin_user,
        name="Hub test batch",
        course=course,
        trainer=trainer,
        start_date=start_date,
        end_date=end_date,
        capacity=capacity,
    )
    if trainer is None:
        return created
    return set_batch_status(batch=created, target=BatchStatus.ACTIVE, actor=admin_user)


def _completed_session(admin_user, batch, *, offset_days: int, topic: str):
    from apps.sessions.models import SessionStatus
    from apps.sessions.services import create_session

    return create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=offset_days),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic=topic,
        status=SessionStatus.COMPLETED,
    )


@pytest.fixture
def graded_batch_work(
    admin_user, trainer_profile, student_profile, published_course, batch, enrollment
):
    """One graded assignment, one recorded test result, one reviewed project.

    Enough for the batch overview's assessments/assignments/projects
    sections to have something other than zero to report on.
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
    from apps.projects.models import ProjectStatus, WorkStatus
    from apps.projects.services import (
        create_project,
        review_project,
        set_project_status,
        student_project_for,
        submit_project,
    )

    assignment = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Roster assignment",
        max_marks=Decimal("100.00"),
    )
    set_assignment_status(
        assignment=assignment, actor=admin_user, status=AssignmentStatus.PUBLISHED
    )
    submission = submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("a.py", b"pass\n")],
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("70.00"))

    test = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Roster test",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )
    set_assessment_status(assessment=test, actor=admin_user, status=AssessmentStatus.PUBLISHED)
    record_result(assessment=test, enrollment=enrollment, actor=admin_user, marks=Decimal("15.00"))

    project = create_project(
        actor=admin_user, course=published_course, batch=batch, title="Roster project"
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)
    work = student_project_for(project=project, student=student_profile)
    submit_project(
        work=work, actor=student_profile.user, files=[SimpleUploadedFile("p.py", b"pass\n")]
    )
    review_project(
        work=work, actor=trainer_profile.user, outcome=WorkStatus.APPROVED, marks=Decimal("18.00")
    )

    return {"assignment": assignment, "assessment": test, "project": project}


# ---------------------------------------------------------------------------
# Two tiny pure functions, tested directly — no database needed for either.
# ---------------------------------------------------------------------------


def test_severity_thresholds():
    from apps.reporting.dashboards import _severity

    assert _severity(1) == "low"
    assert _severity(2) == "medium"
    assert _severity(4) == "medium"
    assert _severity(5) == "high"
    assert _severity(50) == "high"


def test_plural_helper():
    from apps.reporting.dashboards import _plural

    assert _plural(1, "batch", "batches") == "batch"
    assert _plural(2, "batch", "batches") == "batches"
    assert _plural(0, "batch", "batches") == "batches"
    assert _plural(1, "trainer") == "trainer"
    assert _plural(3, "trainer") == "trainers"


# ---------------------------------------------------------------------------
# Access — every role, every endpoint.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, batch, trainer_profile):
    for url in (
        MANAGER_URL,
        _overview_url(batch),
        _students_url(batch),
        _trainer_url(trainer_profile),
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


@pytest.mark.django_db
def test_a_student_is_refused_every_manager_hub_endpoint(
    api_client_no_csrf, student_profile, batch, trainer_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    for url in (
        MANAGER_URL,
        _overview_url(batch),
        _students_url(batch),
        _trainer_url(trainer_profile),
    ):
        assert api_client_no_csrf.get(url).status_code == 403, url


@pytest.mark.django_db
def test_a_counsellor_is_refused_every_manager_hub_endpoint(
    api_client_no_csrf, counsellor_user, batch, trainer_profile, enrollment
):
    """A counsellor holds `batch.view_any` but not `report.view_any` — the
    hubs are staff-facing reporting, not the admissions screens counsellors
    already have."""
    api_client_no_csrf.force_login(counsellor_user)
    for url in (
        MANAGER_URL,
        _overview_url(batch),
        _students_url(batch),
        _trainer_url(trainer_profile),
    ):
        assert api_client_no_csrf.get(url).status_code == 403, url


@pytest.mark.django_db
def test_a_manager_sees_every_endpoint(
    api_client_no_csrf, manager_user, batch, trainer_profile, enrollment
):
    api_client_no_csrf.force_login(manager_user)
    for url in (
        MANAGER_URL,
        _overview_url(batch),
        _students_url(batch),
        _trainer_url(trainer_profile),
    ):
        assert api_client_no_csrf.get(url).status_code == 200, url


# ---------------------------------------------------------------------------
# GET /dashboards/manager/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_manager_dashboard_shape(api_client_no_csrf, admin_user, batch, enrollment):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    assert set(body) == {"batches", "students", "trainers", "attention", "as_of"}
    assert set(body["batches"]) == {"total", "active", "behind_schedule", "at_risk"}
    assert set(body["students"]) == {"total", "active", "at_risk"}
    assert set(body["trainers"]) == {"total", "with_overdue_dsr"}
    assert isinstance(body["attention"], list)
    assert date.fromisoformat(body["as_of"]) == timezone.localdate()
    for row in body["attention"]:
        assert set(row) == {"kind", "label", "count", "href", "severity"}
        assert row["severity"] in ("low", "medium", "high")
        assert row["count"] > 0


@pytest.mark.django_db
def test_manager_dashboard_refused_for_a_trainer(api_client_no_csrf, trainer_profile):
    """Narrower than `can_read_reports`: a trainer has their own workload and
    batch screens; this one rolls up the whole institution."""
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(MANAGER_URL).status_code == 403


@pytest.mark.django_db
def test_manager_dashboard_counts_reflect_the_institution(
    api_client_no_csrf, manager_user, batch, enrollment, other_enrollment, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    assert body["batches"]["total"] == 1
    assert body["batches"]["active"] == 1
    assert body["students"]["active"] == 2
    assert body["trainers"]["total"] == 1


@pytest.mark.django_db
def test_manager_dashboard_attention_is_empty_when_nothing_needs_it(
    api_client_no_csrf, manager_user
):
    """An institution with nothing in it yet has nothing to flag — and the
    screen is meant to say exactly that, not show a placeholder."""
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    assert body["attention"] == []
    assert body["batches"] == {"total": 0, "active": 0, "behind_schedule": 0, "at_risk": 0}
    assert body["students"] == {"total": 0, "active": 0, "at_risk": 0}
    assert body["trainers"] == {"total": 0, "with_overdue_dsr": 0}


@pytest.mark.django_db
def test_manager_dashboard_attention_lists_dsr_pending_review(
    api_client_no_csrf, manager_user, admin_user, trainer_profile, batch
):
    from apps.dsr.services import start_dsr, submit_dsr

    session = _completed_session(admin_user, batch, offset_days=1, topic="Needs review")
    dsr = start_dsr(session=session, actor=trainer_profile.user)
    submit_dsr(dsr=dsr, actor=trainer_profile.user)

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    item = next(row for row in body["attention"] if row["kind"] == "dsr_pending_review")
    assert item["count"] == 1
    assert item["severity"] == "low"
    assert "dsr" in item["href"]


@pytest.mark.django_db
def test_manager_dashboard_counts_a_batch_behind_schedule(
    api_client_no_csrf, manager_user, admin_user, trainer_profile, published_course
):
    from apps.progress.reports import timeline_progress

    behind = _active_batch(
        admin_user,
        published_course,
        trainer=trainer_profile,
        start_date=timezone.localdate() - timedelta(days=40),
        end_date=timezone.localdate() + timedelta(days=27),
        capacity=5,
    )
    _completed_session(admin_user, behind, offset_days=35, topic="Nothing covered yet")
    # This session was created COMPLETED without ever recording a covered
    # lesson, so `percent_complete` stays 0 while 40 of 67 days have passed.
    assert timeline_progress(behind)["status"] == "behind"

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    assert body["batches"]["behind_schedule"] == 1
    item = next(row for row in body["attention"] if row["kind"] == "batches_behind_schedule")
    assert item["count"] == 1


@pytest.mark.django_db
def test_manager_dashboard_and_batch_overview_agree_on_at_risk_students(
    api_client_no_csrf, manager_user, admin_user, trainer_profile, batch, enrollment
):
    """The same bulk risk gather feeds the KPI strip, the attention queue and
    the batch overview beneath it — proven by checking all three agree."""
    for day in range(4):
        session = _completed_session(admin_user, batch, offset_days=day + 1, topic=f"Class {day}")
        from apps.attendance.services import mark_attendance

        mark_attendance(
            session=session,
            actor=trainer_profile.user,
            entries=[
                {
                    "enrollment_id": str(enrollment.pk),
                    "status": "present" if day == 0 else "absent",
                }
            ],
        )

    api_client_no_csrf.force_login(manager_user)
    dashboard = api_client_no_csrf.get(MANAGER_URL).json()
    assert dashboard["students"]["at_risk"] == 1
    assert dashboard["batches"]["at_risk"] == 1
    item = next(row for row in dashboard["attention"] if row["kind"] == "students_at_risk")
    assert item["count"] == 1

    overview = api_client_no_csrf.get(_overview_url(batch)).json()
    assert overview["students"]["at_risk"] == 1

    roster = api_client_no_csrf.get(_students_url(batch)).json()
    row = next(r for r in roster["results"] if r["enrollment_id"] == str(enrollment.pk))
    assert "attendance" in row["risk_flags"]


@pytest.mark.django_db
def test_manager_dashboard_attention_lists_trainer_reviews_outstanding(
    api_client_no_csrf, manager_user, trainer_profile
):
    from apps.trainers.models import TrainerProfile

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()

    item = next(row for row in body["attention"] if row["kind"] == "trainer_reviews_outstanding")
    assert item["count"] == TrainerProfile.objects.count()
    assert "trainers" in item["href"]


@pytest.mark.django_db
def test_manager_dashboard_a_reviewed_trainer_drops_off_the_outstanding_queue(
    api_client_no_csrf, manager_user, trainer_profile
):
    from apps.performance.services import create_review

    create_review(
        actor=manager_user,
        trainer=trainer_profile,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        rating=4,
    )

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()
    kinds = {row["kind"] for row in body["attention"]}
    assert "trainer_reviews_outstanding" not in kinds


@pytest.mark.django_db
def test_manager_dashboard_counts_trainers_with_overdue_dsr(
    api_client_no_csrf, manager_user, admin_user, trainer_profile, batch
):
    _completed_session(admin_user, batch, offset_days=1, topic="Never reported")

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(MANAGER_URL).json()
    assert body["trainers"]["with_overdue_dsr"] == 1


@pytest.mark.django_db
def test_the_bulk_behind_schedule_check_agrees_with_timeline_progress(
    admin_user, trainer_profile, published_course
):
    """The guarantee that makes the bulk check safe: a batch clearly behind
    and a batch clearly not must sort into the same buckets `timeline_progress`
    itself would put them in — the same discipline `test_reporting.py` holds
    `metrics.by_batch` to."""
    from apps.batches.models import Batch
    from apps.progress.reports import timeline_progress
    from apps.reporting.dashboards import _behind_schedule_batch_ids

    behind = _active_batch(
        admin_user,
        published_course,
        trainer=trainer_profile,
        start_date=timezone.localdate() - timedelta(days=40),
        end_date=timezone.localdate() + timedelta(days=27),
        capacity=5,
    )
    _completed_session(admin_user, behind, offset_days=35, topic="No progress")

    fresh = _active_batch(
        admin_user,
        published_course,
        trainer=trainer_profile,
        start_date=timezone.localdate() - timedelta(days=1),
        end_date=timezone.localdate() + timedelta(days=66),
        capacity=5,
    )
    _completed_session(admin_user, fresh, offset_days=1, topic="Day one")

    ids = _behind_schedule_batch_ids(Batch.objects.filter(pk__in=[behind.pk, fresh.pk]))

    assert behind.pk in ids
    assert fresh.pk not in ids
    assert (behind.pk in ids) == (timeline_progress(behind)["status"] == "behind")
    assert (fresh.pk in ids) == (timeline_progress(fresh)["status"] == "behind")


# ---------------------------------------------------------------------------
# GET /batches/<id>/overview/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_overview_shape(api_client_no_csrf, admin_user, batch, enrollment):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()

    assert set(body) == {
        "batch",
        "course",
        "trainer",
        "attendance",
        "timeline",
        "sessions",
        "dsr",
        "assessments",
        "assignments",
        "projects",
        "students",
        "as_of",
    }
    assert set(body["batch"]) == {
        "id",
        "code",
        "name",
        "kind",
        "status",
        "delivery_mode",
        "start_date",
        "end_date",
        "capacity",
        "seats_taken",
    }
    assert set(body["course"]) == {"id", "title", "code"}
    assert set(body["trainer"]) == {"id", "name", "trainer_id"}
    assert set(body["attendance"]) == {"percentage", "present", "absent", "total_sessions"}
    assert set(body["sessions"]) == {"total", "completed", "cancelled", "upcoming"}
    assert set(body["dsr"]) == {"expected", "submitted", "approved", "pending_review", "overdue"}
    assert set(body["assessments"]) == {"total", "completed", "average_percent"}
    assert set(body["assignments"]) == {"total", "submitted", "graded"}
    assert set(body["projects"]) == {"total", "submitted", "reviewed"}
    assert set(body["students"]) == {"total", "active", "at_risk"}
    assert date.fromisoformat(body["as_of"]) == timezone.localdate()


@pytest.mark.django_db
def test_batch_overview_empty_batch_has_null_percentages_and_zero_counts(
    api_client_no_csrf, admin_user, published_course
):
    empty = _active_batch(
        admin_user,
        published_course,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=60),
    )

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(empty)).json()

    assert body["trainer"] is None
    assert body["attendance"] == {
        "percentage": None,
        "present": 0,
        "absent": 0,
        "total_sessions": 0,
    }
    assert body["timeline"]["percent_complete"] is None
    assert body["timeline"]["percent_expected"] is None
    assert body["timeline"]["status"] == "not_started"
    assert body["sessions"] == {"total": 0, "completed": 0, "cancelled": 0, "upcoming": 0}
    assert body["dsr"] == {
        "expected": 0,
        "submitted": 0,
        "approved": 0,
        "pending_review": 0,
        "overdue": 0,
    }
    assert body["assessments"] == {"total": 0, "completed": 0, "average_percent": None}
    assert body["assignments"] == {"total": 0, "submitted": 0, "graded": 0}
    assert body["projects"] == {"total": 0, "submitted": 0, "reviewed": 0}
    assert body["students"] == {"total": 0, "active": 0, "at_risk": 0}
    assert body["batch"]["seats_taken"] == 0


@pytest.mark.django_db
def test_batch_overview_batch_with_no_trainer_returns_null(
    api_client_no_csrf, admin_user, published_course, student_profile
):
    """Not the empty-batch case: this batch has a student on it, just nobody
    assigned to teach it yet — `trainer` is still `null`, not missing."""
    from apps.enrollments.services import enrol_student

    trainerless = _active_batch(
        admin_user,
        published_course,
        start_date=timezone.localdate() - timedelta(days=1),
        end_date=timezone.localdate() + timedelta(days=60),
    )
    enrol_student(student=student_profile, batch=trainerless, actor=admin_user)

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(trainerless)).json()

    assert body["trainer"] is None
    assert body["students"]["total"] == 1


@pytest.mark.django_db
def test_batch_overview_trainer_sees_their_own_batch(api_client_no_csrf, trainer_profile, batch):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(_overview_url(batch)).status_code == 200


@pytest.mark.django_db
def test_batch_overview_trainer_cannot_open_another_trainers_batch(
    api_client_no_csrf, trainer_profile_two, batch
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    assert api_client_no_csrf.get(_overview_url(batch)).status_code == 404


@pytest.mark.django_db
def test_batch_overview_unknown_batch_is_404(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/batches/{uuid.uuid4()}/overview/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_batch_overview_dsr_counts_distinguish_submitted_approved_and_overdue(
    api_client_no_csrf, admin_user, manager_user, trainer_profile, batch
):
    """The single requirement this task calls out by name: submitted,
    approved and overdue must not collapse into one number."""
    from apps.dsr.models import DSRStatus
    from apps.dsr.services import review_dsr, start_dsr, submit_dsr

    approved_session = _completed_session(admin_user, batch, offset_days=3, topic="Approved")
    approved = start_dsr(session=approved_session, actor=trainer_profile.user)
    approved = submit_dsr(dsr=approved, actor=trainer_profile.user)
    review_dsr(dsr=approved, actor=manager_user, decision=DSRStatus.APPROVED)

    pending_session = _completed_session(admin_user, batch, offset_days=2, topic="Pending review")
    pending = start_dsr(session=pending_session, actor=trainer_profile.user)
    submit_dsr(dsr=pending, actor=trainer_profile.user)

    _completed_session(admin_user, batch, offset_days=1, topic="Never reported")

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()

    assert body["dsr"] == {
        "expected": 3,
        "submitted": 2,
        "approved": 1,
        "pending_review": 1,
        "overdue": 1,
    }


@pytest.mark.django_db
def test_batch_overview_a_draft_dsr_still_counts_as_overdue(
    api_client_no_csrf, admin_user, trainer_profile, batch
):
    """Started but never submitted is not the same as reported."""
    from apps.dsr.services import start_dsr

    session = _completed_session(admin_user, batch, offset_days=1, topic="Draft only")
    start_dsr(session=session, actor=trainer_profile.user)

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()
    assert body["dsr"]["expected"] == 1
    assert body["dsr"]["submitted"] == 0
    assert body["dsr"]["overdue"] == 1


@pytest.mark.django_db
def test_batch_overview_assessments_assignments_and_projects(
    api_client_no_csrf, admin_user, batch, enrollment, graded_batch_work
):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()

    assert body["assessments"] == {"total": 1, "completed": 1, "average_percent": 75.0}
    assert body["assignments"] == {"total": 1, "submitted": 1, "graded": 1}
    assert body["projects"] == {"total": 1, "submitted": 1, "reviewed": 1}


@pytest.mark.django_db
def test_batch_overview_assessment_average_matches_the_metrics_module(
    api_client_no_csrf, admin_user, batch, enrollment, graded_batch_work
):
    """`assessments.average_percent` is `metrics.test_average` verbatim, not a
    second computation that could quietly disagree with the metrics page."""
    from apps.reporting import metrics

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()

    expected = metrics.test_average({"batch": batch.pk})["value"]
    assert body["assessments"]["average_percent"] == expected


@pytest.mark.django_db
def test_batch_overview_attendance_percentage(
    api_client_no_csrf, admin_user, trainer_profile, batch, enrollment, other_enrollment
):
    session = _completed_session(admin_user, batch, offset_days=1, topic="Register")
    from apps.attendance.services import mark_attendance

    mark_attendance(
        session=session,
        actor=trainer_profile.user,
        entries=[
            {"enrollment_id": str(enrollment.pk), "status": "present"},
            {"enrollment_id": str(other_enrollment.pk), "status": "absent"},
        ],
    )

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_overview_url(batch)).json()
    assert body["attendance"] == {"percentage": 50, "present": 1, "absent": 1, "total_sessions": 2}


@pytest.mark.django_db
def test_batch_overview_query_count_does_not_grow_with_students(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment, graded_batch_work
):
    api_client_no_csrf.force_login(admin_user)
    url = _overview_url(batch)

    small = _query_count(api_client_no_csrf, url)
    _add_students(batch, 15, start=1000)
    large = _query_count(api_client_no_csrf, url)

    assert large == small, (
        f"{url} issued {small} queries for 2 students and {large} for 17. "
        "The cost grows with the roster — an N+1."
    )


# ---------------------------------------------------------------------------
# GET /batches/<id>/students/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_roster_shape(api_client_no_csrf, admin_user, batch, enrollment):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_students_url(batch)).json()

    assert {"count", "page", "page_size", "total_pages", "next", "previous", "results"} <= set(body)
    assert body["count"] == 1
    row = body["results"][0]
    assert set(row) == {
        "enrollment_id",
        "student_id",
        "name",
        "status",
        "attendance_percent",
        "assessment_average",
        "assignments_submitted",
        "assignments_total",
        "projects_submitted",
        "projects_total",
        "progress_percent",
        "risk_flags",
        "transferred_in",
    }
    assert row["enrollment_id"] == str(enrollment.pk)
    assert row["student_id"] == enrollment.student.student_id
    assert row["transferred_in"] is False
    assert row["attendance_percent"] is None
    assert row["assessment_average"] is None
    assert row["risk_flags"] == []


@pytest.mark.django_db
def test_roster_query_count_does_not_grow_with_students(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    """The single most important test in this file.

    `student_performance_bulk`, `_transfer_aware_attendance` and the project
    grouped count must each cost a fixed number of queries regardless of how
    many students are on the page — never one query per row.
    """
    api_client_no_csrf.force_login(admin_user)
    url = _students_url(batch)

    small = _query_count(api_client_no_csrf, url)
    _add_students(batch, 15, start=2000)
    large = _query_count(api_client_no_csrf, url)

    assert large == small, (
        f"{url} issued {small} queries for 2 students and {large} for 17. "
        "The cost grows with the roster — an N+1."
    )


@pytest.mark.django_db
def test_roster_transferred_student_attendance_uses_the_chain(
    api_client_no_csrf, admin_user, trainer_profile, batch, published_course, enrollment
):
    """The client's own words: a student who moved batches must not look new."""
    from apps.attendance.services import mark_attendance
    from apps.enrollments.services import transfer_student

    # `batch` (the origin) only runs from 7 days ago, so this has to fit inside it.
    old_session = _completed_session(admin_user, batch, offset_days=5, topic="Before the move")
    mark_attendance(
        session=old_session,
        actor=trainer_profile.user,
        entries=[{"enrollment_id": str(enrollment.pk), "status": "present"}],
    )

    destination = _active_batch(
        admin_user,
        published_course,
        trainer=trainer_profile,
        start_date=timezone.localdate() - timedelta(days=30),
        end_date=timezone.localdate() + timedelta(days=30),
        capacity=5,
    )
    new_enrollment = transfer_student(
        enrollment=enrollment, target_batch=destination, actor=admin_user, reason="Better fit."
    )
    new_session = _completed_session(admin_user, destination, offset_days=1, topic="After the move")
    mark_attendance(
        session=new_session,
        actor=admin_user,
        entries=[{"enrollment_id": str(new_enrollment.pk), "status": "absent"}],
    )

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_students_url(destination)).json()
    row = next(r for r in body["results"] if r["enrollment_id"] == str(new_enrollment.pk))

    assert row["transferred_in"] is True
    # One present on the old batch, one absent on the new one: 1 of 2 is 50%,
    # not the 0% a read of the current row alone would show.
    assert row["attendance_percent"] == 50

    from apps.enrollments.services import transfer_attendance_summary

    assert transfer_attendance_summary(new_enrollment)["percentage"] == 50


@pytest.mark.django_db
def test_roster_can_be_searched_by_student_name(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{_students_url(batch)}?search=Enrolled").json()

    ids = {row["enrollment_id"] for row in body["results"]}
    assert str(enrollment.pk) in ids
    assert str(other_enrollment.pk) not in ids


@pytest.mark.django_db
def test_roster_can_be_ordered(api_client_no_csrf, admin_user, batch, enrollment, other_enrollment):
    api_client_no_csrf.force_login(admin_user)
    ascending = api_client_no_csrf.get(
        f"{_students_url(batch)}?ordering=student__user__first_name"
    ).json()
    descending = api_client_no_csrf.get(
        f"{_students_url(batch)}?ordering=-student__user__first_name"
    ).json()

    asc_ids = [row["enrollment_id"] for row in ascending["results"]]
    desc_ids = [row["enrollment_id"] for row in descending["results"]]
    assert asc_ids == list(reversed(desc_ids))
    assert len(asc_ids) == 2


@pytest.mark.django_db
def test_roster_trainer_sees_only_their_own_batch(
    api_client_no_csrf, trainer_profile, trainer_profile_two, batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(_students_url(batch)).status_code == 200

    api_client_no_csrf.force_login(trainer_profile_two.user)
    assert api_client_no_csrf.get(_students_url(batch)).status_code == 404


@pytest.mark.django_db
def test_roster_row_count_matches_batch_overview_students_total(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    roster = api_client_no_csrf.get(_students_url(batch)).json()
    overview = api_client_no_csrf.get(_overview_url(batch)).json()

    assert roster["count"] == overview["students"]["total"]
    assert overview["batch"]["seats_taken"] == overview["students"]["total"]


@pytest.mark.django_db
def test_roster_figures_agree_with_the_single_student_engine_call(
    api_client_no_csrf, admin_user, batch, enrollment, graded_batch_work
):
    """The bulk roster row and a direct `student_performance` call must never
    disagree — the same guarantee `test_performance.py` holds the cohort
    progress report to."""
    from apps.performance.engine import student_performance

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_students_url(batch)).json()
    row = next(r for r in body["results"] if r["enrollment_id"] == str(enrollment.pk))

    direct = student_performance(enrollment)
    assert row["risk_flags"] == direct["risk"]["triggered"]
    assert row["progress_percent"] == direct["progress"]["percent"]
    assert row["assessment_average"] == direct["assessment"]["average_percent"]
    assert row["assignments_submitted"] == direct["assignments"]["submitted"]
    assert row["assignments_total"] == direct["assignments"]["total"]


# ---------------------------------------------------------------------------
# GET /trainers/<id>/overview/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_trainer_overview_shape(api_client_no_csrf, admin_user, trainer_profile):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()

    assert set(body) == {
        "trainer",
        "batches",
        "students",
        "submission",
        "completion",
        "outcomes",
        "pending",
        "reviews",
        "student_feedback",
        "as_of",
    }
    assert set(body["trainer"]) == {"id", "name", "trainer_id", "email"}
    assert set(body["batches"]) == {"total", "active"}
    assert set(body["students"]) == {"total", "at_risk"}
    assert set(body["submission"]) == {"attendance_rate", "dsr_rate", "dsr_approval_rate"}
    assert set(body["completion"]) == {"assessments", "assignments", "projects"}
    assert set(body["outcomes"]) == {"student_average_score", "student_attendance_percent"}
    assert set(body["pending"]) == {
        "dsr_to_submit",
        "assignments_to_grade",
        "projects_to_review",
        "overdue",
    }
    assert isinstance(body["reviews"], list)
    assert isinstance(body["student_feedback"], list)
    assert body["trainer"]["trainer_id"] == trainer_profile.trainer_id
    assert body["trainer"]["email"] == trainer_profile.user.email


@pytest.mark.django_db
def test_trainer_overview_no_batches_returns_zeroes_not_a_crash(
    api_client_no_csrf, manager_user, trainer_profile_two
):
    """`trainer_profile_two` exists but has never been assigned a batch."""
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(_trainer_url(trainer_profile_two))

    assert response.status_code == 200
    body = response.json()
    assert body["batches"] == {"total": 0, "active": 0}
    assert body["students"] == {"total": 0, "at_risk": 0}
    assert body["submission"] == {
        "attendance_rate": None,
        "dsr_rate": None,
        "dsr_approval_rate": None,
    }
    assert body["completion"] == {"assessments": None, "assignments": None, "projects": None}
    assert body["outcomes"] == {"student_average_score": None, "student_attendance_percent": None}
    assert body["pending"] == {
        "dsr_to_submit": 0,
        "assignments_to_grade": 0,
        "projects_to_review": 0,
        "overdue": 0,
    }
    assert body["reviews"] == []
    assert body["student_feedback"] == []


@pytest.mark.django_db
def test_trainer_overview_a_trainer_sees_their_own(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(_trainer_url(trainer_profile))
    assert response.status_code == 200
    assert response.json()["trainer"]["trainer_id"] == trainer_profile.trainer_id


@pytest.mark.django_db
def test_trainer_overview_a_trainer_cannot_open_someone_elses(
    api_client_no_csrf, trainer_profile, trainer_profile_two
):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(_trainer_url(trainer_profile_two)).status_code == 404


@pytest.mark.django_db
def test_trainer_overview_unknown_trainer_is_404(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/trainers/{uuid.uuid4()}/overview/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_trainer_overview_pending_dsr_and_batch_overview_agree(
    api_client_no_csrf, admin_user, trainer_profile, batch
):
    _completed_session(admin_user, batch, offset_days=1, topic="Overdue")

    api_client_no_csrf.force_login(admin_user)
    batch_body = api_client_no_csrf.get(_overview_url(batch)).json()
    trainer_body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()

    assert batch_body["dsr"]["overdue"] == 1
    assert trainer_body["pending"]["dsr_to_submit"] == 1
    assert trainer_body["submission"]["dsr_approval_rate"] is None


@pytest.mark.django_db
def test_trainer_overview_dsr_approval_rate(
    api_client_no_csrf, admin_user, manager_user, trainer_profile, batch
):
    from apps.dsr.models import DSRStatus
    from apps.dsr.services import review_dsr, start_dsr, submit_dsr

    approved_session = _completed_session(admin_user, batch, offset_days=2, topic="Approved")
    approved = start_dsr(session=approved_session, actor=trainer_profile.user)
    approved = submit_dsr(dsr=approved, actor=trainer_profile.user)
    review_dsr(dsr=approved, actor=manager_user, decision=DSRStatus.APPROVED)

    rejected_session = _completed_session(admin_user, batch, offset_days=1, topic="Rejected")
    rejected = start_dsr(session=rejected_session, actor=trainer_profile.user)
    rejected = submit_dsr(dsr=rejected, actor=trainer_profile.user)
    review_dsr(
        dsr=rejected, actor=manager_user, decision=DSRStatus.REJECTED, comments="Missing detail."
    )

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()
    assert body["submission"]["dsr_approval_rate"] == 50.0


@pytest.mark.django_db
def test_trainer_overview_reviews_and_student_feedback(
    api_client_no_csrf, manager_user, student_profile, trainer_profile
):
    from apps.performance.services import create_feedback, create_review

    review = create_review(
        actor=manager_user,
        trainer=trainer_profile,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        rating=4,
        summary="Solid term.",
    )
    student_note = create_feedback(
        actor=student_profile.user, trainer=trainer_profile, body="Explains things clearly."
    )
    # A manager's own note is not "the reviews of trainer that student gave
    # them" — it must not appear in `student_feedback`.
    create_feedback(
        actor=manager_user,
        trainer=trainer_profile,
        body="Manager's own note.",
        visible_to_subject=False,
    )

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()

    assert len(body["reviews"]) == 1
    review_row = body["reviews"][0]
    assert review_row["id"] == str(review.pk)
    assert review_row["rating"] == 4
    assert review_row["summary"] == "Solid term."
    assert review_row["reviewer"] == manager_user.get_full_name()
    assert set(review_row) == {
        "id",
        "period_start",
        "period_end",
        "rating",
        "summary",
        "reviewer",
        "created_at",
    }

    feedback_ids = {row["id"] for row in body["student_feedback"]}
    assert feedback_ids == {str(student_note.pk)}
    feedback_row = body["student_feedback"][0]
    assert set(feedback_row) == {"id", "body", "created_at", "batch_code"}


@pytest.mark.django_db
def test_trainer_overview_hides_feedback_not_yet_visible_to_the_subject(
    api_client_no_csrf, trainer_profile, student_profile, manager_user
):
    from apps.performance.services import create_feedback

    visible_note = create_feedback(
        actor=student_profile.user, trainer=trainer_profile, body="Great trainer."
    )
    hidden_note = create_feedback(
        actor=student_profile.user,
        trainer=trainer_profile,
        body="Withheld for now.",
        visible_to_subject=False,
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()
    assert {row["id"] for row in body["student_feedback"]} == {str(visible_note.pk)}

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()
    assert {row["id"] for row in body["student_feedback"]} == {
        str(visible_note.pk),
        str(hidden_note.pk),
    }


@pytest.mark.django_db
def test_trainer_overview_completion_and_outcomes_reuse_the_performance_engine(
    api_client_no_csrf, admin_user, trainer_profile, batch, enrollment, graded_batch_work
):
    """Every figure in `completion` and `outcomes` (bar the attendance
    percentage) is `apps.performance.engine.trainer_performance` verbatim."""
    from apps.performance.engine import trainer_performance

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_trainer_url(trainer_profile)).json()

    direct = trainer_performance(trainer_profile)
    assert body["completion"]["assessments"] == direct["assessment_completion_percent"]
    assert body["completion"]["assignments"] == direct["assignment_completion_percent"]
    assert body["completion"]["projects"] == direct["project_completion_percent"]
    assert body["outcomes"]["student_average_score"] == direct["student_average_score"]
    assert body["submission"]["attendance_rate"] == direct["attendance_submission_rate"]
    assert body["submission"]["dsr_rate"] == direct["dsr_submission_rate"]
    assert body["pending"]["assignments_to_grade"] == direct["pending_work"]["assignments"]
    assert body["pending"]["overdue"] == direct["overdue_work"]["total"]
