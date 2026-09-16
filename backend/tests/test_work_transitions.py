"""The activity lifecycle transition table (`apps/work/transitions.py`,
`ACTIVITY_CATALOG.md` "Lifecycle (§25)"): one test per legal edge (correct
actor succeeds, wrong actor 403, a missing precondition 400), an illegal
transition refused 409 with `details.allowed`, and the three system-only
moves refusing a person-initiated call.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.common.exceptions import ApplicationError, AuthorityError
from apps.work import services
from apps.work.models import Activity, ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db


def _make_type(**overrides):
    defaults = {
        "slug": f"tt-{ActivityType.objects.count()}",
        "name": "Transition Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["manager", "trainer"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _activity_at(status, *, student_profile, branch, created_by, enrollment=None, **fields):
    """Constructs an `Activity` directly at `status`, bypassing the
    transition table — each test below exercises exactly one edge out of it,
    not the whole path required to reach it."""
    activity_type = fields.pop("activity_type", None) or _make_type()
    activity = Activity.objects.create(
        student=student_profile,
        enrollment=enrollment,
        batch=enrollment.batch if enrollment else None,
        branch=branch,
        activity_type=activity_type,
        title=fields.pop("title", activity_type.name),
        status=status,
        created_by=created_by,
        **fields,
    )
    return activity


@pytest.fixture
def branch_of(student_profile):
    return student_profile.branch


# ---------------------------------------------------------------------------
# DRAFT -> PLANNED / CANCELLED
# ---------------------------------------------------------------------------


def test_draft_to_planned_by_creator_succeeds(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.DRAFT,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        planned_at=timezone.now() + timedelta(days=1),
    )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.PLANNED
    )
    assert result.status == ActivityStatus.PLANNED


def test_draft_to_planned_requires_planned_at(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.DRAFT,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.PLANNED
        )


def test_draft_to_planned_by_non_creator_is_refused(
    admin_user, manager_user, student_profile, branch_of
):
    activity = _activity_at(
        ActivityStatus.DRAFT,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        planned_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=manager_user, activity=activity, to_status=ActivityStatus.PLANNED
        )


def test_draft_to_cancelled_requires_a_note(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.DRAFT,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.CANCELLED
        )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.CANCELLED, note="Not needed."
    )
    assert result.status == ActivityStatus.CANCELLED


# ---------------------------------------------------------------------------
# PLANNED -> ASSIGNED / CANCELLED
# ---------------------------------------------------------------------------


def test_planned_to_assigned_by_creator_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.PLANNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.ASSIGNED
    )
    assert result.status == ActivityStatus.ASSIGNED


def test_planned_to_assigned_by_an_activity_assign_holder_succeeds(
    admin_user, manager_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.PLANNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=manager_user, activity=activity, to_status=ActivityStatus.ASSIGNED
    )
    assert result.status == ActivityStatus.ASSIGNED


def test_planned_to_assigned_requires_assigned_to(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.PLANNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.ASSIGNED
        )


def test_planned_to_assigned_by_an_unrelated_trainer_is_refused(
    admin_user, student_profile, branch_of, trainer_profile, trainer_profile_two
):
    activity = _activity_at(
        ActivityStatus.PLANNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=trainer_profile_two.user, activity=activity, to_status=ActivityStatus.ASSIGNED
        )


# ---------------------------------------------------------------------------
# ASSIGNED -> IN_PROGRESS / MISSED / CANCELLED / OVERDUE
# ---------------------------------------------------------------------------


def test_assigned_to_in_progress_by_the_assignee_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=trainer_profile.user, activity=activity, to_status=ActivityStatus.IN_PROGRESS
    )
    assert result.status == ActivityStatus.IN_PROGRESS
    assert result.started_at is not None


def test_assigned_to_in_progress_by_someone_else_is_refused(
    admin_user, student_profile, branch_of, trainer_profile, trainer_profile_two
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=trainer_profile_two.user, activity=activity, to_status=ActivityStatus.IN_PROGRESS
        )


def test_assigned_to_missed_by_a_person_is_refused(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.MISSED
        )


def test_assigned_to_missed_by_the_system_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=None, activity=activity, to_status=ActivityStatus.MISSED
    )
    assert result.status == ActivityStatus.MISSED


def test_assigned_to_cancelled_by_creator_requires_a_note(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.CANCELLED
        )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.CANCELLED, note="Cancelled."
    )
    assert result.status == ActivityStatus.CANCELLED


def test_assigned_to_overdue_by_a_person_is_refused(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.OVERDUE
        )


def test_assigned_to_overdue_by_the_system_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=None, activity=activity, to_status=ActivityStatus.OVERDUE
    )
    assert result.status == ActivityStatus.OVERDUE


def test_in_progress_to_overdue_is_system_only(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.IN_PROGRESS,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=trainer_profile.user, activity=activity, to_status=ActivityStatus.OVERDUE
        )
    result = services.transition_activity(
        actor=None, activity=activity, to_status=ActivityStatus.OVERDUE
    )
    assert result.status == ActivityStatus.OVERDUE


# ---------------------------------------------------------------------------
# UNDER_REVIEW -> APPROVED / REQUIRES_ACTION; REQUIRES_ACTION -> IN_PROGRESS
# ---------------------------------------------------------------------------


def test_under_review_has_no_legal_generic_transition(
    admin_user, manager_user, student_profile, branch_of, trainer_profile
):
    """`services.review_activity` (behind `POST .../review/`) is the only
    legal way to leave `UNDER_REVIEW` — it records `reviewed_by`/
    `reviewed_at`/`review_note` and sends the `REQUIRES_ACTION` notification,
    side effects the generic transition table's status write does not
    perform (see the module docstring; `test_work_engine.py` covers
    `review_activity` itself: approval, the required note, self-review
    refusal)."""
    activity = _activity_at(
        ActivityStatus.UNDER_REVIEW,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
        performed_by=trainer_profile.user,
    )
    with pytest.raises(services.TransitionError) as exc:
        services.transition_activity(
            actor=manager_user, activity=activity, to_status=ActivityStatus.APPROVED
        )
    assert exc.value.detail["allowed"] == []

    with pytest.raises(services.TransitionError):
        services.transition_activity(
            actor=manager_user, activity=activity, to_status=ActivityStatus.REQUIRES_ACTION
        )


def test_requires_action_to_in_progress_by_assignee_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.REQUIRES_ACTION,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=trainer_profile.user, activity=activity, to_status=ActivityStatus.IN_PROGRESS
    )
    assert result.status == ActivityStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# {MISSED, CANCELLED, COMPLETED, APPROVED} -> REOPENED; REOPENED -> ASSIGNED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_status",
    [
        ActivityStatus.MISSED,
        ActivityStatus.CANCELLED,
        ActivityStatus.COMPLETED,
        ActivityStatus.APPROVED,
    ],
)
def test_reopen_by_creator_requires_a_reason(admin_user, student_profile, branch_of, from_status):
    activity = _activity_at(
        from_status, student_profile=student_profile, branch=branch_of, created_by=admin_user
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.REOPENED
        )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.REOPENED, note="Reopening."
    )
    assert result.status == ActivityStatus.REOPENED


def test_reopen_by_a_review_holder_succeeds(admin_user, manager_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.APPROVED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    result = services.transition_activity(
        actor=manager_user, activity=activity, to_status=ActivityStatus.REOPENED, note="Reopening."
    )
    assert result.status == ActivityStatus.REOPENED


def test_reopen_by_an_unrelated_trainer_is_refused(
    admin_user, student_profile, branch_of, trainer_profile_two
):
    activity = _activity_at(
        ActivityStatus.APPROVED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(AuthorityError):
        services.transition_activity(
            actor=trainer_profile_two.user,
            activity=activity,
            to_status=ActivityStatus.REOPENED,
            note="Reopening.",
        )


def test_reopened_to_assigned_by_creator_succeeds(
    admin_user, student_profile, branch_of, trainer_profile
):
    activity = _activity_at(
        ActivityStatus.REOPENED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    result = services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.ASSIGNED
    )
    assert result.status == ActivityStatus.ASSIGNED


def test_reopened_to_assigned_requires_assigned_to(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.REOPENED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(ApplicationError):
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.ASSIGNED
        )


# ---------------------------------------------------------------------------
# Illegal transitions
# ---------------------------------------------------------------------------


def test_illegal_transition_is_409_with_the_allowed_list(admin_user, student_profile, branch_of):
    activity = _activity_at(
        ActivityStatus.DRAFT,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
    )
    with pytest.raises(services.TransitionError) as exc:
        services.transition_activity(
            actor=admin_user, activity=activity, to_status=ActivityStatus.APPROVED
        )
    assert exc.value.status_code == 409
    assert sorted(exc.value.detail["allowed"]) == sorted(
        [ActivityStatus.PLANNED, ActivityStatus.CANCELLED]
    )


def test_completion_is_refused_through_the_generic_transition_endpoint(
    admin_user, student_profile, branch_of, trainer_profile
):
    """Completing has its own endpoint (`services.complete_activity`); the
    generic transition table never contains a `-> completed` edge."""
    activity = _activity_at(
        ActivityStatus.ASSIGNED,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(services.TransitionError) as exc:
        services.transition_activity(
            actor=trainer_profile.user, activity=activity, to_status=ActivityStatus.COMPLETED
        )
    assert "completed" not in exc.value.detail["allowed"]


def test_overdue_has_no_legal_generic_transition(
    admin_user, student_profile, branch_of, trainer_profile
):
    """The only way out of `OVERDUE` is `/complete/`."""
    activity = _activity_at(
        ActivityStatus.OVERDUE,
        student_profile=student_profile,
        branch=branch_of,
        created_by=admin_user,
        assigned_to=trainer_profile.user,
    )
    with pytest.raises(services.TransitionError) as exc:
        services.transition_activity(
            actor=trainer_profile.user, activity=activity, to_status=ActivityStatus.CANCELLED
        )
    assert exc.value.detail["allowed"] == []
