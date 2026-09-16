"""The risk engine's write path (ERP Phase 13, ADR-11): `recompute_risk`'s
change detection, the debounced schedule in front of it, and the one
receiver that triggers it from `apps.work`'s signal.

Three things, in the order a bug would actually surface:

* A recompute that changes nothing is silent — no `RISK_CHANGED`, no
  notification — because most recomputes, in a real system, confirm the
  student is still fine.
* A recompute that changes the verdict moves the current one into
  `previous_level`/`previous_triggered` and fires both.
* `schedule_recompute` coalesces a burst of triggers for the same enrolment
  into exactly one scheduled Celery task, proven by mocking and counting the
  call rather than trusting the cache-key logic by inspection.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.notifications.models import Notification, NotificationKind
from apps.performance.models import RiskLevel, RiskState

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    """`schedule_recompute`'s debounce key must start unset for every test,
    or a key left by an earlier test would make the very first `cache.add`
    in this one look like "already pending"."""
    cache.clear()
    yield
    cache.clear()


def _connect_risk_changed():
    """A bare recorder for `RISK_CHANGED` — a list of every send's kwargs,
    since a `Mock` receiver would itself need `dispatch_uid` bookkeeping
    `django.dispatch.Signal` does not require of a plain function."""
    from apps.performance.signals import RISK_CHANGED

    calls: list[dict] = []

    def _receiver(sender, **kwargs):
        calls.append(kwargs)

    RISK_CHANGED.connect(_receiver, weak=False)
    return calls, lambda: RISK_CHANGED.disconnect(_receiver)


# ---------------------------------------------------------------------------
# services.recompute_risk — change detection
# ---------------------------------------------------------------------------


class TestRecomputeRiskChangeDetection:
    def test_first_computation_with_no_risk_has_no_previous_and_fires_nothing(self, enrollment):
        from apps.performance import services

        calls, disconnect = _connect_risk_changed()
        try:
            state = services.recompute_risk(enrollment=enrollment)
        finally:
            disconnect()

        assert state.level == RiskLevel.NONE
        assert state.previous_level == ""
        assert state.previous_triggered is None
        # Landing on "none" on the very first computation is not news.
        assert calls == []
        assert not Notification.objects.filter(kind=NotificationKind.RISK_LEVEL_CHANGED).exists()

    def test_recomputing_with_nothing_changed_fires_neither_signal_nor_notification(
        self, enrollment
    ):
        from apps.performance import services

        services.recompute_risk(enrollment=enrollment)  # the first computation

        calls, disconnect = _connect_risk_changed()
        try:
            state = services.recompute_risk(enrollment=enrollment)  # nothing moved
        finally:
            disconnect()

        assert state.level == RiskLevel.NONE
        assert calls == []
        assert not Notification.objects.filter(kind=NotificationKind.RISK_LEVEL_CHANGED).exists()

    def test_a_changed_verdict_moves_current_into_previous_and_fires_both(
        self, enrollment, admin_user
    ):
        from datetime import date

        from apps.academics.services import get_or_create_policy, update_policy
        from apps.attendance.models import AttendanceRecord, AttendanceStatus
        from apps.performance import services
        from apps.sessions.models import ClassSession, SessionStatus

        services.recompute_risk(enrollment=enrollment)  # baseline: none

        # Force a real attendance shortfall, then lower the threshold so it
        # is guaranteed to trigger regardless of the default's exact value.
        session = ClassSession.objects.create(
            batch=enrollment.batch,
            session_date=date.today(),
            start_time="09:00",
            end_time="11:00",
            status=SessionStatus.COMPLETED,
            created_by=admin_user,
        )
        AttendanceRecord.objects.create(
            session=session, enrollment=enrollment, status=AttendanceStatus.ABSENT
        )
        update_policy(
            policy=get_or_create_policy(),
            actor=admin_user,
            risk_attendance_percent=Decimal("50.00"),
        )

        calls, disconnect = _connect_risk_changed()
        try:
            state = services.recompute_risk(enrollment=enrollment)
        finally:
            disconnect()

        assert state.level in (RiskLevel.WARNING, RiskLevel.CRITICAL)
        assert "attendance" in state.triggered
        assert state.previous_level == RiskLevel.NONE
        assert state.previous_triggered == []

        [sent] = calls
        assert sent["level"] == state.level
        assert sent["previous_level"] == RiskLevel.NONE
        assert sent["enrollment"] == enrollment

        notification = Notification.objects.get(kind=NotificationKind.RISK_LEVEL_CHANGED)
        assert notification.recipient_id == enrollment.batch.trainer.user_id

    def test_risk_state_for_computes_once_on_first_read_and_reuses_it_after(self, enrollment):
        """The Student 360 fallback: no waiting on the background task for a
        brand-new enrolment's very first read, and no recomputation on the
        second."""
        from apps.performance import services

        assert not RiskState.objects.filter(enrollment=enrollment).exists()
        first = services.risk_state_for(enrollment)
        assert RiskState.objects.filter(enrollment=enrollment).count() == 1

        second = services.risk_state_for(enrollment)
        assert second.pk == first.pk
        assert second.computed_at == first.computed_at  # never recomputed on a plain read


# ---------------------------------------------------------------------------
# tasks.schedule_recompute — debounce
# ---------------------------------------------------------------------------


class TestScheduleRecomputeDebounce:
    def test_a_burst_of_triggers_schedules_exactly_one_task(self, enrollment):
        from apps.performance.tasks import schedule_recompute

        with patch("apps.performance.tasks.recompute_risk.apply_async") as mocked:
            results = [schedule_recompute(enrollment.pk) for _ in range(200)]

        assert mocked.call_count == 1
        mocked.assert_called_once_with(args=[str(enrollment.pk)], countdown=5)
        # The first call wins the debounce key; every one after it is told a
        # recompute is already coming, rather than silently doing nothing
        # with no way for a test (or a caller) to tell the difference.
        assert results == [True] + [False] * 199

    def test_two_different_enrolments_each_get_their_own_task(self, enrollment, other_enrollment):
        from apps.performance.tasks import schedule_recompute

        with patch("apps.performance.tasks.recompute_risk.apply_async") as mocked:
            schedule_recompute(enrollment.pk)
            schedule_recompute(other_enrollment.pk)

        assert mocked.call_count == 2

    def test_the_task_clears_its_own_key_so_a_later_change_schedules_again(self, enrollment):
        from apps.performance.tasks import schedule_recompute

        with patch("apps.performance.tasks.recompute_risk.apply_async") as mocked:
            schedule_recompute(enrollment.pk)
        assert mocked.call_count == 1

        # The debounce key is still set — `apply_async` was mocked, so the
        # task's own `finally: cache.delete(key)` never ran.
        with patch("apps.performance.tasks.recompute_risk.apply_async") as mocked_again:
            schedule_recompute(enrollment.pk)
        assert mocked_again.call_count == 0

        # Running the task for real (Celery's eager mode, per `config.settings
        # .test`) clears the key, so the next trigger schedules a fresh task.
        from apps.performance.tasks import recompute_risk

        recompute_risk(str(enrollment.pk))
        with patch("apps.performance.tasks.recompute_risk.apply_async") as mocked_last:
            schedule_recompute(enrollment.pk)
        assert mocked_last.call_count == 1

    def test_a_deleted_enrolment_is_a_silent_no_op(self, enrollment):
        """Gone between scheduling and running (a hard delete, or a race with
        a cascade) is not an error worth logging for a task that could never
        have been retried into finding it."""
        from apps.performance.tasks import recompute_risk

        recompute_risk("00000000-0000-0000-0000-000000000000")  # must not raise


# ---------------------------------------------------------------------------
# The one receiver: apps.work.signals.activity_changed -> schedule_recompute
# ---------------------------------------------------------------------------


class TestActivityCompletedTriggersRecompute:
    def _activity_type(self, **overrides):
        from apps.work.models import ActivityType

        defaults = {
            "slug": f"risk-change-{ActivityType.objects.count()}",
            "name": "Mentoring",
            "category": "mentoring",
            "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer"],
            "allowed_assignee_roles": ["trainer"],
        }
        defaults.update(overrides)
        return ActivityType.objects.create(**defaults)

    def test_completing_an_activity_schedules_a_recompute_for_its_enrolment(
        self, enrollment, admin_user, django_capture_on_commit_callbacks
    ):
        """`on_activity_changed` defers to `transaction.on_commit`
        (`receivers.py`'s own docstring on why) — captured and flushed by
        hand, the same house pattern `test_notifications.py`'s `delivered`
        fixture uses for the same reason."""
        from apps.work.models import Activity, ActivityStatus
        from apps.work.signals import activity_changed

        activity = Activity.objects.create(
            student=enrollment.student,
            enrollment=enrollment,
            batch=enrollment.batch,
            branch=enrollment.batch.branch,
            activity_type=self._activity_type(),
            title="Check-in",
            status=ActivityStatus.COMPLETED,
            created_by=admin_user,
        )

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            with django_capture_on_commit_callbacks(execute=True):
                activity_changed.send(
                    sender=Activity, activity=activity, event="completed", actor=admin_user
                )

        mocked.assert_called_once_with(enrollment.pk)

    def test_other_events_do_not_schedule_a_recompute(self, enrollment, admin_user):
        from apps.work.models import Activity, ActivityStatus
        from apps.work.signals import activity_changed

        activity = Activity.objects.create(
            student=enrollment.student,
            enrollment=enrollment,
            batch=enrollment.batch,
            branch=enrollment.batch.branch,
            activity_type=self._activity_type(),
            title="Check-in",
            status=ActivityStatus.ASSIGNED,
            created_by=admin_user,
        )

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            activity_changed.send(
                sender=Activity, activity=activity, event="created", actor=admin_user
            )

        mocked.assert_not_called()

    def test_an_activity_with_no_enrolment_is_a_no_op(self, admin_user, student_profile):
        from apps.work.models import Activity, ActivityStatus
        from apps.work.signals import activity_changed

        activity = Activity.objects.create(
            student=student_profile,
            enrollment=None,
            branch=student_profile.branch,
            activity_type=self._activity_type(),
            title="Placement call before enrolment",
            status=ActivityStatus.COMPLETED,
            created_by=admin_user,
        )

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            activity_changed.send(
                sender=Activity, activity=activity, event="completed", actor=admin_user
            )

        mocked.assert_not_called()


# ---------------------------------------------------------------------------
# The other trigger points named in ADR-11: one representative check each,
# proving the wiring is live rather than trusting the service-layer diff by
# inspection. Each defers to `transaction.on_commit`, so each needs the same
# capture-and-flush `django_capture_on_commit_callbacks` gives.
# ---------------------------------------------------------------------------


class TestOtherTriggerPoints:
    def test_marking_attendance_schedules_a_recompute(
        self, enrollment, admin_user, django_capture_on_commit_callbacks
    ):
        from datetime import date

        from apps.attendance.models import AttendanceStatus
        from apps.attendance.services import mark_attendance
        from apps.sessions.models import ClassSession, SessionStatus

        session = ClassSession.objects.create(
            batch=enrollment.batch,
            session_date=date.today(),
            start_time="09:00",
            end_time="11:00",
            status=SessionStatus.COMPLETED,
            created_by=admin_user,
        )

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            with django_capture_on_commit_callbacks(execute=True):
                mark_attendance(
                    session=session,
                    actor=admin_user,
                    entries=[
                        {"enrollment_id": str(enrollment.pk), "status": AttendanceStatus.PRESENT}
                    ],
                )

        mocked.assert_called_once_with(enrollment.pk)

    def test_recording_an_assessment_result_schedules_a_recompute(
        self, enrollment, admin_user, django_capture_on_commit_callbacks
    ):
        from apps.assessments.models import (
            Assessment,
            AssessmentCategory,
            AssessmentDelivery,
            AssessmentStatus,
        )
        from apps.assessments.services import record_result

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

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            with django_capture_on_commit_callbacks(execute=True):
                record_result(
                    assessment=assessment, enrollment=enrollment, actor=admin_user, marks=80
                )

        mocked.assert_called_once_with(enrollment.pk)

    def test_grading_a_submission_schedules_a_recompute(
        self, enrollment, admin_user, django_capture_on_commit_callbacks
    ):
        from apps.assignments.models import Assignment, AssignmentStatus, AssignmentSubmission
        from apps.assignments.services import grade_submission
        from apps.common.identifiers import next_assignment_code

        assignment = Assignment.objects.create(
            code=next_assignment_code(),
            course=enrollment.course,
            title="Homework",
            status=AssignmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=assignment, enrollment=enrollment, attempt=1, text_answer="Done."
        )

        with patch("apps.performance.tasks.schedule_recompute") as mocked:
            with django_capture_on_commit_callbacks(execute=True):
                grade_submission(submission=submission, actor=admin_user, marks=Decimal("90"))

        mocked.assert_called_once_with(enrollment.pk)


# ---------------------------------------------------------------------------
# GET /risk/summary/ — flat query cost
# ---------------------------------------------------------------------------


class TestRiskSummaryFlatCost:
    def _make_flagged_enrollment(self, batch, index: int):
        from datetime import date, timedelta

        from apps.accounts.models import User, UserRole
        from apps.common.identifiers import next_enrolment_code, next_student_id
        from apps.enrollments.models import Enrollment, EnrollmentStatus
        from apps.students.models import StudentProfile

        user = User.objects.create_user(
            email=f"risk-summary-{index:03d}@perf.grras.invalid",
            password="Str0ng-Passphrase!42",
            first_name="Risk",
            last_name=f"Student {index}",
            role=UserRole.STUDENT,
            branch=batch.branch,
        )
        profile = StudentProfile.objects.create(
            user=user, student_id=next_student_id(), branch=batch.branch
        )
        enrollment = Enrollment.objects.create(
            code=next_enrolment_code(),
            student=profile,
            batch=batch,
            course=batch.course,
            status=EnrollmentStatus.ACTIVE,
            start_date=date.today() - timedelta(days=10),
        )
        RiskState.objects.create(
            enrollment=enrollment,
            level=RiskLevel.WARNING,
            triggered=["attendance"],
            numbers={},
        )
        return enrollment

    def test_query_count_does_not_grow_with_the_number_of_flagged_enrolments(
        self, api_client_no_csrf, admin_user, batch
    ):
        client = api_client_no_csrf
        client.force_login(admin_user)
        url = "/api/v1/risk/summary/"

        def measure() -> int:
            cache.clear()
            with CaptureQueriesContext(connection) as captured:
                response = client.get(url)
            assert response.status_code == 200
            return len(captured.captured_queries)

        for index in range(2):
            self._make_flagged_enrollment(batch, index)
        small = measure()

        for index in range(2, 25):
            self._make_flagged_enrollment(batch, index)
        large = measure()

        assert large == small, f"{small} queries for a few flagged enrolments, {large} for many"
