"""Stage 4 of the showcase: batches in every state, timetables with today's
classes on them, enrolments spread across the year — and a second run that
creates nothing.

Runs the command up to and including ``batches`` on the empty test database,
twice — then a third time with the clock a day ahead, which must add nothing
but the one-off classes that keep "a class today" true and the ``update_batch``
that keeps the dates relative, and a fourth time three months ahead at ten to
midnight, which is where the two crashes a reviewer reproduced lived: a class
asked for an hour before midnight ended tomorrow, and a batch dated by the
first run had today outside its range by day eighty-five. There are no SITP
rows here, so the imported-batch work is proved to be a clean no-op; the
junk-batch rename is exercised on a stand-in made the way the staging
batches were, by hand, with the junk name.

One test runs the command twice and checks everything, rather than one test
per promise: the people stage in front makes a hundred accounts and the
courses stage a catalogue, and a run per test would put the file well over
its time budget. The three tests after it do not run the command at all:
they call the stage's own functions against a hand-made batch, which is the
only way to reach the imported-SITP path on a database the workbook import
has never touched, and is cheap enough to cover the far-future re-runs a
reviewer found the real defect in.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db.models import Min
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import Batch, BatchKind, BatchSchedule, BatchStatus, DeliveryMode
from apps.batches.services import create_batch, set_batch_status
from apps.common.showcase.context import MARKER, Context
from apps.common.showcase.roster import BATCH_RENAMES, build_roster
from apps.common.showcase.stages.s04_batches import (
    CLASS_HOURS,
    EARLIEST_START,
    LATEST_START,
    SHIFTS_EARLIER,
    SITP_BACKFILL_DAYS,
    SITP_EXTENSION_DAYS,
    SITP_SLOT_DAYS,
    SPECS,
    TZ,
    _clock_time,
    _ensure_today,
    _extend_imported,
    _plus_hours,
    _window,
)
from apps.courses.services import create_category, create_course
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.sessions.models import ClassSession
from apps.sessions.services import MAX_GENERATION_DAYS, create_session
from apps.students.models import StudentProfile
from apps.trainers.models import TrainerProfile

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = (
    "batch",
    "batch_schedule",
    "class_session",
    "session_plan",
    "enrollment",
    "enrollment_status",
    "enrollment_transfer",
    "batch_status",
    "batch_rename",
    "batch_realign",
    "user_deactivation",
)

SPEC_BY_KEY = {spec.key: spec for spec in SPECS}

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks, days_later: int = 0, at_hour: int | None = None) -> str:
    """The command up to ``batches``.

    ``days_later`` moves the clock forward, so a re-run on another day can be
    proved to add nothing but today's one-off class; ``at_hour`` also fixes
    that day's wall clock at ``at_hour``:50, because the interesting failures
    live at the edges of the day rather than at whatever time the suite
    happens to run. The context's ``today``/``now`` and every ``auto_now``
    stamp go through ``timezone.now``, so patching it moves the whole run.
    """
    real_now = timezone.now
    shift = timedelta(days=days_later)
    if at_hour is not None:
        day = timezone.localdate() + timedelta(days=days_later)
        shift = timezone.make_aware(datetime.combine(day, time(at_hour, 50))) - real_now()
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        mock.patch("django.utils.timezone.now", side_effect=lambda: real_now() + shift),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    return {
        "batches": Batch.objects.count(),
        "schedules": BatchSchedule.objects.count(),
        "sessions": ClassSession.objects.count(),
        "planned": ClassSession.objects.filter(planned_lesson__isnull=False).count(),
        "enrolments": Enrollment.objects.count(),
        **{
            f"enrolments_{status}": Enrollment.objects.filter(status=status).count()
            for status in EnrollmentStatus.values
        },
        **{
            f"batches_{status}": Batch.objects.filter(status=status).count()
            for status in BatchStatus.values
        },
        "inactive_users": User.objects.filter(is_active=False).count(),
        "batch_audit": AuditLog.objects.filter(
            resource_type__in=["batch", "batch_schedule", "enrollment"]
        ).count(),
    }


@pytest.fixture
def junk_batch(db):
    """A stand-in for the hand-made staging batch ``temp batch``: no marker,
    no trainer, an upcoming batch with a start already in the past."""
    actor = User.objects.create_superuser(
        email="importer@sitp.grras.invalid", password="Importer-Passw0rd!", first_name="Import"
    )
    category = create_category(actor=actor, name="Scratch", slug="scratch")
    course = create_course(
        actor=actor, title="Scratch course", slug="scratch-course", category=category
    )
    from apps.organisation.models import Branch

    today = timezone.localdate()
    return create_batch(
        actor=actor,
        branch=Branch.objects.get(code="MAIN"),
        name="temp batch",
        course=course,
        start_date=today - timedelta(days=14),
        end_date=today + timedelta(days=76),
        capacity=20,
    )


def by_key() -> dict[str, Batch]:
    """The showcase batches by spec key, through the marker hydrate uses."""
    by_name = {
        batch.name: batch
        for batch in Batch.objects.filter(description__startswith=MARKER).select_related(
            "trainer__user", "course", "branch"
        )
    }
    return {spec.key: by_name[spec.name] for spec in SPECS if spec.name in by_name}


@pytest.mark.django_db
def test_batches_stage_builds_every_state_and_is_idempotent(
    junk_batch, django_capture_on_commit_callbacks
):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table[label][0] == 0, f"second run created {label}: {table[label]}"
        assert table[label][1] > 0, f"second run found no {label}"
    assert counts() == after_first
    assert table.get("batch_redate", (0, 0))[0] == 0, "the second run re-dated a batch"
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"
    assert "imported batches: none on this database" in first
    assert "imported batches: none on this database" in second

    today = timezone.localdate()
    now = timezone.localtime()
    batches = by_key()
    # The demo trainer is absent here, so his batch is not made.
    assert set(batches) == {spec.key for spec in SPECS if spec.key != "d1"}
    assert Batch.objects.filter(description__startswith=MARKER).count() == 14

    # --- Every batch state, on the right dates --------------------------------
    main = {k: b for k, b in batches.items() if b.branch.code == "MAIN"}
    pune = {k: b for k, b in batches.items() if b.branch.code == "PUNE"}
    assert len(main) == 10 and len(pune) == 4
    statuses = {key: batch.status for key, batch in batches.items()}
    assert statuses == {spec.key: spec.status for spec in SPECS if spec.key != "d1"}
    for spec in SPECS:
        if spec.key == "d1":
            continue
        batch = batches[spec.key]
        assert batch.start_date == today + timedelta(days=spec.start), spec.key
        assert batch.end_date == today + timedelta(days=spec.end), spec.key
        assert re.fullmatch(r"GRS-B-\d{5}", batch.code)
        admin = "admin.pune" if spec.branch == "PUNE" else "admin"
        assert batch.created_by.email == f"{admin}@grras.com"
        assert batch.created_at < now - timedelta(days=1), "batch created_at backdated"
    for batch in Batch.objects.filter(status=BatchStatus.ACTIVE, description__startswith=MARKER):
        assert batch.end_date >= today, "an active batch ending in the past is an overrun"
    assert {b.delivery_mode for b in batches.values()} == set(DeliveryMode.values)
    assert {b.kind for b in batches.values()} == set(BatchKind.values)

    # No trainer, no timetable, full, nearly full.
    assert batches["u2"].trainer_id is None
    assert not batches["pu1"].schedules.exists()
    assert batches["u1"].schedules.count() == 3
    assert batches["a4"].seats_available() == 0
    assert batches["a4"].capacity == batches["a4"].seats_taken()
    assert 1 <= batches["a3"].seats_available() <= 3
    assert batches["k1"].enrollments.filter(status=EnrollmentStatus.CANCELLED).count() >= 5
    assert batches["k1"].enrollments.exclude(status=EnrollmentStatus.CANCELLED).count() == 0
    assert (
        AuditLog.objects.filter(
            action=AuditAction.BATCH_STATUS_CHANGED,
            resource_id=str(batches["k1"].pk),
            context__note__startswith=MARKER,
        ).count()
        == 1
    )
    assert batches["x1"].trainer.user.email == "deepak.purohit@grras.com"

    # --- The headline trainer and today's classes ------------------------------
    headline_trainer = TrainerProfile.objects.get(user__email="trainer@grras.com")
    assert batches["a2"].trainer_id == headline_trainer.pk
    started = ClassSession.objects.filter(
        batch=batches["a2"], session_date=today, start_time__lte=now.time()
    )
    assert started.exists(), "the headline batch has a class today that has started"
    assert started.get().trainer_id == headline_trainer.pk
    later = ClassSession.objects.filter(batch=batches["a1"], session_date=today)
    if (now + timedelta(hours=2)).time() <= time(21, 55) and now.date() == today:
        assert later.filter(start_time__gt=now.time()).exists(), "a1 has a class later today"
    else:  # too late in the evening for a class ahead: a started one instead
        assert later.filter(start_time__lte=now.time()).exists()
    # The clock slot: on today's weekday, tagged so a later day finds it; the
    # fixed slots on the spec's days regardless of what day it is.
    weekly = BatchSchedule.objects.filter(batch=batches["a2"])
    assert weekly.count() == 3
    clock = weekly.get(note__startswith="[showcase][today/a2]")
    assert clock.weekday == today.weekday()
    assert started.get().schedule_id == clock.pk
    assert set(weekly.exclude(pk=clock.pk).values_list("weekday", flat=True)) == {0, 2}
    a1_days = BatchSchedule.objects.filter(batch=batches["a1"]).values_list("weekday", flat=True)
    assert set(a1_days) >= {0, 2}
    assert {s.timezone_name for s in BatchSchedule.objects.all()} == {"Asia/Kolkata"}
    # A timetable that clashed would have been refused, so every slot that
    # exists is clash-free; what matters is that nobody was left without one.
    assert "warning: no clash-free slot" not in first

    # Classes across the whole range, with the curriculum on them.
    for key in ("a2", "a4", "c1", "c2", "x1", "pa1", "pc1"):
        batch = batches[key]
        sessions = ClassSession.objects.filter(batch=batch)
        assert sessions.count() >= 20, key
        assert sessions.order_by("session_date").first().session_date >= batch.start_date
        assert sessions.order_by("-session_date").first().session_date <= batch.end_date
    planned = ClassSession.objects.filter(batch=batches["a2"], planned_lesson__isnull=False)
    assert planned.count() > 5

    # --- Enrolments: everybody, in every state, spread across the year -------
    roster = build_roster()
    never = next(p for p in roster if p.flags.get("never_enrolled"))
    inactive_student = next(p for p in roster if p.role == "student" and p.flags.get("inactive"))
    inactive_trainer = next(p for p in roster if p.role == "trainer" and p.flags.get("inactive"))
    assert not Enrollment.objects.filter(student__user__email=never.email).exists()
    for person in roster:
        if person.role != "student" or person is never:
            continue
        assert Enrollment.objects.filter(student__user__email=person.email).exists(), person.email

    showcase = Enrollment.objects.filter(batch__description__startswith=MARKER)
    for row in showcase.select_related("student", "batch"):
        assert row.student.branch_id == row.batch.branch_id
    per_status = {
        status: showcase.filter(status=status).count() for status in EnrollmentStatus.values
    }
    assert per_status[EnrollmentStatus.PENDING] >= 5
    assert per_status[EnrollmentStatus.SUSPENDED] >= 3
    assert per_status[EnrollmentStatus.CANCELLED] >= 4
    assert per_status[EnrollmentStatus.COMPLETED] >= 40
    assert per_status[EnrollmentStatus.ACTIVE] >= 60
    assert per_status[EnrollmentStatus.TRANSFERRED] == 1
    moved = showcase.get(status=EnrollmentStatus.TRANSFERRED)
    assert moved.batch_id == batches["a1"].pk
    assert moved.transferred_to.batch_id == batches["a2"].pk
    assert moved.transferred_to.status == EnrollmentStatus.ACTIVE
    assert moved.status_note.startswith(MARKER)
    assert showcase.filter(status=EnrollmentStatus.SUSPENDED).first().status_note.startswith(MARKER)
    for batch in batches.values():
        if batch.status in (BatchStatus.UPCOMING, BatchStatus.ACTIVE):
            assert 8 <= batch.enrollments.count() <= 25, batch.name

    headline_student = StudentProfile.objects.get(user__email="student@grras.com")
    on_a2 = Enrollment.objects.get(student=headline_student, batch=batches["a2"])
    on_c1 = Enrollment.objects.get(student=headline_student, batch=batches["c1"])
    assert on_a2.status == EnrollmentStatus.ACTIVE
    assert on_c1.status == EnrollmentStatus.COMPLETED

    earliest = showcase.order_by("enrolled_at").first().enrolled_at
    latest = showcase.order_by("-enrolled_at").first().enrolled_at
    assert earliest < now - timedelta(weeks=50), "the trend reaches back a year"
    assert latest < now - timedelta(minutes=29)
    for row in showcase.filter(status=EnrollmentStatus.COMPLETED).select_related("batch"):
        assert row.completed_at is not None
        assert row.completed_at.date() == row.batch.end_date, "completed when the batch ended"
        assert row.enrolled_at < row.completed_at
    for row in showcase.filter(status__in=["suspended", "cancelled"]):
        assert row.status_changed_at > row.enrolled_at
    for row in showcase:
        assert row.created_at == row.enrolled_at

    # --- The junk stand-in: renamed, and dated into the month it now claims ---
    # It has no classes at all, so nothing pins its range: the name says
    # "Aug 2026" and the dates now agree, keeping the ninety days it had.
    junk_batch.refresh_from_db()
    assert junk_batch.name == BATCH_RENAMES["temp batch"]
    assert (junk_batch.start_date.year, junk_batch.start_date.month) == (2026, 8)
    assert junk_batch.start_date.day == (today - timedelta(days=14)).day
    assert junk_batch.end_date - junk_batch.start_date == timedelta(days=90)
    assert "to match the name" in first
    assert junk_batch.status == BatchStatus.UPCOMING
    assert junk_batch.description == "", "not made into a showcase batch"
    assert "rename" in first and f"-> {BATCH_RENAMES['temp batch']!r}" in first
    assert "-> " not in second.split("batches/renames", 1)[0].split("batches/imported", 1)[-1]

    # --- Departures, last -------------------------------------------------------
    for person in (inactive_student, inactive_trainer):
        user = User.objects.get(email=person.email)
        assert user.is_active is False
        assert AuditLog.objects.filter(
            action=AuditAction.USER_DEACTIVATED, resource_id=str(user.pk)
        ).exists()
    assert Enrollment.objects.filter(student__user__email=inactive_student.email).exists()
    assert Batch.objects.filter(trainer__user__email=inactive_trainer.email).exists()
    assert f"departure {inactive_trainer.email}: deactivated" in first
    assert f"departure {inactive_trainer.email}: already inactive" in second

    # --- A re-run tomorrow: no new slot, no new weekly classes ------------------
    # Only the one-off classes that keep "a class today" true for the two
    # clock-slot batches may appear — and only where tomorrow's timetable
    # does not already provide one.
    before_third = counts()
    dates_before = {
        key: (row.start_date, row.end_date)
        for key, row in ((key, Batch.objects.get(pk=batch.pk)) for key, batch in batches.items())
    }
    third = run(django_capture_on_commit_callbacks, days_later=1)
    table = rows(third)
    tomorrow = today + timedelta(days=1)
    one_offs = ClassSession.objects.filter(
        session_date=tomorrow, schedule__isnull=True, notes__startswith=MARKER
    )
    assert table["batch_schedule"][0] == 0, "a re-run tomorrow made a weekly slot"
    assert table["class_session"][0] == one_offs.count() <= 2
    for label in LABELS:
        if label != "class_session":
            assert table[label][0] == 0, f"re-run tomorrow created {label}: {table[label]}"
    assert set(one_offs.values_list("batch_id", flat=True)) <= {batches["a1"].pk, batches["a2"].pk}
    assert BatchSchedule.objects.filter(batch=batches["a2"]).count() == 3
    assert ClassSession.objects.filter(
        batch=batches["a2"], session_date=tomorrow, start_time__lte=now.time()
    ).exists(), "the headline batch still has a started class on the re-run day"

    # Every batch is re-dated so the spec's offsets still describe the day the
    # command ran: every end date moves with the clock, and a start date moves
    # with it as far as the batch's own **first class**, which cannot be left
    # outside its batch's dates. So a batch with no classes at all (the one
    # with no timetable by design, and the cancelled one) keeps its offset
    # exactly — that is what keeps a start "within three days" true on any day
    # — and one generated end to end creeps up to its first class and stops
    # there. The archived batch is the exception: its trainer left at the end
    # of stage 4 and ``Batch.clean`` refuses to re-validate a batch an
    # inactive trainer teaches, so the stage says so and leaves it alone.
    redated = table.get("batch_redate", (0, 0))[0]
    assert redated == len(batches) - 1 == 13
    assert f"batch {batches['x1'].code}: dates left at" in third
    assert counts() == {
        **before_third,
        "sessions": before_third["sessions"] + one_offs.count(),
        "batch_audit": before_third["batch_audit"] + redated,
    }
    for key, batch in batches.items():
        spec = SPEC_BY_KEY[key]
        was_start, was_end = dates_before[key]
        batch.refresh_from_db()
        if key == "x1":
            assert (batch.start_date, batch.end_date) == (was_start, was_end), key
            continue
        assert batch.end_date == tomorrow + timedelta(days=spec.end), key
        first = ClassSession.objects.filter(batch=batch).aggregate(day=Min("session_date"))["day"]
        wanted_start = tomorrow + timedelta(days=spec.start)
        expected_start = wanted_start if first is None else min(wanted_start, first)
        assert batch.start_date == expected_start, key
        assert was_start <= batch.start_date <= wanted_start, key
        assert first is None or batch.start_date <= first, "a class outside its batch's dates"
    # The two with no classes keep the offset exactly, warnings and all.
    for key in ("pu1", "k1"):
        assert batches[key].start_date == tomorrow + timedelta(days=SPEC_BY_KEY[key].start), key

    # --- A re-run three months later, at ten to midnight ----------------------
    # Both crashes a reviewer reproduced, in one run: a clock slot asking for
    # a class an hour before midnight used to end tomorrow, which
    # ``ClassSession.clean`` refuses, and a batch still carrying the first
    # run's dates has today outside them from day eighty-five on. A Sunday is
    # chosen because no fixed slot of the two clock-slot batches falls on one,
    # which is what sends the run down the one-off-class path.
    ahead = 85 + (6 - (today + timedelta(days=85)).weekday()) % 7
    far = today + timedelta(days=ahead)
    assert far.weekday() == 6
    before_fourth = counts()
    fourth = run(django_capture_on_commit_callbacks, days_later=ahead, at_hour=23)
    table = rows(fourth)
    late = ClassSession.objects.filter(session_date=far, notes__startswith=MARKER)
    for label in LABELS:
        if label != "class_session":
            assert table[label][0] == 0, f"the far re-run created {label}: {table[label]}"
    assert table["class_session"][0] == late.count()
    assert 1 <= late.count() <= 2
    for session in late.select_related("batch"):
        assert EARLIEST_START <= session.start_time <= LATEST_START
        assert session.end_time > session.start_time, "a class that ended tomorrow"
        assert session.batch.start_date <= far <= session.batch.end_date
    assert table.get("batch_redate", (0, 0))[0] == len(batches) - 1
    after = counts()
    assert after["sessions"] == before_fourth["sessions"] + late.count()
    assert after["batches"] == before_fourth["batches"]
    assert after["enrolments"] == before_fourth["enrolments"]
    assert after["inactive_users"] == before_fourth["inactive_users"]
    for status in BatchStatus.values:
        assert after[f"batches_{status}"] == before_fourth[f"batches_{status}"]


def _ctx_on(day: date, hour: int = 11, minute: int = 30) -> Context:
    """A context for one notional run day — no command, no hydrate: the
    functions below read ``today``/``now``, count, and write lines."""
    return Context(
        password=SEED_PASSWORD,
        out=lambda line: None,
        today=day,
        now=timezone.make_aware(datetime.combine(day, time(hour, minute))),
    )


@pytest.fixture
def imported_batch(admin_user, branch, trainer_profile, published_course):
    """A stand-in for the SITP workbook batch the institute kept running.

    The import's ``description`` prefix is what tells ``hydrate`` an imported
    batch from a showcase one, and the name carries the ``Group A`` fragment
    ``SITP_EXTENDED`` matches. Dated the way the workbook left all sixteen:
    active, with its end date months in the past — one ``batch_overrun``
    warning each.
    """
    today = timezone.localdate()
    batch = create_batch(
        actor=admin_user,
        branch=branch,
        name="SITP ACE 2026 — Group A",
        course=published_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=120),
        end_date=today - timedelta(days=50),
        capacity=40,
        description="Imported from SITP_ACE_2026_Group_A.xlsx",
    )
    set_batch_status(batch=batch, target=BatchStatus.ACTIVE, actor=admin_user)
    return batch


@pytest.mark.django_db
def test_an_extended_imported_batch_has_classes_in_the_term_it_is_running(
    imported_batch, admin_user
):
    """The four tracks the institute kept must have classes and a curriculum
    inside the ten weeks they are extended to — on the first run *and* on
    every later one.

    The defect this pins down: ``_ensure_classes`` skips generation when the
    slots it is given already have classes, which is what keeps a re-run from
    leaving a trail of "generated 0" audit rows. On a re-run more than seventy
    days later the extension moves the end date but the slots are the same
    slots, so the guard was false and the new term got nothing: four batches
    active, "runs for another ten weeks", with no class for months in either
    direction and an empty ``/teaching/today``, a timetable and a register.
    """
    batch = imported_batch
    today = timezone.localdate()
    weeks = timedelta(days=7)

    first = _ctx_on(today)
    _extend_imported(first, batch, admin_user)
    batch.refresh_from_db()
    assert batch.end_date == today + timedelta(days=SITP_EXTENSION_DAYS)
    assert first.counts["batch_extension"] == 1
    assert first.counts["batch_schedule"] == len(SITP_SLOT_DAYS)
    term = ClassSession.objects.filter(batch=batch)
    assert term.count() == first.counts["class_session"] >= 25
    assert term.order_by("session_date").first().session_date >= today - timedelta(
        days=SITP_BACKFILL_DAYS
    )
    # published_course publishes two lessons; both land on the running term.
    assert first.counts["session_plan"] == 2
    assert term.filter(planned_lesson__isnull=False).count() == 2

    # The same day again: not one row.
    again = _ctx_on(today)
    _extend_imported(again, batch, admin_user)
    assert not any(again.counts.values()), again.counts
    assert ClassSession.objects.filter(batch=batch).count() == term.count()

    # Five months on, which is how this command will really be used.
    far = today + timedelta(days=150)
    later = _ctx_on(far)
    _extend_imported(later, batch, admin_user)
    batch.refresh_from_db()
    assert batch.end_date == far + timedelta(days=SITP_EXTENSION_DAYS)
    assert later.counts["batch_extension"] == 1
    assert later.counts["batch_schedule"] == 0, "the slots are the ones it already had"
    window_start = far - timedelta(days=SITP_BACKFILL_DAYS)
    new_term = ClassSession.objects.filter(batch=batch, session_date__gte=window_start)
    assert new_term.count() == later.counts["class_session"] >= 25
    # Every week of the term that is running has a class in it — including the
    # week containing the day the command ran.
    day = window_start
    while day <= batch.end_date - weeks:
        assert ClassSession.objects.filter(
            batch=batch, session_date__gte=day, session_date__lt=day + weeks
        ).exists(), f"no class in the week of {day}"
        day += weeks
    # And the curriculum is planted on the term now running, not left on the
    # one that ended: the same two lessons, on classes inside this window.
    assert later.counts["session_plan"] == 2
    assert new_term.filter(planned_lesson__isnull=False).count() == 2

    # A second run on that far day is still a no-op.
    far_again = _ctx_on(far)
    _extend_imported(far_again, batch, admin_user)
    assert not any(far_again.counts.values()), far_again.counts


@pytest.mark.django_db
def test_the_one_off_class_today_does_not_double_book_the_trainer(
    admin_user, branch, trainer_profile, published_course
):
    """``create_session`` checks no diary, so this stage checks it.

    ``create_schedule`` refuses a slot that puts a trainer in two rooms at
    once; the one-off class that keeps "a class today" true on a later day
    goes straight to the model, whose only uniqueness is
    ``(batch, date, start_time)``. A trainer teaching two of these batches can
    be asked for the same two hours twice — so the hour moves, the way a
    clashing weekly slot does.
    """
    today = timezone.localdate()
    ctx = _ctx_on(today, hour=15, minute=30)
    spec = SPEC_BY_KEY["a2"]
    batches = [
        create_batch(
            actor=admin_user,
            branch=branch,
            name=f"Booked cohort {index}",
            course=published_course,
            trainer=trainer_profile,
            start_date=today - timedelta(days=14),
            end_date=today + timedelta(days=56),
            capacity=20,
        )
        for index in (1, 2)
    ]
    for batch in batches:
        set_batch_status(batch=batch, target=BatchStatus.ACTIVE, actor=admin_user)
    # The trainer is already teaching 14:30-16:30 today, which is exactly the
    # hour a "started" clock slot asks for at 15:30.
    create_session(
        batch=batches[0],
        actor=admin_user,
        session_date=today,
        start_time=time(14, 30),
        end_time=time(16, 30),
        timezone_name=TZ,
        location="Lab 1",
    )

    _ensure_today(ctx, batches[1], admin_user, spec)

    added = ClassSession.objects.get(batch=batches[1], session_date=today)
    assert added.start_time <= ctx.now.time(), "a class today that has not started"
    assert added.end_time <= time(14, 30) or added.start_time >= time(16, 30), (
        "the trainer is in two rooms at once"
    )
    assert ctx.counts["class_session"] == 1


def test_the_generation_window_is_clamped_to_what_the_service_accepts():
    """``generate_sessions`` refuses more than 366 days in one call, and a
    batch on a long-seeded database is wider than that.

    ``_redate`` widens ``end_date`` with the clock while the batch's first
    class pins ``start_date``, so a span grows a day per day of drift: a
    reviewer measured 608 days at day+400. The whole-range call would raise
    and take the stage with it, so the window keeps its most recent 366 days —
    today's class and the term that is running are the part every screen
    reads. Arithmetic: no database.
    """
    day = date(2026, 9, 27)
    ctx = _ctx_on(day)
    batch = Batch(
        code="GRS-B-09999",
        start_date=day - timedelta(days=520),
        end_date=day + timedelta(days=84),
    )
    window = _window(ctx, batch, None, None)
    assert window is not None
    first, last = window
    assert (last - first).days == MAX_GENERATION_DAYS
    assert last == batch.end_date
    assert first <= day <= last, "the window must cover the day the command runs"

    batch.start_date = day - timedelta(days=42)
    assert _window(ctx, batch, None, None) == (batch.start_date, batch.end_date)
    asked = (day - timedelta(days=200), day + timedelta(days=200))
    assert _window(ctx, batch, *asked) == (batch.start_date, batch.end_date)
    assert _window(ctx, batch, day + timedelta(days=200), day + timedelta(days=300)) is None


@pytest.mark.parametrize("kind", ["started", "later"])
@pytest.mark.parametrize("hour", [0, 6, 12, 19, 21, 22, 23])
@pytest.mark.parametrize("minute", [0, 2, 50])
def test_clock_time_always_fits_inside_the_day(kind, hour, minute):
    """A clock slot always asks for a two-hour class that begins and ends on
    the same day and on the right side of now, whatever time the command runs.

    The "started" branch used to return ``now - 1h`` with no upper clamp, and
    ``_ensure_today`` feeds that straight to ``create_session``: after 22:55
    the class ended tomorrow, ``ClassSession.clean`` refused it and the whole
    command stopped on stage 4. The minutes matter as much as the hours, and
    only :50 was tried here: in the first five minutes of the day an hour ago
    was yesterday, the floor was 00:05, and the "started" class was three
    minutes in the *future* — which cannot be marked, so the headline
    trainer's Today screen was empty for anybody running the seed at 00:02.
    No database needed — this is arithmetic.
    """
    day = date(2026, 9, 27)
    ctx = Context(
        password=SEED_PASSWORD,
        out=lambda line: None,
        today=day,
        now=timezone.make_aware(datetime.combine(day, time(hour, minute))),
    )
    spec = next(s for s in SPECS if s.today == kind)
    wanted, shifts = _clock_time(ctx, spec)
    assert EARLIEST_START <= wanted <= LATEST_START
    assert _plus_hours(wanted, CLASS_HOURS) > wanted, "the class would end tomorrow"
    if shifts is SHIFTS_EARLIER:
        assert wanted <= ctx.now.time(), "a 'started' class that has not started"
    else:
        assert wanted > ctx.now.time(), "a 'later' class that is already over"
