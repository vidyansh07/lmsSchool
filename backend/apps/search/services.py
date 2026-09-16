"""Global search (ERP Phase 11, `API_CONTRACTS.md` "Search and productivity").

One endpoint, ten sources, and exactly one rule: **every source is that
domain's own `visible_*` (or `manageable_*`/capability-gated) queryset, never
an unscoped one.** A search hit is a disclosure in its own right — a caller
who could not open a record's detail page must not be told the record
exists by seeing its title in a results list either, even though the detail
route itself would correctly 403 or 404 if they tried. This is the same
class of bug Phase 9's review caught twice on the activity list and the
timeline (an unscoped fallback query slipped in beside the scoped one); a
search source is a *new* place for exactly that mistake to hide, so each one
below is a single call into the domain's existing access layer, not a fresh
query.

`users`/`staff` has no pre-existing `visible_users` helper — the admin users
list (`apps.accounts.user_views.UserListCreateView`) reaches its queryset
through `apps.accounts.access.visible_accounts`, which is *branch-scoped
only*: it holds no capability check of its own; the view supplies that
separately via `HasCapability`/`Capability.USER_VIEW_ANY`. Calling
`visible_accounts` alone from here — reachable by every authenticated user
through `search.global` — would hand every trainer and student in a branch
the whole staff-and-student directory. `_users` below reproduces the view's
*pair* of checks (the capability, then the branch-scoped queryset), not
just the second half of it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db.models import Q, QuerySet

#: Default hits shown per source when its type is not in `types=`.
DEFAULT_LIMIT = 5

#: Hits shown per source once its type is named in `types=` — generous, but
#: still a page, not "everything": a caller who wants more than this is
#: paging the domain's own list endpoint, which is what it is for.
EXPANDED_LIMIT = 25


def _hit(pk: Any, title: str, subtitle: str, href: str) -> dict:
    return {"id": str(pk), "title": title, "subtitle": subtitle or "", "href": href}


def _user_label(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.email


def _students(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.students import access as students_access

    qs: QuerySet = students_access.visible_students(user).filter(
        Q(user__first_name__icontains=query)
        | Q(user__last_name__icontains=query)
        | Q(user__email__icontains=query)
        | Q(student_id__icontains=query)
        | Q(roll_number__icontains=query)
    )
    total = qs.count()
    rows = list(qs.select_related("user")[:limit])
    return total, [
        _hit(row.pk, _user_label(row.user), row.student_id, f"/students/{row.pk}") for row in rows
    ]


def _trainers(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.trainers import access as trainers_access

    qs = trainers_access.visible_trainers(user).filter(
        Q(user__first_name__icontains=query)
        | Q(user__last_name__icontains=query)
        | Q(user__email__icontains=query)
        | Q(trainer_id__icontains=query)
    )
    total = qs.count()
    rows = list(qs.select_related("user")[:limit])
    return total, [
        _hit(row.pk, _user_label(row.user), row.trainer_id, f"/manage/trainers/{row.pk}")
        for row in rows
    ]


def _users(user, query: str, limit: int) -> tuple[int, list[dict]]:
    """Staff and student *accounts* — distinct from the `students`/`trainers`
    sources above, which search the domain profile, not the login record."""
    from apps.accounts.access import visible_accounts
    from apps.accounts.roles import Capability, has_capability

    # The capability half of `UserListCreateView`'s rule (see module
    # docstring) — `visible_accounts` supplies only the branch half.
    if not has_capability(user, Capability.USER_VIEW_ANY):
        return 0, []

    qs = visible_accounts(user).filter(
        Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
    )
    total = qs.count()
    rows = list(qs[:limit])
    return total, [
        _hit(row.pk, _user_label(row), row.role, f"/admin/users/{row.pk}") for row in rows
    ]


def _batches(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.batches import access as batch_access

    qs = batch_access.visible_batches(user).filter(
        Q(name__icontains=query) | Q(code__icontains=query)
    )
    total = qs.count()
    rows = list(qs[:limit])
    return total, [_hit(row.pk, row.name, row.code, f"/admin/batches/{row.pk}") for row in rows]


def _courses(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.courses import access as course_access

    qs = course_access.visible_courses(user).filter(
        Q(title__icontains=query) | Q(slug__icontains=query)
    )
    total = qs.count()
    rows = list(qs[:limit])
    return total, [_hit(row.pk, row.title, row.slug, f"/admin/courses/{row.pk}") for row in rows]


def _activities(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.work import access as work_access

    # A student's own activity view is a different surface
    # (`GET /students/{id}/activities/`, per-instance visibility rules) —
    # `can_read_staff_activities` is the same "has any business here at all"
    # gate `ActivityListCreateView` itself uses, so a student searching gets
    # nothing here rather than an accidental peek through `visible_activities`
    # falling back to `own`.
    if not work_access.can_read_staff_activities(user):
        return 0, []

    qs = work_access.visible_activities(user).filter(title__icontains=query)
    total = qs.count()
    rows = list(qs.select_related("student__user")[:limit])
    return total, [
        _hit(
            row.pk,
            row.title,
            _user_label(row.student.user) if row.student_id else "",
            f"/activities?id={row.pk}",
        )
        for row in rows
    ]


def _assessments(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.assessments import access as assessment_access

    qs = assessment_access.visible_assessments(user).filter(title__icontains=query)
    total = qs.count()
    rows = list(qs.select_related("batch")[:limit])
    return total, [
        _hit(row.pk, row.title, row.batch.code, f"/teaching/assessments/{row.pk}") for row in rows
    ]


def _assignments(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.assignments import access as assignment_access

    qs = assignment_access.visible_assignments(user).filter(title__icontains=query)
    total = qs.count()
    rows = list(qs.select_related("course")[:limit])
    return total, [
        _hit(row.pk, row.title, row.course.title, f"/teaching/assignments/{row.pk}") for row in rows
    ]


def _projects(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.projects import access as project_access

    qs = project_access.visible_projects(user).filter(title__icontains=query)
    total = qs.count()
    rows = list(qs.select_related("course")[:limit])
    return total, [
        _hit(row.pk, row.title, row.course.title, f"/teaching/projects/{row.pk}") for row in rows
    ]


def _dsrs(user, query: str, limit: int) -> tuple[int, list[dict]]:
    from apps.dsr import access as dsr_access

    if not dsr_access.can_read_dsrs(user):
        return 0, []

    qs = dsr_access.visible_dsrs(user).filter(
        Q(planned_topic__icontains=query) | Q(actual_topic__icontains=query)
    )
    total = qs.count()
    rows = list(qs.select_related("batch")[:limit])
    return total, [
        _hit(
            row.pk, f"{row.batch.code} — {row.report_date}", row.planned_topic, f"/dsr?id={row.pk}"
        )
        for row in rows
    ]


#: `(label, source function)`, keyed by the name `types=` names. Order here
#: is the order groups come back in.
SOURCES: dict[str, tuple[str, Callable[[Any, str, int], tuple[int, list[dict]]]]] = {
    "students": ("Students", _students),
    "trainers": ("Trainers", _trainers),
    "users": ("Staff", _users),
    "batches": ("Batches", _batches),
    "courses": ("Courses", _courses),
    "activities": ("Activities", _activities),
    "assessments": ("Assessments", _assessments),
    "assignments": ("Assignments", _assignments),
    "projects": ("Projects", _projects),
    "dsrs": ("Daily status reports", _dsrs),
}


def search(user, *, query: str, expand: frozenset[str]) -> list[dict]:
    """One group per source. `expand` names the types shown past the 5-hit
    cap — never a way to skip a source's own scoping, only its `limit`."""
    groups = []
    for key, (label, source_fn) in SOURCES.items():
        limit = EXPANDED_LIMIT if key in expand else DEFAULT_LIMIT
        total, results = source_fn(user, query, limit)
        groups.append({"type": key, "label": label, "results": results, "total": total})
    return groups
