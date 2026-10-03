"""Layer the showcase data set onto the current database (local/staging only).

    manage.py seed_showcase                # every stage, in order
    manage.py seed_showcase --list         # the stages and what they cover
    manage.py seed_showcase --only fees    # one stage, on a database that ran the rest
    manage.py seed_showcase --from work    # that stage and everything after it
    manage.py seed_showcase --dry-run      # say what would run, touch nothing

What a showcase is, and the four properties this command keeps — additive,
idempotent, gated, no password on disk — are the docstring of
:mod:`apps.common.showcase`. This module is the runner: the same production
gate and password handling as ``seed_demo_data``, stage selection, one
transaction per stage, timing, and the summary at the end.

One transaction per stage rather than one around the run
--------------------------------------------------------
A full run touches thirty-odd models over a couple of minutes. Wrapping all of
it in one transaction would mean a refusal in stage eight throws away stages
one to seven, and the next attempt starts from nothing. With a transaction per
stage the completed stages stay, and because every stage is idempotent the
re-run walks through them reporting "found" until it reaches the one that
failed. ``--from`` exists so it need not even walk.
"""

from __future__ import annotations

import os
import time

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.common.showcase.context import Context, hydrate
from apps.common.showcase.stages import STAGE_KEYS, STAGES, s10_finish

#: Django's own backends that deliver nowhere: to stdout, to memory, to /dev/null
#: and to a directory. Anything else — SMTP, a provider's, a custom one — is
#: assumed to deliver until ``--allow-real-mail`` says otherwise.
NON_DELIVERING_BACKENDS = frozenset(
    f"django.core.mail.backends.{name}.EmailBackend"
    for name in ("console", "locmem", "dummy", "filebased")
)


class Command(BaseCommand):
    help = (
        "Layer a coherent, live-dated showcase data set on top of the current "
        "database (local/staging only). Additive and idempotent."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--only",
            metavar="KEYS",
            help=(
                "Comma-separated stage keys to run, in canonical order, e.g. "
                "'organisation,people'. The finish stage always runs last."
            ),
        )
        parser.add_argument(
            "--from",
            dest="from_stage",
            metavar="KEY",
            help="Run from this stage to the end.",
        )
        parser.add_argument(
            "--list", action="store_true", help="Print the stages in order and exit."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which stages would run and exit without touching the database.",
        )
        parser.add_argument(
            "--allow-real-mail",
            action="store_true",
            help=(
                "Run even though EMAIL_BACKEND is not one of Django's non-delivering "
                "backends. The showcase fans notifications out to every active account, "
                "imported real addresses included."
            ),
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options) -> None:
        # The gate comes before everything, including --list: a production
        # environment should refuse to so much as describe this command.
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Showcase seeding is disabled in the "
                f"{getattr(settings, 'ENVIRONMENT', 'unknown')} environment. "
                "This command must never run against production data."
            )

        # The second gate is about mail. Publishing an 'everyone' announcement,
        # grading, recording a result, a risk change — each queues an email to
        # every account it concerns, and on a database holding imported real
        # addresses that is real people receiving "[showcase]" mail. An
        # allow-list, not a block-list: only the backends *known* to deliver
        # nowhere pass, so an SMTP backend, a provider's (anymail, SES) and any
        # backend this code has never heard of are all refused alike, unless
        # told in so many words.
        backend = settings.EMAIL_BACKEND
        if backend not in NON_DELIVERING_BACKENDS and not options["allow_real_mail"]:
            raise CommandError(
                f"EMAIL_BACKEND is {backend}, which may deliver mail: the showcase fans "
                "notifications out to every active account, including imported real "
                "addresses. Set EMAIL_BACKEND to the console backend (or another of "
                f"{', '.join(sorted(NON_DELIVERING_BACKENDS))}), or pass --allow-real-mail "
                "if that is really intended."
            )

        if options["list"]:
            self._print_stages()
            return

        selected = self._select(options["only"], options["from_stage"])

        if options["dry_run"]:
            self.stdout.write("Dry run — nothing will be written. Would run:")
            self._print_stages(selected)
            return

        password = self._password()

        ctx = Context(password=password, out=lambda text: self.stdout.write(f"  {text}"))
        hydrate(ctx)

        total = len(STAGES)
        for index, (key, run) in enumerate(STAGES, start=1):
            if key not in selected:
                continue
            self.stdout.write(f"stage {index}/{total} {key} …")
            started = time.perf_counter()
            # A fresh generator per stage, so a stage draws the same sequence
            # under --only as in a full run — see RUN_SEED in the context.
            ctx.rng = ctx.rng_for(key)
            # One transaction per stage — see the module docstring.
            with transaction.atomic():
                run(ctx)
            elapsed = time.perf_counter() - started
            self.stdout.write(self.style.SUCCESS(f"stage {index}/{total} {key} … {elapsed:.1f}s"))

        # The finish stage clears the cache and prints the tables. When the
        # selection left it out, the tables are still the answer to "what
        # happened", so they are printed regardless — but the cache is cleared
        # only when the stage ran, since that is a write of sorts.
        if "finish" not in selected:
            for line in s10_finish.summary_lines(ctx):
                self.stdout.write(line)

        self.stdout.write(self.style.SUCCESS("Showcase data ready."))

    # ------------------------------------------------------------------

    def _password(self) -> str:
        """The shared password, from the environment and nowhere else.

        Identical to ``seed_demo_data``: absent means refuse rather than
        default, and a password the policy would reject on the sign-in form is
        rejected here too, so the accounts can actually sign in.
        """
        password = os.environ.get("DEMO_USER_PASSWORD", "")
        if not password:
            raise CommandError(
                "DEMO_USER_PASSWORD is not set. Supply it through the environment "
                "or the staging secret manager; it is intentionally not defaulted "
                "and must not be committed."
            )
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                "DEMO_USER_PASSWORD does not meet the password policy: " + "; ".join(exc.messages)
            ) from exc
        return password

    @staticmethod
    def _select(only: str | None, from_stage: str | None) -> list[str]:
        """Which stage keys run, always in canonical order.

        ``--only`` and ``--from`` are alternatives; both is ambiguous and is
        refused rather than guessed at. The finish stage is implied by
        ``--only``: it writes nothing, and a run without its summary is a run
        that reports nothing.
        """
        if only and from_stage:
            raise CommandError("Use --only or --from, not both.")

        valid = ", ".join(STAGE_KEYS)
        if only:
            wanted = [key.strip() for key in only.split(",") if key.strip()]
            unknown = sorted(set(wanted) - set(STAGE_KEYS))
            if unknown:
                raise CommandError(f"Unknown stage(s) {', '.join(unknown)}. Valid keys: {valid}.")
            return [key for key in STAGE_KEYS if key in wanted or key == "finish"]

        if from_stage:
            if from_stage not in STAGE_KEYS:
                raise CommandError(f"Unknown stage '{from_stage}'. Valid keys: {valid}.")
            return STAGE_KEYS[STAGE_KEYS.index(from_stage) :]

        return list(STAGE_KEYS)

    def _print_stages(self, selected: list[str] | None = None) -> None:
        total = len(STAGES)
        for index, (key, run) in enumerate(STAGES, start=1):
            if selected is not None and key not in selected:
                continue
            # The first line of each stage module's docstring is its one-line
            # description; the rest is the contract for whoever implements it.
            doc = (run.__module__ and __import__(run.__module__, fromlist=["run"]).__doc__) or ""
            headline = doc.strip().splitlines()[0] if doc.strip() else ""
            self.stdout.write(f"  {index:>2}/{total}  {key:<14} {headline}")
