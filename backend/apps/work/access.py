"""Activity access control.

Same shape as `apps.students.access`/`apps.dsr.access`: a queryset comes
first (`visible_activities`), and every other question ("may this caller
assign/complete/review/delete *this* activity?") is answered against the
concrete record rather than the role alone, because an activity's branch and
batch — not the caller's role — decide whether a `branch`-scoped capability
holder actually reaches it.

A trainer holds **no** `activity.*` capability at all — deliberately. Giving
one would make a trainer's capability set a strict superset of a student's,
which `tests/test_authorization_matrix.py::
test_the_scoped_roles_sit_below_the_ladder` exists specifically to catch
(and which every other domain in this codebase already avoids: see
`apps.dsr.access`, `apps.batches.access`). `PERMISSION_CATALOG.md`'s
`"(assigned)"` note for a trainer on `activity.view_any`/`create`/`complete`
is therefore read as *behaviour*, not as a literal `RolePermission` row: a
trainer reaches an activity exactly when they teach its batch, resolved per
record here (`_trainer_teaches_batch`) the same way a trainer reaches a DSR
or an enrolment — never through `has_capability`.

Four ways into an activity, all folded into `visible_activities`:

* **`activity.view_any`, scoped** (`all`/`branch`) through
  `apps.organisation.scoping.scope_to_branch` — administrators, managers,
  counsellors.
* **A trainer teaching the activity's batch** — resolved directly against
  `apps.authorization.scopes.assigned_batch_ids`, capability-free.
* **Assignee or creator**, regardless of scope or teaching assignment. A
  trainer who created or was assigned an activity for a student who has
  since moved batches must still be able to read what they wrote — the same
  reasoning `apps.dsr.access.visible_dsrs` gives for "the batches this
  trainer teaches now, not only the reports they wrote".
* **The student themselves**, through a separate function
  (`student_visible_activities`) — never folded into `visible_activities`,
  because the filtering rule is different in kind (per-field, per-type
  visibility) and conflating the two would either leak staff-only notes to a
  student union or hide a trainer's own row behind the student filter.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.authorization.scopes import ASSIGNED, BRANCH, assigned_batch_ids, effective_scope
from apps.batches import access as batch_access
from apps.organisation.scoping import actor_branch_id, is_unbounded, scope_to_branch

from .models import Activity


def _base() -> QuerySet[Activity]:
    return Activity.objects.with_related()


def caller_student_profile(user):
    """The caller's own `StudentProfile`, or `None` if they are not a student."""
    return batch_access.student_profile(user)


def _trainer_teaches_batch(user, batch_id) -> bool:
    """Capability-free: does `user` teach the batch `batch_id`, right now?

    `assigned_batch_ids` is purely structural (taught batches plus any
    `ScopeGrant`) — it says nothing about what capability, if any, the
    caller holds, which is exactly what a trainer needs here.
    """
    if batch_id is None:
        return False
    if batch_access.trainer_profile(user) is None:
        return False
    return batch_id in assigned_batch_ids(user)


def can_read_staff_activities(user) -> bool:
    """Whether this caller has any business on the staff-facing endpoints
    (`GET /activities/`, `GET /me/activities/`) at all.

    `visible_activities` already returns nothing to a student, so the list
    would be an empty 200 — safe, but the wrong shape. These two lists are
    a trainer's/counsellor's/manager's own work queue, written for staff;
    a student reaches their own activities through
    `GET /students/{id}/activities/` instead (`can_view_student`, not this).
    Saying so with a 403 keeps the surface honest, the same reasoning
    `apps.dsr.access.can_read_dsrs` gives for its own list.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    return caller_student_profile(user) is None


def visible_activities(user) -> QuerySet[Activity]:
    """Every activity the caller may see through the staff surface."""
    base = _base()
    authenticated = getattr(user, "is_authenticated", False) and user.is_active
    if not authenticated:
        return base.none()

    scoped = base.none()
    if has_capability(user, Capability.ACTIVITY_VIEW_ANY):
        scoped = scope_to_branch(base, user, path="branch", capability=Capability.ACTIVITY_VIEW_ANY)

    taught = base.none()
    if batch_access.trainer_profile(user) is not None:
        taught = base.filter(batch_id__in=assigned_batch_ids(user))

    own = base.filter(Q(assigned_to=user) | Q(created_by=user))
    return (scoped | taught | own).distinct()


def student_visible_activities(student_profile) -> QuerySet[Activity]:
    """What the student named by `student_profile` themselves may see:
    only the types and instances marked visible to a student
    (`ACTIVITY_CATALOG.md` "Student visibility")."""
    return _base().filter(
        student=student_profile, activity_type__visible_to_student=True, student_visible=True
    )


def can_manage_activity_types(user) -> bool:
    return has_capability(user, Capability.ACTIVITY_TYPE_MANAGE)


def _covers(user, capability: str, *, branch_id, batch_id=None) -> bool:
    """Does `user`'s reach for `capability` cover a record in this branch
    (and, for the three capabilities `PERMISSION_CATALOG.md` gives an
    `assigned` tier — `view_any`/`create`/`complete` — this batch)?

    This is deliberately still reachable even though no *system* role's
    default grant uses `assigned` any more (a trainer's default reach is
    resolved separately, capability-free, by `_trainer_teaches_batch`): an
    administrator may narrow a *custom* manager- or counsellor-kind role to
    `assigned` through the role builder (ADR-02), and that configured
    narrowing has to keep working.
    """
    if not has_capability(user, capability):
        return False
    if is_unbounded(user):
        return True
    scope = effective_scope(user, capability)
    if scope == BRANCH:
        caller_branch = actor_branch_id(user)
        return caller_branch is not None and caller_branch == branch_id
    if scope == ASSIGNED:
        return batch_id is not None and batch_id in assigned_batch_ids(user)
    return False


def can_assign(user, activity: Activity) -> bool:
    return activity.created_by_id == getattr(user, "pk", None) or _covers(
        user, Capability.ACTIVITY_ASSIGN, branch_id=activity.branch_id
    )


def can_complete(user, activity: Activity) -> bool:
    return (
        activity.assigned_to_id == getattr(user, "pk", None)
        or _covers(
            user,
            Capability.ACTIVITY_COMPLETE,
            branch_id=activity.branch_id,
            batch_id=activity.batch_id,
        )
        or _trainer_teaches_batch(user, activity.batch_id)
    )


def can_review(user, activity: Activity) -> bool:
    """`activity.review`, scoped, and never the person whose work it is."""
    performer_ids = {activity.performed_by_id, activity.assigned_to_id} - {None}
    if getattr(user, "pk", None) in performer_ids:
        return False
    return _covers(user, Capability.ACTIVITY_REVIEW, branch_id=activity.branch_id)


def can_reopen(user, activity: Activity) -> bool:
    return activity.created_by_id == getattr(user, "pk", None) or _covers(
        user, Capability.ACTIVITY_REVIEW, branch_id=activity.branch_id
    )


def can_delete(user, activity: Activity) -> bool:
    return _covers(user, Capability.ACTIVITY_DELETE, branch_id=activity.branch_id)


def can_create_for(user, *, branch_id, batch_id) -> bool:
    """`activity.create`, scoped to the branch or an `assigned` batch, or a
    trainer teaching the batch."""
    return _covers(
        user, Capability.ACTIVITY_CREATE, branch_id=branch_id, batch_id=batch_id
    ) or _trainer_teaches_batch(user, batch_id)


def can_be_assigned(user, *, branch_id, batch_id) -> bool:
    """Whether `user` is a legitimate assignee for a student in this
    branch/batch context: a branch- or `assigned`-scoped `activity.complete`
    holder, or a trainer teaching the batch — being assigned an activity
    means being the one expected to do the work."""
    return _covers(
        user, Capability.ACTIVITY_COMPLETE, branch_id=branch_id, batch_id=batch_id
    ) or _trainer_teaches_batch(user, batch_id)


__all__ = [
    "caller_student_profile",
    "can_assign",
    "can_be_assigned",
    "can_complete",
    "can_create_for",
    "can_delete",
    "can_manage_activity_types",
    "can_read_staff_activities",
    "can_reopen",
    "can_review",
    "student_visible_activities",
    "visible_activities",
]
