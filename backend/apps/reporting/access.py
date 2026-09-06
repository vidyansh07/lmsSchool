"""Who may read a report.

Reports aggregate other people's records, so the rule is stricter than for the
records themselves: a report is staff-facing. Within that, the scope is the one
already established — an administrator sees everything, a trainer sees the
batches they teach, and nobody else sees a report at all.

The important consequence: a report is always built from a *scoped queryset*,
never from a global one filtered afterwards. A trainer asking for a batch they
do not teach gets an empty report, not somebody else's numbers.
"""

from __future__ import annotations

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access


def can_read_reports(user) -> bool:
    """Any staff view of aggregated data."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if has_capability(user, Capability.REPORT_VIEW_ANY):
        return True
    # A trainer may read reports about their own batches.
    return batch_access.trainer_profile(user) is not None


def can_read_everything(user) -> bool:
    return has_capability(user, Capability.REPORT_VIEW_ANY)


def can_view_any_export_job(user) -> bool:
    """Whether `user` may see and cancel export jobs they did not queue."""
    return has_capability(user, Capability.EXPORT_VIEW_ANY)


def visible_batches(user):
    return batch_access.visible_batches(user)


def visible_enrollments(user):
    return batch_access.visible_enrollments(user)


def visible_trainers(user):
    """Trainer profiles whose rollup the caller may open.

    Same shape as `visible_batches` above: a queryset, not a boolean, so the
    manager hub's trainer overview 404s on a wrong id rather than needing a
    second check bolted onto the view. An administrator or manager — anyone
    holding `performance.view_any`, which is the capability that actually
    owns "read somebody else's performance picture" — reaches every trainer;
    a trainer reaches only themselves; a counsellor or a student reaches
    nobody, the same as `visible_batches`.
    """
    from apps.trainers.models import TrainerProfile

    base = TrainerProfile.objects.select_related("user")
    if has_capability(user, Capability.PERFORMANCE_VIEW_ANY) or can_read_everything(user):
        return base
    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(pk=trainer.pk)
    return base.none()


def can_read_manager_hubs(user) -> bool:
    """The manager hubs' landing summary — an institution-wide figure.

    Deliberately narrower than `can_read_reports`. A trainer already has a
    workload screen and a batch list of their own (`trainer_workload`,
    `batch_summaries`); the summary this gates rolls up the whole
    institution — every batch, every trainer — which is a manager's question,
    not a trainer's. Same rule `AdminDashboardView` already applies to the
    administrator dashboard.
    """
    return can_read_everything(user)


def scope_for(user, *, batch=None, course=None) -> dict:
    """The scope dictionary the metric functions take.

    Resolved through the caller's own visible batches, so an id they cannot
    reach narrows the report to nothing rather than widening it.
    """
    scope: dict = {}
    if batch is not None:
        scope["batch"] = batch.pk
    if course is not None:
        scope["course"] = course.pk

    if not can_read_everything(user):
        # A trainer with no batch filter still sees only their batches, which is
        # expressed by restricting the enrolment set the metrics read.
        scope["restrict_to_batches"] = list(visible_batches(user).values_list("id", flat=True))
    return scope


def could_own_an_export(user) -> bool:
    """Whether this caller is somebody who can have queued an export at all.

    Deliberately wider than "may queue one right now": a counsellor or trainer
    whose rights changed after the fact keeps the history of what they asked
    for, which is the point of not gating the list on the queueing rules.

    It is still not open to everyone. A student never could have owned a job, so
    for them the list is permanently empty — and an endpoint that is always
    blank for a role is better refused than politely empty. That is also what
    keeps the authorization sweep meaningful rather than accumulating routes
    that "return nothing, so they are fine".
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    return (
        can_read_reports(user)
        or has_capability(user, Capability.DATA_EXPORT)
        or has_capability(user, Capability.EXPORT_VIEW_ANY)
    )
