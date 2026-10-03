"""The `/activities/` filterset: every filter narrows, and none of them widens.

Split out from `test_work_visibility.py` (which asks "who may reach this
record at all?") because the question here is different in kind: given a
caller who may already see a set of activities, does each query parameter
actually *cut* that set, and does it still cut inside the caller's own
branch? Both halves matter — the `/activities` screen's "Mine" and "Overdue"
checkboxes were fetching the unfiltered list and changing nothing on screen,
because `BooleanFilter`'s default `NullBooleanSelect` widget coerces the
`?mine=1` spelling the frontend sends (and `MeActivitiesView`'s own docstring
documents) to `None`, which django-filter reads as "not supplied" and drops.
A filter that silently does nothing is indistinguishable from a filter that
narrows to everything, so each case below asserts a row is *absent* as well as
present.

Every case checks both wire spellings, `1` and `true`: the frontend sends the
first (`frontend/lib/work.ts`'s `ActivityFilters`), the OpenAPI schema and
`curl` users the second, and a regression in either is the same dead
checkbox.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.work import services
from apps.work.models import Activity, ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db

ACTIVITIES = "/api/v1/activities/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _make_type(**overrides) -> ActivityType:
    defaults = {
        "slug": f"filt-{ActivityType.objects.count()}",
        "name": "Filter Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer", "counsellor"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _ids(response) -> set[str]:
    assert response.status_code == 200, response.content
    return {row["id"] for row in response.json()["results"]}


def _force_status(activity: Activity, status: str) -> None:
    """Put a row in `status` without walking the lifecycle.

    `services.mark_overdue_and_missed` is what sets `OVERDUE` in production
    and `test_work_transitions.py` already covers that it may only be the
    system taking that edge; replaying DRAFT -> PLANNED -> ASSIGNED -> OVERDUE
    here would test the transition table a second time and say nothing about
    the filterset. Same shortcut `test_dashboards_calendar.py` takes for its
    own overdue fixtures.
    """
    Activity.objects.filter(pk=activity.pk).update(status=status)


@pytest.fixture
def world(
    admin_user,
    manager_user,
    unbounded_superadmin,
    student_profile,
    enrollment,
    trainer_profile,
    other_branch_manager,
    other_branch_student,
):
    """Four activities the Jaipur `manager_user` is asked about:

    * `own` — created by the manager themselves, so "Mine".
    * `assigned` — someone else's, assigned to a trainer, and `OVERDUE`.
    * `other_type` — same branch, a second type, neither mine nor overdue.
    * `elsewhere` — the Pune branch's, created by the Pune manager, and also
      `OVERDUE` and of the shared type, so every filter below has a
      cross-branch row it could leak.
    * `elsewhere_not_mine` — also Pune's, but created by the superadmin, so
      the Pune manager has something of their own to be narrowed *away from*.
    """
    shared_type = _make_type()
    second_type = _make_type(slug="filt-second", name="Second Filter Type")

    own = services.create_activity(
        actor=manager_user, student=student_profile, activity_type=shared_type
    )
    assigned = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=shared_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    _force_status(assigned, ActivityStatus.OVERDUE)
    other_type = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=second_type
    )
    elsewhere = services.create_activity(
        actor=other_branch_manager, student=other_branch_student, activity_type=shared_type
    )
    _force_status(elsewhere, ActivityStatus.OVERDUE)
    elsewhere_not_mine = services.create_activity(
        actor=unbounded_superadmin, student=other_branch_student, activity_type=shared_type
    )

    return {
        "own": str(own.pk),
        "assigned": str(assigned.pk),
        "other_type": str(other_type.pk),
        "elsewhere": str(elsewhere.pk),
        "elsewhere_not_mine": str(elsewhere_not_mine.pk),
        "shared_type": shared_type,
        "second_type": second_type,
        "trainer_user": trainer_profile.user,
    }


# ---------------------------------------------------------------------------
# `mine` — the caller as assignee or creator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["1", "true", "True"])
def test_mine_narrows_to_the_callers_own_work(manager_user, world, flag):
    unfiltered = _ids(_client(manager_user).get(ACTIVITIES))
    assert {world["own"], world["assigned"], world["other_type"]} <= unfiltered

    mine = _ids(_client(manager_user).get(ACTIVITIES, {"mine": flag}))
    assert mine == {world["own"]}
    # The point of the case: `mine` must be strictly smaller. Before the
    # `BooleanWidget` fix `?mine=1` returned `unfiltered` verbatim.
    assert mine < unfiltered


def test_mine_cannot_reach_another_branch(other_branch_manager, world):
    """ "Mine" is a narrowing pass over `access.visible_activities`, never a
    second way in: the Pune manager's own row is the only one they get, and
    the Jaipur rows stay invisible even though one of them is also OVERDUE."""
    unfiltered = _ids(_client(other_branch_manager).get(ACTIVITIES))
    assert {world["elsewhere"], world["elsewhere_not_mine"]} <= unfiltered

    mine = _ids(_client(other_branch_manager).get(ACTIVITIES, {"mine": "1"}))
    assert mine == {world["elsewhere"]}
    assert not (mine & {world["own"], world["assigned"], world["other_type"]})


def test_an_unticked_flag_narrows_nothing(manager_user, world):
    """`0`/`false` is "no opinion", not "not mine" — an unticked checkbox on
    the `/activities` screen must return the same list as no parameter at
    all, or clearing a filter would silently invert it."""
    unfiltered = _ids(_client(manager_user).get(ACTIVITIES))
    for flag in ("0", "false"):
        assert _ids(_client(manager_user).get(ACTIVITIES, {"mine": flag})) == unfiltered
        assert _ids(_client(manager_user).get(ACTIVITIES, {"overdue": flag})) == unfiltered


# ---------------------------------------------------------------------------
# `overdue` — the OVERDUE status, the same set `?status=overdue` returns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["1", "true", "True"])
def test_overdue_narrows_to_overdue_activities(manager_user, world, flag):
    overdue = _ids(_client(manager_user).get(ACTIVITIES, {"overdue": flag}))
    assert overdue == {world["assigned"]}
    assert world["own"] not in overdue
    # Cross-branch: the Pune row is OVERDUE too and must not appear.
    assert world["elsewhere"] not in overdue


def test_overdue_agrees_with_the_status_filter(manager_user, world):
    """`filter_overdue` asks the status question, so the "Overdue" checkbox
    and the `Status -> Overdue` dropdown option cannot disagree on screen."""
    by_flag = _ids(_client(manager_user).get(ACTIVITIES, {"overdue": "1"}))
    by_status = _ids(_client(manager_user).get(ACTIVITIES, {"status": "overdue"}))
    assert by_flag == by_status


def test_mine_and_overdue_compose(manager_user, world):
    """Both ticked is an AND, not a replace: the manager's own row is not
    overdue and the overdue row is not theirs, so the pair is empty."""
    assert _ids(_client(manager_user).get(ACTIVITIES, {"mine": "1", "overdue": "1"})) == set()


# ---------------------------------------------------------------------------
# The rest of the screen's filter bar
# ---------------------------------------------------------------------------


def test_status_narrows_and_stays_in_branch(manager_user, world):
    draft = _ids(_client(manager_user).get(ACTIVITIES, {"status": "draft"}))
    assert {world["own"], world["other_type"]} <= draft
    assert world["assigned"] not in draft
    assert world["elsewhere"] not in draft


def test_type_narrows_and_stays_in_branch(manager_user, world):
    shared = _ids(_client(manager_user).get(ACTIVITIES, {"type": world["shared_type"].slug}))
    assert {world["own"], world["assigned"]} <= shared
    assert world["other_type"] not in shared
    # The Pune row carries the *same* type — the type filter must not become a
    # way around the branch scope.
    assert world["elsewhere"] not in shared


def test_assigned_to_narrows_and_stays_in_branch(manager_user, world):
    assigned = _ids(
        _client(manager_user).get(ACTIVITIES, {"assigned_to": str(world["trainer_user"].pk)})
    )
    assert assigned == {world["assigned"]}


def test_a_cross_branch_id_filters_to_nothing_rather_than_leaking(
    manager_user, world, other_branch_manager
):
    """Filtering by a real id from the other centre is an empty 200, not a
    row: the filterset runs *inside* `access.visible_activities`, so there is
    nothing for it to select."""
    assert (
        _ids(_client(manager_user).get(ACTIVITIES, {"created_by": str(other_branch_manager.pk)}))
        == set()
    )


def test_batch_narrows(manager_user, world, enrollment):
    batch = _ids(_client(manager_user).get(ACTIVITIES, {"batch": str(enrollment.batch_id)}))
    assert batch == {world["assigned"]}
