"""The risk engine's one signal receiver (ERP Phase 13, ADR-11).

Attaches to `apps.work.signals.activity_changed` — the extension point that
module's own docstring names for exactly this ("Phase 13 (risk) needs only
the 'completed' event"). Living here, in `apps.performance`, rather than as
an edit to `apps.work.services`, is the task's own preference for a receiver
over a cross-app service edit; `apps.work` never imports anything from this
app in return.

Per `activity_changed`'s own docstring, sending happens synchronously inside
the same transaction as the write it describes, so scheduling is deferred to
`transaction.on_commit` — a receiver here must not itself decide the
caller's transaction should also carry a debounced recompute for an activity
that, moments later, never actually got saved.
"""

from __future__ import annotations

from django.db import transaction

#: Only this event moves the activity risk rule's numbers (an overdue count
#: or a last completed score) — "created"/"transitioned"/"reviewed"/"deleted"
#: do not change what `_activity_risk_numbers` reads.
_TRIGGERING_EVENT = "completed"


def on_activity_changed(sender, *, activity, event, actor=None, **kwargs) -> None:
    if event != _TRIGGERING_EVENT:
        return
    # `Activity.enrollment` is nullable (a placement call logged before an
    # enrolment exists is still that student's activity) — nothing to
    # recompute a *verdict* for without one.
    enrollment_id = activity.enrollment_id
    if not enrollment_id:
        return

    from .tasks import schedule_recompute

    transaction.on_commit(lambda: schedule_recompute(enrollment_id))
