"""The §103 chain (Phase 25, `docs/erp/USER_JOURNEYS.md` §7, `IMPLEMENTATION_PLAN.md` row 25).

USER_JOURNEYS.md §7, verbatim:

    Trainer completes a mock interview → activity and answers saved →
    appears in Student 360 (Activities, Timeline) → performance components
    update and the overall score shows its provenance → risk recomputed,
    change recorded → next action created by the rule and linked as a
    child → manager notified → manager opens the student, sees the
    activity, approves or asks for action → audit shows every step with
    who and when → the student sees the visible fields → all of it stays
    after the form gets a version 2, after the trainer leaves, after the
    batch ends.

Every arrow above is one assertion below (or a small, clearly-ordered group
of them), walked through the real service functions — never mocked, never
stubbed, exactly one realistic scenario start to finish — the same
whole-pipeline discipline `tests/test_performance.py::
test_the_cohort_report_agrees_with_the_single_student_report` already holds
this codebase to:

* ``apps.work.services.complete_activity`` / ``transition_activity`` /
  ``create_activity`` / ``review_activity``
* ``apps.students.student_360.build``
* ``apps.work.timeline.timeline_for``
* ``apps.performance.engine.student_performance``
* ``apps.performance.services.recompute_risk``
* ``apps.automation.services.dispatch``
* ``apps.audit.services.record`` (read back via ``AuditLog``)

The mock interview activity type, its form and the "communication practice
after a weak mock" automation rule are **not** invented for this test — they
are the real seeded catalog (`apps/work/migrations/0002_seed_catalog.py`,
`apps/forms/migrations/0002_seed_catalog.py`,
`apps/automation/migrations/0002_seed_rules.py`), so this test proves the
production catalog's own chain works, not a fixture built to look like it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.roles import UserRole
from apps.accounts.services import deactivate_user
from apps.audit.models import AuditAction, AuditLog
from apps.automation import services as automation_services
from apps.automation.models import (
    AutomationRule,
    AutomationRun,
    AutomationRunStatus,
    AutomationTrigger,
)
from apps.batches.models import BatchStatus
from apps.batches.services import set_batch_status
from apps.forms import services as forms_services
from apps.forms.models import FormDefinition, FormVersionStatus
from apps.notifications.models import Notification, NotificationKind
from apps.performance import services as performance_services
from apps.performance.engine import student_performance
from apps.performance.models import RiskLevel, RiskState
from apps.students import student_360
from apps.work import access as work_access
from apps.work import services as work_services
from apps.work.models import (
    Activity,
    ActivityCategory,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
)
from apps.work.serializers import ActivityDetailSerializer
from apps.work.timeline import timeline_for

pytestmark = pytest.mark.django_db


def test_the_sect103_chain_from_a_weak_mock_interview_to_manager_approval(
    admin_user,
    manager_user,
    trainer_profile,
    student_profile,
    batch,
    enrollment,
    unbounded_superadmin,
):
    """One student, one weak mock interview, walked end to end."""

    trainer_user = trainer_profile.user

    # -- Arrange: the real seeded catalog, not a lookalike fixture --------
    mock_interview = ActivityType.objects.get(
        slug="mock-interview", status=ActivityTypeStatus.ACTIVE
    )
    followup_type = ActivityType.objects.get(
        slug="communication-practice", status=ActivityTypeStatus.ACTIVE
    )
    form_definition = FormDefinition.objects.get(slug="mock-interview")
    form_version_1 = form_definition.versions.get(status=FormVersionStatus.PUBLISHED)
    assert form_version_1.number == 1

    weak_answers = {
        "technical": 3,
        "communication": 3,  # < 6: trips "Communication practice after a weak mock".
        "confidence": 3,
        "score": 2,  # /10 -> 20%, well under the 50% activity-risk threshold.
        "outcome": "not_ready",
        "strengths": "Arrived on time and answered the warm-up question calmly.",
        "improvements": "Needs to structure answers and slow down under follow-up questions.",
        "notes": "Struggled badly under pressure; flag for the manager.",  # not visible_to_student
    }

    # -----------------------------------------------------------------
    # Arrow 1-2: trainer completes a mock interview -> activity and
    # answers saved.
    # -----------------------------------------------------------------
    activity = work_services.create_activity(
        actor=trainer_user,
        student=student_profile,
        activity_type=mock_interview,
        enrollment=enrollment,
        assigned_to=trainer_user,
        planned_at=timezone.now(),
    )
    activity = work_services.transition_activity(
        actor=trainer_user, activity=activity, to_status=ActivityStatus.PLANNED
    )
    activity = work_services.transition_activity(
        actor=trainer_user, activity=activity, to_status=ActivityStatus.ASSIGNED
    )
    activity = work_services.transition_activity(
        actor=trainer_user, activity=activity, to_status=ActivityStatus.IN_PROGRESS
    )
    activity = work_services.complete_activity(
        actor=trainer_user,
        activity=activity,
        form_values=weak_answers,
        summary="Weak mock interview; needs a communication follow-up.",
    )

    assert activity.status == ActivityStatus.COMPLETED
    assert activity.form_response is not None
    assert activity.form_response.values["communication"] == "3"
    assert activity.score == Decimal("2")
    assert activity.max_score == Decimal("10")
    assert activity.result == "fail"  # 20% < the 60% pass bar

    # -----------------------------------------------------------------
    # Arrow 3: performance components update, with provenance. Computed
    # directly (`apps.performance.engine.student_performance`) — the same
    # call `apps.students.student_360._full_performance` makes, before
    # Student 360 is ever opened, mirroring the debounced Celery recompute
    # a real completion enqueues (`apps.performance.receivers`).
    # -----------------------------------------------------------------
    performance = student_performance(enrollment)
    activity_component = next(c for c in performance["components"] if c["key"] == "activity")
    assert activity_component["value"] == 20.0  # 2/10 normalised to a 0-100 scale
    assert activity_component["sources"], "provenance: the 'why' popover must list this activity"
    source = next(s for s in activity_component["sources"] if s["score"] == 20.0)
    assert source["type"] == mock_interview.name
    assert source["trainer"] == trainer_user.get_full_name()

    # -----------------------------------------------------------------
    # Arrow 4: risk recomputed, the change recorded.
    # -----------------------------------------------------------------
    assert not RiskState.objects.filter(enrollment=enrollment).exists()
    risk_state = performance_services.recompute_risk(enrollment=enrollment)
    assert risk_state.level in (RiskLevel.WARNING, RiskLevel.CRITICAL)
    assert risk_state.previous_level == ""  # first-ever verdict for this enrolment
    assert "activity" in risk_state.triggered

    risk_audit = AuditLog.objects.get(
        action=AuditAction.RISK_RECOMPUTED,
        resource_type="performance.riskstate",
        resource_id=str(risk_state.pk),
    )
    assert risk_audit.context["changed"] is True
    assert risk_audit.context["level"] == risk_state.level

    # The engine's own notification: the batch's trainer is told their
    # student's risk level moved (`services._notify_risk_changed`).
    assert Notification.objects.filter(
        recipient=trainer_user, kind=NotificationKind.RISK_LEVEL_CHANGED
    ).exists()

    # -----------------------------------------------------------------
    # Arrow 5: appears in Student 360 — Activities and Timeline. Reads
    # back the very risk verdict just computed above (`risk_state_for`
    # finds the existing row rather than computing a second one).
    # -----------------------------------------------------------------
    view = student_360.build(manager_user, student_profile)
    assert str(activity.pk) in {row["id"] for row in view["recent_activities"]}
    assert view["risk"]["level"] == risk_state.level

    since, _ = timezone.now() - timezone.timedelta(days=1), None
    entries, _ = timeline_for(
        manager_user,
        student_profile,
        since=since,
        until=timezone.now() + timezone.timedelta(days=1),
    )
    timeline_ids = {entry.id for entry in entries}
    assert f"activity:{activity.pk}" in timeline_ids
    completed_entry = next(entry for entry in entries if entry.id == f"activity:{activity.pk}")
    assert completed_entry.kind == "activity_completed"
    assert completed_entry.actor["id"] == str(trainer_user.pk)

    # -----------------------------------------------------------------
    # Arrow 6: next action created by the (real, seeded) automation rule,
    # linked as a child; the manager notified.
    # -----------------------------------------------------------------
    rule = AutomationRule.objects.get(name="Communication practice after a weak mock")
    assert rule.status == "active"  # the real seeded row, untouched

    automation_services.dispatch(AutomationTrigger.ACTIVITY_COMPLETED, activity)

    run = AutomationRun.objects.filter(rule=rule, object_id=activity.pk).latest("created_at")
    assert run.status == AutomationRunStatus.RAN

    followup = Activity.objects.get(parent=activity, activity_type=followup_type)
    assert followup.automation_run_id == run.pk
    assert followup.assigned_to_id == trainer_user.pk  # "same_assignee"
    assert followup.student_id == student_profile.pk

    assert Notification.objects.filter(
        recipient=manager_user, kind=NotificationKind.ACTIVITY_ASSIGNED, body__icontains="weak mock"
    ).exists()

    # -----------------------------------------------------------------
    # Arrow 7: manager opens the student, sees the activity, approves or
    # asks for action — the real review workflow
    # (`apps.work.services.review_activity`), exercised on a
    # review-gated follow-up the trainer logs after reading the
    # automation's notification.
    # -----------------------------------------------------------------
    review_type = ActivityType.objects.create(
        slug="mock-interview-followup-note",
        name="Follow-up note",
        category=ActivityCategory.REVIEW,
        allowed_creator_roles=[UserRole.TRAINER, UserRole.MANAGER],
        allowed_assignee_roles=[UserRole.TRAINER],
        visible_to_student=False,
        requires_review=True,
        status=ActivityTypeStatus.ACTIVE,
    )
    note_activity = work_services.create_activity(
        actor=trainer_user,
        student=student_profile,
        activity_type=review_type,
        enrollment=enrollment,
        assigned_to=trainer_user,
        planned_at=timezone.now(),
    )
    note_activity.parent = activity
    note_activity.save(update_fields=["parent"])
    note_activity = work_services.transition_activity(
        actor=trainer_user, activity=note_activity, to_status=ActivityStatus.PLANNED
    )
    note_activity = work_services.transition_activity(
        actor=trainer_user, activity=note_activity, to_status=ActivityStatus.ASSIGNED
    )
    note_activity = work_services.transition_activity(
        actor=trainer_user, activity=note_activity, to_status=ActivityStatus.IN_PROGRESS
    )
    note_activity = work_services.complete_activity(
        actor=trainer_user,
        activity=note_activity,
        summary="Discussed the mock interview result with the student and scheduled practice.",
    )
    assert note_activity.status == ActivityStatus.UNDER_REVIEW

    note_activity = work_services.review_activity(
        actor=manager_user,
        activity=note_activity,
        decision="approved",
        note="Good follow-through; keep an eye on the communication score next time.",
    )
    assert note_activity.status == ActivityStatus.APPROVED
    assert note_activity.reviewed_by_id == manager_user.pk

    # -----------------------------------------------------------------
    # Arrow 8: audit shows every step, with who and when.
    # -----------------------------------------------------------------
    activity_trail = list(
        AuditLog.objects.filter(resource_type="activity", resource_id=str(activity.pk)).order_by(
            "created_at"
        )
    )
    actions_seen = [row.action for row in activity_trail]
    assert actions_seen[0] == AuditAction.ACTIVITY_CREATED
    assert AuditAction.ACTIVITY_TRANSITIONED in actions_seen
    assert actions_seen[-1] == AuditAction.ACTIVITY_COMPLETED
    for row in activity_trail:
        assert row.actor_id == trainer_user.pk
        assert row.created_at is not None

    note_trail = list(
        AuditLog.objects.filter(
            resource_type="activity", resource_id=str(note_activity.pk)
        ).order_by("created_at")
    )
    review_row = next(row for row in note_trail if row.action == AuditAction.ACTIVITY_REVIEWED)
    assert review_row.actor_id == manager_user.pk
    assert review_row.context["decision"] == "approved"

    # -----------------------------------------------------------------
    # Arrow 9: the student sees only the visible fields.
    # -----------------------------------------------------------------
    student_view = ActivityDetailSerializer(activity, context={"as_student": True}).data
    # A student-visible activity type: score/result are on a visible field
    # here (the catalog's own `score` field is `student=True`), but the
    # staff-only "notes" field must never reach a student caller.
    assert "notes" not in student_view["form_values"]
    assert student_view["form_values"]["communication"] == "3"
    assert student_view["review_note"] == ""

    # The review-gated follow-up itself is invisible to the student union —
    # its type is not `visible_to_student` at all.
    assert (
        not work_access.student_visible_activities(student_profile)
        .filter(pk=note_activity.pk)
        .exists()
    )
    assert work_access.student_visible_activities(student_profile).filter(pk=activity.pk).exists()

    # -----------------------------------------------------------------
    # Arrow 10: all of it survives a form version 2, the trainer leaving,
    # and the batch ending.
    # -----------------------------------------------------------------
    form_version_2 = forms_services.create_draft_version(
        actor=admin_user, definition=form_definition, cloned_from=form_version_1
    )
    forms_services.publish_version(actor=admin_user, version=form_version_2)
    form_version_1.refresh_from_db()
    assert form_version_1.status == FormVersionStatus.ARCHIVED  # superseded, never deleted
    activity.refresh_from_db()
    assert activity.form_version_id == form_version_1.pk  # the historical answer stays pinned to v1

    view_after_v2 = student_360.build(manager_user, student_profile)
    assert str(activity.pk) in {row["id"] for row in view_after_v2["recent_activities"]}

    deactivate_user(user=trainer_user, actor=admin_user, reason="Left the organisation.")
    trainer_user.refresh_from_db()
    assert trainer_user.is_active is False
    view_after_departure = student_360.build(manager_user, student_profile)
    assert view_after_departure["trainer"]["id"] == str(trainer_user.pk)  # history, not erased

    completed_batch = set_batch_status(batch=batch, target=BatchStatus.COMPLETED, actor=admin_user)
    assert completed_batch.status == BatchStatus.COMPLETED
    view_after_batch_ends = student_360.build(manager_user, student_profile)
    assert view_after_batch_ends["batch"]["status"] == BatchStatus.COMPLETED
    assert str(activity.pk) in {row["id"] for row in view_after_batch_ends["recent_activities"]}

    entries_after, _ = timeline_for(
        manager_user,
        student_profile,
        since=since,
        until=timezone.now() + timezone.timedelta(days=1),
    )
    assert f"activity:{activity.pk}" in {entry.id for entry in entries_after}
