"""Stage 10 — tidy up and say what happened.

Creates nothing. Clears the Django cache — dashboards, the warnings strip,
the fees overview, resolved policies, published forms and templates and the
roles matrix are all cached, and a reviewer opening the app a minute after
seeding would otherwise see the empty database the cache remembers — then
prints two tables:

* what this run **created** against what it **found** already there, per
  model label, which is how a second run proves it made nothing new;
* the **sign-in table**: every roster account with its role and centre, in
  role order, and the one line about the password — the *name* of the
  environment variable, never its value.
"""

from __future__ import annotations

from django.core.cache import cache

from ..context import Context
from ..roster import sorted_for_sign_in

PASSWORD_LINE = "Password: the value of DEMO_USER_PASSWORD (printed nowhere)."  # noqa: S105


def run(ctx: Context) -> None:
    cache.clear()
    ctx.out("cache cleared")
    for line in summary_lines(ctx):
        ctx.out(line)


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
