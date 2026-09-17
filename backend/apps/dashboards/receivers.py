"""Signal receiver invalidating the dashboard caches an activity completion
makes visibly wrong (ERP performance sweep, `PERFORMANCE_PLAN.md`'s caching
table: "dashboard:* ... TTL (+ forget on the writes that matter: activity
complete forgets manager/trainer)").

Connected from `DashboardsConfig.ready()` only, the same "never depend on a
phase that has not shipped" discipline `apps.automation.receivers`'
docstring sets for its own attachment to this same signal — `apps.work`
still imports nothing back from this app.

Only `dashboard:manager` (`apps.reporting.views.ManagerDashboardView`) and
`dashboard:trainer` (`apps.dashboards.views.TrainerDashboardView`) are
named in the plan; `dashboard:admin`, `dashboard:counsellor` and
`dashboard:student` stay TTL-only, exactly as the table specifies. This
bumps the whole prefix (every manager's/trainer's cache), not just the one
whose activity completed — the same "cheap and simple beats a second,
narrower mechanism for a one-minute TTL" trade-off `apps.common.caching`'s
own module docstring describes for the per-person shape in general, and
scoping to only the *relevant* manager/trainer would need threading a
branch id or a trainer id through this receiver for a saving that a 1-minute
TTL already bounds.

`activity_changed` is sent from inside `apps.work.services.complete_activity`'s
own `@transaction.atomic` block, before that write is durable, so this
forgets both prefixes now *and* registers the same forget again via
`transaction.on_commit` — the same double bump
`apps.authorization.services._forget` uses, for the same reason: bumping
only now would leave a window, between this signal firing and
`complete_activity`'s COMMIT, in which a concurrent dashboard read could
recompute from not-yet-committed state and cache that stale count for the
full TTL, with no second write left to correct it.
"""

from __future__ import annotations

from django.db import transaction


def on_activity_changed(sender, *, activity, event, actor=None, **kwargs) -> None:
    """Only ``"completed"`` moves a dashboard's counts enough to matter —
    the plan's own wording ("activity complete forgets manager/trainer"),
    mirroring `apps.automation.receivers.on_activity_changed`'s identical
    ``if event != "completed": return`` guard for the same signal."""
    if event != "completed":
        return

    from apps.common.caching import forget

    def _forget() -> None:
        forget("dashboard:manager")
        forget("dashboard:trainer")

    _forget()
    transaction.on_commit(_forget)
