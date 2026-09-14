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
from apps.organisation.scoping import is_unbounded


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


def visible_export_jobs(user):
    """The export jobs the caller may list, open, download or cancel.

    `export.view_any` sits on the administrator rung, and an administrator is
    bounded to a centre (D-127) — so "any" has to mean "any at this centre".
    Without the narrowing it meant every job in the institution, and the
    download route hands over the rendered file: not a list of what another
    centre exported, but the export itself.

    A job's centre is its requester's, matching
    `apps.common.recovery.BRANCH_PATHS`, because that is whose access
    `tasks.run_export` re-derives the rows from. `requested_by` is nullable and
    the join therefore drops the jobs that have no requester — which is the
    right answer: a job nobody owns belongs to no centre.

    A caller without `export.view_any` keeps their own history, which is what
    `could_own_an_export` is about; that gate stays in the view, because an
    endpoint permanently empty for a role is refused rather than politely blank.
    """
    from apps.organisation.scoping import scope_to_branch

    from .models import ExportJob

    base = ExportJob.objects.with_related()
    if can_view_any_export_job(user):
        return scope_to_branch(base, user, path="requested_by__branch")
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.for_user(user)


def visible_bulk_imports(user):
    """The import previews the caller may open, confirm or reject.

    `ExportJob`'s sibling, and it needed the identical narrowing for the
    identical reason: `report.view_any` reads as "everything" while both roles
    that hold it are bounded to a centre (D-127). Unscoped it handed a manager
    in one city another city's parsed admissions file — the names, addresses and
    phone numbers of people who are not students anywhere yet — along with the
    two buttons that discard it or apply it. Confirming is the worse half: it
    runs `create_student(actor=...)`, so another centre's intake list would have
    been admitted as the confirming manager's own students.

    A run's centre is its uploader's, matching `visible_export_jobs` and
    `apps.common.recovery.BRANCH_PATHS`. `uploaded_by` is SET_NULL and the join
    therefore drops the orphans, which is the right answer once more: a run
    nobody owns belongs to no centre.

    A caller without `report.view_any` keeps their own history, exactly as
    before; the endpoint itself is still gated on `data.import` in the view.
    """
    from apps.organisation.scoping import scope_to_branch

    from .models import BulkImport

    base = BulkImport.objects.select_related("uploaded_by", "session")
    if can_read_everything(user):
        return scope_to_branch(base, user, path="uploaded_by__branch")
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.filter(uploaded_by=user)


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
    from apps.trainers.access import visible_trainers as trainers_in_reach
    from apps.trainers.models import TrainerProfile

    if has_capability(user, Capability.PERFORMANCE_VIEW_ANY) or can_read_everything(user):
        # The capability test stays here — this rollup is gated on
        # `performance.view_any`, not on `trainer.view_any` — but the queryset
        # is borrowed, so the hub and the trainer list cannot disagree about
        # which people exist.
        return trainers_in_reach(user)
    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return TrainerProfile.objects.select_related("user", "branch").filter(pk=trainer.pk)
    return TrainerProfile.objects.none()


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

    # Two reasons to restrict, and only the first used to exist. A trainer has
    # no `report.view_any` and never saw the institution. A branch-scoped
    # manager *holds* `report.view_any` — so without the second clause every
    # metric, dashboard figure and export ran institution-wide for exactly the
    # role branches exist to bound, while their batch list did not. Two screens
    # disagreeing, and the one that leaked was the aggregate.
    if not can_read_everything(user) or not is_unbounded(user):
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
