"""Resolving a strategy name to a real user (ERP Phase 14, ADR-13).

`create_activity.assign_to`, `send_notification.to` and `create_review.reviewer`
each take a *strategy* — a named role in the story just played out
(`same_assignee`, `batch_trainer`, `counsellor`, `creator`, `manager`,
`assignee`, `submitter`, `student`, `enquiry_owner`, `least_busy_counsellor`)
or a literal user id — and this module is the one
place a strategy turns into an actual `User`. `services.py`'s ALLOWLIST
(one set of these per action) enumerates which of the two it accepts.

Everything here takes a :class:`RunContext` (an internal, non-JSON bag of
the real objects a dispatch already loaded), never `AutomationRule` or the
JSON `context` dict a condition was evaluated against — the strategy layer
does not care about templating strings, only about finding a person.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.accounts.models import User
from apps.accounts.roles import UserRole


@dataclass
class RunContext:
    """The real (non-JSON) objects this dispatch has in hand.

    `activity` is set only when the triggering object *is* an `Activity`
    (`ACTIVITY_COMPLETED`/`ACTIVITY_OVERDUE`) — that is what makes
    `same_assignee`/`assignee`/`creator` resolvable at all; for every other
    trigger those three strategies simply have nothing to resolve and are
    treated as "no recipient" rather than an error (the run still succeeds;
    that one recipient is just skipped).
    """

    student: Any = None
    enrollment: Any = None
    activity: Any = None
    branch: Any = None
    #: The submitted `FormAssignment` (`FORM_SUBMITTED` only). For that
    #: trigger `assignee`/`same_assignee`/`submitter` resolve to the person
    #: who filled the form, and `creator` to whoever sent it.
    form_assignment: Any = None
    #: The enquiry the occurrence is about: the enquiry of an enquiry event,
    #: or of an activity or form about one. `enquiry_owner` resolves here.
    enquiry: Any = None


def _first_manager(rctx: RunContext) -> User | None:
    """The institution has no single "this student's manager" column
    anywhere in the data model (unlike `trainer`, which the batch names, or
    `counsellor`, which `Enrollment.created_by` approximates) — a manager
    runs a centre, not a caseload. The best available, deterministic answer
    is the first active manager at the student's branch; if the centre has
    none, the recipient is skipped rather than guessed at (ADR-13: a failed
    resolution skips the recipient, not the run).
    """
    branch = rctx.branch or getattr(rctx.student, "branch", None)
    qs = User.objects.filter(role=UserRole.MANAGER, is_active=True)
    if branch is not None:
        qs = qs.filter(branch_id=branch.pk)
    return qs.order_by("pk").first()


def _least_busy_counsellor(rctx: RunContext) -> User | None:
    """The active counsellor at the occurrence's centre with the fewest open
    activities assigned to them — a fair way to spread new enquiries
    without anyone keeping a queue. Ties go to the earliest account."""
    from django.db.models import Count, Q

    from apps.work.models import OPEN_STATUSES

    branch = rctx.branch
    if branch is None and rctx.enquiry is not None:
        branch = rctx.enquiry.branch
    if branch is None and rctx.student is not None:
        branch = getattr(rctx.student, "branch", None)
    qs = User.objects.filter(role=UserRole.COUNSELLOR, is_active=True)
    if branch is not None:
        qs = qs.filter(branch_id=branch.pk)
    return (
        qs.annotate(
            open_work=Count(
                "assigned_activities",
                filter=Q(
                    assigned_activities__status__in=list(OPEN_STATUSES),
                    assigned_activities__deleted_at__isnull=True,
                ),
            )
        )
        .order_by("open_work", "pk")
        .first()
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def resolve_user(strategy: Any, *, rctx: RunContext) -> User | None:
    """`strategy` is one of the named keywords below, a bare user id
    (string or `UUID`), or (for `send_notification.to` only — checked by
    the caller, not here) a role slug, in which case this returns `None`
    and the caller falls back to a role-wide broadcast."""
    if strategy in ("same_assignee", "assignee", "submitter"):
        if rctx.activity is not None and strategy != "submitter":
            return rctx.activity.assigned_to
        if rctx.form_assignment is not None:
            return rctx.form_assignment.assigned_to
        return None
    if strategy == "creator":
        if rctx.activity is not None:
            return rctx.activity.created_by
        if rctx.form_assignment is not None:
            return rctx.form_assignment.requested_by
        return None
    if strategy == "batch_trainer" or strategy == "trainer":
        batch = rctx.enrollment.batch if rctx.enrollment is not None else None
        if batch is None and rctx.activity is not None:
            batch = rctx.activity.batch
        return batch.trainer.user if batch is not None and batch.trainer_id else None
    if strategy == "counsellor":
        return rctx.enrollment.created_by if rctx.enrollment is not None else None
    if strategy == "student":
        return rctx.student.user if rctx.student is not None and rctx.student.user_id else None
    if strategy == "manager":
        return _first_manager(rctx)
    if strategy == "enquiry_owner":
        enquiry = rctx.enquiry
        return enquiry.owner if enquiry is not None and enquiry.owner_id else None
    if strategy == "least_busy_counsellor":
        return _least_busy_counsellor(rctx)
    if _is_uuid(strategy):
        return User.objects.filter(pk=strategy, is_active=True).first()
    return None
