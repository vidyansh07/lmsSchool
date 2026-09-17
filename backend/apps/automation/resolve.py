"""Resolving a strategy name to a real user (ERP Phase 14, ADR-13).

`create_activity.assign_to`, `send_notification.to` and `create_review.reviewer`
each take a *strategy* — a named role in the story just played out
(`same_assignee`, `batch_trainer`, `counsellor`, `creator`, `manager`,
`assignee`, `student`) or a literal user id — and this module is the one
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
    if strategy == "same_assignee" or strategy == "assignee":
        return rctx.activity.assigned_to if rctx.activity is not None else None
    if strategy == "creator":
        return rctx.activity.created_by if rctx.activity is not None else None
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
    if _is_uuid(strategy):
        return User.objects.filter(pk=strategy, is_active=True).first()
    return None
