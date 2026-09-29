"""Stage 6 — the classes as they were held: registers, reports, progress.

Stage 4 generated every class a timetable predicts; this stage makes the
ones that have already happened look *held*, through the same services a
trainer's phone would call at the end of each class. Scope: every showcase
batch's past classes (``ctx.showcase_batches``), and the **last 21 days** of
the four extended SITP batches (``ctx.imported_batches`` still ending on or
after today). The twelve completed SITP batches keep their imported history
untouched. "Past" means the class has ended: any earlier date, or today with
``ends_at`` behind the clock.

Creates, idempotently:

* **Session statuses** (``apps.sessions.services``): one past class of the
  weekend Python batch *cancelled* with a reason; one future class of the
  evening AWS batch *rescheduled* a day on through ``reschedule_session``;
  every showcase class under way right now *in_progress* (today's started
  class of the headline batch; the later one stays scheduled). Each is keyed
  by a ``[showcase][cancel/…]``/``[resched/…]`` tag in ``cancellation_reason``
  or by the status itself.
* **Registers** (``apps.attendance.services.mark_attendance``) on every held
  class, as the trainer who took it, rotated present/absent/late/excused
  with notes on the misses; the register auto-completes the class. About
  8 % of held classes are completed through ``set_session_status`` with **no
  register** (``registers_outstanding``). Ten absent marks are turned to
  present through ``correct_record`` with a reason, so ``AttendanceCorrection``
  history exists. Attendance is tuned per batch (:data:`TUNING`) so roughly
  six batches in ten sit above the 75 % rule and the rest below — two of them
  well below — and ~15 % of each batch's students are chronic absentees, so
  the risk rule flags people rather than everybody.
* **Topics** (``record_session_topic``) on every showcase class this stage
  completes, paced per batch so ``timeline_progress`` reads *ahead*,
  *on_track* and *behind* on different batches rather than "ahead" on all of
  them (nine lessons in a forty-class batch would otherwise all be covered by
  week three). A lesson runs over several classes; every seventh class with
  nothing new is a *skipped* revision class.
* **Daily status reports** (``apps.dsr.services``): ``start_dsr`` as the
  session's trainer, ``submit_dsr``, then ``review_dsr`` as the centre's
  **manager** — approved for most, and by recency: the six newest left
  *draft*, four *submitted*, four *under_review*, three *revision_required*
  and three *rejected*, both of the latter with comments. About 10 % of held
  classes get **no report** (the overdue-DSR warning). ``submitted_at`` and
  ``reviewed_at`` are backdated to the evening of the class.
* **Learning state** (``touch_lesson``/``set_lesson_completion``) for
  enrolments that ``grants_access()`` today, on the showcase batches and the
  four extended SITP batches alike: the headline student is 70 % through
  the DevOps course with the next lesson opened last night, others range
  from nothing opened through 10 % to 100 % around the calendar's line (see
  below), timestamps spread from enrolment to now; bookmarks and notes
  (``apps.learning.services``) for the headline student and a few
  classmates.
* **Trainer requirements** (``apps.requirements.services``): four raised by
  trainers with future ``needed_by`` — two *open* (one on the headline
  batch), one *fulfilled* by a named trainer, one *closed* — with replies
  from the managers and an admin.

Idempotent by class (a completed class is found, never re-held), by
``(session, enrolment)`` for marks, by the correction reason's tag, by
session for reports (one per class), by ``(enrolment, lesson)`` for progress,
bookmarks and notes, and by title plus a ``[showcase][req/…]`` tag for
requirements. Every draw is made from a generator seeded by the row's
**natural key** (batch name, class date and time; student id) rather than
from ``ctx.rng`` in sequence, so a run on a later day — when more classes
have become "past" — decides exactly the same about the classes an earlier
run already held.

Risk recomputes are coalesced
-----------------------------
Every register and every correction defers a risk recompute per student to
commit (``apps.performance.tasks.schedule_recompute``). Its debounce assumes
a worker and a shared cache: under eager Celery the task runs at once and
clears its own key, and under the local-memory cache the settings give a
test run the pending keys are culled once three hundred exist — so six
thousand marks would mean thousands of ``student_performance`` runs in the
on-commit phase, two minutes of it, most of them repeats. This stage
therefore takes the register services' own deferred callbacks off the
connection as soon as each service returns (:func:`_drop_recompute_hooks`
— only those two closures, by module and name; the services' other hooks,
the Student 360 cache bumps, stay) and registers one callback of its own,
last, that schedules exactly one recompute per student on a register. With
a real worker that is one task per student, which is what the debounce
would have done anyway. It relies on ``connection.run_on_commit`` being the
list Django's own ``captureOnCommitCallbacks`` reads, which is the same
contract the test tooling stands on.

Progress and risk are shaped together
-------------------------------------
The risk engine reads course progress against a straight-line expectation
from the batch's dates (``apps.performance.engine._expected_progress_percent``)
and flags a student more than fifteen points behind it, critical past
twenty-two. So the lesson state here is drawn *around* that line: most
students within a dozen points of it, the chronic absentees of the register
well behind it (some having opened nothing), a few in the warning band, a
few finished — and the headline student seventy per cent through, ahead of
his batch. Risk levels then differ per student for reasons a reviewer can
read off the register and the progress screen, rather than two thirds of
the institute showing critical because everybody's progress was random.

Leaves in ``ctx``: nothing new.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import (
    COUNTS_AS_PRESENT,
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceStatus,
)
from apps.attendance.services import REGISTERABLE_STATUSES, correct_record, mark_attendance
from apps.batches.models import Batch, BatchStatus
from apps.courses.models import Lesson, PublishStatus
from apps.dsr.models import DSR, DSRStatus
from apps.dsr.services import review_dsr, start_dsr, submit_dsr
from apps.enrollments.models import (
    ACCESS_GRANTING_STATUSES,
    Enrollment,
    EnrollmentStatus,
    LessonProgress,
)
from apps.enrollments.services import set_lesson_completion, touch_lesson
from apps.learning.models import LessonBookmark, LessonNote
from apps.learning.services import set_bookmark, set_note
from apps.performance import tasks as risk_tasks
from apps.requirements.models import RequirementReply, RequirementStatus, TrainerRequirement
from apps.requirements.services import close_requirement, raise_requirement, reply_to_requirement
from apps.sessions.models import ClassSession, SessionStatus, TopicStatus
from apps.sessions.services import (
    record_session_topic,
    reschedule_session,
    set_session_status,
)

from ..context import RUN_SEED, Context, batch_key
from ..roster import DOMAIN, MAIN, PUNE
from .s04_batches import SPECS

STAGE = "academics"

#: How far back the extended SITP batches are held: stage 4 backfilled their
#: classes over the same window, so this is every class it made for them.
SITP_WINDOW_DAYS = 21

#: Held classes left without a register / without a report, beyond the one
#: per batch that is always left (positions below), so the warnings strip
#: has something on every batch and the totals land near 8 % and 10 %.
NO_REGISTER_SHARE = 0.05
NO_DSR_SHARE = 0.07
#: Position (in date order) of the class in every batch that is always left
#: without a register, and the one always left without a report.
NO_REGISTER_POSITION = 3
NO_DSR_POSITION = 1

#: Chronic absentees: this share of each batch's students, present this often.
CHRONIC_SHARE = 0.15
CHRONIC_PRESENT = 0.40
#: A suspended student is on the register but rarely in the room.
SUSPENDED_PRESENT = 0.20
LATE_SHARE = 0.12
EXCUSED_SHARE = 0.15

#: Absent marks turned to present with a reason, per batch: the headline
#: batch and Pune's morning MERN cohort, so both managers see history.
CORRECTIONS: dict[str, int] = {"a2": 6, "pa1": 4}

#: The newest reports, by class recency, in the states the manager's queue
#: and the trainer's banner need. Everything older is approved.
RECENT_DSR_STATES: tuple[tuple[str, int], ...] = (
    (DSRStatus.DRAFT, 6),
    (DSRStatus.SUBMITTED, 4),
    (DSRStatus.UNDER_REVIEW, 4),
    (DSRStatus.REVISION_REQUIRED, 3),
    (DSRStatus.REJECTED, 3),
)

#: Every seventh class with no new lesson is a revision class: topic skipped.
REVISION_EVERY = 7

#: The on-commit hooks this stage takes over: the register services' own
#: deferred recompute closures, named by module and enclosing function so
#: nothing else those services defer is touched.
RECOMPUTE_HOOK_MODULE = "apps.attendance.services"
RECOMPUTE_HOOK_OWNERS = ("mark_attendance", "correct_record")

#: The headline student's progress through the course he is walked through.
HEADLINE_FRACTION = 0.70
#: How lesson progress sits against the calendar's expected percent (as a
#: fraction of the course): most students inside the rule's fifteen-point
#: band, the chronic absentees well past the critical line (22.5 points),
#: a few in between. Shares are of the non-chronic students.
ON_TRACK_SPREAD = (-0.12, 0.15)
WARNING_BEHIND = (0.16, 0.22)
CHRONIC_BEHIND = (0.28, 0.45)
WARNING_SHARE = 0.10
FINISHED_SHARE = 0.06
NOTHING_OPENED_SHARE = 0.05
#: A chronic absentee's progress: nothing opened, the first tenth, or well
#: behind the line — a third each.
CHRONIC_NOTHING = 0.34
CHRONIC_TENTH = 0.67
#: Which of the batch spec keys carry the cancelled/rescheduled class.
CANCEL_KEY = "a3"
RESCHEDULE_KEY = "a1"
RESCHEDULE_MIN_DAYS_AHEAD = 7


@dataclass(frozen=True)
class Tuning:
    """Per batch: the attendance share to aim for (of counted marks), and the
    timeline variance wanted against the calendar (percent points; the
    reports' thresholds are ±15)."""

    attendance: float
    variance: int = 0


#: Keyed by stage 4's spec key. Seven of eleven sit above 75 %; the demo
#: trainer's weekend batch and Pune's evening analytics cohort are the ones
#: clearly at risk. Variance: the flagship batches on track, the internship
#: and the analytics cohort ahead, the weekend Python and Ansible ones behind.
TUNING: dict[str, Tuning] = {
    "a1": Tuning(0.78, 0),
    "a2": Tuning(0.83, 0),
    "a3": Tuning(0.64, -25),
    "a4": Tuning(0.87, 20),
    "c1": Tuning(0.81, 0),
    "c2": Tuning(0.68, 0),
    "x1": Tuning(0.78, 0),
    "d1": Tuning(0.50, -20),
    "pa1": Tuning(0.80, 0),
    "pa2": Tuning(0.54, 20),
    "pc1": Tuning(0.82, 0),
}
DEFAULT_TUNING = Tuning(0.74, 0)
#: The four extended SITP tracks, in key order: two above the line, two below.
IMPORTED_TUNING: tuple[Tuning, ...] = (Tuning(0.84), Tuning(0.62), Tuning(0.79), Tuning(0.71))

LATE_NOTES = (
    "Came in fifteen minutes late — traffic on Tonk Road.",
    "Joined after the first exercise; bus was late.",
    "Late by ten minutes, informed on the group.",
    "Arrived late from the placement briefing.",
)
ABSENT_NOTES = (
    "",
    "",
    "No message from the student.",
    "Called home; will attend the make-up class.",
    "Missed the second class this week — counsellor informed.",
)
EXCUSED_NOTES = (
    "Informed in advance: family function.",
    "Medical leave, certificate shared on WhatsApp.",
    "College exam today; will cover the lab from the recording.",
    "Away for a campus interview.",
)

TEACHING_NOTES = (
    "Covered {lesson} end to end with a hands-on lab; most of the class finished the "
    "exercise before the break.",
    "Walked through {lesson} on the board first, then everybody built it on their own "
    "machines. Good questions from the back row.",
    "{lesson}: slower than planned — three students had to reinstall the tooling, so "
    "the last twenty minutes became a troubleshooting session.",
    "Revised yesterday's material for ten minutes, then {lesson}. Assigned the practice "
    "set on the LMS for tomorrow.",
    "{lesson} went well; paired the stronger students with the ones who missed Monday.",
)
REVISION_NOTES = (
    "Revision and doubt-clearing class: went back over the week's labs and took a short "
    "verbal quiz.",
    "Practice session: the students worked through the exercise sheet while I went round the room.",
)
ISSUES = (
    "",
    "",
    "",
    "Projector in the lab flickered for the first ten minutes.",
    "Wi-Fi dropped twice during the online segment; switched to the hotspot.",
    "Two lab machines still have the old package versions.",
)
CONCERNS = (
    "",
    "",
    "{name} is struggling with the basics — arranged a doubt session on Saturday.",
    "{name} has missed three classes in a row; counsellor to call the guardian.",
    "{name} asked for extra practice material; shared the reference sheet.",
)
REVIEW_COMMENTS: dict[str, tuple[str, ...]] = {
    DSRStatus.APPROVED: ("", "", "Good detail, thanks.", "Noted — keep the pace."),
    DSRStatus.REVISION_REQUIRED: (
        "The present count does not match the register — please reconcile and resubmit.",
        "Add what was assigned for homework; the students' section is empty.",
        "Name the students you flagged so the counsellor can follow up.",
    ),
    DSRStatus.REJECTED: (
        "This is the previous class's report copied over — please write today's.",
        "The class is marked as held but the register says it was cancelled. Redo.",
        "Topic and times do not match the timetable for this class.",
    ),
}

#: Notes the headline student left on the course he is walked through.
HEADLINE_BOOKMARKS: tuple[tuple[int, str], ...] = (
    (1, "Revise the Dockerfile layering example before the lab test."),
    (4, "Ask sir about rolling updates vs recreate."),
)
HEADLINE_NOTES: tuple[tuple[int, str], ...] = (
    (
        0,
        "Key points:\n- images are immutable, containers are not\n- `docker ps -a` shows "
        "the stopped ones too\n- clean up with `docker system prune` (careful!)",
    ),
    (2, "Volumes vs bind mounts — bind mount for dev, named volume for the DB. Try both."),
)
CLASSMATE_BOOKMARK_LESSON = 2
CLASSMATE_NOTE = "Practice this one again before Friday's test."


@dataclass(frozen=True)
class RequirementSpec:
    """One requirement, as the roster would have raised it. ``raiser`` is a
    trainer's roster local part; ``replies`` are ``(local part, message)`` of
    staff; ``fulfilled_by`` a trainer's local part for the *fulfilled*
    outcome; ``closer`` who settles it. ``age`` days ago it was raised."""

    key: str
    raiser: str
    branch: str
    title: str
    details: str
    needed_in: int
    outcome: str  # open / fulfilled / closed
    age: int
    batch: str | None = None
    replies: tuple[tuple[str, str], ...] = ()
    fulfilled_by: str | None = None
    closer: str | None = None
    closing_note: str = ""


REQUIREMENTS: tuple[RequirementSpec, ...] = (
    RequirementSpec(
        "projector-lab1",
        "trainer",
        MAIN,
        "Projector in Lab 1 flickers during the afternoon slot",
        "It cuts out for a few seconds every couple of minutes once the room warms up. "
        "Fine in the morning. Needs the bulb or the cable looked at before the weekend batch.",
        needed_in=5,
        outcome=RequirementStatus.OPEN,
        age=3,
        replies=(("manager", "Raised with the vendor; a replacement bulb arrives Thursday."),),
    ),
    RequirementSpec(
        "k8s-vms",
        "trainer",
        MAIN,
        "Three more Ubuntu VMs for the Kubernetes lab",
        "The cluster exercise needs one control plane and two workers per pair; with "
        "twenty-seven students we are three machines short on the lab host.",
        needed_in=10,
        outcome=RequirementStatus.OPEN,
        age=5,
        batch="a2",
        replies=(
            ("manager", "Checking with IT whether the lab host has the memory for it."),
            ("admin", "Approved — IT will provision the three VMs by Monday."),
        ),
    ),
    RequirementSpec(
        "rhcsa-cover",
        "trainer",
        MAIN,
        "Cover for Saturday's RHCSA class",
        "I am at the Udaipur college drive on Saturday. Somebody comfortable with "
        "LVM and the storage lab, please — that is where the batch is.",
        needed_in=2,
        outcome=RequirementStatus.FULFILLED,
        age=6,
        replies=(("manager", "Rohit has the morning free; confirming with him."),),
        fulfilled_by="rohit.kumawat",
        closer="manager",
        closing_note="Rohit took the class; storage lab completed.",
    ),
    RequirementSpec(
        "mongo-credits",
        "ankit.kulkarni",
        PUNE,
        "MongoDB Atlas credits for the MERN project week",
        "The free tier throttles once every pair deploys; a small credit pack would "
        "keep the project week from stalling on connection limits.",
        needed_in=21,
        outcome=RequirementStatus.CLOSED,
        age=8,
        replies=(
            ("manager.pune", "Let us try the free tier with fewer clusters first."),
            ("ankit.kulkarni", "Fine for now — one shared cluster per four students."),
        ),
        closer="manager.pune",
        closing_note="Using the free tier for now; revisit if the project cohort grows.",
    ),
)


# ---------------------------------------------------------------------------
# What the stage works on
# ---------------------------------------------------------------------------


@dataclass
class Held:
    """One past class in scope, with everything decided about it up front."""

    key: str
    batch: Batch
    session: ClassSession
    imported: bool
    register: bool
    report: bool


@dataclass
class Scope:
    """The batches in scope, their rosters, and every held class in date order."""

    batches: list[tuple[str, Batch, bool]] = field(default_factory=list)
    by_spec: dict[str, Batch] = field(default_factory=dict)
    tuning: dict[str, Tuning] = field(default_factory=dict)
    rosters: dict[str, list[Enrollment]] = field(default_factory=dict)
    chronic: dict[str, set[Any]] = field(default_factory=dict)
    held: list[Held] = field(default_factory=list)
    lessons: dict[Any, list[Lesson]] = field(default_factory=dict)
    #: Every enrolment whose deferred risk recompute this stage took over
    #: from a register service, to schedule once at the end.
    recompute: set[Any] = field(default_factory=set)


def _seed(*parts: Any) -> random.Random:
    """A generator for one row, from its natural key — see the module docstring."""
    return random.Random(":".join([str(RUN_SEED), STAGE, *(str(p) for p in parts)]))  # noqa: S311


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    if not ctx.showcase_batches:
        raise RuntimeError("No showcase batches yet: run the batches stage first.")

    scope = _timed(ctx, "scope", lambda: _scope(ctx))
    _timed(ctx, "statuses", lambda: _ensure_statuses(ctx, scope))
    _timed(ctx, "held classes", lambda: _find_held(ctx, scope))
    _timed(ctx, "registers", lambda: _ensure_registers(ctx, scope))
    _timed(ctx, "corrections", lambda: _ensure_corrections(ctx, scope))
    _timed(ctx, "topics", lambda: _ensure_topics(ctx, scope))
    _timed(ctx, "reports", lambda: _ensure_reports(ctx, scope))
    _timed(ctx, "learning", lambda: _ensure_learning(ctx, scope))
    _timed(ctx, "requirements", lambda: _ensure_requirements(ctx, scope))
    _release_recomputes(ctx, scope)


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> Any:
    started = perf_counter()
    result = step()
    ctx.out(f"academics/{what}: {perf_counter() - started:.1f}s")
    return result


def _scope(ctx: Context) -> Scope:
    scope = Scope()
    names = {batch_key(spec.name): spec.key for spec in SPECS}
    for key, batch in ctx.showcase_batches.items():
        if batch.status == BatchStatus.CANCELLED:
            continue
        spec_key = names.get(key)
        if spec_key is not None:
            scope.by_spec[spec_key] = batch
        scope.tuning[key] = TUNING.get(spec_key or "", DEFAULT_TUNING)
        scope.batches.append((key, batch, False))

    extended = sorted(
        (key, batch)
        for key, batch in ctx.imported_batches.items()
        if batch.end_date >= ctx.today and batch.status == BatchStatus.ACTIVE
    )
    if not ctx.imported_batches:
        ctx.out("imported batches: none on this database")
    elif not extended:
        ctx.out("imported batches: none still running")
    for index, (key, batch) in enumerate(extended):
        scope.tuning[key] = IMPORTED_TUNING[index % len(IMPORTED_TUNING)]
        scope.batches.append((key, batch, True))

    for key, batch, _imported in scope.batches:
        roster = list(
            Enrollment.objects.filter(batch=batch, status__in=REGISTERABLE_STATUSES)
            .select_related("student__user")
            .order_by("student__student_id")
        )
        scope.rosters[key] = roster
        draw = _seed("absentees", key)
        ids = [row.pk for row in roster]
        scope.chronic[key] = set(draw.sample(ids, k=round(len(ids) * CHRONIC_SHARE)))
        if batch.course_id not in scope.lessons:
            scope.lessons[batch.course_id] = list(
                Lesson.objects.filter(
                    module__course_id=batch.course_id,
                    module__status=PublishStatus.PUBLISHED,
                    status=PublishStatus.PUBLISHED,
                )
                .select_related("module")
                .order_by("module__position", "position")
            )
    return scope


def _ended(ctx: Context, session: ClassSession) -> bool:
    return session.session_date < ctx.today or session.ends_at <= ctx.now


def _under_way(ctx: Context, session: ClassSession) -> bool:
    return session.session_date == ctx.today and session.starts_at <= ctx.now < session.ends_at


def _trainer_user(ctx: Context, session: ClassSession) -> User:
    """Who takes the register and writes the report: the trainer frozen on the
    class, else the centre's admin for a class nobody is on record for."""
    if session.trainer_id and session.trainer.user_id:
        return session.trainer.user
    return ctx.actor_for(session.batch.branch.code)


def _reviewer(ctx: Context, batch: Batch) -> User:
    """The centre's manager; the admin where the centre has none. Never a
    trainer — a trainer-role account may not review its own report."""
    return ctx.managers.get(batch.branch.code) or ctx.actor_for(batch.branch.code)


# ---------------------------------------------------------------------------
# Session statuses: cancelled, rescheduled, in progress
# ---------------------------------------------------------------------------


def _ensure_statuses(ctx: Context, scope: Scope) -> None:
    _ensure_cancelled(ctx, scope)
    _ensure_rescheduled(ctx, scope)
    _ensure_in_progress(ctx, scope)


def _ensure_cancelled(ctx: Context, scope: Scope) -> None:
    """One past class that did not happen, before the registers pass so it is
    never held. Found by its tag; otherwise the third most recent past
    scheduled class of the weekend Python batch."""
    batch = scope.by_spec.get(CANCEL_KEY)
    if batch is None:
        return
    tag = ctx.tag(f"cancel/{CANCEL_KEY}")
    if ClassSession.objects.filter(
        batch=batch, status=SessionStatus.CANCELLED, cancellation_reason__startswith=tag
    ).exists():
        ctx.found_existing("session_cancelled")
        ctx.out(f"cancelled class {batch.code}: found")
        return
    past = list(
        ClassSession.objects.filter(
            batch=batch, status=SessionStatus.SCHEDULED, session_date__lt=ctx.today
        ).order_by("-session_date", "-start_time")[:3]
    )
    if not past:
        ctx.out(f"cancelled class {batch.code}: no past class to cancel")
        return
    session = past[-1]
    set_session_status(
        session=session,
        target=SessionStatus.CANCELLED,
        actor=ctx.actor_for(batch.branch.code),
        reason=ctx.tag(f"cancel/{CANCEL_KEY}", "Trainer unwell; covered in the make-up slot."),
    )
    ctx.created("session_cancelled")
    ctx.out(f"cancelled class {batch.code} on {session.session_date:%d %b}: created")


def _ensure_rescheduled(ctx: Context, scope: Scope) -> None:
    """One future class moved a day on, the original kept as ``rescheduled``."""
    batch = scope.by_spec.get(RESCHEDULE_KEY)
    if batch is None:
        return
    tag = ctx.tag(f"resched/{RESCHEDULE_KEY}")
    if ClassSession.objects.filter(
        batch=batch, status=SessionStatus.RESCHEDULED, cancellation_reason__startswith=tag
    ).exists():
        ctx.found_existing("session_rescheduled")
        ctx.out(f"rescheduled class {batch.code}: found")
        return
    session = (
        ClassSession.objects.filter(
            batch=batch,
            status=SessionStatus.SCHEDULED,
            session_date__gte=ctx.days_ahead(RESCHEDULE_MIN_DAYS_AHEAD),
        )
        .order_by("session_date", "start_time")
        .first()
    )
    if session is None:
        ctx.out(f"rescheduled class {batch.code}: no future class to move")
        return
    # The next free day at the same time, inside the batch: the unique
    # constraint on (batch, date, start) is the arbiter of "free".
    for days in range(1, 8):
        new_date = session.session_date + timedelta(days=days)
        if new_date > batch.end_date:
            break
        if ClassSession.objects.filter(
            batch=batch, session_date=new_date, start_time=session.start_time
        ).exists():
            continue
        reschedule_session(
            session=session,
            actor=ctx.actor_for(batch.branch.code),
            new_date=new_date,
            new_start=session.start_time,
            new_end=session.end_time,
            reason=ctx.tag(
                f"resched/{RESCHEDULE_KEY}", "Lab 2 booked for the placement drive; moved a day."
            ),
        )
        ctx.created("session_rescheduled")
        ctx.out(
            f"rescheduled class {batch.code} {session.session_date:%d %b} -> "
            f"{new_date:%d %b}: created"
        )
        return
    ctx.out(f"rescheduled class {batch.code}: no free day within a week")


def _ensure_in_progress(ctx: Context, scope: Scope) -> None:
    """Every showcase class under way right now. Today's started class of the
    headline batch is the one the contract names; a fixed slot that happens
    to be running is treated the same, because it is."""
    for _key, batch, imported in scope.batches:
        if imported:
            continue
        for session in ClassSession.objects.filter(
            batch=batch, session_date=ctx.today
        ).select_related("trainer__user", "batch__branch"):
            if not _under_way(ctx, session):
                continue
            if session.status == SessionStatus.IN_PROGRESS:
                ctx.found_existing("session_in_progress")
                ctx.out(f"class under way {batch.code} {session.start_time:%H:%M}: found")
            elif session.status == SessionStatus.SCHEDULED:
                set_session_status(
                    session=session,
                    target=SessionStatus.IN_PROGRESS,
                    actor=_trainer_user(ctx, session),
                )
                ctx.created("session_in_progress")
                ctx.out(f"class under way {batch.code} {session.start_time:%H:%M}: created")


# ---------------------------------------------------------------------------
# The held classes
# ---------------------------------------------------------------------------


def _find_held(ctx: Context, scope: Scope) -> None:
    for key, batch, imported in scope.batches:
        rows = ClassSession.objects.filter(batch=batch, session_date__lte=ctx.today)
        if imported:
            rows = rows.filter(session_date__gte=ctx.days_ago(SITP_WINDOW_DAYS))
        rows = rows.exclude(
            status__in=(SessionStatus.CANCELLED, SessionStatus.RESCHEDULED)
        ).select_related("trainer__user", "batch__branch", "planned_lesson__module")
        position = 0
        for session in rows.order_by("session_date", "start_time"):
            if not _ended(ctx, session):
                continue
            draw = _seed("class", key, session.session_date, session.start_time)
            register = draw.random() >= NO_REGISTER_SHARE and position != NO_REGISTER_POSITION
            report = draw.random() >= NO_DSR_SHARE and position != NO_DSR_POSITION
            scope.held.append(Held(key, batch, session, imported, register, report))
            position += 1
    ctx.out(f"held classes in scope: {len(scope.held)}")


# ---------------------------------------------------------------------------
# Registers
# ---------------------------------------------------------------------------


def _ensure_registers(ctx: Context, scope: Scope) -> None:
    per_batch: dict[str, list[Held]] = {}
    for held in scope.held:
        per_batch.setdefault(held.key, []).append(held)

    for key, batch, _imported in scope.batches:
        if not per_batch.get(key):
            continue
        made = found = without = 0
        found_sessions: list[ClassSession] = []
        for held in per_batch[key]:
            session = held.session
            if session.status == SessionStatus.COMPLETED:
                found += 1
                found_sessions.append(session)
                continue
            actor = _trainer_user(ctx, session)
            entries = _entries(scope, key, session) if held.register else []
            if not entries:
                # Left without a register by design — or nobody was enrolled
                # yet on the day, which is the same thing on the screens.
                set_session_status(session=session, target=SessionStatus.COMPLETED, actor=actor)
                ctx.created("session_completed")
                without += 1
                continue
            hooks = len(connection.run_on_commit)
            result = mark_attendance(session=session, actor=actor, entries=entries)
            _drop_recompute_hooks(
                scope, since=hooks, enrollment_ids=[e["enrollment_id"] for e in entries]
            )
            if session.status != SessionStatus.COMPLETED:
                # A class that was in progress: the register does not complete it.
                set_session_status(session=session, target=SessionStatus.COMPLETED, actor=actor)
            when = _end_of(ctx, session) + timedelta(minutes=10)
            ctx.backdate(session, attendance_taken_at=when)
            # The whole register at once: the same queryset ``update()``
            # ``ctx.backdate`` makes, without a round trip per mark — six
            # thousand of those was half this stage.
            AttendanceRecord.objects.filter(session=session).update(marked_at=when, created_at=when)
            ctx.created("attendance_register")
            ctx.created("attendance_record", result["created"])
            made += 1
        if found_sessions:
            # A held class found again is a register found — or, for the
            # ones left without one, a completion found, under its own label.
            registered = [s for s in found_sessions if s.attendance_taken_at is not None]
            ctx.found_existing("attendance_register", len(registered))
            ctx.found_existing("session_completed", len(found_sessions) - len(registered))
            ctx.found_existing(
                "attendance_record",
                AttendanceRecord.objects.filter(session__in=registered).count(),
            )
        ctx.out(
            f"registers {batch.code} {batch.name[:32]}: {made} taken, {found} found, "
            f"{without} left without; attendance {_attendance_percent(batch):.0f}%"
        )


def _entries(scope: Scope, key: str, session: ClassSession) -> list[dict[str, Any]]:
    """The marks for one class, drawn from the class's own generator over the
    roster in register order, so the same class gets the same register on
    every run. A student not yet enrolled on the day is not on it."""
    tuning = scope.tuning[key]
    chronic = scope.chronic[key]
    draw = _seed("register", key, session.session_date, session.start_time)
    regular = min(0.97, (tuning.attendance - CHRONIC_SHARE * CHRONIC_PRESENT) / (1 - CHRONIC_SHARE))
    entries: list[dict[str, Any]] = []
    for row in scope.rosters[key]:
        if timezone.localtime(row.enrolled_at).date() > session.session_date:
            continue
        if row.status == EnrollmentStatus.SUSPENDED:
            present = SUSPENDED_PRESENT
        elif row.pk in chronic:
            present = CHRONIC_PRESENT
        else:
            present = regular
        if draw.random() < present:
            if draw.random() < LATE_SHARE:
                status, note = AttendanceStatus.LATE, draw.choice(LATE_NOTES)
            else:
                status, note = AttendanceStatus.PRESENT, ""
        elif draw.random() < EXCUSED_SHARE:
            status, note = AttendanceStatus.EXCUSED, draw.choice(EXCUSED_NOTES)
        else:
            status, note = AttendanceStatus.ABSENT, draw.choice(ABSENT_NOTES)
        entries.append({"enrollment_id": row.pk, "status": status, "note": note})
    return entries


def _attendance_percent(batch: Batch) -> float:
    marks = list(
        AttendanceRecord.objects.filter(session__batch=batch)
        .counted()
        .values_list("status", flat=True)
    )
    if not marks:
        return 0.0
    return 100 * sum(1 for status in marks if status in COUNTS_AS_PRESENT) / len(marks)


def _end_of(ctx: Context, session: ClassSession) -> datetime:
    """When the class ended, as an aware datetime, never after now."""
    return min(timezone.localtime(session.ends_at), ctx.now - timedelta(minutes=1))


def _within_the_day(ended: datetime, offsets: dict[str, timedelta]) -> dict[str, datetime]:
    """``ended`` plus each offset, all held inside the class's own local day.

    A daily report belongs to the day it reports on: the DSR list, the overdue
    warning and the weekly compliance figures all read its timestamps, and a
    report filed twenty minutes after a class that ended at 23:52 would land in
    the next day's bucket while the register stayed in this one. So when the
    offsets do not fit before local midnight they are compressed into whatever
    time is left, which keeps their order — created, submitted, reviewed — and
    keeps every one of them on the session's date.
    """
    midnight = timezone.localtime(ended).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = midnight + timedelta(days=1) - timedelta(minutes=1)
    span = max(offsets.values(), default=timedelta())
    remaining = day_end - ended
    if span and remaining < span:
        scale = max(remaining, timedelta()) / span
        offsets = {name: off * scale for name, off in offsets.items()}
    return {name: ended + off for name, off in offsets.items()}


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


def _ensure_corrections(ctx: Context, scope: Scope) -> None:
    """Absent marks turned to present a couple of days later, with a reason.
    Found by the reason's tag; candidates are the oldest uncorrected absences
    in register order, so a re-run picks up where a stopped one left off."""
    tag = ctx.tag("correction")
    for spec_key, wanted in CORRECTIONS.items():
        batch = scope.by_spec.get(spec_key)
        if batch is None:
            continue
        done = AttendanceRecord.objects.filter(
            session__batch=batch, correction_reason__startswith=tag
        ).count()
        ctx.found_existing("attendance_correction", min(done, wanted))
        candidates = (
            AttendanceRecord.objects.filter(
                session__batch=batch, status=AttendanceStatus.ABSENT, correction_reason=""
            )
            .select_related("session__trainer__user", "session__batch__branch", "enrollment")
            .order_by(
                "session__session_date", "session__start_time", "enrollment__student__student_id"
            )
        )
        made = 0
        for row in candidates[: max(wanted - done, 0)]:
            hooks = len(connection.run_on_commit)
            correct_record(
                record_row=row,
                actor=_trainer_user(ctx, row.session),
                status=AttendanceStatus.PRESENT,
                reason=ctx.tag(
                    "correction",
                    "Was present — marked absent by mistake; checked against the lab sign-in.",
                ),
            )
            _drop_recompute_hooks(scope, since=hooks, enrollment_ids=[row.enrollment_id])
            when = min(ctx.at(row.session.session_date + timedelta(days=2), 10, 20), ctx.now)
            ctx.backdate(row, corrected_at=when)
            history = (
                AttendanceCorrection.objects.filter(record=row).order_by("-created_at").first()
            )
            if history is not None:
                ctx.backdate(history, created_at=when)
            ctx.created("attendance_correction")
            made += 1
        ctx.out(f"corrections {batch.code}: {made} created, {done} found")


# ---------------------------------------------------------------------------
# Topics: what each class actually covered
# ---------------------------------------------------------------------------


def _ensure_topics(ctx: Context, scope: Scope) -> None:
    """Record actual lessons on the showcase classes this stage completed, at
    the pace the batch's tuning asks for. Imported batches are left alone:
    their three-lesson courses were covered in June."""
    per_batch: dict[str, list[Held]] = {}
    for held in scope.held:
        if not held.imported:
            per_batch.setdefault(held.key, []).append(held)

    for key, batch, imported in scope.batches:
        if imported or not per_batch.get(key):
            continue
        lessons = scope.lessons.get(batch.course_id, [])
        covered_ids = set(
            ClassSession.objects.filter(
                batch=batch,
                status=SessionStatus.COMPLETED,
                topic_status=TopicStatus.COMPLETED,
                actual_lesson_id__isnull=False,
            ).values_list("actual_lesson_id", flat=True)
        )
        fresh = [
            held.session
            for held in per_batch[key]
            if held.session.status == SessionStatus.COMPLETED
            and held.session.topic_status == TopicStatus.PLANNED
            and held.session.actual_lesson_id is None
        ]
        recorded = len(per_batch[key]) - len(fresh)
        ctx.found_existing("session_topic", recorded)
        if not fresh:
            continue
        wanted = _wanted_covered(ctx, batch, scope.tuning[key], len(lessons))
        remaining = [lesson for lesson in lessons if lesson.pk not in covered_ids]
        need = max(0, min(wanted - len(covered_ids), len(remaining)))
        last = next((lesson for lesson in reversed(lessons) if lesson.pk in covered_ids), None)
        idle = 0
        for index, session in enumerate(fresh):
            lesson = remaining[index * need // len(fresh)] if need else last
            if lesson is not None and lesson is last:
                # Nothing new: the class carries on with the lesson the
                # previous one taught. Every seventh such class is revision;
                # the skip spends the count, so the next lesson's first
                # class is always taught.
                idle += 1
            actor = _trainer_user(ctx, session)
            if lesson is None or idle == REVISION_EVERY:
                idle = 0
                record_session_topic(
                    session=session, actor=actor, lesson=None, status=TopicStatus.SKIPPED
                )
            else:
                record_session_topic(session=session, actor=actor, lesson=lesson)
                last = lesson
            ctx.created("session_topic")
        ctx.out(
            f"topics {batch.code}: {len(fresh)} recorded, {recorded} found; "
            f"{min(wanted, len(lessons))} of {len(lessons)} lessons covered"
        )


def _wanted_covered(ctx: Context, batch: Batch, tuning: Tuning, total: int) -> int:
    """How many lessons the batch should have covered by today, so the
    timeline reads as the tuning asks: a finished batch covered all of them."""
    if batch.status in (BatchStatus.COMPLETED, BatchStatus.ARCHIVED) or ctx.today >= batch.end_date:
        return total
    span = max((batch.end_date - batch.start_date).days, 1)
    elapsed = min(max((ctx.today - batch.start_date).days, 0), span)
    target = min(max(elapsed * 100 / span + tuning.variance, 0), 100)
    return max(0, min(total, round(total * target / 100)))


# ---------------------------------------------------------------------------
# Daily status reports
# ---------------------------------------------------------------------------


def _ensure_reports(ctx: Context, scope: Scope) -> None:
    eligible = [
        held
        for held in scope.held
        if held.report
        and held.session.trainer_id
        and held.session.status == SessionStatus.COMPLETED
    ]
    eligible.sort(key=lambda h: (h.session.session_date, h.session.start_time, h.key), reverse=True)
    targets: dict[Any, str] = {}
    cursor = 0
    for status, count in RECENT_DSR_STATES:
        for held in eligible[cursor : cursor + count]:
            targets[held.session.pk] = status
        cursor += count

    existing = set(
        DSR.all_objects.filter(session__in=[h.session for h in eligible]).values_list(
            "session_id", flat=True
        )
    )
    made: dict[str, int] = {}
    found = 0
    for held in eligible:
        if held.session.pk in existing:
            found += 1
            continue
        target = targets.get(held.session.pk, DSRStatus.APPROVED)
        _write_report(ctx, scope, held, target)
        made[target] = made.get(target, 0) + 1
    ctx.found_existing("dsr", found)
    ctx.created("dsr", sum(made.values()))
    summary = ", ".join(f"{count} {status}" for status, count in sorted(made.items()))
    ctx.out(f"reports: {found} found; created {summary or 'none'}")


def _write_report(ctx: Context, scope: Scope, held: Held, target: str) -> None:
    session = held.session
    draw = _seed("report", held.key, session.session_date, session.start_time)
    trainer = _trainer_user(ctx, session)
    lesson = session.actual_lesson or session.planned_lesson
    planned = session.planned_lesson
    if session.topic_status == TopicStatus.SKIPPED or lesson is None:
        actual_topic = "Project work and doubts" if held.imported else "Revision and practice"
        notes = draw.choice(REVISION_NOTES)
    else:
        actual_topic = f"{lesson.module.title}: {lesson.title}"
        notes = draw.choice(TEACHING_NOTES).format(lesson=lesson.title)
    planned_topic = f"{planned.module.title}: {planned.title}" if planned else actual_topic

    concern = draw.choice(CONCERNS)
    if concern:
        absent_ids = set(
            AttendanceRecord.objects.filter(
                session=session, status=AttendanceStatus.ABSENT
            ).values_list("enrollment_id", flat=True)
        )
        absentees = [row for row in scope.rosters[held.key] if row.pk in absent_ids]
        concern = (
            concern.format(name=draw.choice(absentees).student.user.get_full_name())
            if absentees
            else ""
        )

    dsr = start_dsr(
        session=session,
        actor=trainer,
        planned_topic=planned_topic[:250],
        actual_topic=actual_topic[:250],
        module=lesson.module if lesson is not None else None,
        teaching_notes=notes,
        issues=draw.choice(ISSUES),
        student_concerns=concern,
        assignment_given=draw.random() < 0.45,
        assessment_conducted=draw.random() < 0.10,
    )
    ended = _end_of(ctx, session)
    offsets: dict[str, timedelta] = {"created_at": timedelta(minutes=5)}
    if target != DSRStatus.DRAFT:
        submit_dsr(dsr=dsr, actor=trainer)
        offsets["submitted_at"] = timedelta(minutes=20)
    if target not in (DSRStatus.DRAFT, DSRStatus.SUBMITTED):
        comments = draw.choice(REVIEW_COMMENTS.get(target, ("",)))
        review_dsr(dsr=dsr, actor=_reviewer(ctx, held.batch), decision=target, comments=comments)
        offsets["reviewed_at"] = timedelta(hours=2, minutes=draw.randint(0, 40))
    stamps = _within_the_day(ended, offsets)
    latest = ctx.now - timedelta(minutes=1)
    ctx.backdate(dsr, **{name: min(when, latest) for name, when in stamps.items()})


# ---------------------------------------------------------------------------
# Learning state
# ---------------------------------------------------------------------------


def _ensure_learning(ctx: Context, scope: Scope) -> None:
    headline = ctx.students[MAIN][0] if ctx.students.get(MAIN) else None
    seen: set[tuple[Any, Any]] = set()
    made = found = 0
    for key, batch, _imported in scope.batches:
        if batch.status not in ACCESS_GRANTING_STATUSES:
            continue
        lessons = scope.lessons.get(batch.course_id, [])
        if not lessons:
            continue
        rows = Enrollment.objects.filter(
            batch=batch, status__in=(EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED)
        ).select_related("student__user", "batch", "course")
        for row in rows.order_by("student__student_id"):
            pair = (row.student_id, row.course_id)
            if pair in seen or not row.grants_access(on_date=ctx.today):
                continue
            seen.add(pair)
            complete = _completed_lessons(ctx, scope, key, batch, row, headline, len(lessons))
            if complete == 0 and _nothing_opened(ctx, scope, key, batch, row, headline):
                continue
            # The services resolve the enrolment from (student, course), so
            # that is the key the existence check must use too.
            existing = set(
                LessonProgress.objects.filter(
                    enrollment__student_id=row.student_id,
                    lesson__module__course_id=row.course_id,
                ).values_list("lesson_id", flat=True)
            )
            start = max(batch.start_date, timezone.localtime(row.enrolled_at).date())
            end = min(ctx.today, batch.end_date)
            span = max((end - start).days, 1)
            for index, lesson in enumerate(lessons[:complete]):
                if lesson.pk in existing:
                    found += 1
                    continue
                progress = set_lesson_completion(student=row.student, lesson=lesson, completed=True)
                day = start + timedelta(days=span * (index + 1) // (complete + 1))
                done_at = min(ctx.at(day, 19 + index % 3, 10 + index * 7 % 50), ctx.now)
                ctx.backdate(
                    progress,
                    first_accessed_at=done_at - timedelta(hours=1),
                    last_accessed_at=done_at,
                    completed_at=done_at,
                    created_at=done_at - timedelta(hours=1),
                )
                made += 1
            if complete >= len(lessons):
                continue
            lesson = lessons[complete]
            if lesson.pk in existing:
                found += 1
                continue
            progress = touch_lesson(student=row.student, lesson=lesson)
            if progress is None:
                continue
            if headline is not None and row.student_id == headline.pk:
                recent = ctx.at(ctx.days_ago(1), 20, 15)
            else:
                recent = ctx.at(ctx.days_ago(_seed("recent", *pair).randint(0, 5)), 19, 30)
            opened = min(recent, ctx.now - timedelta(hours=1))
            ctx.backdate(
                progress, first_accessed_at=opened, last_accessed_at=opened, created_at=opened
            )
            made += 1
    ctx.created("lesson_progress", made)
    ctx.found_existing("lesson_progress", found)
    ctx.out(f"lesson progress: {made} created, {found} found")
    _ensure_bookmarks(ctx, scope, headline)


def _completed_lessons(
    ctx: Context, scope: Scope, key: str, batch: Batch, row: Enrollment, headline: Any, total: int
) -> int:
    """How many lessons this student has finished, drawn around the line the
    risk engine measures against (see the module docstring): the headline
    student a fixed way; a chronic absentee behind it, or barely started, or
    never opened it; everybody else within the rule's band, bar a few in the
    warning band, a few finished and a few who have opened nothing.

    Counted on the course's own grid — nine lessons make eleven-point steps,
    wider than the rule's band — so a student meant to be on track is rounded
    *up* to the line and one meant to be behind is rounded *down* past it,
    rather than ``round()`` dropping the former into the warning band by
    accident.
    """
    if headline is not None and row.student_id == headline.pk:
        return total if batch.status == BatchStatus.COMPLETED else round(HEADLINE_FRACTION * total)
    draw = _seed("learning", row.student_id, batch.course_id)
    expected = _expected_fraction(ctx, batch)
    roll = draw.random()
    if row.pk in scope.chronic.get(key, set()):
        if roll < CHRONIC_NOTHING:
            return 0
        if roll < CHRONIC_TENTH:
            return max(1, round(0.10 * total))
        return _floor_lessons(expected - draw.uniform(*CHRONIC_BEHIND), total)
    if roll < NOTHING_OPENED_SHARE and batch.status != BatchStatus.COMPLETED:
        return 0
    if roll < NOTHING_OPENED_SHARE + FINISHED_SHARE:
        return total
    if roll < NOTHING_OPENED_SHARE + FINISHED_SHARE + WARNING_SHARE:
        return _floor_lessons(expected - WARNING_BEHIND[0], total)
    return _ceil_lessons(expected + draw.uniform(*ON_TRACK_SPREAD), total)


def _nothing_opened(
    ctx: Context, scope: Scope, key: str, batch: Batch, row: Enrollment, headline: Any
) -> bool:
    """Whether a student with no finished lesson has not opened one either —
    the same draw as :func:`_completed_lessons`, read for its first branch,
    so the two never disagree about the same student."""
    if headline is not None and row.student_id == headline.pk:
        return False
    draw = _seed("learning", row.student_id, batch.course_id)
    roll = draw.random()
    if row.pk in scope.chronic.get(key, set()):
        return roll < CHRONIC_NOTHING
    return roll < NOTHING_OPENED_SHARE and batch.status != BatchStatus.COMPLETED


def _expected_fraction(ctx: Context, batch: Batch) -> float:
    """Where the calendar says a student should be, as the engine reads it:
    a straight line from the batch's first day to its last."""
    if ctx.today <= batch.start_date:
        return 0.0
    if ctx.today >= batch.end_date:
        return 1.0
    span = (batch.end_date - batch.start_date).days
    return (ctx.today - batch.start_date).days / span if span > 0 else 1.0


def _floor_lessons(fraction: float, total: int) -> int:
    return max(0, min(total, math.floor(fraction * total)))


def _ceil_lessons(fraction: float, total: int) -> int:
    return max(0, min(total, math.ceil(fraction * total)))


def _ensure_bookmarks(ctx: Context, scope: Scope, headline: Any) -> None:
    if headline is None:
        return
    a2 = scope.by_spec.get("a2")
    c1 = scope.by_spec.get("c1")
    plans: list[tuple[Enrollment, int, str, str]] = []  # (enrolment, lesson index, kind, text)
    if a2 is not None:
        row = Enrollment.objects.filter(student=headline, batch=a2).order_by("-enrolled_at").first()
        if row is not None:
            plans += [(row, i, "bookmark", note) for i, note in HEADLINE_BOOKMARKS]
            plans += [(row, i, "note", body) for i, body in HEADLINE_NOTES]
        classmates = (
            Enrollment.objects.filter(batch=a2, status=EnrollmentStatus.ACTIVE)
            .exclude(student=headline)
            .filter(lesson_progress__isnull=False)
            .distinct()
            .order_by("student__student_id")[:3]
        )
        for mate in classmates:
            plans.append((mate, CLASSMATE_BOOKMARK_LESSON, "bookmark", ""))
            plans.append((mate, CLASSMATE_BOOKMARK_LESSON, "note", CLASSMATE_NOTE))
    if c1 is not None:
        row = Enrollment.objects.filter(student=headline, batch=c1).order_by("-enrolled_at").first()
        if row is not None:
            plans.append(
                (row, 3, "note", "LVM: pvcreate -> vgcreate -> lvcreate. Then mkfs and fstab.")
            )

    for row, index, kind, text in plans:
        lessons = scope.lessons.get(row.course_id, [])
        if index >= len(lessons):
            continue
        lesson = lessons[index]
        when = min(ctx.at(ctx.days_ago(2 + index), 21, 5 + index), ctx.now)
        if kind == "bookmark":
            if LessonBookmark.objects.filter(enrollment=row, lesson=lesson).exists():
                ctx.found_existing("lesson_bookmark")
                continue
            made = set_bookmark(enrollment=row, lesson=lesson, note=text)
            ctx.created("lesson_bookmark")
        else:
            if LessonNote.objects.filter(enrollment=row, lesson=lesson).exists():
                ctx.found_existing("lesson_note")
                continue
            made = set_note(enrollment=row, lesson=lesson, body=text)
            ctx.created("lesson_note")
        if made is not None:
            ctx.backdate(made, created_at=when)


# ---------------------------------------------------------------------------
# Trainer requirements
# ---------------------------------------------------------------------------


def _ensure_requirements(ctx: Context, scope: Scope) -> None:
    for spec in REQUIREMENTS:
        tag = ctx.tag(f"req/{spec.key}")
        raiser = _user(ctx, spec.raiser)
        requirement = TrainerRequirement.objects.filter(
            title=spec.title, details__startswith=tag
        ).first()
        raised_at = ctx.at(ctx.days_ago(spec.age), 9, 40)
        if requirement is None:
            batch = scope.by_spec.get(spec.batch) if spec.batch else None
            requirement = raise_requirement(
                actor=raiser,
                title=spec.title,
                details=ctx.tag(f"req/{spec.key}", spec.details),
                batch=batch,
                needed_by=ctx.days_ahead(spec.needed_in),
            )
            ctx.backdate(requirement, created_at=raised_at)
            ctx.created("requirement")
            ctx.out(f"requirement '{spec.title[:40]}': created")
        else:
            ctx.found_existing("requirement")
            ctx.out(f"requirement '{spec.title[:40]}': found")

        for offset, (author, message) in enumerate(spec.replies, start=1):
            user = _user(ctx, author)
            if RequirementReply.objects.filter(
                requirement=requirement, author=user, message=message
            ).exists():
                ctx.found_existing("requirement_reply")
                continue
            if not requirement.is_open:
                # A closed requirement takes no replies; a run that closed it
                # before all replies were in stays as it is.
                continue
            reply = reply_to_requirement(requirement=requirement, actor=user, message=message)
            ctx.backdate(reply, created_at=raised_at + timedelta(hours=3 * offset))
            ctx.created("requirement_reply")

        if spec.outcome == RequirementStatus.OPEN:
            continue
        if not requirement.is_open:
            ctx.found_existing("requirement_closed")
            continue
        fulfilled_by = None
        if spec.fulfilled_by:
            fulfilled_by = next(
                (
                    profile
                    for profile in ctx.trainers.get(spec.branch, [])
                    if profile.user.email == f"{spec.fulfilled_by}@{DOMAIN}"
                ),
                None,
            )
        close_requirement(
            requirement=requirement,
            actor=_user(ctx, spec.closer or spec.raiser),
            fulfilled_by=fulfilled_by,
            note=spec.closing_note,
        )
        ctx.backdate(requirement, closed_at=raised_at + timedelta(days=1, hours=2))
        ctx.created("requirement_closed")


def _user(ctx: Context, local_part: str) -> User:
    try:
        return ctx.users[local_part]
    except KeyError:
        raise RuntimeError(
            f"{local_part}@{DOMAIN} is not loaded: run the people stage first."
        ) from None


# ---------------------------------------------------------------------------
# One risk recompute per student, not one per mark
# ---------------------------------------------------------------------------


def _drop_recompute_hooks(scope: Scope, *, since: int, enrollment_ids: list[Any]) -> None:
    """Take the recompute callbacks one register service just deferred off
    the connection, and remember whose recompute this stage now owes.

    ``since`` is how many hooks the connection held before the service was
    called; only the entries after it are looked at, and of those only the
    closures ``mark_attendance``/``correct_record`` define for the purpose
    (matched by module and enclosing function). The Student 360 cache bump
    those services also defer — a different module — is kept where it is.
    """
    hooks = connection.run_on_commit
    kept = hooks[:since]
    for entry in hooks[since:]:
        func = entry[1]
        owner = getattr(func, "__qualname__", "").split(".")[0]
        if (
            getattr(func, "__module__", "") == RECOMPUTE_HOOK_MODULE
            and owner in RECOMPUTE_HOOK_OWNERS
        ):
            continue
        kept.append(entry)
    hooks[:] = kept
    scope.recompute.update(enrollment_ids)


def _release_recomputes(ctx: Context, scope: Scope) -> None:
    """Registered last, after every other hook this stage's services left:
    the one recompute per student the dropped callbacks would have made."""
    ids = sorted(scope.recompute, key=str)
    if not ids:
        return

    def _release() -> None:
        started = perf_counter()
        for enrollment_id in ids:
            risk_tasks.schedule_recompute(enrollment_id)
        ctx.out(f"academics/risk recomputes: {len(ids)} scheduled, {perf_counter() - started:.1f}s")

    transaction.on_commit(_release)


__all__ = ["REQUIREMENTS", "TUNING", "run"]
