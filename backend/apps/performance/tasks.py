"""Background risk recomputation (ERP Phase 13, ADR-11).

`recompute_risk` is a thin wrapper around `services.recompute_risk` — the
business logic lives there, not here, exactly `apps.work.tasks`' own pattern,
so a management command or a test can call the same function without going
through Celery.

Debounce
--------
A trainer marking a 60-student register, or an import re-running 200 rows of
attendance history, touches the same handful of enrolments over and over in
one burst. Scheduling a recompute on every one of those writes would run the
(not-cheap — a full `student_performance`) engine 200 times for what is, in
substance, one change per enrolment.

`schedule_recompute` claims a short-lived cache key per enrolment
(`cache.add` — an atomic "set only if absent", which every backend this
codebase configures supports: `LocMemCache` in tests, Redis via
`django-redis` in every deployed environment) before queuing anything. The
first caller in a burst wins the key and schedules the task; every caller
after it, for as long as the key stands, sees `cache.add` fail and does
nothing — a recompute for that enrolment is already coming and will read
whatever the *latest* numbers are when it actually runs, not a stale
snapshot from whichever call happened to schedule it.

The key is cleared by the task itself the moment it runs (`finally`, so a
recomputation that raises still clears it), not by its own TTL — the TTL
below is only a safety net against a task that is scheduled but, for
whatever reason, never runs (a worker outage), so a stuck key cannot wedge
this enrolment's risk out of ever recomputing again.

Window: 5 seconds (``DEBOUNCE_SECONDS``). Long enough to coalesce one
request's bulk write or one import's burst — a register or a result import
finishes in well under that — short enough that a single genuine change
(a trainer grading one submission) is never stale for more than a few
seconds on the next page load. Not "a few minutes": ADR-11's whole premise is
that a level change is an *event* worth noticing quickly, and a long window
would make every fresh flag feel delayed for no coalescing benefit once a
burst has already finished.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger("grras.performance")

#: See "Window" in the module docstring.
DEBOUNCE_SECONDS = 5

#: The pending-key's own TTL — well past `DEBOUNCE_SECONDS` so it never
#: expires before the task it is guarding has had a fair chance to run, but
#: still bounded so a worker outage cannot wedge an enrolment's debounce
#: open forever. Not the mechanism that normally clears the key — the task's
#: own `finally` is — just the fallback for when that never gets to run.
_PENDING_KEY_TTL = 120

_PENDING_KEY = "risk:pending:{enrollment_id}"


def schedule_recompute(enrollment_id) -> bool:
    """Queue a debounced risk recompute for one enrolment.

    Returns whether a new task was actually scheduled (`False` means one is
    already pending) — callers do not need to check this; it exists mainly
    so a test can observe the debounce directly instead of trusting the
    cache-key logic by inspection.
    """
    key = _PENDING_KEY.format(enrollment_id=enrollment_id)
    if not cache.add(key, True, _PENDING_KEY_TTL):
        return False
    recompute_risk.apply_async(args=[str(enrollment_id)], countdown=DEBOUNCE_SECONDS)
    return True


@shared_task(name="performance.recompute_risk", ignore_result=True)
def recompute_risk(enrollment_id: str) -> None:
    from apps.enrollments.models import Enrollment

    from . import services

    key = _PENDING_KEY.format(enrollment_id=enrollment_id)
    try:
        try:
            enrollment = Enrollment.objects.select_related(
                "student", "course", "batch", "batch__trainer__user"
            ).get(pk=enrollment_id)
        except Enrollment.DoesNotExist:
            # Gone (or soft-deleted) between scheduling and running — nothing
            # to recompute, and not an error worth logging for a task that
            # could never have been retried into finding it.
            return
        services.recompute_risk(enrollment=enrollment)
    finally:
        cache.delete(key)
