"""The performance and risk engine, and the reviews built on top of it.

Three layers, tested in the order a bug would actually appear in:

* :mod:`apps.performance.risk` — pure arithmetic against thresholds, no
  database at all. If a rule is wrong, it is wrong here, cheaply.
* :mod:`apps.performance.engine` — the same numbers `apps.progress.reports`
  and `apps.attendance.models` already computed, assembled into one picture,
  never a second calculation of anything they own.
* the API and the review/feedback record on top of it — who may see what, who
  may write what, and that a review freezes what it saw.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultSource,
)
from apps.assignments.models import Assignment, AssignmentStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.audit.models import AuditAction, AuditLog
from apps.common.identifiers import next_assignment_code, next_enrolment_code, next_student_id
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.performance import risk
from apps.performance.models import Feedback, PerformanceReview
from apps.sessions.models import ClassSession, SessionStatus
from apps.students.models import StudentProfile

SMALL = 3
LARGE = 12


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    """Every test starts and ends with a clean per-request policy memo."""
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


# ---------------------------------------------------------------------------
# risk.py — pure rules, no database
# ---------------------------------------------------------------------------


def _policy(**overrides) -> SimpleNamespace:
    defaults = {
        "risk_attendance_percent": Decimal("75.00"),
        "risk_assessment_average_percent": Decimal("50.00"),
        "risk_missed_assignments": 2,
        "risk_progress_variance_percent": Decimal("15.00"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _numbers(**overrides) -> dict:
    """A healthy, fully-measured baseline. Tests override just one section."""
    base = {
        "attendance": {"percent": 90, "has_records": True},
        "assessment": {"average_percent": 80, "recorded": 3, "total": 3},
        "assignments": {"missed": 0, "overdue_total": 0},
        "progress": {
            "actual_percent": 50,
            "expected_percent": 40,
            "variance": -10,
            "has_lessons": True,
        },
    }
    for key, value in overrides.items():
        base[key] = {**base[key], **value}
    return base


class TestAttendanceRisk:
    def test_not_triggered_when_no_records_exist(self):
        outcome = risk._attendance_risk(
            _numbers(attendance={"percent": 0, "has_records": False}), _policy()
        )
        assert outcome.triggered is False
        assert outcome.severity == risk.NONE

    def test_not_triggered_at_the_threshold(self):
        outcome = risk._attendance_risk(
            _numbers(attendance={"percent": 75, "has_records": True}), _policy()
        )
        assert outcome.triggered is False

    def test_triggered_below_the_threshold(self):
        outcome = risk._attendance_risk(
            _numbers(attendance={"percent": 60, "has_records": True}), _policy()
        )
        assert outcome.triggered is True
        assert outcome.numbers == {"percent": 60, "threshold": "75.00"}

    def test_severity_is_warning_close_to_the_threshold(self):
        outcome = risk._attendance_risk(
            _numbers(attendance={"percent": 70, "has_records": True}), _policy()
        )
        assert outcome.triggered is True
        assert outcome.severity == risk.WARNING

    def test_severity_is_critical_far_below_the_threshold(self):
        outcome = risk._attendance_risk(
            _numbers(attendance={"percent": 10, "has_records": True}), _policy()
        )
        assert outcome.triggered is True
        assert outcome.severity == risk.CRITICAL


class TestAcademicRisk:
    def test_not_triggered_when_nothing_is_scored_yet(self):
        outcome = risk._academic_risk(
            _numbers(assessment={"average_percent": None, "recorded": 0, "total": 2}), _policy()
        )
        assert outcome.triggered is False
        assert outcome.severity == risk.NONE

    def test_not_triggered_at_the_threshold(self):
        outcome = risk._academic_risk(
            _numbers(assessment={"average_percent": 50, "recorded": 2, "total": 2}), _policy()
        )
        assert outcome.triggered is False

    def test_triggered_below_the_threshold(self):
        outcome = risk._academic_risk(
            _numbers(assessment={"average_percent": 30, "recorded": 2, "total": 2}), _policy()
        )
        assert outcome.triggered is True

    def test_severity_is_critical_far_below_the_threshold(self):
        outcome = risk._academic_risk(
            _numbers(assessment={"average_percent": 5, "recorded": 2, "total": 2}), _policy()
        )
        assert outcome.severity == risk.CRITICAL


class TestAssignmentRisk:
    def test_not_triggered_below_the_threshold_count(self):
        outcome = risk._assignment_risk(_numbers(assignments={"missed": 1}), _policy())
        assert outcome.triggered is False
        assert outcome.numbers["missed"] == 1

    def test_triggered_at_the_threshold_count(self):
        outcome = risk._assignment_risk(_numbers(assignments={"missed": 2}), _policy())
        assert outcome.triggered is True

    def test_severity_is_critical_well_past_the_threshold(self):
        outcome = risk._assignment_risk(_numbers(assignments={"missed": 5}), _policy())
        assert outcome.severity == risk.CRITICAL

    def test_no_overdue_work_is_not_a_risk(self):
        outcome = risk._assignment_risk(_numbers(assignments={"missed": 0}), _policy())
        assert outcome.triggered is False
        assert "No overdue" in outcome.detail


class TestProgressRisk:
    def test_not_triggered_when_there_are_no_published_lessons(self):
        outcome = risk._progress_risk(
            _numbers(
                progress={
                    "actual_percent": 0,
                    "expected_percent": 60,
                    "variance": None,
                    "has_lessons": False,
                }
            ),
            _policy(),
        )
        assert outcome.triggered is False
        assert outcome.severity == risk.NONE

    def test_not_triggered_within_the_threshold(self):
        outcome = risk._progress_risk(
            _numbers(
                progress={
                    "actual_percent": 30,
                    "expected_percent": 40,
                    "variance": 10,
                    "has_lessons": True,
                }
            ),
            _policy(),
        )
        assert outcome.triggered is False

    def test_triggered_beyond_the_threshold(self):
        outcome = risk._progress_risk(
            _numbers(
                progress={
                    "actual_percent": 10,
                    "expected_percent": 60,
                    "variance": 50,
                    "has_lessons": True,
                }
            ),
            _policy(),
        )
        assert outcome.triggered is True

    def test_severity_is_critical_far_behind_schedule(self):
        outcome = risk._progress_risk(
            _numbers(
                progress={
                    "actual_percent": 0,
                    "expected_percent": 90,
                    "variance": 90,
                    "has_lessons": True,
                }
            ),
            _policy(),
        )
        assert outcome.severity == risk.CRITICAL


class TestEvaluate:
    def test_reports_every_rule_even_when_none_are_triggered(self):
        result = risk.evaluate(_numbers(), _policy())
        assert result["at_risk"] is False
        assert result["triggered"] == []
        assert result["triggered_count"] == 0
        assert {outcome["key"] for outcome in result["outcomes"]} == {
            "attendance",
            "academic",
            "assignments",
            "progress",
        }

    def test_at_risk_is_true_when_any_rule_triggers(self):
        result = risk.evaluate(_numbers(attendance={"percent": 10, "has_records": True}), _policy())
        assert result["at_risk"] is True
        assert result["triggered"] == ["attendance"]
        assert result["triggered_count"] == 1

    def test_triggered_count_counts_every_rule_that_fires(self):
        result = risk.evaluate(
            _numbers(
                attendance={"percent": 10, "has_records": True},
                assessment={"average_percent": 5, "recorded": 2, "total": 2},
            ),
            _policy(),
        )
        assert result["triggered_count"] == 2

    def test_a_switched_off_rule_still_reports_its_numbers(self):
        """Nothing is ever hidden — even a rule with nothing to say reports why."""
        result = risk.evaluate(
            _numbers(assessment={"average_percent": None, "recorded": 0, "total": 0}), _policy()
        )
        academic = next(o for o in result["outcomes"] if o["key"] == "academic")
        assert academic["triggered"] is False
        assert academic["numbers"]["percent"] is None


# ---------------------------------------------------------------------------
# engine._expected_progress_percent — pure, a fake batch is enough
# ---------------------------------------------------------------------------


def _batch_like(start_date, end_date) -> SimpleNamespace:
    return SimpleNamespace(start_date=start_date, end_date=end_date)


class TestExpectedProgress:
    def test_zero_before_the_batch_starts(self):
        from apps.performance.engine import _expected_progress_percent

        today = date(2026, 1, 1)
        batch = _batch_like(date(2026, 2, 1), date(2026, 4, 1))
        assert _expected_progress_percent(batch, today=today) == 0

    def test_full_after_the_batch_ends(self):
        from apps.performance.engine import _expected_progress_percent

        today = date(2026, 5, 1)
        batch = _batch_like(date(2026, 1, 1), date(2026, 4, 1))
        assert _expected_progress_percent(batch, today=today) == 100

    def test_linear_partway_through(self):
        from apps.performance.engine import _expected_progress_percent

        batch = _batch_like(date(2026, 1, 1), date(2026, 1, 11))
        today = date(2026, 1, 6)
        assert _expected_progress_percent(batch, today=today) == 50

    def test_none_when_the_batch_has_no_dates(self):
        from apps.performance.engine import _expected_progress_percent

        assert _expected_progress_percent(_batch_like(None, None)) is None


# ---------------------------------------------------------------------------
# engine.student_performance — the database-backed picture
# ---------------------------------------------------------------------------


@pytest.fixture
def bare_enrollment(admin_user, category, trainer_profile, other_student_profile):
    """A student on a course with no lessons, no assignments, nothing at all.

    The fixture the "nothing to measure" tests need: everything the engine
    could read is genuinely absent, not merely zero.
    """
    from apps.batches.models import BatchStatus
    from apps.batches.services import create_batch, set_batch_status
    from apps.courses import services as course_services
    from apps.courses.models import PublishStatus
    from apps.enrollments.services import enrol_student

    course = course_services.create_course(
        actor=admin_user,
        title="Bare Course",
        category=category,
        short_description="Nothing published on it yet.",
    )
    # `IN_REVIEW`, not `PUBLISHED`: publishing a course requires at least one
    # published module with a published lesson in it, which is exactly the
    # content this fixture must *not* have. `published_lessons` and
    # `published_modules` (see `apps.progress.bulk`) only read module/lesson
    # status, never the course's own — so a batch can run on an in-review
    # course and genuinely have zero published content.
    course_services.set_course_status(
        course=course, target=PublishStatus.IN_REVIEW, actor=admin_user, may_publish=True
    )
    course.refresh_from_db()

    today = timezone.localdate()
    bare_batch = create_batch(
        actor=admin_user,
        name="Bare Batch",
        course=course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=50),
        capacity=5,
    )
    bare_batch = set_batch_status(batch=bare_batch, target=BatchStatus.ACTIVE, actor=admin_user)
    return enrol_student(student=other_student_profile, batch=bare_batch, actor=admin_user)


@pytest.mark.django_db
class TestStudentPerformanceNothingToMeasure:
    def test_triggers_no_risk(self, bare_enrollment):
        from apps.performance.engine import student_performance

        result = student_performance(bare_enrollment)
        assert result["risk"]["at_risk"] is False
        assert result["risk"]["triggered"] == []

    def test_every_numeric_key_is_a_number_or_none_never_a_crash(self, bare_enrollment):
        from apps.performance.engine import student_performance

        result = student_performance(bare_enrollment)
        assert result["overall_score"] is None
        assert result["attendance"]["percent"] is None
        assert result["attendance"]["has_records"] is False
        assert result["assessment"]["average_percent"] is None
        assert result["assignments"]["percent"] is None
        assert result["assignments"]["missed"] == 0
        assert result["projects"]["percent"] is None
        assert result["progress"]["percent"] is None
        assert result["counts"]["components_measured"] == 0
        assert result["counts"]["risk_flags"] == 0

    def test_a_course_with_no_lessons_does_not_count_toward_the_score(
        self, bare_enrollment, admin_user
    ):
        from apps.performance.engine import student_performance

        assessment = Assessment.objects.create(
            batch=bare_enrollment.batch,
            course=bare_enrollment.course,
            title="Only test",
            category=AssessmentCategory.WEEKLY_TEST,
            delivery=AssessmentDelivery.OFFLINE,
            status=AssessmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )
        AssessmentResult.objects.create(
            assessment=assessment,
            enrollment=bare_enrollment,
            marks_obtained=80,
            source=ResultSource.MANUAL,
        )

        result = student_performance(bare_enrollment)
        assert result["overall_score"] == 80.0
        assert result["counts"]["components_measured"] == 1


@pytest.mark.django_db
class TestStudentPerformanceOverallScore:
    def test_is_the_mean_of_the_measured_components(self, enrollment, admin_user):
        """Two published lessons (untouched: 0%) and an 80% test average -> 40."""
        from apps.performance.engine import student_performance

        assessment = Assessment.objects.create(
            batch=enrollment.batch,
            course=enrollment.course,
            title="Weekly Test",
            category=AssessmentCategory.WEEKLY_TEST,
            delivery=AssessmentDelivery.OFFLINE,
            status=AssessmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )
        AssessmentResult.objects.create(
            assessment=assessment,
            enrollment=enrollment,
            marks_obtained=80,
            source=ResultSource.MANUAL,
        )

        result = student_performance(enrollment)
        assert result["overall_score"] == 40.0
        assert result["counts"]["components_measured"] == 2


@pytest.mark.django_db
class TestAttendanceRiskViaEngine:
    def _sessions(self, batch, admin_user, count):
        return [
            ClassSession.objects.create(
                batch=batch,
                session_date=date.today() - timedelta(days=count - index),
                start_time="09:00",
                end_time="11:00",
                status=SessionStatus.COMPLETED,
                created_by=admin_user,
            )
            for index in range(count)
        ]

    def test_below_threshold_triggers_the_attendance_rule(self, enrollment, batch, admin_user):
        from apps.performance.engine import student_performance

        sessions = self._sessions(batch, admin_user, 4)
        for index, session in enumerate(sessions):
            status = AttendanceStatus.PRESENT if index == 0 else AttendanceStatus.ABSENT
            AttendanceRecord.objects.create(session=session, enrollment=enrollment, status=status)

        result = student_performance(enrollment)
        attendance_outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "attendance")
        assert attendance_outcome["triggered"] is True
        assert result["attendance"]["percent"] == 25

    def test_at_or_above_threshold_does_not_trigger(self, enrollment, batch, admin_user):
        from apps.performance.engine import student_performance

        sessions = self._sessions(batch, admin_user, 4)
        for session in sessions:
            AttendanceRecord.objects.create(
                session=session, enrollment=enrollment, status=AttendanceStatus.PRESENT
            )

        result = student_performance(enrollment)
        attendance_outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "attendance")
        assert attendance_outcome["triggered"] is False

    def test_changing_the_threshold_flips_the_verdict_without_new_code(
        self, enrollment, batch, admin_user
    ):
        from apps.academics.services import get_or_create_policy, update_policy
        from apps.performance.engine import student_performance

        sessions = self._sessions(batch, admin_user, 4)
        for index, session in enumerate(sessions):
            status = AttendanceStatus.PRESENT if index < 2 else AttendanceStatus.ABSENT
            AttendanceRecord.objects.create(session=session, enrollment=enrollment, status=status)

        before = student_performance(enrollment)
        before_outcome = next(o for o in before["risk"]["outcomes"] if o["key"] == "attendance")
        assert before_outcome["triggered"] is True  # 50% < the 75% default

        update_policy(
            policy=get_or_create_policy(),
            actor=admin_user,
            risk_attendance_percent=Decimal("40.00"),
        )

        after = student_performance(enrollment)
        after_outcome = next(o for o in after["risk"]["outcomes"] if o["key"] == "attendance")
        assert after_outcome["triggered"] is False  # 50% >= the new 40% threshold


@pytest.mark.django_db
class TestAcademicRiskViaEngine:
    def test_a_low_average_triggers_the_academic_rule(self, enrollment, admin_user):
        from apps.performance.engine import student_performance

        assessment = Assessment.objects.create(
            batch=enrollment.batch,
            course=enrollment.course,
            title="Weekly Test",
            category=AssessmentCategory.WEEKLY_TEST,
            delivery=AssessmentDelivery.OFFLINE,
            status=AssessmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )
        AssessmentResult.objects.create(
            assessment=assessment,
            enrollment=enrollment,
            marks_obtained=20,
            source=ResultSource.MANUAL,
        )

        result = student_performance(enrollment)
        outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "academic")
        assert outcome["triggered"] is True

    def test_no_assessments_yet_is_not_an_academic_risk(self, enrollment):
        """The exact case the module warns about: no marks is not a failing average."""
        from apps.performance.engine import student_performance

        result = student_performance(enrollment)
        outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "academic")
        assert outcome["triggered"] is False
        assert outcome["numbers"]["percent"] is None


@pytest.mark.django_db
class TestAssignmentRiskViaEngine:
    def _overdue_assignment(self, course, admin_user):
        return Assignment.objects.create(
            code=next_assignment_code(),
            course=course,
            title="Overdue work",
            due_at=timezone.now() - timedelta(days=5),
            status=AssignmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )

    def test_below_the_threshold_count_does_not_trigger(self, enrollment, admin_user):
        from apps.performance.engine import student_performance

        self._overdue_assignment(enrollment.course, admin_user)

        result = student_performance(enrollment)
        outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "assignments")
        assert outcome["triggered"] is False
        assert result["assignments"]["missed"] == 1

    def test_at_the_threshold_count_triggers(self, enrollment, admin_user):
        from apps.performance.engine import student_performance

        self._overdue_assignment(enrollment.course, admin_user)
        self._overdue_assignment(enrollment.course, admin_user)

        result = student_performance(enrollment)
        outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "assignments")
        assert outcome["triggered"] is True
        assert result["assignments"]["missed"] == 2

    def test_a_future_due_date_is_not_missed(self, enrollment, admin_user):
        from apps.performance.engine import student_performance

        Assignment.objects.create(
            code=next_assignment_code(),
            course=enrollment.course,
            title="Not due yet",
            due_at=timezone.now() + timedelta(days=5),
            status=AssignmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )

        result = student_performance(enrollment)
        assert result["assignments"]["missed"] == 0


@pytest.mark.django_db
class TestProgressRiskViaEngine:
    def test_far_behind_schedule_triggers_the_progress_rule(self, enrollment):
        from apps.performance.engine import student_performance

        today = timezone.localdate()
        batch = enrollment.batch
        batch.start_date = today - timedelta(days=40)
        batch.end_date = today + timedelta(days=20)
        batch.save(update_fields=["start_date", "end_date"])

        result = student_performance(enrollment)
        outcome = next(o for o in result["risk"]["outcomes"] if o["key"] == "progress")
        assert outcome["triggered"] is True
        assert result["progress"]["variance"] > 15


# ---------------------------------------------------------------------------
# engine.student_performance_bulk
# ---------------------------------------------------------------------------


def _add_students(batch, count: int, *, start: int = 0) -> list[Enrollment]:
    users = User.objects.bulk_create(
        User(
            email=f"engineperf-{start + index:03d}@perf.grras.invalid",
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


@pytest.mark.django_db
class TestStudentPerformanceBulk:
    def test_every_requested_enrollment_is_a_key_including_empty_ones(
        self, enrollment, other_enrollment
    ):
        from apps.performance.engine import student_performance_bulk

        cohort = Enrollment.objects.filter(pk__in=[enrollment.pk, other_enrollment.pk])
        result = student_performance_bulk(cohort)

        assert set(result) == {enrollment.pk, other_enrollment.pk}
        # `other_enrollment` has never touched anything on the course: still a
        # full row (0% of the two published lessons), not a gap.
        assert result[other_enrollment.pk]["overall_score"] == 0.0
        assert result[other_enrollment.pk]["risk"]["at_risk"] is False

    def test_agrees_with_the_single_student_calculation(
        self, enrollment, other_enrollment, admin_user, batch
    ):
        from apps.performance.engine import student_performance, student_performance_bulk

        session = ClassSession.objects.create(
            batch=batch,
            session_date=date.today() - timedelta(days=1),
            start_time="09:00",
            end_time="11:00",
            status=SessionStatus.COMPLETED,
            created_by=admin_user,
        )
        AttendanceRecord.objects.create(
            session=session, enrollment=enrollment, status=AttendanceStatus.PRESENT
        )

        cohort = list(Enrollment.objects.with_related().filter(batch=batch))
        bulk = student_performance_bulk(cohort)

        for row in cohort:
            assert bulk[row.pk] == student_performance(row)

    def test_returns_empty_for_an_empty_request(self):
        from apps.performance.engine import student_performance_bulk

        assert student_performance_bulk(Enrollment.objects.none()) == {}

    def test_query_cost_does_not_grow_with_the_cohort(
        self, batch, enrollment, django_assert_num_queries
    ):
        from apps.common.request_context import clear_scope
        from apps.performance.engine import student_performance_bulk

        def measure() -> int:
            # Cleared so neither call benefits from the other's cached policy
            # lookup — otherwise the *second* call looks artificially cheaper.
            clear_scope()
            cohort = Enrollment.objects.filter(batch=batch)
            with CaptureQueriesContext(connection) as captured:
                student_performance_bulk(cohort)
            return len(captured.captured_queries)

        _add_students(batch, SMALL)
        small = measure()

        _add_students(batch, LARGE, start=100)
        large = measure()

        assert large == small, (
            f"{small} queries for a few students, {large} for many more — the cost "
            f"grew with the roster."
        )


# ---------------------------------------------------------------------------
# engine.trainer_performance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTrainerPerformance:
    def test_a_trainer_with_no_batches_gets_a_full_none_dict(self, trainer_profile_two):
        from apps.performance.engine import trainer_performance

        result = trainer_performance(trainer_profile_two)
        assert result["batches_handled"] == 0
        assert result["students_handled"] == 0
        assert result["attendance_submission_rate"] is None
        assert result["student_average_score"] is None
        assert result["pending_work"] == {
            "assignments": 0,
            "projects": 0,
            "assessments": 0,
            "total": 0,
        }

    def test_counts_batches_and_students(self, enrollment, trainer_profile, batch):
        from apps.performance.engine import trainer_performance

        result = trainer_performance(trainer_profile)
        assert result["batches_handled"] == 1
        assert result["students_handled"] == 1
        assert result["counts"]["batches"] == 1

    def test_dsr_figures_are_none_while_the_dsr_app_has_no_model_yet(
        self, enrollment, trainer_profile
    ):
        """`apps.dsr` is under construction elsewhere; this must degrade, not crash."""
        from django.apps import apps as django_apps

        from apps.performance.engine import trainer_performance

        try:
            django_apps.get_model("dsr", "DSR")
            pytest.skip("The dsr.DSR model now exists; this guard is no longer exercised.")
        except LookupError:
            pass

        result = trainer_performance(trainer_profile)
        assert result["dsr_submission_rate"] is None
        assert result["dsr_submitted_count"] is None

    def test_pending_and_overdue_work_are_shaped_dicts_with_totals(
        self, enrollment, trainer_profile
    ):
        from apps.performance.engine import trainer_performance

        result = trainer_performance(trainer_profile)
        for section in ("pending_work", "overdue_work"):
            assert set(result[section]) == {"assignments", "projects", "assessments", "total"}
            assert result[section]["total"] == sum(
                value for key, value in result[section].items() if key != "total"
            )


# ---------------------------------------------------------------------------
# Access: who may see whose performance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerformanceAccess:
    def test_a_student_sees_only_their_own_performance(
        self, api_client_no_csrf, student_profile, enrollment
    ):
        api_client_no_csrf.force_login(student_profile.user)
        response = api_client_no_csrf.get("/api/v1/performance/me/")
        assert response.status_code == 200
        ids = {row["enrollment_id"] for row in response.data}
        assert ids == {str(enrollment.pk)}

    def test_a_trainer_sees_only_the_students_on_batches_they_teach(
        self, api_client_no_csrf, trainer_profile, enrollment, batch
    ):
        api_client_no_csrf.force_login(trainer_profile.user)
        response = api_client_no_csrf.get(f"/api/v1/batches/{batch.id}/performance/")
        assert response.status_code == 200
        assert {row["enrollment_id"] for row in response.data} == {str(enrollment.pk)}

    def test_a_trainer_cannot_view_a_batch_they_do_not_teach(
        self, api_client_no_csrf, trainer_profile_two, batch
    ):
        """Not merely refused: a batch outside a trainer's own is not visible at
        all, so this is a 404 — the same IDOR-safe shape every other batch-scoped
        view in this codebase uses (see `apps.batches.access.visible_batches`)."""
        api_client_no_csrf.force_login(trainer_profile_two.user)
        response = api_client_no_csrf.get(f"/api/v1/batches/{batch.id}/performance/")
        assert response.status_code == 404

    def test_a_counsellor_is_refused_batch_performance(
        self, api_client_no_csrf, counsellor_user, batch
    ):
        api_client_no_csrf.force_login(counsellor_user)
        response = api_client_no_csrf.get(f"/api/v1/batches/{batch.id}/performance/")
        assert response.status_code == 403

    def test_a_manager_may_view_any_batch(
        self, api_client_no_csrf, manager_user, batch, enrollment
    ):
        api_client_no_csrf.force_login(manager_user)
        response = api_client_no_csrf.get(f"/api/v1/batches/{batch.id}/performance/")
        assert response.status_code == 200

    def test_a_trainer_with_no_trainer_profile_gets_an_empty_own_view(
        self, api_client_no_csrf, admin_user
    ):
        api_client_no_csrf.force_login(admin_user)
        response = api_client_no_csrf.get("/api/v1/performance/trainer/me/")
        assert response.status_code == 200
        assert response.data == {}


# ---------------------------------------------------------------------------
# Reviews and feedback
# ---------------------------------------------------------------------------


def _review_payload(**overrides) -> dict:
    today = date.today()
    payload = {
        "period_start": (today - timedelta(days=30)).isoformat(),
        "period_end": today.isoformat(),
        "rating": 4,
        "summary": "Solid month.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestReviewWriting:
    def test_a_counsellor_cannot_write_a_review(
        self, api_client_no_csrf, counsellor_user, student_profile
    ):
        api_client_no_csrf.force_login(counsellor_user)
        response = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(student_profile.pk)),
            format="json",
        )
        assert response.status_code == 403

    def test_nobody_may_review_themselves_at_the_service_layer(self, manager_user, student_profile):
        from apps.common.exceptions import AuthorityError
        from apps.performance import services

        # A manager who happens to also be the student's own account: refused
        # regardless of the capability they hold.
        with pytest.raises(AuthorityError):
            services.create_review(
                actor=student_profile.user,
                student=student_profile,
                period_start=date.today() - timedelta(days=1),
                period_end=date.today(),
                rating=5,
            )

    def test_self_review_is_refused_through_the_api_too(
        self, api_client_no_csrf, admin_user, student_profile
    ):
        """An admin holding `review.manage_any` may still not review themselves."""
        from apps.accounts.roles import UserRole
        from apps.students.services import create_student

        self_student = create_student(
            email="self-reviewer@example.test",
            first_name="Self",
            last_name="Reviewer",
            actor=admin_user,
            password="correct-horse-battery-staple",
            send_invitation=False,
        )
        self_student.user.role = UserRole.ADMIN
        self_student.user.save(update_fields=["role"])

        api_client_no_csrf.force_login(self_student.user)
        response = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(self_student.pk)),
            format="json",
        )
        assert response.status_code == 403

    def test_a_manager_can_review_a_student_and_the_snapshot_is_frozen(
        self, api_client_no_csrf, manager_user, enrollment, admin_user
    ):
        student = enrollment.student
        api_client_no_csrf.force_login(manager_user)

        response = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(student.pk)),
            format="json",
        )
        assert response.status_code == 201
        review_id = response.data["id"]
        frozen_snapshot = PerformanceReview.objects.get(pk=review_id).snapshot

        # Change the underlying data after the review was written...
        assessment = Assessment.objects.create(
            batch=enrollment.batch,
            course=enrollment.course,
            title="New test",
            category=AssessmentCategory.WEEKLY_TEST,
            delivery=AssessmentDelivery.OFFLINE,
            status=AssessmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )
        AssessmentResult.objects.create(
            assessment=assessment,
            enrollment=enrollment,
            marks_obtained=10,
            source=ResultSource.MANUAL,
        )

        # ...and the frozen review must not have moved.
        review_after = PerformanceReview.objects.get(pk=review_id)
        assert review_after.snapshot == frozen_snapshot

    def test_writing_a_review_is_audited(self, api_client_no_csrf, manager_user, enrollment):
        api_client_no_csrf.force_login(manager_user)
        response = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(enrollment.student.pk)),
            format="json",
        )
        assert response.status_code == 201
        assert AuditLog.objects.filter(
            action=AuditAction.REVIEW_RECORDED, resource_id=response.data["id"]
        ).exists()

    def test_updating_a_review_is_audited(self, api_client_no_csrf, manager_user, enrollment):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(enrollment.student.pk)),
            format="json",
        )
        review_id = created.data["id"]

        response = api_client_no_csrf.patch(
            f"/api/v1/performance/reviews/{review_id}/", {"rating": 2}, format="json"
        )
        assert response.status_code == 200
        assert response.data["rating"] == 2
        assert AuditLog.objects.filter(
            action=AuditAction.REVIEW_UPDATED, resource_id=review_id
        ).exists()

    def test_a_student_cannot_see_another_students_review(
        self, api_client_no_csrf, manager_user, enrollment, other_student_profile
    ):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(enrollment.student.pk)),
            format="json",
        )
        review_id = created.data["id"]

        api_client_no_csrf.force_login(other_student_profile.user)
        response = api_client_no_csrf.get(f"/api/v1/performance/reviews/{review_id}/")
        assert response.status_code == 404

    def test_the_subject_can_read_their_own_review(
        self, api_client_no_csrf, manager_user, enrollment
    ):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(enrollment.student.pk)),
            format="json",
        )
        review_id = created.data["id"]

        api_client_no_csrf.force_login(enrollment.student.user)
        response = api_client_no_csrf.get(f"/api/v1/performance/reviews/{review_id}/")
        assert response.status_code == 200

    def test_a_soft_deleted_review_is_hidden_from_the_list_but_kept_in_all_objects(
        self, api_client_no_csrf, manager_user, enrollment
    ):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            "/api/v1/performance/reviews/",
            _review_payload(student=str(enrollment.student.pk)),
            format="json",
        )
        review_id = created.data["id"]

        response = api_client_no_csrf.delete(
            f"/api/v1/performance/reviews/{review_id}/",
            {"reason": "Recorded against the wrong student"},
            format="json",
        )
        assert response.status_code == 204

        listing = api_client_no_csrf.get("/api/v1/performance/reviews/")
        assert review_id not in {row["id"] for row in listing.data}
        assert PerformanceReview.all_objects.filter(pk=review_id).exists()
        assert not PerformanceReview.objects.filter(pk=review_id).exists()


@pytest.mark.django_db
class TestFeedback:
    def test_a_counsellor_cannot_leave_feedback(
        self, api_client_no_csrf, counsellor_user, student_profile
    ):
        api_client_no_csrf.force_login(counsellor_user)
        response = api_client_no_csrf.post(
            "/api/v1/performance/feedback/",
            {"student": str(student_profile.pk), "body": "Doing well."},
            format="json",
        )
        assert response.status_code == 403

    def test_leaving_feedback_is_audited(self, api_client_no_csrf, manager_user, student_profile):
        api_client_no_csrf.force_login(manager_user)
        response = api_client_no_csrf.post(
            "/api/v1/performance/feedback/",
            {"student": str(student_profile.pk), "body": "Great progress this week."},
            format="json",
        )
        assert response.status_code == 201
        assert AuditLog.objects.filter(
            action=AuditAction.FEEDBACK_RECORDED, resource_id=response.data["id"]
        ).exists()

    def test_hidden_feedback_is_not_shown_to_its_subject(
        self, api_client_no_csrf, manager_user, student_profile
    ):
        api_client_no_csrf.force_login(manager_user)
        api_client_no_csrf.post(
            "/api/v1/performance/feedback/",
            {
                "student": str(student_profile.pk),
                "body": "Private note for the next formal review.",
                "visible_to_subject": False,
            },
            format="json",
        )

        api_client_no_csrf.force_login(student_profile.user)
        response = api_client_no_csrf.get("/api/v1/performance/feedback/")
        assert response.data == []

    def test_visible_feedback_is_shown_to_its_subject(
        self, api_client_no_csrf, manager_user, student_profile
    ):
        api_client_no_csrf.force_login(manager_user)
        api_client_no_csrf.post(
            "/api/v1/performance/feedback/",
            {"student": str(student_profile.pk), "body": "Keep it up."},
            format="json",
        )

        api_client_no_csrf.force_login(student_profile.user)
        response = api_client_no_csrf.get("/api/v1/performance/feedback/")
        assert len(response.data) == 1

    def test_nobody_may_leave_feedback_about_themselves(self, manager_user, student_profile):
        from apps.common.exceptions import AuthorityError
        from apps.performance import services

        with pytest.raises(AuthorityError):
            services.create_feedback(
                actor=student_profile.user, student=student_profile, body="Self-praise."
            )

    def test_a_soft_deleted_feedback_row_is_hidden_but_recoverable(
        self, api_client_no_csrf, manager_user, student_profile
    ):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            "/api/v1/performance/feedback/",
            {"student": str(student_profile.pk), "body": "Noted."},
            format="json",
        )
        feedback_id = created.data["id"]

        response = api_client_no_csrf.delete(
            f"/api/v1/performance/feedback/{feedback_id}/",
            {"reason": "Duplicate entry"},
            format="json",
        )
        assert response.status_code == 204
        assert Feedback.all_objects.filter(pk=feedback_id).exists()
        assert not Feedback.objects.filter(pk=feedback_id).exists()


# ---------------------------------------------------------------------------
# Risk thresholds endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRiskThresholds:
    def test_only_an_administrator_may_change_the_thresholds(
        self, api_client_no_csrf, manager_user
    ):
        api_client_no_csrf.force_login(manager_user)
        response = api_client_no_csrf.patch(
            "/api/v1/performance/risk-thresholds/",
            {"risk_attendance_percent": "60.00"},
            format="json",
        )
        assert response.status_code == 403

    def test_changing_a_threshold_is_audited(self, api_client_no_csrf, admin_user):
        api_client_no_csrf.force_login(admin_user)
        response = api_client_no_csrf.patch(
            "/api/v1/performance/risk-thresholds/",
            {"risk_attendance_percent": "60.00"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["risk_attendance_percent"] == "60.00"
        assert AuditLog.objects.filter(action=AuditAction.RISK_THRESHOLDS_UPDATED).exists()

    def test_reading_the_thresholds_returns_the_code_defaults_with_nothing_configured(
        self, api_client_no_csrf, admin_user
    ):
        api_client_no_csrf.force_login(admin_user)
        response = api_client_no_csrf.get("/api/v1/performance/risk-thresholds/")
        assert response.status_code == 200
        assert response.data["risk_missed_assignments"] == 2
