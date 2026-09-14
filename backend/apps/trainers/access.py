"""Trainer record access control.

The counterpart to `apps.students.access`, and written for the same reason: a
branch is a property of who is asking, and `_base_queryset()` in `views.py` takes
no user.

* **Administrators, managers and counsellors** hold `trainer.view_any`, bounded
  to their own centre — a counsellor staffing a batch must not be offered
  somebody who works in another city, and `services.assign_trainer` refuses the
  pairing anyway.
* **Trainers** reach themselves.
* **Students** reach nobody. A trainer's record is staff data.

`apps.reporting.access.visible_trainers` delegates its base to this function, so
the manager hub's trainer overview and the trainer list agree about who exists.
It keeps its own capability test, because the rollup is gated on
`performance.view_any` rather than on `trainer.view_any` — a different question
about the same set of people.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.organisation.scoping import scope_to_branch

from .models import TrainerProfile


def _base() -> QuerySet[TrainerProfile]:
    return TrainerProfile.objects.select_related("user", "branch")


def visible_trainers(user) -> QuerySet[TrainerProfile]:
    """Every trainer record the caller may see, as a queryset."""
    base = _base()

    if has_capability(user, Capability.TRAINER_VIEW_ANY):
        return scope_to_branch(base, user, path="branch")
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        return base.filter(pk=trainer.pk)

    return base.none()


def reachable_trainers(user) -> QuerySet[TrainerProfile]:
    """Every trainer record whose *centre* the caller is in — audience aside.

    The branch half of the detail route's answer, for the reason written out at
    :func:`apps.students.access.reachable_students`: another centre's trainer is
    a 404, while a colleague at the caller's own centre stays the 403 that
    :class:`~apps.common.permissions.IsOwnerOrHasCapability` has always given.
    """
    return scope_to_branch(_base(), user, path="branch")


def can_view_trainer(user, profile: TrainerProfile) -> bool:
    return visible_trainers(user).filter(pk=profile.pk).exists()
