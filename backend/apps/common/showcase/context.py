"""What every showcase stage receives, and how it finds what earlier stages made.

A stage is a plain function ``run(ctx)``. It gets one :class:`Context`: the
clock, the shared password, a seeded generator, the progress writer, and a set
of *actor slots* — the superadmin, the branches, one admin/manager/counsellor
per centre, the trainers and students per centre, the courses, the batches —
that earlier stages fill and later stages read. A stage never looks another
stage's rows up by guessing; it reads the slot.

Because the command can start at any stage (``--only fees``), the slots are
also filled from the database before anything runs: :func:`hydrate` walks the
roster and loads whichever people, centres, courses and batches already exist.
A stage that created a row on a previous run finds it in the same slot it
would have put it in.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

from django.utils import timezone

from .roster import MAIN, Person, build_roster

T = TypeVar("T")

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from apps.accounts.models import User
    from apps.authorization.models import Role
    from apps.batches.models import Batch
    from apps.courses.models import Course
    from apps.enrollments.models import Enrollment
    from apps.organisation.models import Branch
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile
    from apps.work.models import ActivityType

#: Every free-text field a stage writes carries this, so a stage can find its
#: own rows on a re-run (``notes__startswith=MARKER``) and a person reading
#: the database can tell a showcase row from a real one at a glance.
MARKER = "[showcase]"

#: Seeds ``Context.rng`` — **once per stage**, not once per run. The roster has
#: its own seed (``roster.ROSTER_SEED``); this one drives everything a stage
#: draws at run time — which students are absent, which payment is late. The
#: command reseeds the generator with ``f"{RUN_SEED}:{stage key}"`` before
#: each stage (:meth:`Context.rng_for`), so a stage draws the same sequence
#: whether it runs after nine others or alone under ``--only``; a shared
#: generator would make ``--only fees`` pick different students than the full
#: run did, miss every natural-key lookup, and create the rows a second time.
RUN_SEED = 20260901

#: What the SITP workbook import writes at the start of every batch
#: description (``apps.reporting.management.commands.import_sitp_workbooks``).
#: It is how :func:`hydrate` tells an imported batch from a showcase one
#: without a roster of imported people.
IMPORTED_PREFIX = "Imported from "


def batch_key(name: str) -> str:
    """The key ``Context.batches`` is filed under: the batch's name, normalised.

    A batch's ``code`` is allocated from a sequence and differs between
    databases; its name is chosen by the stage that creates it and is the same
    everywhere, which is what makes it a key a re-run can find.
    """
    return " ".join(name.lower().split())


@dataclass
class Context:
    """Everything a stage needs. Slots are filled by stages and by :func:`hydrate`."""

    #: The shared sign-in password from ``DEMO_USER_PASSWORD``. Never written
    #: anywhere: passed to the account services and forgotten.
    password: str = field(repr=False)
    #: Where progress lines go — the command's stdout. Stages never print.
    out: Callable[[str], None]

    #: The local date and an aware local datetime (``settings.TIME_ZONE``,
    #: Asia/Kolkata), taken once at the start so a run that crosses midnight
    #: still describes one day.
    today: date = field(default_factory=timezone.localdate)
    now: datetime = field(default_factory=timezone.localtime)
    #: Seeded, so the same "random" choices on every run.
    rng: random.Random = field(
        default_factory=lambda: random.Random(RUN_SEED)  # noqa: S311 — determinism
    )
    #: Model label → rows created this run. ``found`` is the other side: rows a
    #: stage looked for and did not need to create. The finish stage prints
    #: both, which is how a second run proves it made nothing new.
    counts: Counter = field(default_factory=Counter)
    found: Counter = field(default_factory=Counter)
    #: The deterministic roster (:func:`apps.common.showcase.roster.build_roster`).
    roster: list[Person] = field(default_factory=build_roster)

    # --- Actor slots -----------------------------------------------------
    #: The boss: ``owner@grras.com``. The actor for anything institution-wide.
    superadmin: User | None = None
    #: Every roster user that exists, keyed by the email's local part
    #: (``"admin.pune"``), for the stages that need a specific person.
    users: dict[str, User] = field(default_factory=dict)
    #: Keyed by branch code: MAIN, PUNE, UDR.
    branches: dict[str, Branch] = field(default_factory=dict)
    #: One per branch code: the first admin/manager/counsellor the roster lists
    #: for that centre. Bounded actors for branch-scoped writes.
    admins: dict[str, User] = field(default_factory=dict)
    managers: dict[str, User] = field(default_factory=dict)
    counsellors: dict[str, User] = field(default_factory=dict)
    #: Keyed by branch code, in roster order; the headline trainer/student is
    #: first in MAIN's list.
    trainers: dict[str, list[TrainerProfile]] = field(default_factory=dict)
    students: dict[str, list[StudentProfile]] = field(default_factory=dict)
    #: Keyed by course slug.
    courses: dict[str, Course] = field(default_factory=dict)
    #: Keyed by :func:`batch_key` of the batch's name — every batch on the
    #: database. The two views below are the ones stages usually want.
    batches: dict[str, Batch] = field(default_factory=dict)
    #: The batches a showcase stage created: their ``description`` starts with
    #: :data:`MARKER`. Stage 4 must write ``description=ctx.note(...)`` on
    #: every batch it creates for this to hold.
    showcase_batches: dict[str, Batch] = field(default_factory=dict)
    #: The batches the SITP workbook import created (``description`` starts
    #: with :data:`IMPORTED_PREFIX`). Their students are not on the roster;
    #: reach them through :meth:`live_enrolments`.
    imported_batches: dict[str, Batch] = field(default_factory=dict)
    #: Keyed by slug — the eighteen catalog types plus any a stage adds.
    activity_types: dict[str, ActivityType] = field(default_factory=dict)
    #: Custom :class:`~apps.authorization.models.Role` rows by slug, so a
    #: later stage (a role-audience announcement) need not guess stage 2's.
    roles: dict[str, Role] = field(default_factory=dict)
    #: The roster by email, so a profile or user can be traced back to the
    #: facts the roster states about that person (``flags``).
    people: dict[str, Person] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.people = {person.email: person for person in self.roster}

    # --- Bookkeeping -----------------------------------------------------

    def created(self, label: str, n: int = 1) -> None:
        """Count a row this run created. ``label`` is a model label, e.g. ``"branch"``."""
        self.counts[label] += n

    def found_existing(self, label: str, n: int = 1) -> None:
        """Count a row this run looked for and found already there."""
        self.found[label] += n

    def note(self, text: str) -> str:
        """``text`` with the showcase marker in front — for every note, reason,
        description and comment a stage writes."""
        return f"{MARKER} {text}"

    def tag(self, key: str, text: str = "") -> str:
        """A marker that also names the row: ``[showcase][fee/GRS-E-00012/2] …``.

        For rows with no natural key of their own — a payment, a delivery, an
        activity history entry — the note is the key. A stage writes
        ``note=ctx.tag(f"fee/{enrolment.code}/{n}")`` and finds the row again
        with ``note__startswith=ctx.tag(...)``. Keep ``key`` short: the
        field it lands in may be a bounded ``CharField``.
        """
        prefix = f"{MARKER}[{key}]"
        return f"{prefix} {text}" if text else prefix

    def ensure(self, label: str, what: str, existing: T | None, create: Callable[[], T]) -> T:
        """Found-or-created in one place: the pattern every stage repeats.

        ``existing`` is the natural-key lookup's result (``None`` when absent);
        ``create`` is the service call. Counts and logs whichever happened and
        returns the row either way.
        """
        if existing is not None:
            self.found_existing(label)
            self.out(f"{what}: found")
            return existing
        row = create()
        self.created(label)
        self.out(f"{what}: created")
        return row

    def rng_for(self, stage_key: str) -> random.Random:
        """The generator for one stage; the command installs it as ``rng``."""
        return random.Random(f"{RUN_SEED}:{stage_key}")  # noqa: S311 — determinism

    def ensure_password(self, user: User) -> None:
        """Make a *found* account sign in with the current password.

        A found account keeps whatever hash it had, so after the host's
        ``DEMO_USER_PASSWORD`` is rotated the sign-in table would lie about
        every account a previous run created. Checked, not blindly reset:
        ``check_password`` is a hash comparison and writes nothing.
        """
        if not user.check_password(self.password):
            user.set_password(self.password)
            user.save(update_fields=["password"])
            self.out(f"password reset for {user.email}")

    # --- Dates -----------------------------------------------------------

    def days_ago(self, n: int) -> date:
        return self.today - timedelta(days=n)

    def weeks_ago(self, n: int) -> date:
        return self.today - timedelta(weeks=n)

    def days_ahead(self, n: int) -> date:
        return self.today + timedelta(days=n)

    def at(self, day: date, hour: int, minute: int = 0) -> datetime:
        """An aware datetime on ``day`` at local wall-clock time."""
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    # --- Actors ----------------------------------------------------------

    def actor_for(self, branch_code: str) -> User:
        """The admin for a centre, or the superadmin when the centre has none.

        An admin sees every centre but *belongs* to one, so records created
        by ``actor_for("PUNE")`` land in Pune without every call naming the
        branch. UDR has no staff, so its few records are the superadmin's.
        """
        actor = self.admins.get(branch_code) or self.superadmin
        if actor is None:
            raise RuntimeError("No superadmin yet: run the organisation stage first.")
        return actor

    def branch(self, code: str) -> Branch:
        try:
            return self.branches[code]
        except KeyError:
            raise RuntimeError(
                f"Branch {code} is not loaded: run the organisation stage first."
            ) from None

    # --- People, by the facts the roster states about them -------------------

    def person_for(self, user: User) -> Person | None:
        """The roster entry behind a user, or ``None`` for an account the
        roster does not know (a demo, SITP or hand-made one)."""
        return self.people.get(user.email)

    def _flag(self, user: User, name: str) -> Any:
        person = self.person_for(user)
        return person.flags.get(name) if person is not None else None

    def enrollable_students(self, branch_code: str) -> list[StudentProfile]:
        """The centre's showcase students a batch may enrol.

        Leaves out the one the roster says never enrolled and any whose user
        is inactive — ``enrol_student`` refuses an inactive user, so a stage
        that enrols "everyone" would stop on the first one. The inactive
        student is deactivated at the *end* of stage 4, after enrolment, so
        that in a full run they are enrolled first and then leave.
        """
        return [
            profile
            for profile in self.students.get(branch_code, [])
            if profile.user.is_active and not self._flag(profile.user, "never_enrolled")
        ]

    def assignable_trainers(self, branch_code: str) -> list[TrainerProfile]:
        """The centre's trainers a batch may be given: active user, accepting.

        ``Batch.clean`` refuses an inactive trainer and the wizard hides one
        who is not accepting assignments, so those two stay out of the pool
        here and appear only where a stage wants exactly that state.
        """
        return [
            profile
            for profile in self.trainers.get(branch_code, [])
            if profile.user.is_active
            and getattr(profile, "is_accepting_assignments", True)
            and not self._flag(profile.user, "inactive")
        ]

    def live_enrolments(self, batch: Batch) -> QuerySet[Enrollment]:
        """A batch's live enrolments with their students loaded — the way to
        reach the imported SITP students, who are on no roster."""
        from apps.enrollments.models import LIVE_STATUSES, Enrollment

        return (
            Enrollment.objects.filter(batch=batch, status__in=LIVE_STATUSES)
            .select_related("student__user", "batch")
            .order_by("pk")
        )

    # --- Making rows look historical ---------------------------------------

    @staticmethod
    def backdate(instance: Any, **fields: Any) -> None:
        """Overwrite timestamps a service stamped with *now*.

        ``created_at``/``updated_at`` are ``auto_now``-style and several
        services stamp ``submitted_at``, ``enrolled_at``, ``issued_at`` and
        the like with the moment of the call, so a row created today looks
        like it happened today whatever date it describes. Charts read those
        timestamps, and a showcase whose every enrolment started this morning
        has no trend to draw.

        This is the **only** sanctioned way to make a row look historical: a
        queryset ``update()`` writes exactly the named columns, runs no
        ``save()`` hooks and no ``auto_now``, and fires no signal. Call it
        *after* the service that created the row — never in place of the
        service, and never for a field the service accepts as a parameter
        (``paid_on``, ``session_date``, ``completed_at``…): pass those in.

        Call it after the **last** service call on the row: a later
        ``save()`` re-stamps every ``auto_now`` field (``recorded_at`` on an
        assessment result, ``updated_at`` everywhere), undoing the backdate.
        """
        type(instance).objects.filter(pk=instance.pk).update(**fields)
        instance.refresh_from_db(fields=list(fields))


def hydrate(ctx: Context) -> None:
    """Fill the actor slots from whatever the database already holds.

    Runs before any stage, so ``--only fees`` on a database that ran the
    earlier stages last week sees the same context it would have seen in one
    continuous run. Anything not there yet is simply left empty; a stage
    that needs it fails with a message naming the stage to run first.

    People are found by roster email — the roster is the contract — and the
    first admin/manager/counsellor the roster lists per centre becomes that
    centre's default actor. Branches, courses and activity types are loaded
    wholesale by code/slug: they are shared institution-wide and a stage may
    legitimately want the imported SITP courses that no stage created.
    Batches are loaded by :func:`batch_key`, the same key a stage files a
    new batch under.
    """
    from apps.accounts.models import User, UserRole
    from apps.authorization.models import Role
    from apps.batches.models import Batch
    from apps.courses.models import Course
    from apps.organisation.models import Branch
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile
    from apps.work.models import ActivityType

    ctx.branches = {branch.code: branch for branch in Branch.objects.all()}

    by_email = {
        user.email: user
        for user in User.objects.filter(email__in=[p.email for p in ctx.roster]).select_related(
            "branch"
        )
    }
    trainer_profiles = {
        profile.user_id: profile
        for profile in TrainerProfile.objects.filter(user__in=by_email.values()).select_related(
            "user", "branch"
        )
    }
    student_profiles = {
        profile.user_id: profile
        for profile in StudentProfile.objects.filter(user__in=by_email.values()).select_related(
            "user", "branch"
        )
    }

    for person in ctx.roster:
        user = by_email.get(person.email)
        if user is None:
            continue
        if user.role != person.role:
            # The roster is the contract. An account on this address with a
            # different role was made by somebody else, and filing it under
            # the roster's role would send every branch-scoped write astray.
            raise RuntimeError(
                f"{person.email} exists with role {user.role!r}, but the showcase "
                f"roster says {person.role!r}. Fix the account or the roster first."
            )
        ctx.users[person.local_part] = user
        code = person.branch_code or MAIN
        if person.role == UserRole.SUPERADMIN:
            ctx.superadmin = ctx.superadmin or user
        elif person.role == UserRole.ADMIN:
            ctx.admins.setdefault(code, user)
        elif person.role == UserRole.MANAGER:
            ctx.managers.setdefault(code, user)
        elif person.role == UserRole.COUNSELLOR:
            ctx.counsellors.setdefault(code, user)
        elif person.role == UserRole.TRAINER:
            profile = trainer_profiles.get(user.pk)
            if profile is not None:
                ctx.trainers.setdefault(code, []).append(profile)
        elif person.role == UserRole.STUDENT:
            profile = student_profiles.get(user.pk)
            if profile is not None:
                ctx.students.setdefault(code, []).append(profile)

    ctx.courses = {course.slug: course for course in Course.objects.all()}

    ctx.batches = {}
    for batch in Batch.objects.select_related("course", "branch", "trainer").order_by("pk"):
        key = batch_key(batch.name)
        if key in ctx.batches:
            # Two batches, one name. Neither is the wrong one, but a stage
            # that files by name would find whichever came last and act on
            # it, so say so rather than let it happen quietly. The older row
            # keeps the key.
            ctx.out(
                f"warning: batches {ctx.batches[key].code} and {batch.code} share the "
                f"name {batch.name!r}; the older keeps the key"
            )
            continue
        ctx.batches[key] = batch
    ctx.showcase_batches = {
        key: batch for key, batch in ctx.batches.items() if batch.description.startswith(MARKER)
    }
    ctx.imported_batches = {
        key: batch
        for key, batch in ctx.batches.items()
        if batch.description.startswith(IMPORTED_PREFIX)
    }

    ctx.activity_types = {kind.slug: kind for kind in ActivityType.objects.all()}
    ctx.roles = {role.slug: role for role in Role.objects.filter(is_system=False)}


__all__ = ["IMPORTED_PREFIX", "MARKER", "RUN_SEED", "Context", "batch_key", "hydrate"]
