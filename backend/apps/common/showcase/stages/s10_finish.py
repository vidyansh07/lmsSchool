"""Stage 10 — tidy up and say what happened.

Creates nothing. Clears the Django cache — dashboards, the warnings strip,
the fees overview, resolved policies, published forms and templates and the
roles matrix are all cached, and a reviewer opening the app a minute after
seeding would otherwise see the empty database the cache remembers — unless
the cache and the Celery broker are the same Redis database, in which case
``cache.clear()`` is a ``FLUSHDB`` that would empty the task queue too, and
the clear is skipped with a warning. Then **abandons the outbox** this run
filled: every notification the stages raised queued an
``notifications.EmailMessage`` row that the worker and the retry sweep would
deliver later under whatever ``EMAIL_BACKEND`` *they* run with, so the
command's mail gate alone does not keep showcase mail off the wire. Every
row still deliverable and created since the run started is moved to
``ABANDONED`` (the outbox's terminal "given up" status) with a note saying
why. Finally prints two tables:

* what this run **created** against what it **found** already there, per
  model label, which is how a second run proves it made nothing new;
* the **sign-in table**: every roster account with its role and centre, in
  role order, and the one line about the password — the *name* of the
  environment variable, never its value.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from ..context import Context
from ..roster import sorted_for_sign_in

PASSWORD_LINE = "Password: the value of DEMO_USER_PASSWORD (printed nowhere)."  # noqa: S105


def run(ctx: Context) -> None:
    _clear_cache(ctx)
    _abandon_queued_mail(ctx)
    for line in summary_lines(ctx):
        ctx.out(line)


def _clear_cache(ctx: Context) -> None:
    """``cache.clear()``, unless it would also flush the Celery queue.

    On Redis the Django cache's ``clear()`` is ``FLUSHDB`` on the cache's
    database. ``base.py`` defaults ``CELERY_BROKER_URL`` to ``CACHE_URL``, so
    a host that set only the one has its queued tasks — the outbox sends this
    very run raised, anything else in flight — in the same database, and the
    clear would drop them on the floor. Staging keeps them apart (``/0`` and
    ``/1``), so there the clear runs; a host that shares them gets the
    warning instead and a cache that expires on its own.
    """
    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    cache_url = getattr(settings, "CACHE_URL", "") or ""
    if broker and cache_url and broker == cache_url:
        ctx.out(
            "warning: cache NOT cleared — CELERY_BROKER_URL is the same Redis database as "
            "CACHE_URL, and clearing it would empty the task queue. Set them to different "
            "databases, or wait for the cached dashboards to expire."
        )
        return
    cache.clear()
    ctx.out("cache cleared")


def _abandon_queued_mail(ctx: Context) -> None:
    """Take this run's mail out of the outbox before a worker can send it.

    The gate in the command checks the *command's* ``EMAIL_BACKEND``; the
    worker and the beat sweep (``notifications.tasks``) read their own, later,
    and will attempt every row that is still ``PENDING`` or ``FAILED``. The
    rows are kept — they are the evidence a notifications screen shows — but
    moved to ``ABANDONED``, the one status the sweep never picks up again,
    with the reason in ``last_error`` where the outbox already keeps such
    notes. Only rows created since ``ctx.now`` (the run's start) are touched,
    so mail somebody else queued before the run is left for the sweep; a
    second run finds nothing left to abandon.
    """
    from apps.notifications.models import EmailMessage, EmailStatus

    abandoned = EmailMessage.objects.filter(
        status__in=(EmailStatus.PENDING, EmailStatus.FAILED), created_at__gte=ctx.now
    ).update(status=EmailStatus.ABANDONED, last_error=ctx.note("not delivered: showcase run"))
    ctx.out(f"queued mail abandoned: {abandoned}")


def summary_lines(ctx: Context) -> list[str]:
    """Both tables, as lines, so the command can print them on any success."""
    lines: list[str] = ["", "Rows by model (this run)"]
    labels = sorted(set(ctx.counts) | set(ctx.found))
    if not labels:
        lines.append("  (nothing counted — no stage that creates rows ran)")
    else:
        lines.append(f"  {'model':<24} {'created':>8} {'found':>8}")
        for label in labels:
            lines.append(f"  {label:<24} {ctx.counts[label]:>8} {ctx.found[label]:>8}")
        lines.append(f"  {'total':<24} {sum(ctx.counts.values()):>8} {sum(ctx.found.values()):>8}")

    lines += ["", "Sign in as"]
    lines.append(f"  {'role':<12} {'centre':<8} email")
    for person in sorted_for_sign_in(ctx.roster):
        lines.append(f"  {person.role:<12} {person.branch_code or '—':<8} {person.email}")
    lines += ["", PASSWORD_LINE]
    return lines
