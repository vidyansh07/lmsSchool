"""The two questions the branch seam keeps apart, asked without a database.

`apps.organisation.scoping` is the one place in the codebase where "sees every
centre" and "is in no centre" are told apart. Everything else — sixteen access
modules, the recycle bin's restore guard, `create_user` — reads the answer from
here, so a wrong answer here is wrong everywhere at once and in the direction
nobody notices: a manager quietly seeing another city's students.

These tests are deliberately about the helpers alone, on hand-built objects
rather than rows, because the properties they defend are properties of the
*logic* and a database would only make them slower to state:

* a null branch is **not** a licence, for anybody but a platform operator;
* `AnonymousUser` reaches these helpers — they are called above the
  authenticated guard by convention — and must not raise `AttributeError`;
* `branch_scope_key` gives "everything" and "nothing" different keys, so a
  cache built on it cannot serve one audience's rows to the other.

The queryset half of the seam (`scope_to_branch`,
`scope_to_branch_or_shared`) needs real SQL and is proved in
`tests/test_branch_scoping.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.accounts.roles import UserRole
from apps.organisation.scoping import (
    actor_branch_id,
    branch_scope_key,
    is_unbounded,
    scope_to_branch,
    scope_to_branch_or_shared,
)


def _actor(*, role=UserRole.MANAGER, branch_id="branch-a", is_superuser=False, is_active=True):
    """A stand-in for a signed-in user, with only the attributes the seam reads."""
    return SimpleNamespace(
        is_authenticated=True,
        is_active=is_active,
        is_superuser=is_superuser,
        role=role,
        branch_id=branch_id,
    )


class _RecordingQuerySet:
    """A queryset that remembers what was asked of it instead of running SQL.

    Enough to state the two claims that are about *shape* rather than about
    rows: an unbounded caller's queryset comes back as the very same object,
    and a caller with no centre never reaches `.filter()` at all.
    """

    def __init__(self):
        self.filter_calls: list[tuple] = []
        self.none_calls = 0

    def filter(self, *args, **kwargs):
        self.filter_calls.append((args, kwargs))
        return self

    def none(self):
        self.none_calls += 1
        return self


# ---------------------------------------------------------------------------
# is_unbounded — who sees every centre
# ---------------------------------------------------------------------------


def test_a_superadmin_by_role_is_unbounded():
    assert is_unbounded(_actor(role=UserRole.SUPERADMIN, branch_id=None)) is True


def test_a_django_superuser_is_unbounded_whatever_its_role_says():
    assert is_unbounded(_actor(role=UserRole.ADMIN, is_superuser=True)) is True


def test_an_administrator_is_unbounded():
    """D-129 as amended on 14 September 2026: "admin sees every centre"."""
    assert is_unbounded(_actor(role=UserRole.ADMIN)) is True
    assert is_unbounded(_actor(role=UserRole.ADMIN, branch_id=None)) is True


@pytest.mark.parametrize(
    "role",
    [UserRole.MANAGER, UserRole.COUNSELLOR, UserRole.TRAINER, UserRole.STUDENT],
)
def test_every_role_below_administrator_is_bounded(role):
    assert is_unbounded(_actor(role=role)) is False, role


def test_a_bounded_role_with_no_branch_at_all_is_still_not_unbounded():
    """The whole point. A missing branch is the *absence* of reach, not all of it."""
    assert is_unbounded(_actor(role=UserRole.MANAGER, branch_id=None)) is False


def test_an_inactive_superadmin_is_not_unbounded():
    assert is_unbounded(_actor(role=UserRole.SUPERADMIN, is_active=False)) is False


def test_an_anonymous_caller_is_not_unbounded_and_does_not_raise():
    assert is_unbounded(AnonymousUser()) is False


def test_no_caller_at_all_is_not_unbounded():
    assert is_unbounded(None) is False


# ---------------------------------------------------------------------------
# actor_branch_id — which centre a caller is in
# ---------------------------------------------------------------------------


def test_a_bounded_caller_reports_the_plain_column_value():
    assert actor_branch_id(_actor(branch_id="branch-a")) == "branch-a"


def test_a_superadmin_reports_no_centre_rather_than_every_centre():
    """`None` from this function means *no centre*; only `is_unbounded` means all."""
    assert actor_branch_id(_actor(role=UserRole.SUPERADMIN, branch_id=None)) is None


def test_an_inactive_caller_reports_no_centre():
    assert actor_branch_id(_actor(is_active=False)) is None


def test_an_anonymous_caller_reports_no_centre_and_does_not_raise():
    assert actor_branch_id(AnonymousUser()) is None


def test_no_caller_at_all_reports_no_centre():
    assert actor_branch_id(None) is None


# ---------------------------------------------------------------------------
# scope_to_branch — the shape of the narrowing
# ---------------------------------------------------------------------------


def test_an_unbounded_caller_gets_back_the_identical_queryset_object():
    """Not merely an equal one: nothing about a superadmin's query plan changes."""
    queryset = _RecordingQuerySet()
    assert scope_to_branch(queryset, _actor(role=UserRole.SUPERADMIN)) is queryset
    assert queryset.filter_calls == []
    assert queryset.none_calls == 0


def test_a_bounded_caller_is_filtered_on_the_named_path():
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, _actor(branch_id="branch-a"), path="batch__branch")
    assert queryset.filter_calls == [((), {"batch__branch_id": "branch-a"})]


def test_the_default_path_is_the_models_own_branch_column():
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, _actor(branch_id="branch-a"))
    assert queryset.filter_calls == [((), {"branch_id": "branch-a"})]


def test_scoping_the_branch_table_itself_compares_the_primary_key():
    """`path="id"` names no relation — the row *is* the centre.

    Appending `_id` to it asks for a field called `id_id`, which raised
    `FieldError` and 500'd the branch list for every bounded caller.
    """
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, _actor(branch_id="branch-a"), path="id")
    assert queryset.filter_calls == [((), {"id": "branch-a"})]


def test_a_caller_with_no_centre_is_emptied_and_never_filtered():
    """Fail closed. A missing branch must not fall through to an unfiltered set."""
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, _actor(branch_id=None))
    assert queryset.none_calls == 1
    assert queryset.filter_calls == []


def test_an_anonymous_caller_is_emptied_rather_than_raising():
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, AnonymousUser())
    assert queryset.none_calls == 1
    assert queryset.filter_calls == []


def test_an_inactive_caller_is_emptied_even_though_they_carry_a_branch():
    queryset = _RecordingQuerySet()
    scope_to_branch(queryset, _actor(branch_id="branch-a", is_active=False))
    assert queryset.none_calls == 1
    assert queryset.filter_calls == []


# ---------------------------------------------------------------------------
# scope_to_branch_or_shared — the nullable-foreign-key trap
# ---------------------------------------------------------------------------


def test_an_unbounded_caller_gets_back_the_identical_queryset_from_the_shared_variant():
    queryset = _RecordingQuerySet()
    assert (
        scope_to_branch_or_shared(queryset, _actor(role=UserRole.SUPERADMIN), path="batch__branch")
        is queryset
    )
    assert queryset.filter_calls == []


def test_a_bounded_caller_keeps_the_rows_that_belong_to_no_batch():
    """One `filter` carrying an OR, never an inner join that drops the null rows."""
    queryset = _RecordingQuerySet()
    scope_to_branch_or_shared(queryset, _actor(branch_id="branch-a"), path="batch__branch")

    assert len(queryset.filter_calls) == 1
    (args, kwargs) = queryset.filter_calls[0]
    assert kwargs == {}
    assert len(args) == 1
    rendered = str(args[0])
    assert "batch__isnull" in rendered, rendered
    assert "batch__branch_id" in rendered, rendered
    assert "OR" in rendered, rendered


def test_a_caller_with_no_centre_is_emptied_by_the_shared_variant_too():
    """The same answer `scope_to_branch` gives, and for the same reason.

    An earlier reading handed a branchless caller the course-wide rows, on the
    grounds that those belong to no centre. It made "bounded to nothing" mean
    two different things in two helpers one screen apart, and it meant a manager
    created through the Django admin read every course-wide assignment, project
    and notice in the institution. The account that really does see everything
    is a superadmin, and `is_unbounded` has already answered above.
    """
    queryset = _RecordingQuerySet()
    scope_to_branch_or_shared(queryset, _actor(branch_id=None), path="batch__branch")
    assert queryset.none_calls == 1
    assert queryset.filter_calls == []


def test_an_anonymous_caller_is_emptied_rather_than_reaching_the_course_wide_rows():
    queryset = _RecordingQuerySet()
    scope_to_branch_or_shared(queryset, AnonymousUser(), path="batch__branch")
    assert queryset.none_calls == 1
    assert queryset.filter_calls == []


def test_a_deeper_path_treats_everything_before_the_last_segment_as_the_relation():
    queryset = _RecordingQuerySet()
    scope_to_branch_or_shared(
        queryset, _actor(branch_id="branch-a"), path="enrollment__batch__branch"
    )

    assert len(queryset.filter_calls) == 1
    rendered = str(queryset.filter_calls[0][0][0])
    assert "enrollment__batch__isnull" in rendered, rendered
    assert "enrollment__batch__branch_id" in rendered, rendered


# ---------------------------------------------------------------------------
# branch_scope_key — two audiences, two cache segments
# ---------------------------------------------------------------------------


def test_seeing_everything_and_seeing_nothing_get_different_cache_keys():
    """`actor_branch_id` alone answers `None` to both, which is how a cache
    ends up serving one centre's rows to the account that should see none."""
    everything = branch_scope_key(_actor(role=UserRole.SUPERADMIN, branch_id=None))
    nothing = branch_scope_key(_actor(branch_id=None))
    assert everything != nothing
    assert everything == "*"
    assert nothing == "-"


def test_a_bounded_caller_keys_on_their_own_branch():
    assert branch_scope_key(_actor(branch_id="branch-a")) == "branch-a"


def test_two_branches_never_share_a_cache_key():
    assert branch_scope_key(_actor(branch_id="branch-a")) != branch_scope_key(
        _actor(branch_id="branch-b")
    )


def test_an_anonymous_caller_keys_as_nothing_rather_than_as_everything():
    assert branch_scope_key(AnonymousUser()) == "-"
