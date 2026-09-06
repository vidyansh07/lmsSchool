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
