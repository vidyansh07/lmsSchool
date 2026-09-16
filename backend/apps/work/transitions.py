"""The activity lifecycle transition table (§25, `ACTIVITY_CATALOG.md`).

Pure data plus pure lookups — no database access, no capability check. This
module answers "what is legal, in principle, and who *kind* of actor may do
it?"; `services.transition_activity` resolves that actor kind against the
concrete caller and activity (capability, scope, self-review refusal) and is
the only place the two meet. Kept separate the same way
`apps.batches.services.TRANSITIONS` is data and `set_batch_status` is the
function that reads it — except here the "who" half is rich enough (creator,
assignee, a capability holder who must not be the performer, a system-only
move) to earn its own small vocabulary rather than being folded into prose in
the raising function.

Completion (`IN_PROGRESS`/`OVERDUE`/`ASSIGNED` -> `COMPLETED`, and the
system's own `COMPLETED` -> `UNDER_REVIEW` step) is deliberately **absent**
from this table. `API_CONTRACTS.md` gives completion its own endpoint,
`POST /activities/{id}/complete/`, because completing has form validation and
side effects the generic `/transition/` endpoint does not — so calling
`/transition/` with `to=completed` is refused 409 here exactly like any other
edge this table does not contain, and `details.allowed` for an `OVERDUE`
activity is correctly empty: the only legal next step is `/complete/`.

The same reasoning excludes `UNDER_REVIEW -> APPROVED`/`REQUIRES_ACTION`.
`services.review_activity` (behind `POST /activities/{id}/review/`) records
who reviewed the activity and when (`reviewed_by`/`reviewed_at`/`review_note`)
and sends the `REQUIRES_ACTION` notification — side effects
`services.transition_activity`'s generic status write does not perform. Were
these edges left in this table, `POST /transition/ {"to": "approved"}` would
move `UNDER_REVIEW` straight to `APPROVED` under the same `REVIEW_HOLDER`
check `/review/` uses, silently losing that attribution. `details.allowed`
for an `UNDER_REVIEW` activity is correctly empty: the only legal next step
is `/review/`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ActivityStatus

DRAFT = ActivityStatus.DRAFT
PLANNED = ActivityStatus.PLANNED
ASSIGNED = ActivityStatus.ASSIGNED
IN_PROGRESS = ActivityStatus.IN_PROGRESS
COMPLETED = ActivityStatus.COMPLETED
MISSED = ActivityStatus.MISSED
OVERDUE = ActivityStatus.OVERDUE
CANCELLED = ActivityStatus.CANCELLED
REOPENED = ActivityStatus.REOPENED
UNDER_REVIEW = ActivityStatus.UNDER_REVIEW
APPROVED = ActivityStatus.APPROVED
REQUIRES_ACTION = ActivityStatus.REQUIRES_ACTION


class Actor:
    """The *kind* of caller a transition accepts. `services._actor_allowed`
    turns one of these into an actual yes/no for one (actor, activity) pair."""

    #: `activity.created_by`.
    CREATOR = "creator"
    #: `activity.assigned_to`.
    ASSIGNEE = "assignee"
    #: The creator, or a holder of `activity.assign` scoped to the activity.
    ASSIGN_HOLDER = "assign_holder"
    #: A holder of `activity.review` scoped to the activity, who is not the
    #: performer or the assignee — a reviewer cannot review their own work.
    REVIEW_HOLDER = "review_holder"
    #: A holder of `activity.review` scoped to the activity, or the creator.
    REOPEN_HOLDER = "reopen_holder"
    #: Nobody. Only the beat task (`services.mark_overdue_and_missed`),
    #: calling with `actor=None`, may take this edge — a person attempting it
    #: through the API is refused `AuthorityError`, not "not in the table".
    SYSTEM = "system"


@dataclass(frozen=True)
class Edge:
    to: str
    actor: str
    #: A note is required for this move (cancel, reopen, "requires action").
    requires_note: bool = False
    #: A field that must already be set on the activity before this move:
    #: `"planned_at"` before `PLANNED`, `"assigned_to"` before `ASSIGNED`.
    precondition: str | None = None


#: One row per *source* status. `docs/erp/ACTIVITY_CATALOG.md`'s table,
#: transcribed exactly — see the module docstring for what is deliberately
#: not here (completion).
TRANSITIONS: dict[str, tuple[Edge, ...]] = {
    DRAFT: (
        Edge(PLANNED, Actor.CREATOR, precondition="planned_at"),
        Edge(CANCELLED, Actor.CREATOR, requires_note=True),
    ),
    PLANNED: (
        Edge(ASSIGNED, Actor.ASSIGN_HOLDER, precondition="assigned_to"),
        Edge(CANCELLED, Actor.ASSIGN_HOLDER, requires_note=True),
    ),
    ASSIGNED: (
        Edge(IN_PROGRESS, Actor.ASSIGNEE),
        Edge(MISSED, Actor.SYSTEM),
        Edge(CANCELLED, Actor.ASSIGN_HOLDER, requires_note=True),
        Edge(OVERDUE, Actor.SYSTEM),
    ),
    IN_PROGRESS: (Edge(OVERDUE, Actor.SYSTEM),),
    # UNDER_REVIEW -> APPROVED/REQUIRES_ACTION deliberately has no row here —
    # see the module docstring. `POST /activities/{id}/review/` /
    # `services.review_activity` is the only legal way to make that move.
    UNDER_REVIEW: (),
    REQUIRES_ACTION: (Edge(IN_PROGRESS, Actor.ASSIGNEE),),
    MISSED: (Edge(REOPENED, Actor.REOPEN_HOLDER, requires_note=True),),
    CANCELLED: (Edge(REOPENED, Actor.REOPEN_HOLDER, requires_note=True),),
    COMPLETED: (Edge(REOPENED, Actor.REOPEN_HOLDER, requires_note=True),),
    APPROVED: (Edge(REOPENED, Actor.REOPEN_HOLDER, requires_note=True),),
    REOPENED: (Edge(ASSIGNED, Actor.CREATOR, precondition="assigned_to"),),
    OVERDUE: (),
}


def legal_targets(status: str) -> frozenset[str]:
    """Every status `status` may legally move to through `/transition/`.

    Empty for a status whose only way forward is `/complete/` (`OVERDUE`) or
    that has no way forward at all through this table.
    """
    return frozenset(edge.to for edge in TRANSITIONS.get(status, ()))


def edge_for(status: str, target: str) -> Edge | None:
    """The edge `status -> target`, or `None` if it is not in the table."""
    for edge in TRANSITIONS.get(status, ()):
        if edge.to == target:
            return edge
    return None
