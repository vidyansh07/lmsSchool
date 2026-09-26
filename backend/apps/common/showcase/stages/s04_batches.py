"""Stage 4 — batches, timetables, generated classes and enrolments.

Creates, through ``apps.batches.services``, ``apps.sessions.services`` and
``apps.enrollments.services``, always as the centre's admin
(``ctx.actor_for(branch_code)``), and idempotently by
:func:`~apps.common.showcase.context.batch_key` of the batch name:

* **Fifteen showcase batches** (:data:`SPECS`) via ``create_batch``, every
  one with ``description=ctx.note(...)`` — that marker is how
  :func:`~apps.common.showcase.context.hydrate` tells a showcase batch from an
  imported or hand-made one. Dated relative to ``ctx.today`` so every status
  is real on any day: MAIN has two *upcoming* (in 3 and 21 days), four
  *active* (started 2, 6, 12 and 20 weeks ago, ending 8-14 weeks ahead), two
  *completed* (26→10 and 40→22 weeks ago), one *cancelled* (with a reason)
  and one *archived* (completed, then archived); PUNE has one upcoming, two
  active and one completed. Between them: a batch with **no trainer**, one
  with **no timetable**, one **full** (capacity equals the seats taken), one
  **nearly full** (two seats left), every delivery mode and every kind
  (``regular``, ``internship``, and ``modular`` standing in for a fast
  track, which is the nearest thing the enum has). Status moves only through
  ``set_batch_status`` along ``TRANSITIONS``, so the cascades and audit rows
  happen; a batch found part-way is walked the rest of the way. A batch
  *found* from an earlier run is re-dated through ``update_batch``, so the
  spec's offsets still describe today — the end date widened, the start date
  moved up but never past the batch's first class, because the classes already
  generated pin the range from the inside (``ClassSession.clean`` refuses a
  class outside its batch's dates and ``update_batch`` does not look). The two
  batches with no classes at all therefore keep their offsets exactly, which
  is what keeps the ``batch_seats`` warning (a start within three days) alive
  on any day. Without any of this every relative state decays with the
  calendar: the
  batch "starting in three days" is overdue by next week, the active ones
  drift past their end dates into ``batch_overrun``, and from eighty-five
  days on the class this stage adds for today falls outside its batch and the
  command dies. A batch whose trainer has since left cannot be re-validated
  at all (``Batch.clean`` refuses an inactive trainer), so its dates are left
  where they are and the line says so.
* the **headline trainer** (``ctx.trainers[MAIN][0]``) teaches the MAIN
  batch that started six weeks ago; it has a class **today that has already
  started** — a timetable slot on today's weekday starting an hour ago
  (clamped to 00:00..21:55, so a two-hour class still begins and ends inside
  today) — and the batch that started two weeks ago has one
  later today (after 19:55 there is no room for a two-hour class ahead, so
  that slot too becomes one that started an hour ago). Both are timetable
  slots rather than one-off classes, so ``generate_sessions`` makes today's
  class the way it makes every other. Those two *clock slots* are placed
  first, so every other slot yields to them rather than the other way round,
  and each carries ``note=ctx.tag("today/<spec key>")``: the weekday is
  whatever day the seed first ran, and the tag is how a later run recognises
  the slot instead of adding another on *its* weekday. The fixed slots never
  depend on the day the command runs. ``create_session`` then covers today
  where the timetable does not — a calendar holiday, or a re-run on a day
  the clock slot does not fall on — with a one-off class, the only row this
  stage adds on a later day. It is skipped where today falls outside the
  batch's own dates, and a service that refuses it (a class already at that
  minute) is logged rather than raised: one class is not worth the six stages
  queued behind this one.
* **timetables**: two to four weekly slots per scheduled batch via
  ``create_schedule`` (``Asia/Kolkata``; Lab 1/2/3 or Online). Trainers and
  times are spread so nothing clashes, and a slot that still clashes is
  moved an hour at a time until the conflict guard accepts it — the guard is
  the arbiter, not this module's arithmetic. The internship track and the
  Pune MERN cohort carry a **Saturday** slot as well as their weekdays,
  because a walkthrough on a Saturday or Sunday otherwise found their two
  trainers' ``/teaching/today`` empty: only the two clock slots are placed on
  the day the command runs, and every other timetable is fixed. Then
  ``generate_sessions`` across the batch's whole date range and
  ``autoplan_batch`` (stage 3 published the lessons), so ``timeline_status``
  has planned lessons.
* **enrolments** via ``enrol_student`` while the batch is upcoming or
  active — always *before* the batch moves on to completed, cancelled or
  archived. Every roster student except the one flagged ``never_enrolled``
  is placed on one to three batches in their centre (8-18 per batch), the
  headline student on the six-weeks-ago batch **and** the 26→10-weeks-ago
  one (stage 7 certifies that completion). A batch that is running took its
  enrolments in the week around its start; one that finished months ago took
  them over the ten weeks before it, which is what keeps every month of the
  last year on the enrolment trend rather than nine spikes with four empty
  months between them. A few are *pending* — created
  that way, because ``TRANSITIONS`` has no road from active back to
  pending — a few *suspended* and *cancelled* through
  ``set_enrollment_status`` with a note, and one student is moved between
  the two youngest MAIN active batches through ``transfer_student``.
  ``enrolled_at``/``created_at``/``status_changed_at`` are then backdated to
  the batch's start (plus that jitter) so the enrolment trend spreads across
  the year rather than spiking this morning, and each batch's own
  ``created_at`` is moved back behind its earliest enrolment.
* the **demo accounts** (``@demo.grras.invalid``, present on staging, absent
  on a fresh database): when they exist, ``student1..20`` are enrolled on the
  two youngest MAIN active batches and ``trainer1`` gets a MAIN active batch
  of his own — with a clock slot like the headline trainer's, because a
  walkthrough that signs in as the demo trainer lands on ``/teaching/today``
  and a weekend-only timetable left that screen empty Monday to Friday.
  Nothing about those accounts is ever edited.
* the **imported SITP batches** (``ctx.imported_batches``): the summer
  programme ended, so every one is 'active' with an end date months ago —
  a ``batch_overrun`` warning each. Four tracks the institute kept running
  (:data:`SITP_EXTENDED`) are **extended** through ``update_batch`` to end
  ten weeks from today, given three weekly slots, classes from three weeks
  ago to the new end, and a plan — planted on the classes generated for the
  term that is running rather than through ``autoplan_batch``, which walks a
  batch's unplanned classes oldest-first and would spend the course's three
  published lessons on the ones the workbook import made in May. The
  generation is *forced* on every run that moves the end date: the slots are
  the ones the first run made and already carry its classes, so the guard
  that stops this stage regenerating a timetable it has already made would
  otherwise leave each re-extended batch active, with ten weeks ahead of it
  and no class in either direction. Eleven of
  the rest are **completed** through ``set_batch_status``, which completes
  their ~860 active enrolments — the one deliberate change to rows this
  stage did not create, and the cascade's ``completed_at`` is backdated to
  the batch's own end date so the chart shows the programme ending when it
  ended. The twelfth (:data:`SITP_OVERRUN`) is **left active with its end
  date in the past on purpose**: those sixteen batches are the database's
  only ``batch_overrun`` warning, and completing every one of them left that
  warning kind with nothing to show on any screen. A batch already
  completed, or already ending on or after today, is left alone. On a
  database with no import this is a no-op, and says so.
* the **junk staging batches**: any batch whose lower-cased name is a key of
  ``roster.BATCH_RENAMES`` is renamed through ``update_batch`` and dated into
  the month its new name claims, both in one call — ``update_batch`` applies
  every field it is given and then calls ``full_clean`` once, so a start
  after the old end is never validated on the way. The month is a fixed
  string in the new name, so that alignment is to an absolute month and not
  to ``ctx.today``, and the range is only ever *widened* around the classes
  the batch already has. A batch whose first class falls before the month its
  name claims is left dated as it is, with a line naming the class that pins
  it: on staging that is ``new first batch``, whose seventy-eight classes run
  September to December under a name that says July. ``dsa in python`` keeps
  its name.
* **last of all**, the roster's inactive student and inactive trainer are
  deactivated through ``set_user_active`` — after they were enrolled and
  given a batch, so the inactive filters show rows with history.

The stage's last line counts the past classes it leaves ``scheduled``: every
one of them is a register stage 7 still has to mark, and on the staging clone
that is a few hundred, not a few.

Idempotent by batch name, ``(batch, weekday)`` for fixed slots and the
``today/<key>`` tag for the two clock slots, ``(batch, date, start_time)``
for classes (a database constraint), ``(student, batch)`` for enrolments,
and status for everything that moves. Nothing is keyed on the day the
command runs: a re-run on the same day creates nothing at all, and one on a
later day adds only the one-off class that keeps "a class today" true and the
``update_batch`` that keeps each spec's dates the offsets it asks for. Every random draw happens in
:func:`_plan` before any database work, so a ``--only batches`` run draws
exactly what a full run drew.

Leaves in ``ctx``: ``batches``, ``showcase_batches`` and ``imported_batches``
updated for the stages after it.
"""

from __future__ import annotations

import calendar
import itertools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from time import perf_counter
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Max, Min, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import set_user_active
from apps.batches.models import (
    Batch,
    BatchKind,
    BatchSchedule,
    BatchStatus,
    DeliveryMode,
    Weekday,
)
from apps.batches.services import (
    ScheduleConflictError,
    create_batch,
    create_schedule,
    set_batch_status,
    update_batch,
)
from apps.common.exceptions import ApplicationError
from apps.courses.models import Lesson, PublishStatus
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.enrollments.services import enrol_student, set_enrollment_status, transfer_student
from apps.sessions.models import ClassSession, SessionStatus
from apps.sessions.services import (
    MAX_GENERATION_DAYS,
    autoplan_batch,
    create_session,
    generate_sessions,
    plan_session_topic,
)
from apps.students.models import StudentProfile
from apps.trainers.models import TrainerProfile

from ..context import MARKER, Context, batch_key
from ..roster import BATCH_RENAMES, DOMAIN, MAIN, PUNE

TZ = "Asia/Kolkata"
DEMO_DOMAIN = "demo.grras.invalid"
DEMO_STUDENTS = 20
CLASS_HOURS = 2

#: The earliest and latest a class may start. A class an hour before "now"
#: at 00:30 would start yesterday, and one after 21:55 would end tomorrow.
#: The floor is midnight itself rather than five past it: a run at 00:02 that
#: clamped to 00:05 asked for a class three minutes in the *future*, and a
#: class that has not started cannot be marked
#: (``ClassSession.can_take_attendance``), so for the first five minutes of
#: every day the headline trainer's Today screen had nothing on it — the one
#: state this stage exists to build.
EARLIEST_START = time(0, 0)
LATEST_START = time(21, 55)

#: Hour offsets tried, in order, when a slot clashes. The two clock slots
#: use their own lists: the started one only moves earlier, so it stays
#: started; the later one only moves later, so it stays ahead.
SHIFTS = (0, 1, 2, -1, 3, -2, 4)
SHIFTS_EARLIER = (0, -1, -2, -3)
SHIFTS_LATER = (0, 1, 2, 3)

#: Every clock slot's note starts with this (``ctx.tag("today/<key>")``), so
#: the fixed-slot lookup by weekday can leave the clock slots out of it.
CLOCK_TAG_PREFIX = f"{MARKER}[today/"

#: Name fragments (lower-cased) of the imported SITP tracks that keep running,
#: matched as whole words so that ``group a`` never claims a ``Group A2``.
SITP_EXTENDED = ("group a", "full stack web mern", "aws data engineer", "data science with ai_ml")

#: The one imported track left **active with its end date months in the
#: past**. Those sixteen batches are the only ``batch_overrun`` rows the
#: database has (``apps.warnings.services``: "past the end date and still
#: active"), so completing all of them leaves that warning kind unreachable on
#: the admin and counsellor screens. The smallest track keeps the flag, which
#: costs seventeen enrolments left active on a batch that ended in July.
SITP_OVERRUN = ("ms-az 204",)
SITP_EXTENSION_DAYS = 70
SITP_BACKFILL_DAYS = 21
SITP_SLOT_DAYS = (Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)
SITP_SLOT_START = time(10, 0)

#: A batch that started longer ago than this draws its enrolments from a much
#: wider admissions window (:func:`_jitter`).
LONG_PAST_WEEKS = 20
#: Days around a batch's start date that one enrolment may fall on: a week
#: either side for a batch running or about to, ten weeks for one long done.
JITTER_RECENT = (-7, 3)
JITTER_OLD = (-70, 3)

#: The road to each status from a freshly created (upcoming) batch.
STATUS_PATHS: dict[str, tuple[str, ...]] = {
    BatchStatus.UPCOMING: (),
    BatchStatus.ACTIVE: (BatchStatus.ACTIVE,),
    BatchStatus.COMPLETED: (BatchStatus.ACTIVE, BatchStatus.COMPLETED),
    BatchStatus.ARCHIVED: (BatchStatus.ACTIVE, BatchStatus.COMPLETED, BatchStatus.ARCHIVED),
    BatchStatus.CANCELLED: (BatchStatus.CANCELLED,),
}


# ---------------------------------------------------------------------------
# What the stage creates: written out, so every run makes the same batches
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchSpec:
    """One showcase batch, dated in days relative to today.

    ``trainer`` is a roster local part, ``demo:<local part>`` for a demo
    account (the spec is skipped when that account is missing), or ``None``
    for a batch nobody teaches yet. ``spare`` is what makes a batch full
    (``0``) or nearly full (``2``): the capacity becomes the planned seats
    plus that; ``None`` uses the fixed ``capacity``. ``today`` asks for a
    clock slot on the weekday the seed first runs: ``"started"`` an hour
    ago, ``"later"`` two hours ahead. ``days`` lists the fixed weekly slots;
    the first ``slots`` of them are used, whatever day it is.
    """

    key: str
    name: str
    branch: str
    course: str
    trainer: str | None
    status: str
    start: int
    end: int
    delivery: str
    kind: str
    days: tuple[int, ...]
    slots: int
    start_time: time | None
    location: str
    seats: int
    note: str
    spare: int | None = None
    capacity: int = 40
    today: str | None = None
    pending: int = 0
    suspended: int = 0
    cancelled: int = 0
    headline: bool = False
    reason: str = ""


MON, TUE, WED, THU, FRI, SAT, SUN = Weekday.values

SPECS: tuple[BatchSpec, ...] = (
    # --- Jaipur ------------------------------------------------------------
    BatchSpec(
        "u1", "RHCSA Morning — Oct 2026", MAIN, "rhcsa", "trainer",
        BatchStatus.UPCOMING, 3, 3 + 84, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(TUE, THU, SAT, MON, WED), slots=3, start_time=time(8, 0), location="Lab 1",
        seats=10, pending=3, note="Morning RHCSA cohort; admissions open until the first class.",
    ),
    BatchSpec(
        "u2", "AWS Solutions Architect Weekend — Oct 2026", MAIN, "aws-solutions-architect",
        None, BatchStatus.UPCOMING, 21, 21 + 112, DeliveryMode.ONLINE, BatchKind.REGULAR,
        days=(SAT, SUN), slots=2, start_time=time(10, 0), location="Online",
        seats=8, pending=2, note="Weekend AWS cohort; trainer still to be confirmed.",
    ),
    BatchSpec(
        "a1", "AWS Solutions Architect Evening — Sep 2026", MAIN, "aws-solutions-architect",
        "rohit.kumawat", BatchStatus.ACTIVE, -14, 98, DeliveryMode.HYBRID, BatchKind.REGULAR,
        days=(MON, WED, FRI, TUE, THU), slots=2, start_time=time(18, 0), location="Lab 2",
        seats=14, suspended=1, cancelled=2, today="later",
        note="Evening AWS cohort for working professionals; labs in Lab 2, theory online.",
    ),
    BatchSpec(
        "a2", "DevOps Engineering Morning — Aug 2026", MAIN, "devops-engineering", "trainer",
        BatchStatus.ACTIVE, -42, 84, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(MON, WED, FRI, TUE, THU), slots=2, start_time=time(11, 0), location="Lab 1",
        seats=16, cancelled=2, today="started", headline=True,
        note="Flagship DevOps cohort: Docker, Kubernetes and Ansible in Lab 1.",
    ),
    BatchSpec(
        "a3", "Python Full Stack Weekend — Jul 2026", MAIN, "python-django-full-stack",
        "neha.saxena", BatchStatus.ACTIVE, -84, 56, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(SAT, SUN), slots=2, start_time=time(9, 0), location="Lab 3",
        seats=16, spare=2, suspended=2, note="Weekend Python & Django cohort; two seats left.",
    ),
    BatchSpec(
        "a4", "Data Science Internship — May 2026", MAIN, "data-science-ml", "priya.malhotra",
        BatchStatus.ACTIVE, -140, 70, DeliveryMode.HYBRID, BatchKind.INTERNSHIP,
        days=(MON, TUE, THU, SAT), slots=4, start_time=time(14, 0), location="Lab 2",
        seats=14, spare=0,
        note="Thirty-week internship track with Saturday labs; every seat is taken.",
    ),
    BatchSpec(
        "c1", "RHCSA Evening — Mar 2026", MAIN, "rhcsa", "trainer",
        BatchStatus.COMPLETED, -182, -70, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(MON, WED, FRI), slots=3, start_time=time(18, 0), location="Lab 1",
        seats=16, headline=True, note="Evening RHCSA cohort; finished, certificates due.",
    ),
    BatchSpec(
        "c2", "Python Django Fast Track — Dec 2025", MAIN, "python-django-full-stack",
        "neha.saxena", BatchStatus.COMPLETED, -280, -154, DeliveryMode.ONLINE, BatchKind.MODULAR,
        days=(MON, TUE, WED, THU), slots=3, start_time=time(19, 0), location="Online",
        seats=12, note="Eighteen-week fast track taught online, four evenings a week.",
    ),
    BatchSpec(
        "x1", "RHCSA Weekend — Sep 2025", MAIN, "rhcsa", "deepak.purohit",
        BatchStatus.ARCHIVED, -364, -252, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(SAT, SUN), slots=2, start_time=time(10, 0), location="Lab 3",
        seats=10, note="Last year's weekend RHCSA cohort; archived after completion.",
    ),
    BatchSpec(
        "k1", "Ethical Hacking Evening — Aug 2026", MAIN, "ethical-hacking", "sameer.bhatt",
        BatchStatus.CANCELLED, -28, 56, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(), slots=0, start_time=None, location="",
        seats=8, note="Evening security cohort that did not run.",
        reason="Trainer unavailable; the students were moved to the next cohort.",
    ),
    BatchSpec(
        "d1", "Ansible Automation Weekend — Aug 2026", MAIN, "devops-engineering",
        "demo:trainer1", BatchStatus.ACTIVE, -35, 70, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(SAT, SUN), slots=2, start_time=time(14, 0), location="Lab 2",
        seats=0, capacity=30, today="started",
        note="Weekend Ansible cohort taught by the demo trainer.",
    ),
    # --- Pune --------------------------------------------------------------
    BatchSpec(
        "pu1", "DevOps Engineering Weekend — Oct 2026", PUNE, "devops-engineering",
        "shivani.nair", BatchStatus.UPCOMING, 10, 10 + 98, DeliveryMode.ONLINE, BatchKind.REGULAR,
        days=(), slots=0, start_time=None, location="Online",
        seats=10, pending=2, note="Weekend DevOps cohort; timetable not yet published.",
    ),
    BatchSpec(
        "pa1", "MERN Full Stack Morning — Aug 2026", PUNE, "mern-full-stack", "ankit.kulkarni",
        BatchStatus.ACTIVE, -56, 70, DeliveryMode.HYBRID, BatchKind.REGULAR,
        days=(MON, WED, FRI, SAT), slots=4, start_time=time(9, 0), location="Lab 1",
        seats=18, suspended=1,
        note="Morning MERN cohort; project work online on Fridays, reviews on Saturdays.",
    ),
    BatchSpec(
        "pa2", "Data Analytics Evening — Sep 2026", PUNE, "data-science-ml", "tushar.patel",
        BatchStatus.ACTIVE, -21, 84, DeliveryMode.OFFLINE, BatchKind.REGULAR,
        days=(TUE, THU, SAT), slots=3, start_time=time(18, 0), location="Lab 2",
        seats=16, cancelled=1, note="Evening analytics cohort: SQL, Pandas and Power BI.",
    ),
    BatchSpec(
        "pc1", "DevOps Engineering Fast Track — Apr 2026", PUNE, "devops-engineering",
        "shivani.nair", BatchStatus.COMPLETED, -154, -56, DeliveryMode.ONLINE, BatchKind.MODULAR,
        days=(MON, TUE, WED, THU), slots=3, start_time=time(7, 0), location="Online",
        seats=14, note="Fourteen-week early-morning fast track, taught online.",
    ),
)  # fmt: skip

#: The two youngest MAIN active batches: the demo students join them, and the
#: one transfer moves a student from the first to the second.
TRANSFER_FROM, TRANSFER_TO = "a1", "a2"
DEMO_BATCHES = ("a1", "a2")
DEMO_BATCH_KEY = "d1"


# ---------------------------------------------------------------------------
# The plan: every random choice, made before the database is touched
# ---------------------------------------------------------------------------


@dataclass
class Placement:
    """One student on one batch: how they join and, for a few, how they leave."""

    student: StudentProfile
    spec_key: str
    status: str  # what enrol_student is asked for: active or pending
    target: str | None  # suspended / cancelled, applied afterwards; None = stays
    jitter: int  # days around the batch start, for enrolled_at
    later: int  # days after enrolling, for the status change


@dataclass
class Plan:
    specs: list[BatchSpec] = field(default_factory=list)
    placements: dict[str, list[Placement]] = field(default_factory=dict)
    demo: list[Placement] = field(default_factory=list)
    transfer: tuple[StudentProfile, str, str] | None = None
    #: Filled during the run: spec key -> batch, and the rows this run made.
    batches: dict[str, Batch] = field(default_factory=dict)
    created_batches: list[Batch] = field(default_factory=list)
    created_rows: list[tuple[Enrollment, Placement]] = field(default_factory=list)
    transfer_rows: tuple[Enrollment, Enrollment] | None = None


def _plan(ctx: Context) -> Plan:
    """Draw everything now, in a fixed order, whatever the database holds.

    The pool per centre is every roster student except the one who never
    enrolled — *not* ``enrollable_students``, which also drops an inactive
    user: the roster's inactive student is deactivated at the end of this
    very stage, and a second run that planned without them would place every
    later student one seat over and miss its own rows.
    """
    plan = Plan()
    plan.specs = [spec for spec in SPECS if _wanted(ctx, spec)]
    headline = ctx.students[MAIN][0] if ctx.students.get(MAIN) else None

    for code in (MAIN, PUNE):
        pool = [
            profile
            for profile in ctx.students.get(code, [])
            if not _flag(ctx, profile.user, "never_enrolled")
        ]
        ctx.rng.shuffle(pool)
        cycle = itertools.cycle(pool)

        for spec in plan.specs:
            if spec.branch != code or spec.seats == 0:
                continue
            chosen: list[StudentProfile] = []
            if spec.headline and headline is not None and code == MAIN:
                chosen.append(headline)
            while pool and len(chosen) < min(spec.seats, len(pool)):
                candidate = next(cycle)
                if candidate not in chosen:
                    chosen.append(candidate)
            plan.placements[spec.key] = _placements(ctx, spec, chosen, headline)

    # The transfer: a plain active student on the source batch who is not on
    # the target, so the move is the only way they reach it.
    on_target = {p.student.pk for p in plan.placements.get(TRANSFER_TO, [])}
    for placement in plan.placements.get(TRANSFER_FROM, []):
        student = placement.student
        if (
            placement.status == EnrollmentStatus.ACTIVE
            and placement.target is None
            and student.pk not in on_target
            and student is not headline
            and not _flag(ctx, student.user, "inactive")
        ):
            plan.transfer = (student, TRANSFER_FROM, TRANSFER_TO)
            break

    # Demo placements are drawn whether or not the accounts exist, so the
    # draw count — and therefore every draw after it — is the same on a
    # database with the demo roster and on one without.
    demo_profiles = _demo_students(ctx)
    has_demo_batch = any(spec.key == DEMO_BATCH_KEY for spec in plan.specs)
    for index in range(1, DEMO_STUDENTS + 1):
        jitter, later = ctx.rng.randint(-7, 3), ctx.rng.randint(7, 28)
        profile = demo_profiles.get(f"student{index}@{DEMO_DOMAIN}")
        if profile is None:
            continue
        for key in _demo_keys(index, has_demo_batch):
            plan.demo.append(
                Placement(
                    student=profile,
                    spec_key=key,
                    status=EnrollmentStatus.ACTIVE,
                    target=None,
                    jitter=jitter,
                    later=later,
                )
            )
    return plan


def _placements(
    ctx: Context, spec: BatchSpec, chosen: list[StudentProfile], headline: StudentProfile | None
) -> list[Placement]:
    """The chosen students with their fates. The few who wait, leave or are
    suspended come from the tail — never the headline student, who must stay
    active where a walkthrough expects to find him."""
    tail = [s for s in chosen if s is not headline]
    pending = set(tail[len(tail) - spec.pending :]) if spec.pending else set()
    rest = tail[: len(tail) - spec.pending]
    suspended = set(rest[len(rest) - spec.suspended :]) if spec.suspended else set()
    rest = rest[: len(rest) - spec.suspended]
    cancelled = set(rest[len(rest) - spec.cancelled :]) if spec.cancelled else set()

    rows = []
    for student in chosen:
        status, target = EnrollmentStatus.ACTIVE, None
        if student in pending:
            status = EnrollmentStatus.PENDING
        elif student in suspended:
            target = EnrollmentStatus.SUSPENDED
        elif student in cancelled:
            target = EnrollmentStatus.CANCELLED
        rows.append(
            Placement(
                student=student,
                spec_key=spec.key,
                status=status,
                target=target,
                jitter=_jitter(ctx, spec),
                later=ctx.rng.randint(7, 28),
            )
        )
    return rows


def _jitter(ctx: Context, spec: BatchSpec) -> int:
    """How many days off the batch's start one student's enrolment falls.

    Narrow for a batch that is running or about to — it opened a week before
    the first class and filled — and ten weeks wide for one that finished
    months ago. Not decoration: anchored within a week of nine batch starts,
    every one of the two hundred-odd enrolments landed on nine dates, and the
    weekly and monthly enrolment trends (``/analytics``, ``/admin/overview``,
    ``/manage``, ``/admissions/dashboard``) had four of the last twelve
    months at exactly zero, which reads as a broken chart rather than as a
    quiet October. The wide window is only ever given to batches whose
    enrolments are all completed, so it costs no other state a thing.
    """
    low, high = JITTER_OLD if spec.start <= -LONG_PAST_WEEKS * 7 else JITTER_RECENT
    return ctx.rng.randint(low, high)


def _wanted(ctx: Context, spec: BatchSpec) -> bool:
    """A spec on a demo trainer exists only where that trainer does."""
    if spec.trainer and spec.trainer.startswith("demo:"):
        return _demo_trainer(ctx, spec) is not None
    return True


def _flag(ctx: Context, user: User, name: str) -> Any:
    person = ctx.person_for(user)
    return person.flags.get(name) if person is not None else None


def _demo_students(ctx: Context) -> dict[str, StudentProfile]:
    """The demo students by email — those at MAIN and still active, which is
    all ``enrol_student`` would accept anyway."""
    main = ctx.branches.get(MAIN)
    if main is None:
        return {}
    emails = [f"student{i}@{DEMO_DOMAIN}" for i in range(1, DEMO_STUDENTS + 1)]
    return {
        profile.user.email: profile
        for profile in StudentProfile.objects.filter(
            user__email__in=emails, user__is_active=True, branch=main
        ).select_related("user", "branch")
    }


def _demo_keys(index: int, has_demo_batch: bool) -> list[str]:
    """Which batches the ``index``-th demo student joins.

    Three ways, not two. With all twenty of them on the two youngest MAIN
    active batches, those two carried 28 and 24 enrolments on staging — over
    the 8-25 a batch is meant to show — while the demo trainer's own batch,
    which every demo student joins anyway, sat at twenty. So a third of them
    join only that one. Where the demo trainer is missing his batch is not
    created either, and the twenty split two ways as before: a demo student
    on no batch is worse than a crowded batch.
    """
    share = (index - 1) * 3 // DEMO_STUDENTS
    keys = [DEMO_BATCHES[share]] if share < len(DEMO_BATCHES) else []
    if has_demo_batch:
        keys.append(DEMO_BATCH_KEY)
    elif not keys:
        keys = [DEMO_BATCHES[index % len(DEMO_BATCHES)]]
    return keys


def _demo_trainer(ctx: Context, spec: BatchSpec) -> TrainerProfile | None:
    local_part = (spec.trainer or "").removeprefix("demo:")
    branch = ctx.branches.get(spec.branch)
    if branch is None:
        return None
    return (
        TrainerProfile.objects.filter(
            user__email=f"{local_part}@{DEMO_DOMAIN}", user__is_active=True, branch=branch
        )
        .select_related("user", "branch")
        .first()
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    if not ctx.students:
        raise RuntimeError("No roster students yet: run the people stage first.")
    started_at = timezone.now()
    plan = _plan(ctx)

    _timed(ctx, "batches", lambda: _ensure_batches(ctx, plan))
    _timed(ctx, "timetables", lambda: _ensure_timetables(ctx, plan))
    _timed(ctx, "enrolments", lambda: _ensure_enrolments(ctx, plan))
    _timed(ctx, "statuses", lambda: _ensure_statuses(ctx, plan))
    _timed(ctx, "transfer", lambda: _ensure_transfer(ctx, plan))
    _timed(ctx, "backdating", lambda: _backdate(ctx, plan))
    _timed(ctx, "imported batches", lambda: _ensure_imported(ctx, started_at))
    _timed(ctx, "renames", lambda: _ensure_renames(ctx))
    _timed(ctx, "departures", lambda: _ensure_departures(ctx))
    _report_registers(ctx)


def _report_registers(ctx: Context) -> None:
    """Hand stage 7 the number, out loud.

    Every past class this stage generated is still ``scheduled``, so
    ``ClassSession.can_take_attendance`` is true for all of them and the
    registers-outstanding and ``dsr_missing`` counts read in the hundreds
    until stage 7 marks them. Worth one query and one line, because on the
    staging clone that is a few hundred classes rather than a few.

    Two numbers, because the first line said "this stage's" of a count that
    was the whole database's — the imported and hand-made batches' own
    unmarked classes included, which this stage never generated and stage 7
    is not obliged to mark. This stage's own are the marked batches plus the
    imported ones it extended.
    """
    mine = [batch.pk for key, batch in ctx.imported_batches.items() if _keeps_running(key)]
    past = ClassSession.objects.filter(session_date__lt=ctx.today, status=SessionStatus.SCHEDULED)
    outstanding = past.filter(
        Q(batch__description__startswith=MARKER) | Q(batch_id__in=mine)
    ).count()
    ctx.out(
        f"classes: {outstanding} past classes on this stage's batches still 'scheduled' "
        f"for stage 7 to mark ({past.count()} on the whole database)"
    )


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> None:
    started = perf_counter()
    step()
    ctx.out(f"batches/{what}: {perf_counter() - started:.1f}s")


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------


def _ensure_batches(ctx: Context, plan: Plan) -> None:
    for spec in plan.specs:
        key = batch_key(spec.name)
        batch = ctx.batches.get(key)
        if batch is None:
            batch = _create_batch(ctx, spec)
            ctx.created("batch")
            plan.created_batches.append(batch)
            ctx.out(f"batch {spec.name} ({batch.code}): created")
        else:
            ctx.found_existing("batch")
            ctx.out(f"batch {spec.name} ({batch.code}): found")
            _redate(ctx, batch, spec)
        ctx.batches[key] = batch
        ctx.showcase_batches[key] = batch
        plan.batches[spec.key] = batch


def _create_batch(ctx: Context, spec: BatchSpec) -> Batch:
    course = ctx.courses.get(spec.course)
    if course is None:
        raise RuntimeError(f"Course {spec.course!r} is not loaded: run the courses stage first.")
    # Full and nearly full are relative to the roster seats planned for the
    # batch; the demo students never join those two, so the arithmetic holds
    # on staging and on an empty database alike.
    capacity = spec.capacity if spec.spare is None else spec.seats + spec.spare
    return create_batch(
        actor=ctx.actor_for(spec.branch),
        branch=ctx.branch(spec.branch),
        name=spec.name,
        course=course,
        trainer=_trainer_for(ctx, spec),
        start_date=ctx.days_ahead(spec.start),
        end_date=ctx.days_ahead(spec.end),
        capacity=capacity,
        delivery_mode=spec.delivery,
        kind=spec.kind,
        description=ctx.note(spec.note),
    )


def _redate(ctx: Context, batch: Batch, spec: BatchSpec) -> None:
    """Keep a *found* batch's dates the offsets its spec asks for.

    A batch's dates are written once, by the run that created it, so on a
    database seeded weeks ago every relative state has quietly decayed: the
    batch "starting in three days" started last week (and with it the
    ``batch_seats`` warning), the active ones have drifted towards their end
    dates, and once ``ctx.today`` passes the end date the class
    ``_ensure_today`` adds for today is refused by ``ClassSession.clean`` and
    the command stops on stage 4 — eighty-five days after the first seeding,
    every time. So the range moves with the clock.

    **The classes the batch already has are the arbiter.** They sit inside the
    old range and ``update_batch`` does not look at them, so a range that no
    longer covers them would strand a class outside its batch's dates: the
    same validation error, deferred to whatever re-validates that class next.
    So ``end_date`` is only ever *widened* — which is what keeps today inside
    the range — and ``start_date`` moves towards the offset the spec asks for
    but never past the batch's **first class**. A batch with no classes at all
    (the one with no timetable by design, and the cancelled one) therefore
    keeps its "starts in ten days" exactly, on any day, and with it the
    ``batch_seats`` warning that only fires within three days of a start; a
    batch generated end to end can only creep up to its own first class, and
    a completed batch's window grows a day per day of drift while its end
    stays the promised ten weeks ago. Both dates go in one ``update_batch``
    call, which applies every field before its single ``full_clean``.
    """
    wanted_start, wanted_end = ctx.days_ahead(spec.start), ctx.days_ahead(spec.end)
    first = ClassSession.objects.filter(batch=batch).aggregate(first=Min("session_date"))["first"]
    start = wanted_start if first is None else min(wanted_start, first)
    end = max(batch.end_date, wanted_end)
    if (start, end) == (batch.start_date, batch.end_date):
        ctx.found_existing("batch_redate")
        return
    try:
        update_batch(batch=batch, actor=ctx.actor_for(spec.branch), start_date=start, end_date=end)
    except (ApplicationError, ValidationError) as exc:
        # ``update_batch`` re-validates the whole batch, and ``Batch.clean``
        # refuses an inactive trainer: the archived batch taught by the
        # trainer who left at the end of this stage cannot be saved again.
        # It is a year in the past and has no class today, so frozen dates
        # cost it nothing — but the in-memory instance now holds the values
        # the service tried, and the steps after this one read them.
        batch.refresh_from_db(fields=["start_date", "end_date"])
        # Counted as found, not silently dropped: every spec batch is then
        # accounted for under one label or the other, so the finish table's
        # arithmetic still adds up to the fifteen batches.
        ctx.found_existing("batch_redate")
        ctx.out(f"batch {batch.code}: dates left at {batch.start_date}..{batch.end_date} ({exc})")
        return
    ctx.created("batch_redate")
    ctx.out(f"batch {batch.code}: re-dated {start:%d %b %Y}..{end:%d %b %Y}")


def _trainer_for(ctx: Context, spec: BatchSpec) -> TrainerProfile | None:
    if spec.trainer is None:
        return None
    if spec.trainer.startswith("demo:"):
        return _demo_trainer(ctx, spec)
    email = f"{spec.trainer}@{DOMAIN}"
    profile = next((p for p in ctx.trainers.get(spec.branch, []) if p.user.email == email), None)
    if profile is None:
        raise RuntimeError(f"Trainer {email} is not loaded: run the people stage first.")
    if not profile.user.is_active:
        # Only reachable when this stage's last step ran on an earlier
        # attempt but this batch was never made: ``Batch.clean`` refuses the
        # departed trainer, so the centre's last active trainer stands in.
        pool = ctx.assignable_trainers(spec.branch)
        if not pool:
            raise RuntimeError(f"No active trainer at {spec.branch} for {spec.name}.")
        stand_in = pool[-1]
        ctx.out(f"batch {spec.name}: {email} is inactive, using {stand_in.user.email}")
        return stand_in
    return profile


# ---------------------------------------------------------------------------
# Timetables and classes
# ---------------------------------------------------------------------------


def _ensure_timetables(ctx: Context, plan: Plan) -> None:
    # The two clock slots first: their times are dictated by the clock, so
    # everything else must be the side that yields.
    ordered = sorted(plan.specs, key=lambda spec: 0 if spec.today else 1)
    for spec in ordered:
        batch = plan.batches.get(spec.key)
        if batch is None or spec.status == BatchStatus.CANCELLED:
            continue
        if spec.start_time is None and spec.today is None:
            ctx.out(f"timetable {batch.code}: none by design")
            continue
        actor = ctx.actor_for(spec.branch)
        location = spec.location or "Lab 1"
        schedules: list[BatchSchedule] = []
        if spec.today:
            # Found by its tag on whatever weekday the seed first ran; only
            # ever created on today's weekday, once.
            wanted, shifts = _clock_time(ctx, spec)
            slot = _ensure_slot(
                ctx,
                batch,
                actor,
                ctx.today.weekday(),
                wanted,
                location,
                shifts,
                tag=ctx.tag(f"today/{spec.key}"),
            )
            schedules.append(slot)
        if spec.start_time is not None:
            for weekday in spec.days[: spec.slots]:
                schedules.append(
                    _ensure_slot(ctx, batch, actor, weekday, spec.start_time, location, SHIFTS)
                )
        _ensure_classes(ctx, batch, actor, [s for s in schedules if s is not None])
        if spec.today:
            _ensure_today(ctx, batch, actor, spec)


def _clock_time(ctx: Context, spec: BatchSpec) -> tuple[time, tuple[int, ...]]:
    """When the clock slot starts, and which way it may move to dodge a clash.

    ``"started"`` is an hour ago, on the minute, and clamped to the
    00:00..21:55 window so that a two-hour class still begins and ends inside
    today — and before 01:00, where an hour ago was yesterday, it is *now* to
    the minute rather than the window's floor: a class five minutes into the
    future has not started, and a class that has started is the whole point of
    this slot. ``"later"`` is two hours ahead — while a
    two-hour class starting then still ends today; from 19:55 on there is no
    such class, and a slot clamped to 21:55 would already be in the past by
    the time the run finished, so the batch gets a started class instead.
    """
    later = ctx.now + timedelta(hours=2)
    if spec.today == "later" and later.date() == ctx.today and later.time() <= LATEST_START:
        return later.time().replace(second=0, microsecond=0), SHIFTS_LATER
    earlier = ctx.now - timedelta(hours=1)
    if earlier.date() != ctx.today:
        # Before 01:00: an hour ago was yesterday, and a class cannot start
        # before its own day. The clock itself is then the latest start that
        # has already happened — 00:00 at midnight, 00:02 at 00:02 — where
        # the window's floor would have been a start in the future.
        return max(EARLIEST_START, ctx.now.time().replace(second=0, microsecond=0)), SHIFTS_EARLIER
    # Clamped at both ends. Without the upper clamp, a run after 22:55 asks
    # for a class that ends tomorrow; ``_ensure_slot`` is protected by
    # ``_shift``, but ``_ensure_today`` feeds this straight to
    # ``create_session``, and ``ClassSession.clean`` refused it — the whole
    # command died there on four days in seven. 21:55 is still an hour or
    # more "ago" at 22:55, which is all the state on screen needs.
    started = max(EARLIEST_START, earlier.time().replace(second=0, microsecond=0))
    return min(started, LATEST_START), SHIFTS_EARLIER


_ANY_MONDAY = date(2000, 1, 3)


def _shift(start: time, hours: int) -> time | None:
    """``start`` moved by ``hours``, or ``None`` when that leaves the day."""
    moved = datetime.combine(_ANY_MONDAY, start) + timedelta(hours=hours)
    if moved.date() != _ANY_MONDAY or not EARLIEST_START <= moved.time() <= LATEST_START:
        return None
    return moved.time()


def _plus_hours(start: time, hours: int) -> time:
    return (datetime.combine(_ANY_MONDAY, start) + timedelta(hours=hours)).time()


def _ensure_slot(
    ctx: Context,
    batch: Batch,
    actor: User,
    weekday: int,
    start: time,
    location: str,
    shifts: tuple[int, ...],
    tag: str | None = None,
) -> BatchSchedule | None:
    """One weekly slot: found by its ``tag`` (a clock slot, on whatever
    weekday it was first made) or by ``weekday`` (a fixed slot, clock slots
    left out so the two never stand in for each other), else created on
    ``weekday`` at the first start time the conflict guard accepts."""
    if tag is not None:
        existing = BatchSchedule.objects.filter(batch=batch, note__startswith=tag).first()
    else:
        existing = (
            BatchSchedule.objects.filter(batch=batch, weekday=weekday)
            .exclude(note__startswith=CLOCK_TAG_PREFIX)
            .first()
        )
    if existing is not None:
        ctx.found_existing("batch_schedule")
        return existing
    for shift in shifts:
        moved = _shift(start, shift)
        if moved is None:
            continue
        try:
            schedule = create_schedule(
                batch=batch,
                actor=actor,
                weekday=weekday,
                start_time=moved,
                end_time=_plus_hours(moved, CLASS_HOURS),
                timezone_name=TZ,
                location=location,
                note=tag or "",
            )
        except ScheduleConflictError:
            continue
        ctx.created("batch_schedule")
        if shift:
            ctx.out(
                f"slot {batch.code} {Weekday(weekday).label} moved to {moved:%H:%M} "
                f"({shift:+d}h) to avoid a clash"
            )
        return schedule
    ctx.out(f"warning: no clash-free slot for {batch.code} on {Weekday(weekday).label}")
    return None


def _window(
    ctx: Context, batch: Batch, start: date | None, end: date | None
) -> tuple[date, date] | None:
    """The window ``generate_sessions`` is asked for, clamped to what it takes.

    The service refuses a window wider than ``MAX_GENERATION_DAYS`` (366) —
    a mistyped date should not make ten thousand rows — and a batch on a
    database seeded months ago is wider than that: :func:`_redate` moves its
    ``end_date`` with the clock on every run while its ``start_date`` is
    pinned by its own first class, so the span grows a day per day of drift
    (three of the fifteen were past five hundred days on a clone re-run at
    day+400). A whole-range call would then raise ``ApplicationError`` and
    take the stage, and the nine stages behind it, with it. The *recent* end
    of the window is the one every screen reads — today's class, the term
    that is running — so a window too wide keeps its last 366 days and says
    so. ``None`` means there is no window at all: the batch's dates and the
    window asked for do not overlap, which ``generate_sessions`` also
    refuses.
    """
    first = max(start or batch.start_date, batch.start_date)
    last = min(end or batch.end_date, batch.end_date)
    if first > last:
        return None
    if (last - first).days > MAX_GENERATION_DAYS:
        first = last - timedelta(days=MAX_GENERATION_DAYS)
        ctx.out(
            f"classes {batch.code}: {MAX_GENERATION_DAYS} days is all one call may generate, "
            f"so the window is the most recent {first:%d %b %Y}..{last:%d %b %Y}"
        )
    return first, last


def _ensure_classes(
    ctx: Context,
    batch: Batch,
    actor: User,
    schedules: list[BatchSchedule],
    start: date | None = None,
    end: date | None = None,
    plan_from: date | None = None,
    force: bool = False,
) -> None:
    """Materialise the timetable and put the curriculum on it, counting what
    that made.

    ``generate_sessions`` skips classes that exist, but it records an audit
    row for every call, so a re-run would leave a trail of "generated 0"
    entries. A slot is generated across the whole window in one call, so a
    slot that has any class at all has all of them: generation runs only
    while one of ``schedules`` — the slots this stage put there — has none.
    "Found" counts only the classes on those slots, so an imported batch's
    own classes are not reported as this stage's.

    ``force`` overrides that guard, for the one caller whose *window* moves
    rather than its slots: when an extended imported batch is re-dated ten
    weeks past a later today, the three slots this stage gave it already
    carry the term that has just ended, "some slot has none" is false, and
    the ten weeks just bought would get no classes at all — a batch shown as
    active with an empty timetable in both directions, which is the one state
    this step promises. ``generate_sessions`` is idempotent by the
    ``(batch, date, start_time)`` constraint, so forcing it costs one audit
    row per extended batch on the runs that actually re-extend, and nothing
    on the runs that do not.

    The window is clamped to what the service will accept (:func:`_window`).

    ``plan_from`` narrows what the curriculum is put on (:func:`_plan_from`);
    without it the whole batch is planned by ``autoplan_batch``.
    """
    if not schedules:
        return
    made = {"created": 0, "skipped": 0, "on_holiday": 0}
    generate = force or any(
        not ClassSession.objects.filter(schedule=schedule).exists() for schedule in schedules
    )
    window = _window(ctx, batch, start, end) if generate else None
    if generate and window is not None:
        made = generate_sessions(batch=batch, actor=actor, start=window[0], end=window[1])
    elif generate:
        ctx.out(
            f"classes {batch.code}: nothing to generate — no window inside "
            f"{batch.start_date:%d %b %Y}..{batch.end_date:%d %b %Y}"
        )
    else:
        made["skipped"] = ClassSession.objects.filter(schedule__in=schedules).count()
    ctx.created("class_session", made["created"])
    ctx.found_existing("class_session", made["skipped"])
    already = ClassSession.objects.filter(batch=batch, planned_lesson__isnull=False).count()
    if plan_from is None:
        planned = autoplan_batch(batch=batch, actor=actor)["planned"]
    else:
        planned = _plan_from(batch, actor, plan_from)
    ctx.created("session_plan", planned)
    ctx.found_existing("session_plan", already)
    ctx.out(
        f"classes {batch.code}: {made['created']} generated, {made['skipped']} already there, "
        f"{made['on_holiday']} on holidays; {planned} lessons planned"
    )


def _plan_from(batch: Batch, actor: User, since: date) -> int:
    """Plan the classes from ``since`` on, oldest of *those* first.

    ``autoplan_batch`` walks every unplanned class in date order, which is
    right for a batch this stage generated end to end and wrong for an
    imported one: each imported course has exactly three published lessons,
    and an imported batch's three oldest unplanned classes are the ones the
    SITP workbook import made in May. The lessons landed there and the term
    that is actually running got none, so ``timeline_status`` read off a
    curriculum four months out of date. The same service underneath
    (``plan_session_topic``) — a different queue.
    """
    lessons = Lesson.objects.filter(
        module__course_id=batch.course_id, status=PublishStatus.PUBLISHED
    ).order_by("module__position", "position")
    # Only what is planned *inside this window* counts as spent. Handing one
    # lesson to two classes of the same term would be wrong; handing it to the
    # term after — which is what a batch extended a second time is — is the
    # course being taught again. Without this an extension at day+150 found
    # all three lessons spent on the term that had ended and left the term now
    # running with no curriculum at all, while a same-day re-run still plans
    # nothing, which is what keeps this idempotent.
    used = set(
        ClassSession.objects.filter(
            batch=batch, planned_lesson__isnull=False, session_date__gte=since
        ).values_list("planned_lesson_id", flat=True)
    )
    available = [lesson for lesson in lessons if lesson.pk not in used]
    sessions = (
        ClassSession.objects.filter(
            batch=batch, planned_lesson__isnull=True, session_date__gte=since
        )
        .exclude(status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED))
        .order_by("session_date", "start_time")
    )
    planned = 0
    for session, lesson in zip(sessions, available, strict=False):
        plan_session_topic(session=session, actor=actor, lesson=lesson)
        planned += 1
    return planned


def _free_today(ctx: Context, batch: Batch, wanted: time, shifts: tuple[int, ...]) -> time | None:
    """``wanted``, or the first shift of it that double-books nobody.

    ``create_schedule`` reads the diary before it writes a weekly slot
    (``find_conflicts``: the same batch, or the same trainer, in overlapping
    hours); ``create_session`` does not, and its only uniqueness is
    ``(batch, date, start_time)``. A trainer here teaches more than one batch
    — the headline one teaches three — and two of them can want the same two
    hours of the same day: a "started" one-off at 08:00 for one batch lands
    exactly on top of the generated 08:00 class of another. So the diary is
    read here, the way ``_ensure_slot`` lets the conflict guard arbitrate,
    and the shifts keep the class on the right side of now — earlier for one
    that has started, later for one still ahead. ``None`` means every
    candidate hour is taken, and the stage says so rather than writing a
    class that says the trainer was in two rooms at once.
    """
    booked: list[tuple[time, time]] = []
    if batch.trainer_id is not None:
        booked = list(
            ClassSession.objects.filter(trainer_id=batch.trainer_id, session_date=ctx.today)
            .exclude(status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED))
            .values_list("start_time", "end_time")
        )
    # The batch's own classes block by the unique constraint whoever teaches
    # them — including a slot whose trainer was frozen as somebody else.
    taken = set(
        ClassSession.objects.filter(batch=batch, session_date=ctx.today).values_list(
            "start_time", flat=True
        )
    )
    for shift in shifts:
        moved = _shift(wanted, shift)
        if moved is None or moved in taken:
            continue
        ends = _plus_hours(moved, CLASS_HOURS)
        if any(moved < until and ends > since for since, until in booked):
            continue
        return moved
    return None


def _ensure_today(ctx: Context, batch: Batch, actor: User, spec: BatchSpec) -> None:
    """Today's class where the timetable did not put one — the calendar
    marks today a holiday, or this is a re-run on a day the clock slot does
    not fall on: the one-off ``create_session`` the contract names.

    "A class that has started" is one whose start is at or before now; "a
    class later today" is one whose start is still ahead — a fixed 18:00
    slot that ended hours ago does not count.
    """
    if not (batch.start_date <= ctx.today <= batch.end_date):
        # ``ClassSession.clean`` refuses a class outside its batch's dates,
        # and a batch whose dates could not be re-dated (an archived one
        # whose trainer has left) can fall behind today. Nothing to add.
        ctx.out(
            f"classes {batch.code}: today is outside "
            f"{batch.start_date:%d %b %Y}..{batch.end_date:%d %b %Y}, no one-off class"
        )
        return
    wanted, shifts = _clock_time(ctx, spec)
    today = ClassSession.objects.filter(batch=batch, session_date=ctx.today)
    if shifts is SHIFTS_LATER:
        exists = today.filter(start_time__gt=ctx.now.time()).exists()
    else:
        exists = today.filter(start_time__lte=ctx.now.time()).exists()
    if exists:
        return
    free = _free_today(ctx, batch, wanted, shifts)
    if free is None:
        ctx.out(f"classes {batch.code}: no free two hours today for a one-off class")
        return
    try:
        create_session(
            batch=batch,
            actor=actor,
            session_date=ctx.today,
            start_time=free,
            end_time=_plus_hours(free, CLASS_HOURS),
            timezone_name=TZ,
            location=spec.location or "Lab 1",
            notes=ctx.note("Extra class outside the weekly timetable."),
        )
    except (ApplicationError, ValidationError) as exc:
        # A class already at that minute — two runs inside the five minutes
        # after midnight both want 00:05 — or any other state the model
        # refuses. One class is not worth the stages queued behind this one;
        # ``_ensure_renames`` has handled a refused service call this way
        # since the stage was written.
        ctx.out(f"classes {batch.code}: no one-off class today ({exc})")
        return
    ctx.created("class_session")
    ctx.out(f"classes {batch.code}: one-off class today at {free:%H:%M}")


# ---------------------------------------------------------------------------
# Enrolments
# ---------------------------------------------------------------------------


def _ensure_enrolments(ctx: Context, plan: Plan) -> None:
    by_batch: dict[str, list[Placement]] = {}
    for key, rows in plan.placements.items():
        by_batch.setdefault(key, []).extend(rows)
    for placement in plan.demo:
        by_batch.setdefault(placement.spec_key, []).append(placement)

    for spec in plan.specs:
        batch = plan.batches.get(spec.key)
        rows = by_batch.get(spec.key, [])
        if batch is None or not rows:
            continue
        actor = ctx.actor_for(spec.branch)
        existing = _existing_enrolments(batch)
        made = found = moved = 0
        for placement in rows:
            row = existing.get(placement.student.pk)
            if row is None:
                if not placement.student.user.is_active or not batch.is_enrollable:
                    # The service would refuse; said here so the count
                    # explains itself rather than the stage stopping.
                    why = "inactive student" if batch.is_enrollable else f"{batch.status} batch"
                    who = placement.student.student_id
                    # Counted under its own label: a run that silently placed
                    # nobody would otherwise print a finish table that looks
                    # exactly like a run that placed everybody.
                    ctx.found_existing("enrollment_skipped")
                    ctx.out(f"enrolment {batch.code}/{who}: skipped ({why})")
                    continue
                row = enrol_student(
                    student=placement.student,
                    batch=batch,
                    actor=actor,
                    status=placement.status,
                    note=ctx.note("Awaiting fee confirmation.")
                    if placement.status == EnrollmentStatus.PENDING
                    else "",
                )
                ctx.created("enrollment")
                plan.created_rows.append((row, placement))
                made += 1
            else:
                ctx.found_existing("enrollment")
                found += 1
            if placement.target and _move_enrolment(ctx, row, placement.target, actor):
                moved += 1
        ctx.out(f"enrolments {batch.code}: {made} created, {found} found, {moved} moved on")


def _existing_enrolments(batch: Batch) -> dict[Any, Enrollment]:
    """The latest enrolment per student on a batch — cancelled and transferred
    ones included, because a row this stage moved on is still its row."""
    rows: dict[Any, Enrollment] = {}
    for row in Enrollment.objects.filter(batch=batch).order_by("enrolled_at", "pk"):
        rows[row.student_id] = row
    return rows


def _move_enrolment(ctx: Context, row: Enrollment, target: str, actor: User) -> bool:
    """Suspend or cancel one enrolment, once."""
    if row.status != EnrollmentStatus.ACTIVE:
        # Already there, or somewhere else (completed by a cascade,
        # transferred): not this stage's row to move any more.
        ctx.found_existing("enrollment_status")
        return False
    note = {
        EnrollmentStatus.SUSPENDED: ctx.note("Fees overdue; suspended until the balance clears."),
        EnrollmentStatus.CANCELLED: ctx.note("Withdrew before the course ended."),
    }[target]
    set_enrollment_status(enrollment=row, target=target, actor=actor, note=note)
    ctx.created("enrollment_status")
    return True


# ---------------------------------------------------------------------------
# Statuses and the transfer
# ---------------------------------------------------------------------------


def _ensure_statuses(ctx: Context, plan: Plan) -> None:
    for spec in plan.specs:
        batch = plan.batches.get(spec.key)
        if batch is None:
            continue
        _walk_status(ctx, batch, spec.status, ctx.actor_for(spec.branch), spec.reason)


def _walk_status(ctx: Context, batch: Batch, target: str, actor: User, reason: str = "") -> None:
    """Move a batch along the transition table to ``target``, from wherever
    it is now — so a run that stopped half-way finishes the walk."""
    if batch.status == target:
        ctx.found_existing("batch_status")
        return
    path = STATUS_PATHS[target]
    position = path.index(batch.status) + 1 if batch.status in path else 0
    for step in path[position:]:
        note = ctx.note(reason) if step == BatchStatus.CANCELLED and reason else ""
        try:
            set_batch_status(batch=batch, target=step, actor=actor, note=note)
        except (ApplicationError, ValidationError) as exc:
            # A batch found somewhere this road does not pass through —
            # somebody cancelled one the spec wants completed — raises
            # ``TransitionError``, and a batch the model will not re-save
            # raises ``ValidationError``. Stop the walk, not the stage.
            ctx.out(f"batch {batch.code}: stopped at {batch.status} ({exc})")
            return
        ctx.created("batch_status")
    ctx.out(f"batch {batch.code}: now {batch.status}")


def _ensure_transfer(ctx: Context, plan: Plan) -> None:
    if plan.transfer is None:
        ctx.out("transfer: nobody to move")
        return
    student, from_key, to_key = plan.transfer
    source_batch, target_batch = plan.batches.get(from_key), plan.batches.get(to_key)
    if source_batch is None or target_batch is None:
        return
    source = (
        Enrollment.objects.filter(student=student, batch=source_batch)
        .order_by("-enrolled_at")
        .first()
    )
    if source is None:
        ctx.out(f"transfer: {student.student_id} never joined {source_batch.code}")
        return
    if source.status == EnrollmentStatus.TRANSFERRED:
        ctx.found_existing("enrollment_transfer")
        ctx.out(f"transfer {student.student_id} {source_batch.code}->{target_batch.code}: found")
        return
    moved = transfer_student(
        enrollment=source,
        target_batch=target_batch,
        actor=ctx.actor_for(MAIN),
        reason=ctx.note("Moved to the morning cohort at the student's request."),
    )
    ctx.created("enrollment_transfer")
    plan.transfer_rows = (source, moved)
    ctx.out(f"transfer {student.student_id} {source_batch.code}->{target_batch.code}: created")


# ---------------------------------------------------------------------------
# Making it look like it happened when it happened
# ---------------------------------------------------------------------------


def _backdate(ctx: Context, plan: Plan) -> None:
    """Only the rows this run created, each after its last service call, as
    the context's ``backdate`` contract requires."""
    latest = ctx.now - timedelta(minutes=30)

    # The enrolment dates first, batch by batch, because a batch cannot have
    # been created after the first student joined it and the old batches'
    # wide admissions window (:func:`_jitter`) reaches back further than the
    # four weeks below.
    dated: list[tuple[Enrollment, Placement, Batch, datetime]] = []
    opened_by: dict[Any, datetime] = {}
    for row, placement in plan.created_rows:
        batch = plan.batches[placement.spec_key]
        # The status walk may have completed or cancelled this row through
        # a cascade, on another instance; read what it is now.
        row.refresh_from_db()
        enrolled = _enrolled_at(ctx, batch, placement.jitter, latest)
        dated.append((row, placement, batch, enrolled))
        opened_by[batch.pk] = min(opened_by.get(batch.pk, enrolled), enrolled)

    for batch in plan.created_batches:
        # Opened for admissions four weeks before the first class — a week
        # ago, even for the batch that starts three weeks from now — or a day
        # before its earliest enrolment, whichever is further back.
        opened = min(ctx.at(batch.start_date - timedelta(days=28), 11, 0), latest)
        first_joined = opened_by.get(batch.pk)
        if first_joined is not None:
            opened = min(opened, first_joined - timedelta(days=1))
        ctx.backdate(batch, created_at=opened)

    for row, placement, batch, enrolled in dated:
        fields: dict[str, Any] = {
            "enrolled_at": enrolled,
            "created_at": enrolled,
            "status_changed_at": enrolled,
        }
        if row.status in (EnrollmentStatus.SUSPENDED, EnrollmentStatus.CANCELLED):
            if batch.status == BatchStatus.CANCELLED:
                # Cancelled with the batch, on the day it would have started.
                changed = max(enrolled + timedelta(days=1), ctx.at(batch.start_date, 16, 0))
            else:
                changed = enrolled + timedelta(days=placement.later)
            fields["status_changed_at"] = min(changed, latest)
        elif row.status == EnrollmentStatus.COMPLETED:
            finished = min(ctx.at(batch.end_date, 18, 0), latest)
            fields["status_changed_at"] = finished
            fields["completed_at"] = finished
        ctx.backdate(row, **fields)

    if plan.transfer_rows is not None:
        source, moved = plan.transfer_rows
        source.refresh_from_db()
        # A week in: long enough to know the cohort was wrong for them,
        # short enough that even the two-week-old batch shows it as history.
        when = min(source.enrolled_at + timedelta(days=7), latest)
        ctx.backdate(source, status_changed_at=when)
        ctx.backdate(moved, enrolled_at=when, created_at=when, status_changed_at=when)


def _enrolled_at(ctx: Context, batch: Batch, jitter: int, latest: datetime) -> datetime:
    """Around the batch start — a few days before or just after — and never
    after now, even for a batch that has not started yet."""
    anchor = min(batch.start_date, ctx.today)
    day = min(anchor + timedelta(days=jitter), ctx.today)
    return min(ctx.at(day, 10 + abs(jitter) % 7, 15), latest)


# ---------------------------------------------------------------------------
# The imported SITP batches
# ---------------------------------------------------------------------------


def _ensure_imported(ctx: Context, started_at: datetime) -> None:
    if not ctx.imported_batches:
        ctx.out("imported batches: none on this database")
        return
    for key, batch in ctx.imported_batches.items():
        actor = ctx.actor_for(batch.branch.code)
        if _keeps_running(key):
            _extend_imported(ctx, batch, actor)
        elif _stays_overrun(key):
            _leave_overrun(ctx, batch)
        else:
            _complete_imported(ctx, batch, actor, started_at)


def _mentions(key: str, fragments: tuple[str, ...]) -> bool:
    """Whether a batch key names one of ``fragments`` — as whole words, so
    ``group a`` matches ``… — Group A`` and not a future ``Group A2`` or
    ``Group AB``."""
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(fragment)}(?![a-z0-9])", key) for fragment in fragments
    )


def _keeps_running(key: str) -> bool:
    """Whether an imported batch is one of the tracks the institute kept."""
    return _mentions(key, SITP_EXTENDED)


def _stays_overrun(key: str) -> bool:
    """Whether an imported batch is the one left active past its end date."""
    return _mentions(key, SITP_OVERRUN)


def _leave_overrun(ctx: Context, batch: Batch) -> None:
    """Left exactly as the import made it — and counted, so the finish table
    shows that the decision was taken rather than the batch forgotten."""
    ctx.found_existing("batch_overrun")
    if batch.status == BatchStatus.ACTIVE and batch.end_date < ctx.today:
        ctx.out(
            f"imported {batch.code}: left active past {batch.end_date:%d %b %Y} on purpose "
            "— the only batch_overrun warning on the database"
        )
    else:
        ctx.out(
            f"imported {batch.code}: meant to be the batch_overrun warning, "
            f"but it is {batch.status} and ends {batch.end_date:%d %b %Y}"
        )


def _extend_imported(ctx: Context, batch: Batch, actor: User) -> None:
    if batch.status != BatchStatus.ACTIVE:
        ctx.out(f"imported {batch.code}: {batch.status}, not extended")
        return
    extended = False
    if batch.end_date >= ctx.today:
        ctx.found_existing("batch_extension")
        ctx.out(f"imported {batch.code}: already runs to {batch.end_date:%d %b}")
    else:
        try:
            update_batch(batch=batch, actor=actor, end_date=ctx.days_ahead(SITP_EXTENSION_DAYS))
        except (ApplicationError, ValidationError) as exc:
            # ``update_batch`` re-validates the whole batch, so an imported
            # batch whose @sitp trainer has been deactivated refuses the
            # extension. Left as found — it stays an overrun warning — and
            # refreshed, because the failed call mutated the instance.
            batch.refresh_from_db(fields=["end_date"])
            ctx.out(f"imported {batch.code}: not extended ({exc})")
            return
        ctx.created("batch_extension")
        extended = True
        ctx.out(f"imported {batch.code}: extended to {batch.end_date:%d %b}")
    location = "Online" if batch.delivery_mode == DeliveryMode.ONLINE else "Lab 2"
    schedules = [
        _ensure_slot(ctx, batch, actor, weekday, SITP_SLOT_START, location, SHIFTS)
        for weekday in SITP_SLOT_DAYS
    ]
    window_start = max(ctx.days_ago(SITP_BACKFILL_DAYS), batch.start_date)
    _ensure_classes(
        ctx,
        batch,
        actor,
        [s for s in schedules if s is not None],
        start=window_start,
        end=batch.end_date,
        # The curriculum belongs on the term that is running, not on the
        # classes the workbook import made in May.
        plan_from=window_start,
        # Forced exactly when the end date moved. The slots are the ones an
        # earlier run made, and they already carry that run's classes, so
        # the "some slot has none" guard is false — the ten weeks just
        # bought would be a batch shown as active with no class in either
        # direction, on every run more than seventy days after the first.
        force=extended,
    )


def _finish_cascade(ctx: Context, batch: Batch) -> None:
    """Re-date the completions of a batch that was already completed.

    The backdate below happens in the same breath as the status change and is
    keyed off the rows that moved during *this* run. An attempt killed between
    the two — a Ctrl-C, a failure in a stage behind this one, a crashed
    worker — leaves its seventy-odd enrolments stamped with the moment of that
    dead run, and no later run would ever go back for them: the batch is
    completed by then, so the early return above is all they get, and the
    "enrolments completed" trend carries a one-day spike of several hundred
    rows for good. Keyed off the *target* value instead of off the run, so it
    writes only what is not already right and converges to nothing.
    """
    finished = ctx.at(batch.end_date, 18, 0)
    repaired = (
        Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.COMPLETED)
        .exclude(completed_at=finished)
        .update(status_changed_at=finished, completed_at=finished)
    )
    if repaired:
        ctx.out(
            f"imported {batch.code}: {repaired} completions re-dated to "
            f"{batch.end_date:%d %b %Y}, the day the programme ended"
        )


def _complete_imported(ctx: Context, batch: Batch, actor: User, started_at: datetime) -> None:
    if batch.status in (BatchStatus.COMPLETED, BatchStatus.ARCHIVED):
        ctx.found_existing("batch_status")
        _finish_cascade(ctx, batch)
        return
    if batch.status != BatchStatus.ACTIVE:
        ctx.out(f"imported {batch.code}: {batch.status}, left alone")
        return
    set_batch_status(
        batch=batch,
        target=BatchStatus.COMPLETED,
        actor=actor,
        note=ctx.note("SITP summer programme ended."),
    )
    ctx.created("batch_status")
    # The cascade stamped every completion with this minute. The programme
    # ended on the batch's end date, so that is when the chart should say.
    finished = ctx.at(batch.end_date, 18, 0)
    cascaded = Enrollment.objects.filter(
        batch=batch, status=EnrollmentStatus.COMPLETED, status_changed_at__gte=started_at
    )
    # One statement rather than ``ctx.backdate`` per row: the twelve batches
    # carry 858 enrolments between them, and a row-at-a-time backdate spent
    # two of this stage's five seconds on 1,716 queries whose values nothing
    # reads back. Exactly the same sanctioned bypass ``Context.backdate`` is —
    # the named columns only, no ``save()``, no ``auto_now``, no signal — one
    # queryset wide. A ``backdate_all(queryset, **fields)`` on the context
    # would put this back inside the framework where it belongs.
    count = cascaded.update(status_changed_at=finished, completed_at=finished)
    ctx.out(f"imported {batch.code}: completed, {count} enrolments completed with it")


# ---------------------------------------------------------------------------
# The junk staging batches
# ---------------------------------------------------------------------------


#: The month a renamed batch should be dated into, as its new name states it:
#: ``"… — Aug 2026"``. Read from a fixed string, so the alignment is to an
#: absolute month and does not move with ``ctx.today``.
_NAME_MONTH = re.compile(r"—\s*([A-Za-z]{3})\s+(\d{4})\s*$")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _ensure_renames(ctx: Context) -> None:
    """Rename the hand-made staging batches and date them into their month.

    Driven from ``BATCH_RENAMES`` rather than from ``ctx.batches``, so that a
    batch renamed on an earlier run is still *checked* on this one: the name
    is gone from the keys by then, and a loop over the old keys alone could
    never finish a job it had half done.
    """
    for old_key, new_name in BATCH_RENAMES.items():
        batch = ctx.batches.get(old_key)
        renaming = batch is not None
        if not renaming:
            batch = ctx.batches.get(batch_key(new_name))
            if batch is None:
                continue
            ctx.found_existing("batch_rename")
        fields: dict[str, Any] = {"name": new_name} if renaming else {}
        fields.update(_aligned_dates(ctx, batch, new_name))
        if not fields:
            ctx.found_existing("batch_realign")
            continue
        try:
            update_batch(batch=batch, actor=ctx.actor_for(batch.branch.code), **fields)
        except (ApplicationError, ValidationError) as exc:
            # Somebody else's row in a state the model refuses to re-validate
            # (an inactive trainer, say). Not worth stopping the stage over —
            # but the failed call already applied the fields to the instance,
            # which the stages after this one read out of ``ctx.batches``.
            batch.refresh_from_db(fields=["name", "start_date", "end_date"])
            ctx.out(f"rename {batch.code} {old_key!r}: refused ({exc})")
            continue
        if renaming:
            ctx.created("batch_rename")
            del ctx.batches[old_key]
            ctx.batches[batch_key(new_name)] = batch
            ctx.out(f"rename {batch.code}: {old_key!r} -> {new_name!r}")
        if "start_date" in fields:
            ctx.created("batch_realign")
            ctx.out(
                f"rename {batch.code}: dated {batch.start_date:%d %b %Y}.."
                f"{batch.end_date:%d %b %Y} to match the name"
            )
        else:
            # Renamed and deliberately left where it is: ``_aligned_dates``
            # found a class that pins the range and named it. Counted all the
            # same, so four renames always account for four realign rows and
            # the finish table does not go quiet about the ones it skipped.
            ctx.found_existing("batch_realign")


def _aligned_dates(ctx: Context, batch: Batch, new_name: str) -> dict[str, date]:
    """The dates that put a renamed batch in the month its new name claims.

    Two rules, both from the classes the batch already has. ``start_date``
    moves to the same day of the month the name names — and only if no class
    falls before it, because a class outside its batch's dates is what
    ``ClassSession.clean`` refuses and ``update_batch`` never checks.
    ``end_date`` keeps the batch's length, unless that would land it before
    the last class, in which case the last class is the floor. So no class is
    ever left outside its batch, and a batch whose classes cannot be
    reconciled with its name is left dated as it is, with the class that pins
    it named in the log.

    ``{}`` means nothing to do — no month in the name, or the dates already
    say what the name says.
    """
    match = _NAME_MONTH.search(new_name)
    if match is None or match[1].lower() not in _MONTHS:
        return {}
    year, month = int(match[2]), _MONTHS.index(match[1].lower()) + 1
    day = min(batch.start_date.day, calendar.monthrange(year, month)[1])
    start = date(year, month, day)
    end = start + (batch.end_date - batch.start_date)
    classes = ClassSession.objects.filter(batch=batch).aggregate(
        first=Min("session_date"), last=Max("session_date")
    )
    if classes["first"] is not None and start > classes["first"]:
        ctx.out(
            f"rename {batch.code}: dated {batch.start_date:%b %Y} and left there; "
            f"its first class is {classes['first']:%d %b %Y}"
        )
        return {}
    end = max(end, classes["last"] or end)
    if (start, end) == (batch.start_date, batch.end_date):
        return {}
    return {"start_date": start, "end_date": end}


# ---------------------------------------------------------------------------
# Departures
# ---------------------------------------------------------------------------


def _ensure_departures(ctx: Context) -> None:
    """The roster's inactive student and trainer leave — last, so that they
    were enrolled and given a batch first and the inactive filters show
    accounts with a history."""
    for code, profiles in list(ctx.students.items()) + list(ctx.trainers.items()):
        for profile in profiles:
            if not _flag(ctx, profile.user, "inactive"):
                continue
            user = profile.user
            if not user.is_active:
                ctx.found_existing("user_deactivation")
                ctx.out(f"departure {user.email}: already inactive")
                continue
            set_user_active(
                user=user,
                is_active=False,
                actor=ctx.actor_for(code),
                reason=ctx.note("Left the institute; account closed by the centre."),
            )
            ctx.created("user_deactivation")
            ctx.out(f"departure {user.email}: deactivated")
