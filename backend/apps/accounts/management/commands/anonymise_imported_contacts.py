"""Make imported contact details undeliverable, before mail is switched on.

    python manage.py anonymise_imported_contacts --dry-run
    python manage.py anonymise_imported_contacts [--keep grras.com --keep other.org]

Why this exists
---------------
The SITP workbooks (``import_sitp_workbooks``) brought real students' Gmail
addresses and real phone numbers into a database that is otherwise a
demonstration. As long as the mail backend delivers nowhere that is harmless.
The moment SMTP credentials arrive so that password reset and email
verification can work for real, every announcement, grade notification and
fee reminder the showcase fans out would reach those people. This command is
the step that must happen *first*.

What it does
------------
For every account whose address is neither on a reserved domain (``.invalid``,
``.test``, ``.example``, ``.localhost`` — the same four
``scripts/verify_demo.sh`` accepts) nor on a ``--keep`` domain (default
``grras.com``, the showcase roster's own domain, whose accounts people sign in
as):

* **Email** becomes ``rtu-<roll number>@sitp.grras.invalid`` — the form the
  import itself gives a student the sheet had no address for, so an
  anonymised student is indistinguishable from one who never had one. The
  roll number is lower-cased and any character an address cannot carry is
  turned into ``-``. With no roll number: ``student-<student id>@…``; with no
  student profile at all (a staff account): ``user-<pk>@…``. The two fallbacks
  carry a different prefix from ``rtu-`` so they can never collide with a real
  roll number. Two students can share a roll number across workbooks, and
  ``email`` is unique (case-insensitively, ``user_email_ci_unique``): the
  second gets ``-2``, the third ``-3``. The report says how many needed one.
* **Phone** — the account's, and the student profile's guardian and emergency
  contact numbers — becomes ``+000000000000``. That satisfies ``PHONE_RE``
  (an optional ``+``, then 8-15 digits) so the record still validates when
  somebody edits it, and cannot be dialled: E.164 country codes never begin
  with ``0``, so no carrier can route it. A number in some real range, or one
  invented to look like an Indian mobile, might belong to somebody; this one
  cannot. Blank stays blank.
* **WhatsApp opt-in** is cleared and **email verification** is reset on the
  accounts changed. Consent was given for a number and an address that no
  longer exist; it does not transfer to a placeholder.
* **Anything already queued** to a real address is withdrawn: outbox emails
  still ``pending``/``failed`` are abandoned and their address replaced, and
  queued/failed WhatsApp-or-email deliveries to a rewritten account are
  cancelled. Otherwise the first sweep after SMTP is switched on would send
  yesterday's backlog to the very people this is protecting.

What it deliberately does not do
--------------------------------
It **does not remember the old values**. Not in a note, an audit context, a
report or a mapping file — that is the point of running it. The one audit
record carries counts only. Reversal is by restoring the database backup taken
before the run; there is no other way back, so take one.

It also leaves alone what it cannot rewrite or what cannot be delivered: the
append-only audit log (whose ``actor_label`` holds addresses), and outbox rows
already ``sent``. The report counts the latter so the remainder is visible.

Safety
------
* Gated on ``settings.ALLOW_DEMO_SEED`` like every seeder, so it cannot run
  against production data.
* One transaction: a failure part-way leaves nothing changed.
* Idempotent: a rewritten account is on a reserved domain, so a second run
  finds nothing, changes nothing and writes no audit record.
* ``--dry-run`` computes the whole plan and writes nothing.
* Never prints a real address in full. Output is counts plus, at most, a
  masked sample (``s***@g***.com``).
* Every non-reserved, non-kept account is in scope, staff included: a person
  signing in with a real address will be locked out of that address. The report
  gives the count by role so that is not a surprise.
"""

from __future__ import annotations

import re
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.validators import PHONE_RE

#: Kept in step with ``import_sitp_workbooks.PLACEHOLDER_DOMAIN``; the tests
#: assert they are equal rather than importing across apps for one string.
PLACEHOLDER_DOMAIN = "sitp.grras.invalid"

#: The four suffixes ``scripts/verify_demo.sh`` treats as "cannot receive mail".
RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost")

#: The showcase roster's own domain.
DEFAULT_KEEP = ("grras.com",)

#: Not diallable: E.164 country codes never start with 0. Passes ``PHONE_RE``.
UNDIALLABLE_PHONE = "+000000000000"

_UNSAFE_LOCAL_PART = re.compile(r"[^a-z0-9._-]+")

SAMPLE_SIZE = 5


def is_kept_or_reserved_q(keep: list[str]) -> Q:
    """The accounts this command must leave alone, as a query."""
    q = Q()
    for suffix in RESERVED_SUFFIXES:
        q |= Q(email__iendswith=suffix)
    for domain in keep:
        q |= Q(email__iendswith="@" + domain)
    return q


def mask(address: str) -> str:
    """``sam.student@gmail.com`` -> ``s***@g***.com``: enough to recognise a
    kind of address by, not enough to recover one."""
    local, _, domain = address.partition("@")
    host, _, tld = domain.rpartition(".")
    return f"{local[:1]}***@{host[:1]}***.{tld}" if host else f"{local[:1]}***@***"


def _clean_local_part(value: str) -> str:
    return _UNSAFE_LOCAL_PART.sub("-", value.strip().lower()).strip("-")


class Command(BaseCommand):
    help = (
        "Rewrite imported real email addresses and phone numbers to unroutable "
        "placeholders, so that a delivering mail backend can be switched on. "
        "Irreversible except by restoring a backup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            action="append",
            default=None,
            metavar="DOMAIN",
            help=(
                "A domain whose accounts are left alone. Repeat for several. "
                f"Default: {', '.join(DEFAULT_KEEP)}. Reserved domains are always kept."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change, and change nothing.",
        )

    def handle(self, *args, **options):
        # The gate comes first, before anything is read.
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Anonymising imported contacts is disabled in the "
                f"{getattr(settings, 'ENVIRONMENT', 'unknown')} environment. "
                "This command must never run against production data."
            )

        keep = [
            d.strip().lower().lstrip("@")
            for d in (options["keep"] if options["keep"] is not None else DEFAULT_KEEP)
            if d.strip().lstrip("@")
        ]
        dry_run = options["dry_run"]

        with transaction.atomic():
            summary = self._run(keep=keep, dry_run=dry_run)
            if dry_run:
                # Nothing was written, but roll back anyway: a dry run must be
                # incapable of writing, not merely careful not to.
                transaction.set_rollback(True)

        self._report(summary, keep=keep, dry_run=dry_run)

    # ------------------------------------------------------------------

    def _run(self, *, keep: list[str], dry_run: bool) -> dict:
        users = list(
            User.objects.exclude(is_kept_or_reserved_q(keep))
            .select_related("student_profile")
            .order_by("created_at", "pk")
        )
        summary: dict = {
            "accounts": len(users),
            "by_role": Counter(u.role for u in users),
            "suffixed": 0,
            "phones": 0,
            "profile_phones": 0,
            "opt_ins_cleared": 0,
            "outbox_withdrawn": 0,
            "deliveries_cancelled": 0,
            "sample": [],
        }
        if not users:
            summary["history_left"] = self._history_left(keep)
            return summary

        # Every candidate address is on the placeholder domain, so that is the
        # only place a collision can be. Lower-cased: the constraint is on
        # ``lower(email)``.
        taken = {
            e.lower()
            for e in User.objects.filter(email__iendswith="@" + PLACEHOLDER_DOMAIN).values_list(
                "email", flat=True
            )
        }

        now = timezone.now()
        profiles = []
        for user in users:
            profile = getattr(user, "student_profile", None)
            original = user.email
            base = self._base(user, profile)
            candidate, n = f"{base}@{PLACEHOLDER_DOMAIN}", 1
            while candidate in taken:
                n += 1
                candidate = f"{base}-{n}@{PLACEHOLDER_DOMAIN}"
            if n > 1:
                summary["suffixed"] += 1
            taken.add(candidate)

            if len(summary["sample"]) < SAMPLE_SIZE:
                summary["sample"].append(f"{mask(original)} -> {candidate}")

            user.email = candidate
            user.is_email_verified = False
            user.email_verified_at = None
            if user.phone:
                user.phone = UNDIALLABLE_PHONE
                summary["phones"] += 1
            if user.whatsapp_opt_in:
                user.whatsapp_opt_in = False
                summary["opt_ins_cleared"] += 1
            user.updated_at = now

            if profile is not None:
                changed = False
                for field in ("guardian_phone", "emergency_contact_phone"):
                    if getattr(profile, field):
                        setattr(profile, field, UNDIALLABLE_PHONE)
                        summary["profile_phones"] += 1
                        changed = True
                if changed:
                    profile.updated_at = now
                    profiles.append(profile)

        assert PHONE_RE.match(UNDIALLABLE_PHONE)

        if dry_run:
            # Counted as the run would leave it: the rows a real run withdraws
            # are not history, so counting them here would report a number the
            # real run never produces.
            summary["history_left"] = self._history_left(keep, sent_only=True)
            return summary

        User.objects.bulk_update(
            users,
            [
                "email",
                "phone",
                "whatsapp_opt_in",
                "is_email_verified",
                "email_verified_at",
                "updated_at",
            ],
            batch_size=200,
        )
        if profiles:
            from apps.students.models import StudentProfile

            StudentProfile.objects.bulk_update(
                profiles,
                ["guardian_phone", "emergency_contact_phone", "updated_at"],
                batch_size=200,
            )

        summary["outbox_withdrawn"], summary["deliveries_cancelled"] = self._withdraw_queued(
            [u.pk for u in users], keep
        )
        summary["history_left"] = self._history_left(keep)

        # One record for the operation, counts only. Written inline, in the
        # transaction: the record and the change commit together or not at all.
        # No action is named for a bulk anonymisation; USER_UPDATED is the
        # closest (USER_EMAIL_CHANGED would omit the phone numbers, and
        # BULK_IMPORT_* describes rows arriving, not leaving).
        record(
            action=AuditAction.USER_UPDATED,
            actor=None,
            actor_label="system:anonymise_imported_contacts",
            resource_type="user",
            durable=False,
            context={
                "operation": "anonymise_imported_contacts",
                "kept_domains": keep,
                "accounts": summary["accounts"],
                "address_suffixed": summary["suffixed"],
                "phones_replaced": summary["phones"] + summary["profile_phones"],
                "whatsapp_opt_ins_cleared": summary["opt_ins_cleared"],
                "outbox_withdrawn": summary["outbox_withdrawn"],
                "deliveries_cancelled": summary["deliveries_cancelled"],
            },
        )
        return summary

    @staticmethod
    def _base(user: User, profile) -> str:
        """The local part for this account.

        A roll number first, so an anonymised student reads exactly like one
        the sheet had no address for. The two fallbacks carry a different
        prefix so neither can collide with a real roll number.
        """
        if profile is not None:
            roll = _clean_local_part(profile.roll_number)
            if roll:
                return f"rtu-{roll}"
            student_id = _clean_local_part(profile.student_id)
            if student_id:
                return f"student-{student_id}"
        return f"user-{user.pk.hex}"

    @staticmethod
    def _withdraw_queued(user_ids: list, keep: list[str]) -> tuple[int, int]:
        from apps.communication.models import Delivery, DeliveryState
        from apps.notifications.models import EmailMessage, EmailStatus

        # Outbox rows are matched by their own address, not by a user link: a
        # verification email has no notification behind it, so the same
        # predicate is rebuilt here over the outbox's own column name.
        real = Q()
        for suffix in RESERVED_SUFFIXES:
            real |= Q(to_email__iendswith=suffix)
        for domain in keep:
            real |= Q(to_email__iendswith="@" + domain)
        outbox = EmailMessage.objects.filter(
            status__in=[EmailStatus.PENDING, EmailStatus.FAILED]
        ).exclude(real)
        withdrawn = outbox.update(
            status=EmailStatus.ABANDONED,
            to_email=f"withdrawn@{PLACEHOLDER_DOMAIN}",
            last_error="Withdrawn: the recipient's address was anonymised.",
            updated_at=timezone.now(),
        )
        cancelled = Delivery.objects.filter(
            recipient_id__in=user_ids,
            state__in=[DeliveryState.QUEUED, DeliveryState.PROCESSING, DeliveryState.FAILED],
        ).update(
            state=DeliveryState.CANCELLED,
            address="",
            error="Withdrawn: the recipient's contact details were anonymised.",
            next_attempt_at=None,
            updated_at=timezone.now(),
        )
        return withdrawn, cancelled

    @staticmethod
    def _history_left(keep: list[str], *, sent_only: bool = False) -> int:
        """Outbox rows still addressed to a real domain: history, not deliverable.

        After a real run only sent rows remain, because the pending and failed
        ones were withdrawn. ``sent_only`` makes a dry run report that same
        number instead of counting rows it is about to withdraw.
        """
        from apps.notifications.models import EmailMessage, EmailStatus

        real = Q()
        for suffix in RESERVED_SUFFIXES:
            real |= Q(to_email__iendswith=suffix)
        for domain in keep:
            real |= Q(to_email__iendswith="@" + domain)
        rows = EmailMessage.objects.exclude(real)
        if sent_only:
            rows = rows.exclude(status__in=[EmailStatus.PENDING, EmailStatus.FAILED])
        return rows.count()

    def _report(self, s: dict, *, keep: list[str], dry_run: bool) -> None:
        w = self.stdout.write
        verb = "would be" if dry_run else "were"
        if dry_run:
            w("DRY RUN: nothing has been changed.")
        w(f"Kept domains: {', '.join(keep) or '(none)'} plus {', '.join(RESERVED_SUFFIXES)}")
        if not s["accounts"]:
            w("Nothing to do: every account is on a reserved or kept domain.")
        else:
            w(f"Accounts whose email {verb} rewritten: {s['accounts']}")
            w("  by role: " + ", ".join(f"{r}={n}" for r, n in sorted(s["by_role"].items())))
            w(f"  needing a suffix to stay unique: {s['suffixed']}")
            w(
                f"Phone numbers {verb} replaced: {s['phones']} on accounts, "
                f"{s['profile_phones']} on profiles"
            )
            w(f"WhatsApp opt-ins {verb} cleared: {s['opt_ins_cleared']}")
            if not dry_run:
                w(f"Queued emails withdrawn: {s['outbox_withdrawn']}")
                w(f"Queued deliveries cancelled: {s['deliveries_cancelled']}")
            for line in s["sample"]:
                w(f"  e.g. {line}")
        w(
            f"Left as history (not deliverable): {s['history_left']} outbox rows already "
            "addressed to a real domain; the audit log is append-only."
        )
        if s["accounts"] and not dry_run:
            w("Irreversible except by restoring the database backup taken before this run.")
