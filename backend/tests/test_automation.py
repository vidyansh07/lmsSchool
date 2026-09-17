"""The automation engine (ERP Phase 14, ADR-13): each trigger firing with
the correct context, each action, idempotency, the depth guard, the
save-time permission check, and a loop bounded by that same depth guard.

Fixtures come from `tests/conftest.py` — `admin_user`/`manager_user`/
`counsellor_user`/`trainer`/`enrollment`/`student_profile`/`trainer_profile`
— the same set every other phase's tests build on.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.automation import services
from apps.automation.models import AutomationRule, AutomationRun, AutomationRunStatus
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.notifications.models import Notification, NotificationKind
from apps.performance.models import PerformanceReview, RiskLevel, RiskState
from apps.work.models import Activity, ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _pause_seeded_rules(db):
    """The 9 rows `automation.0002_seed_rules` seeds are active in every
    real database, including the test one — pause them so a test that
    builds its own `RISK_CHANGED`/`ACTIVITY_COMPLETED`/... rule exercises
    only the rule it just created, not a seeded rule with overlapping
    conditions running its own actions alongside it."""
    AutomationRule.objects.update(status="paused")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _activity_type(**overrides) -> ActivityType:
    defaults = {
        "slug": f"auto-type-{ActivityType.objects.count()}",
        "name": "Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer"],
        "allowed_assignee_roles": ["trainer", "manager", "counsellor"],
        "visible_to_student": True,
        "requires_review": False,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _completed_activity(
    enrollment, *, activity_type=None, score=None, max_score=None, created_by=None, **overrides
):
    activity_type = activity_type or _activity_type()
    if created_by is None:
        created_by = enrollment.batch.trainer.user
    defaults = {
        "student": enrollment.student,
        "enrollment": enrollment,
        "batch": enrollment.batch,
        "branch": enrollment.batch.branch,
        "activity_type": activity_type,
        "title": "Test activity",
        "status": ActivityStatus.COMPLETED,
        "completed_at": timezone.now(),
        "score": score,
        "max_score": max_score,
        "created_by": created_by,
    }
    defaults.update(overrides)
    return Activity.objects.create(**defaults)


def _rule(actor, *, trigger, conditions=None, actions=None, status="active", branch=None):
    return services.create_rule(
        actor=actor,
        name=f"Test rule {AutomationRule.objects.count()}",
        trigger=trigger,
        conditions=conditions or [],
        actions=actions or [],
        status=status,
        branch=branch,
    )


def _risk_state(
    enrollment, *, level=RiskLevel.WARNING, triggered=None, previous_level=""
) -> RiskState:
    return RiskState.objects.create(
        enrollment=enrollment,
        level=level,
        triggered=triggered or [],
        numbers={},
        computed_at=timezone.now(),
        previous_level=previous_level,
        previous_triggered=None,
    )


# ---------------------------------------------------------------------------
# One test per trigger — fires with the correct context
# ---------------------------------------------------------------------------


class TestTriggersFireWithCorrectContext:
    def test_activity_completed(self, admin_user, enrollment):
        activity_type = _activity_type(slug="mock-interview-test")
        activity = _completed_activity(
            enrollment, activity_type=activity_type, score=Decimal("4"), max_score=Decimal("10")
        )
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            conditions=[{"path": "activity.type", "op": "eq", "value": activity_type.slug}],
        )

        from apps.automation.models import AutomationTrigger

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        assert run.trigger == "ACTIVITY_COMPLETED"
        assert str(run.object_id) == str(activity.pk)

    def test_activity_overdue(self, admin_user, enrollment):
        activity = _completed_activity(
            enrollment,
            status=ActivityStatus.OVERDUE,
            completed_at=None,
            due_at=timezone.now() - timedelta(days=3),
        )
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_OVERDUE",
            conditions=[{"path": "activity.days_overdue", "op": "gte", "value": 2}],
        )

        from apps.automation.models import AutomationTrigger

        services.dispatch(AutomationTrigger.ACTIVITY_OVERDUE, activity, days_overdue=3)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN

    def test_assessment_failed(self, admin_user, enrollment):
        from apps.assessments.models import (
            Assessment,
            AssessmentCategory,
            AssessmentDelivery,
            AssessmentStatus,
        )
        from apps.assessments.services import record_result
        from apps.automation.models import AutomationTrigger

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
        rule = _rule(
            admin_user,
            trigger="ASSESSMENT_FAILED",
            conditions=[{"path": "assessment.percent", "op": "lt", "value": 40}],
        )

        result, _created = record_result(
            assessment=assessment, enrollment=enrollment, actor=admin_user, marks=Decimal("20")
        )

        # `record_result` defers the dispatch to `transaction.on_commit`
        # (see `apps.assessments.services`) — call the same task body it
        # enqueues, directly, the same as every other trigger test here.
        services.dispatch(
            AutomationTrigger.ASSESSMENT_FAILED, result, percent=20.0, attempt_number=1
        )

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN

    def test_attendance_threshold(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        rule = _rule(
            admin_user,
            trigger="ATTENDANCE_THRESHOLD",
            conditions=[{"path": "attendance.percent", "op": "lt", "value": 75}],
        )

        services.dispatch(
            AutomationTrigger.ATTENDANCE_THRESHOLD, enrollment, percent=60.0, absent_streak=4
        )

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN

    def test_project_overdue(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger
        from apps.common.identifiers import next_project_code
        from apps.projects.models import Project, ProjectStatus, StudentProject, WorkStatus

        project = Project.objects.create(
            code=next_project_code(),
            course=enrollment.course,
            title="Capstone",
            end_date=timezone.localdate() - timedelta(days=5),
            status=ProjectStatus.PUBLISHED,
            created_by=admin_user,
        )
        student_project = StudentProject.objects.create(
            project=project, enrollment=enrollment, status=WorkStatus.ASSIGNED
        )
        rule = _rule(
            admin_user,
            trigger="PROJECT_OVERDUE",
            conditions=[{"path": "project.days_overdue", "op": "gte", "value": 3}],
        )

        services.dispatch(AutomationTrigger.PROJECT_OVERDUE, student_project, days_overdue=5)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN

    def test_assignment_overdue(self, admin_user, enrollment):
        from apps.assignments.models import Assignment, AssignmentStatus
        from apps.automation.models import AutomationTrigger
        from apps.common.identifiers import next_assignment_code

        assignment = Assignment.objects.create(
            code=next_assignment_code(),
            course=enrollment.course,
            title="Homework",
            status=AssignmentStatus.PUBLISHED,
            max_marks=100,
            created_by=admin_user,
            due_at=timezone.now() - timedelta(days=2),
        )
        rule = _rule(
            admin_user,
            trigger="ASSIGNMENT_OVERDUE",
            conditions=[{"path": "assignment.days_overdue", "op": "gte", "value": 1}],
        )

        services.dispatch(
            AutomationTrigger.ASSIGNMENT_OVERDUE,
            assignment,
            enrollment=enrollment,
            assignment_id=str(assignment.pk),
            days_overdue=2,
        )

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        # Recorded against the enrolment, not the (shared) assignment — see
        # `services._build`'s docstring.
        assert str(run.object_id) == str(enrollment.pk)

    def test_risk_changed(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        state = _risk_state(enrollment, level=RiskLevel.CRITICAL, previous_level=RiskLevel.WARNING)
        rule = _rule(
            admin_user,
            trigger="RISK_CHANGED",
            conditions=[{"path": "risk.level", "op": "eq", "value": "critical"}],
        )

        services.dispatch(
            AutomationTrigger.RISK_CHANGED,
            state,
            enrollment=enrollment,
            level="critical",
            previous_level="warning",
            triggered=["attendance"],
            previous_triggered=[],
        )

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN


# ---------------------------------------------------------------------------
# One test per action
# ---------------------------------------------------------------------------


class TestActions:
    def test_create_activity_sets_parent_and_automation_run(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        target_type = _activity_type(slug="follow-up-test")
        source = _completed_activity(enrollment)
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {
                    "type": "create_activity",
                    "params": {"type": target_type.slug, "assign_to": "creator", "due_in_days": 5},
                }
            ],
        )
        source.created_by = admin_user
        source.save(update_fields=["created_by"])

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, source)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        child = Activity.objects.get(activity_type=target_type)
        assert child.parent_id == source.pk
        assert child.automation_run_id == run.pk
        assert child.assigned_to_id == admin_user.pk

    def test_send_notification_delivers_to_a_resolved_user(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        activity = _completed_activity(enrollment)
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {
                    "type": "send_notification",
                    "params": {
                        "to": "student",
                        "kind": NotificationKind.ACTIVITY_COMPLETED,
                        "title": "Hello {{student.name}}",
                        "body": "Well done.",
                    },
                }
            ],
        )

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        notification = Notification.objects.get(recipient=enrollment.student.user)
        assert enrollment.student.user.first_name in notification.title

    def test_send_email_always_skips_with_a_clear_reason(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        activity = _completed_activity(enrollment)
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[{"type": "send_email", "params": {"to": "student", "template": "whatever"}}],
        )

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        outcome = run.result["actions"][0]
        assert outcome["skipped"] is True
        assert "communication center" in outcome["reason"]

    def test_send_whatsapp_always_skips_with_a_clear_reason(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        activity = _completed_activity(enrollment)
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {"type": "send_whatsapp", "params": {"to": "student", "template": "whatever"}}
            ],
        )

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        outcome = run.result["actions"][0]
        assert outcome["skipped"] is True
        assert "provider configured" in outcome["reason"]

    def test_create_review_opens_a_draft(self, admin_user, manager_user, enrollment):
        from apps.automation.models import AutomationTrigger

        state = _risk_state(enrollment, level=RiskLevel.CRITICAL, previous_level=RiskLevel.WARNING)
        rule = _rule(
            admin_user,
            trigger="RISK_CHANGED",
            actions=[
                {
                    "type": "create_review",
                    "params": {"review_type": "ad_hoc", "reviewer": "manager", "due_in_days": 7},
                }
            ],
        )

        services.dispatch(
            AutomationTrigger.RISK_CHANGED,
            state,
            enrollment=enrollment,
            level="critical",
            previous_level="warning",
            triggered=[],
            previous_triggered=[],
        )

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        review = PerformanceReview.objects.get(student=enrollment.student)
        assert review.status == "draft"
        assert review.reviewer_id == manager_user.pk

    def test_flag_risk_writes_a_manual_override(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        state = _risk_state(enrollment, level=RiskLevel.NONE)
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {"type": "flag_risk", "params": {"level": "warning", "reason": "Missed calls."}}
            ],
        )
        activity = _completed_activity(enrollment)

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        run = AutomationRun.objects.get(rule=rule)
        assert run.status == AutomationRunStatus.RAN
        state.refresh_from_db()
        assert state.level == RiskLevel.WARNING
        assert state.manual_override is True
        assert state.manual_override_expires_at is not None


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_the_same_occurrence_twice_produces_exactly_one_ran_run(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger

        activity = _completed_activity(enrollment)
        rule = _rule(admin_user, trigger="ACTIVITY_COMPLETED")

        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)
        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        assert AutomationRun.objects.filter(rule=rule).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_two_simultaneous_dispatches_of_the_same_occurrence_make_one_run(
        self, admin_user, enrollment
    ):
        """The genuine concurrent race `AGENT_PLAYBOOK.md` calls for — mirrors
        `tests/test_work_engine.py::test_two_simultaneous_creates_with_the_same_client_key_make_one_row`.
        """
        from apps.automation.models import AutomationTrigger

        activity = _completed_activity(enrollment)
        rule = _rule(admin_user, trigger="ACTIVITY_COMPLETED")

        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def attempt() -> None:
            try:
                barrier.wait(timeout=5)
                services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)
            except Exception as exc:  # pragma: no cover - surfaced via `errors`
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors, errors
        assert AutomationRun.objects.filter(rule=rule).count() == 1


# ---------------------------------------------------------------------------
# Rate guard
# ---------------------------------------------------------------------------


class TestRateGuard:
    def test_stops_at_the_daily_limit_per_object(self, admin_user, enrollment):
        from apps.automation.models import AutomationTrigger
        from apps.policies.services import update_policy

        update_policy(
            actor=admin_user,
            category="automation",
            key="max_runs_per_object_per_day",
            value=1,
            branch=None,
            reason="test",
        )

        rule = _rule(admin_user, trigger="ACTIVITY_COMPLETED")
        activity = _completed_activity(enrollment)

        # First occurrence: within the (lowered to 1) daily limit — runs.
        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        # A second, genuinely distinct occurrence of the *same* activity
        # (object id unchanged) — a re-review-and-re-complete cycle, say.
        # The rate guard counts by (rule, object), not by occurrence, so
        # this is the one already at the limit.
        activity.completed_at = timezone.now() + timedelta(minutes=1)
        activity.save(update_fields=["completed_at"])
        services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

        runs = AutomationRun.objects.filter(rule=rule, object_id=activity.pk).order_by("created_at")
        assert runs.count() == 2
        assert runs[0].status == AutomationRunStatus.RAN
        assert runs[1].status == AutomationRunStatus.SKIPPED
        assert "max_runs_per_object_per_day" in runs[1].result["reason"]


# ---------------------------------------------------------------------------
# Depth guard + loop
# ---------------------------------------------------------------------------


class TestDepthGuardAndLoop:
    def test_a_flag_risk_chain_that_could_loop_forever_is_bounded_at_depth_three(
        self, admin_user, enrollment
    ):
        """Two rules that flip a `RiskState` back and forth via `flag_risk`
        — each firing on the level the other just set — would loop forever
        without the depth guard. This proves the guard, not an ad-hoc
        cycle-detector, is what stops it."""
        from apps.automation.models import AutomationTrigger

        state = _risk_state(enrollment, level=RiskLevel.WARNING)

        rule_to_critical = _rule(
            admin_user,
            trigger="RISK_CHANGED",
            conditions=[{"path": "risk.level", "op": "eq", "value": "warning"}],
            actions=[{"type": "flag_risk", "params": {"level": "critical", "reason": "loop test"}}],
        )
        rule_to_warning = _rule(
            admin_user,
            trigger="RISK_CHANGED",
            conditions=[{"path": "risk.level", "op": "eq", "value": "critical"}],
            actions=[{"type": "flag_risk", "params": {"level": "warning", "reason": "loop test"}}],
        )

        services.dispatch(
            AutomationTrigger.RISK_CHANGED,
            state,
            depth=0,
            enrollment=enrollment,
            level="warning",
            previous_level=None,
            triggered=[],
            previous_triggered=[],
        )

        runs = list(AutomationRun.objects.order_by("depth"))
        depths = [run.depth for run in runs]
        assert depths == [0, 1, 2, 3]
        assert [run.status for run in runs[:3]] == [AutomationRunStatus.RAN] * 3
        assert runs[3].status == AutomationRunStatus.SKIPPED
        assert "depth" in runs[3].result["reason"]
        # The chain never reaches a 5th run (depth 4) — proof it is bounded,
        # not merely slow.
        assert AutomationRun.objects.count() == 4
        assert {run.rule_id for run in runs[:3]} == {rule_to_critical.pk, rule_to_warning.pk}


# ---------------------------------------------------------------------------
# The save-time permission check
# ---------------------------------------------------------------------------


class TestSaveTimePermissionCheck:
    def test_an_author_lacking_communication_send_cannot_save_a_send_notification_rule(
        self, trainer
    ):
        with pytest.raises(AuthorityError):
            services.create_rule(
                actor=trainer,
                name="Should be refused",
                trigger="ACTIVITY_COMPLETED",
                actions=[
                    {
                        "type": "send_notification",
                        "params": {"to": "student", "kind": "activity.completed", "title": "x"},
                    }
                ],
            )

    def test_an_author_lacking_review_manage_any_cannot_save_a_create_review_rule(self, trainer):
        with pytest.raises(AuthorityError):
            services.create_rule(
                actor=trainer,
                name="Should be refused",
                trigger="RISK_CHANGED",
                actions=[{"type": "create_review", "params": {"reviewer": "manager"}}],
            )

    def test_an_author_holding_every_needed_permission_may_save(self, admin_user):
        rule = services.create_rule(
            actor=admin_user,
            name="Allowed",
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {
                    "type": "send_notification",
                    "params": {"to": "student", "kind": "activity.completed", "title": "x"},
                }
            ],
        )
        assert rule.pk is not None

    def test_an_unknown_operator_is_refused_at_save_time(self, admin_user):
        with pytest.raises(ApplicationError):
            services.create_rule(
                actor=admin_user,
                name="Bad operator",
                trigger="ACTIVITY_COMPLETED",
                conditions=[{"path": "activity.score", "op": "regex_match", "value": "x"}],
            )

    def test_a_path_outside_the_triggers_allowlist_is_refused_at_save_time(self, admin_user):
        with pytest.raises(ApplicationError):
            services.create_rule(
                actor=admin_user,
                name="Bad path",
                trigger="ACTIVITY_COMPLETED",
                conditions=[{"path": "risk.level", "op": "eq", "value": "critical"}],
            )

    def test_sync_pauses_a_rule_whose_author_lost_a_needed_permission(self, admin_user, trainer):
        rule = _rule(
            admin_user,
            trigger="ACTIVITY_COMPLETED",
            actions=[
                {
                    "type": "send_notification",
                    "params": {"to": "student", "kind": "activity.completed", "title": "x"},
                }
            ],
        )
        rule.created_by = trainer
        rule.save(update_fields=["created_by"])

        paused = services.sync_rule_authors()

        rule.refresh_from_db()
        assert paused == 1
        assert rule.status == "paused"

    def test_sync_never_touches_a_rule_with_no_author(self, admin_user):
        """The 9 seeded rows have no individual author — sync must not treat
        that as "lost permission"."""
        rule = _rule(admin_user, trigger="ACTIVITY_COMPLETED")
        rule.created_by = None
        rule.save(update_fields=["created_by"])

        paused = services.sync_rule_authors()

        rule.refresh_from_db()
        assert paused == 0
        assert rule.status == "active"


class TestListCreateViewOverHTTP:
    """A real `client.get(url)` through the DRF view layer, not just a
    `services.*` call: this is the exact gap that let
    `AutomationRuleListCreateView`'s missing `serializer_class` ship to
    staging with a green test suite and a clean `check --deploy` — every
    other test in this file calls the service functions directly, so
    `ListAPIView.get()`'s own `self.get_serializer(page, many=True)` call
    (which needs `get_serializer_class()` to resolve, regardless of what
    `@extend_schema(responses=...)` declares for documentation purposes)
    never actually ran until a real request hit it. See
    docs/erp/AGENT_PLAYBOOK.md's note on this class of bug."""

    def test_listing_rules_over_http_does_not_500(self, api_client_no_csrf, admin_user):
        _rule(admin_user, trigger="ACTIVITY_COMPLETED")
        api_client_no_csrf.force_login(admin_user)
        response = api_client_no_csrf.get("/api/v1/automation-rules/")
        assert response.status_code == 200, response.data
        assert response.data["count"] >= 1
