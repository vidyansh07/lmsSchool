"""Stage 6 of the showcase: every past showcase class held — registers with
corrections, topics, daily status reports in every state, lesson progress,
bookmarks and notes, trainer requirements — and a second run that creates
nothing.

Runs the command up to and including ``academics`` on the empty test
database, twice, with every on-commit hook executed so the risk recomputes
the registers owe actually happen. There are no SITP rows here, so the
imported part is proved to be a clean no-op. One test runs the command
twice and checks everything: the five stages make a hundred accounts, a
catalogue, fifteen batches with their classes and then hold three hundred
of them, and a run per promise would put the file far over its time budget.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import models
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.attendance.models import (
    COUNTS_AS_PRESENT,
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceStatus,
)
from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import Batch, BatchStatus
from apps.common.showcase.context import MARKER
from apps.common.showcase.stages.s04_batches import SPECS
from apps.common.showcase.stages.s06_academics import (
    CORRECTIONS,
    HEADLINE_FRACTION,
    RECENT_DSR_STATES,
    REQUIREMENTS,
)
from apps.courses.models import Lesson, PublishStatus
from apps.dsr.models import DSR, DSRStatus
from apps.enrollments.models import Enrollment, EnrollmentStatus, LessonProgress
from apps.enrollments.models import LessonProgressStatus as Progress
from apps.learning.models import LessonBookmark, LessonNote
from apps.performance.models import RiskState
from apps.requirements.models import RequirementReply, RequirementStatus, TrainerRequirement
from apps.sessions.models import ClassSession, SessionStatus, TopicStatus
from apps.students.models import StudentProfile

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches,academics"

#: The labels this stage counts on every run. The second run must show
#: created 0 for each. ``session_in_progress`` is not here: it exists only
#: while a showcase class is under way on the clock, so it is checked apart.
LABELS = (
    "attendance_register",
    "attendance_record",
    "attendance_correction",
    "session_completed",
    "session_cancelled",
    "session_rescheduled",
    "session_topic",
    "dsr",
    "lesson_progress",
    "lesson_bookmark",
    "lesson_note",
    "requirement",
    "requirement_reply",
    "requirement_closed",
)

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks) -> str:
    """The command up to ``academics``, with every on-commit hook executed."""
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    """Everything the stage may touch, and the things it must not."""
    return {
        "sessions": ClassSession.objects.count(),
        **{
            f"sessions_{status}": ClassSession.objects.filter(status=status).count()
            for status in SessionStatus.values
        },
        **{
            f"topics_{status}": ClassSession.objects.filter(topic_status=status).count()
            for status in TopicStatus.values
        },
        "marks": AttendanceRecord.objects.count(),
        "corrections": AttendanceCorrection.objects.count(),
        "dsrs": DSR.all_objects.count(),
        **{
            f"dsrs_{status}": DSR.objects.filter(status=status).count()
            for status in DSRStatus.values
        },
        "progress": LessonProgress.objects.count(),
        "progress_completed": LessonProgress.objects.filter(status=Progress.COMPLETED).count(),
        "bookmarks": LessonBookmark.objects.count(),
        "notes": LessonNote.objects.count(),
        "requirements": TrainerRequirement.objects.count(),
        "replies": RequirementReply.objects.count(),
        # Outside the contract: nothing here may move.
        "users": User.objects.count(),
        "batches": Batch.objects.count(),
        "students": StudentProfile.objects.count(),
        **{
            f"enrolments_{status}": Enrollment.objects.filter(status=status).count()
            for status in EnrollmentStatus.values
        },
        "lessons": Lesson.objects.count(),
    }


def by_key() -> dict[str, Batch]:
    by_name = {
        batch.name: batch
        for batch in Batch.objects.filter(description__startswith=MARKER).select_related(
            "trainer__user", "course", "branch"
        )
    }
    return {spec.key: by_name[spec.name] for spec in SPECS if spec.name in by_name}


def ended(session: ClassSession, now) -> bool:
    return session.session_date < now.date() or session.ends_at <= now


def attendance_percent(batch: Batch) -> float:
    marks = list(
        AttendanceRecord.objects.filter(session__batch=batch)
        .counted()
        .values_list("status", flat=True)
    )
    return 100 * sum(1 for s in marks if s in COUNTS_AS_PRESENT) / len(marks) if marks else 0.0


@pytest.mark.django_db
def test_academics_stage_builds_every_state_and_is_idempotent(
    django_capture_on_commit_callbacks,
):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table[label][0] == 0, f"second run created {label}: {table[label]}"
        assert table[label][1] > 0, f"second run found no {label}"
    if "session_in_progress" in table:
        assert table["session_in_progress"][0] == 0, "second run re-started a class"
    assert counts() == after_first
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"
        assert rows(first)[label][1] == 0, f"first run found {label} on an empty database"
    assert "imported batches: none on this database" in first
    assert "imported batches: none on this database" in second
    assert SEED_PASSWORD not in first + second

    today = timezone.localdate()
    now = timezone.localtime()
    batches = by_key()
    showcase = ClassSession.objects.filter(batch__description__startswith=MARKER)
    past = [s for s in showcase.select_related("batch") if ended(s, now)]
    held = [s for s in past if s.status == SessionStatus.COMPLETED]
    assert len(past) >= 250, "the four stages in front made fewer classes than expected"

    # --- Session statuses: every ended class is held, cancelled or moved ----
    assert not any(s.status == SessionStatus.SCHEDULED for s in past), "a past class left unheld"
    assert not showcase.filter(status=SessionStatus.COMPLETED, session_date__gt=today).exists(), (
        "a future class marked held"
    )
    cancelled = showcase.filter(status=SessionStatus.CANCELLED)
    assert cancelled.count() == 1
    assert cancelled.get().batch_id == batches["a3"].pk
    assert cancelled.get().cancellation_reason.startswith(f"{MARKER}[cancel/a3]")
    assert not AttendanceRecord.objects.filter(session=cancelled.get()).exists()
    moved = showcase.filter(status=SessionStatus.RESCHEDULED)
    assert moved.count() == 1
    original = moved.select_related("rescheduled_to").get()
    assert original.batch_id == batches["a1"].pk
    assert original.cancellation_reason.startswith(f"{MARKER}[resched/a1]")
    assert original.session_date >= today + timedelta(days=7)
    assert original.rescheduled_to.status == SessionStatus.SCHEDULED
    assert original.rescheduled_to.session_date > original.session_date
    assert original.rescheduled_to.start_time == original.start_time
    under_way = [
        s
        for s in showcase.filter(session_date=today)
        if s.starts_at <= now < s.ends_at and s.status != SessionStatus.CANCELLED
    ]
    assert {s.pk for s in under_way} == set(
        showcase.filter(status=SessionStatus.IN_PROGRESS).values_list("pk", flat=True)
    ), "exactly the classes under way on the clock are in progress"
    later_today = showcase.filter(session_date=today, start_time__gt=now.time())
    assert set(later_today.values_list("status", flat=True)) <= {SessionStatus.SCHEDULED}

    # --- Registers: on most held classes, by the trainer, backdated ---------
    without = [s for s in held if s.attendance_taken_at is None]
    assert 0.04 <= len(without) / len(held) <= 0.14, f"{len(without)} of {len(held)} unregistered"
    assert not AttendanceRecord.objects.filter(session__in=without).exists()
    marks = AttendanceRecord.objects.filter(session__batch__description__startswith=MARKER)
    assert rows(first)["attendance_record"] == (marks.count(), 0)
    assert not AttendanceRecord.objects.exclude(pk__in=marks).exists(), "a mark off the showcase"
    assert set(marks.values_list("status", flat=True)) == set(AttendanceStatus.values)
    assert marks.filter(status=AttendanceStatus.LATE).exclude(note="").exists()
    assert marks.filter(status=AttendanceStatus.EXCUSED).exclude(note="").exists()
    # A present mark carries no note — unless it was an absence corrected.
    assert not (
        marks.filter(status=AttendanceStatus.PRESENT, correction_reason="")
        .exclude(note="")
        .exists()
    )
    for mark in marks.select_related("session__trainer", "enrollment").iterator(chunk_size=500):
        session = mark.session
        assert session.status == SessionStatus.COMPLETED
        assert mark.marked_by_id == session.trainer.user_id, "the register is the trainer's"
        assert timezone.localtime(mark.marked_at).date() == session.session_date, "not backdated"
        assert mark.marked_at <= now
        assert mark.created_at == mark.marked_at
        assert timezone.localtime(mark.enrollment.enrolled_at).date() <= session.session_date
    for session in held:
        if session.attendance_taken_at is not None:
            assert session.attendance_taken_by_id == session.trainer.user_id
            assert timezone.localtime(session.attendance_taken_at).date() == session.session_date

    # --- Attendance tuned per batch: most above the 75 % rule, some well under
    rates = {
        key: attendance_percent(batch)
        for key, batch in batches.items()
        if AttendanceRecord.objects.filter(session__batch=batch).exists()
    }
    assert len(rates) >= 9
    assert sum(1 for r in rates.values() if r >= 75) >= round(len(rates) * 0.55)
    assert sum(1 for r in rates.values() if r < 75) >= 3
    assert sum(1 for r in rates.values() if r < 70) >= 2, rates
    # Chronic absentees: on a batch with a term behind it, some students sit
    # far below their classmates.
    a4 = batches["a4"]
    per_student: dict = {}
    for mark in AttendanceRecord.objects.filter(session__batch=a4).counted():
        per_student.setdefault(mark.enrollment_id, []).append(mark.status in COUNTS_AS_PRESENT)
    student_rates = sorted(100 * sum(v) / len(v) for v in per_student.values() if len(v) >= 10)
    assert student_rates and student_rates[0] < 65, student_rates
    assert student_rates[-1] > 85, student_rates
    assert student_rates[-1] - student_rates[0] > 25, student_rates

    # --- Corrections: absent turned present, with a reason and history ------
    corrected = marks.filter(correction_reason__startswith=f"{MARKER}[correction]")
    assert corrected.count() == sum(CORRECTIONS.values())
    assert rows(first)["attendance_correction"] == (corrected.count(), 0)
    assert set(corrected.values_list("session__batch_id", flat=True)) == {
        batches[key].pk for key in CORRECTIONS
    }
    for mark in corrected.select_related("session"):
        assert mark.previous_status == AttendanceStatus.ABSENT
        assert mark.status == AttendanceStatus.PRESENT
        assert mark.corrected_by_id == mark.session.trainer.user_id
        assert mark.corrected_at > mark.marked_at
        assert mark.corrected_at <= now
        history = list(mark.corrections.all())
        assert len(history) == 1
        assert (history[0].from_status, history[0].to_status) == ("absent", "present")
        assert history[0].reason == mark.correction_reason
        assert history[0].created_at == mark.corrected_at
    assert AttendanceCorrection.objects.count() == corrected.count()

    # --- Topics: every held class records what it covered, at a pace -------
    assert not any(s.topic_status == TopicStatus.PLANNED for s in held)
    assert any(s.topic_status == TopicStatus.SKIPPED for s in held), "no revision class"
    for session in held:
        if session.topic_status == TopicStatus.COMPLETED:
            assert session.actual_lesson_id is not None
            assert session.actual_lesson.module.course_id == session.batch.course_id
        else:
            assert session.actual_lesson_id is None
    for key in ("c1", "c2", "x1", "pc1"):
        batch = batches[key]
        published = Lesson.objects.filter(
            module__course_id=batch.course_id,
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        ).count()
        covered = (
            ClassSession.objects.filter(batch=batch, actual_lesson__isnull=False)
            .values("actual_lesson_id")
            .distinct()
            .count()
        )
        assert covered == published, f"finished batch {key} covered {covered}/{published}"
    running = {
        key: ClassSession.objects.filter(batch=batches[key], actual_lesson__isnull=False)
        .values("actual_lesson_id")
        .distinct()
        .count()
        for key in ("a2", "a3", "a4")
    }
    assert 0 < running["a2"] < 9 and 0 < running["a3"] < 9, running
    assert running["a4"] > running["a2"], "the internship is further on than the newer cohort"
    assert (
        AuditLog.objects.filter(action=AuditAction.SESSION_TOPIC_RECORDED).count()
        == rows(first)["session_topic"][0]
    )

    # --- Daily status reports: by the trainer, reviewed by the manager -----
    reports = DSR.objects.filter(batch__description__startswith=MARKER).select_related(
        "session__trainer", "trainer", "reviewed_by"
    )
    assert rows(first)["dsr"] == (reports.count(), 0)
    assert not DSR.all_objects.exclude(pk__in=reports).exists()
    by_status = {status: reports.filter(status=status).count() for status in DSRStatus.values}
    for status, wanted in RECENT_DSR_STATES:
        assert by_status[status] == wanted, (status, by_status)
    assert by_status[DSRStatus.APPROVED] > 100
    reportable = [s for s in held if s.trainer_id]
    with_report = set(reports.values_list("session_id", flat=True))
    missing = [s for s in reportable if s.pk not in with_report]
    assert 0.05 <= len(missing) / len(reportable) <= 0.20, f"{len(missing)} of {len(reportable)}"
    dates = sorted(reports.values_list("report_date", flat=True), reverse=True)
    drafts = reports.filter(status=DSRStatus.DRAFT)
    assert min(drafts.values_list("report_date", flat=True)) >= dates[9], "drafts are the newest"
    for dsr in reports:
        session = dsr.session
        assert session.status == SessionStatus.COMPLETED
        assert dsr.trainer_id == session.trainer_id, "the report is the class's trainer's"
        assert dsr.report_date == session.session_date
        assert dsr.actual_topic and dsr.planned_topic and dsr.teaching_notes
        assert dsr.created_at <= now
        assert timezone.localtime(dsr.created_at).date() == session.session_date
        if dsr.status == DSRStatus.DRAFT:
            assert dsr.submitted_at is None and dsr.reviewed_at is None
            continue
        assert dsr.submitted_at is not None
        assert timezone.localtime(dsr.submitted_at).date() == session.session_date
        assert dsr.submitted_at <= now
        if dsr.status == DSRStatus.SUBMITTED:
            assert dsr.reviewed_at is None and dsr.reviewed_by_id is None
            continue
        assert dsr.reviewed_at is not None and dsr.reviewed_at > dsr.submitted_at
        assert dsr.reviewed_at <= now
        assert dsr.reviewed_by.role == UserRole.MANAGER, "a manager reviews, never the trainer"
        assert dsr.reviewed_by.branch_id == session.batch.branch_id
        if dsr.status in (DSRStatus.REJECTED, DSRStatus.REVISION_REQUIRED):
            assert dsr.manager_comments.strip(), "sent back without a reason"
    assert AuditLog.objects.filter(action=AuditAction.DSR_CREATED).count() == reports.count()
    assert AuditLog.objects.filter(action=AuditAction.DSR_REJECTED).count() == 3
    assert AuditLog.objects.filter(action=AuditAction.DSR_REVISION_REQUESTED).count() == 3

    # --- Learning state: only where access is granted, spread over time ----
    progress = LessonProgress.objects.select_related("enrollment__batch", "lesson__module")
    assert rows(first)["lesson_progress"] == (progress.count(), 0)
    for row in progress:
        assert row.enrollment.grants_access(), "progress on an enrolment without access"
        assert row.lesson.module.course_id == row.enrollment.course_id
        assert row.first_accessed_at <= row.last_accessed_at <= now
        assert row.first_accessed_at >= row.enrollment.enrolled_at - timedelta(days=1)
        assert row.created_at == row.first_accessed_at
        if row.status == Progress.COMPLETED:
            assert row.completed_at == row.last_accessed_at
        else:
            assert row.completed_at is None
    assert not LessonProgress.objects.filter(
        enrollment__batch__status=BatchStatus.UPCOMING
    ).exists()
    headline = StudentProfile.objects.get(user__email="student@grras.com")
    mine = Enrollment.objects.get(student=headline, batch=batches["a2"])
    lessons = Lesson.objects.filter(
        module__course_id=mine.course_id,
        module__status=PublishStatus.PUBLISHED,
        status=PublishStatus.PUBLISHED,
    ).count()
    done = LessonProgress.objects.filter(enrollment=mine, status=Progress.COMPLETED).count()
    assert done == round(HEADLINE_FRACTION * lessons)
    opened = LessonProgress.objects.get(enrollment=mine, status=Progress.IN_PROGRESS)
    assert timezone.localtime(opened.last_accessed_at).date() == today - timedelta(days=1)
    # Over every active showcase enrolment (a single batch is too few students
    # for shares of a few per cent): some finished, some barely started, some
    # nothing at all, and the rest spread between.
    published = {
        course_id: Lesson.objects.filter(
            module__course_id=course_id,
            module__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        ).count()
        for course_id in Batch.objects.filter(
            description__startswith=MARKER, status=BatchStatus.ACTIVE
        ).values_list("course_id", flat=True)
    }
    done_by_enrolment = dict(
        LessonProgress.objects.filter(status=Progress.COMPLETED)
        .values_list("enrollment_id")
        .annotate(n=models.Count("pk"))
        .values_list("enrollment_id", "n")
    )
    fractions = [
        done_by_enrolment.get(row.pk, 0) / published[row.course_id]
        for row in Enrollment.objects.filter(
            batch__description__startswith=MARKER,
            batch__status=BatchStatus.ACTIVE,
            status=EnrollmentStatus.ACTIVE,
        )
        if published.get(row.course_id)
    ]
    assert len(fractions) >= 80
    assert sum(1 for f in fractions if f == 0) >= 3, "nobody has opened nothing"
    assert sum(1 for f in fractions if 0 < f <= 0.12) >= 3, "nobody barely started"
    assert sum(1 for f in fractions if f == 1.0) >= 2, "nobody finished"
    assert len({round(f, 1) for f in fractions}) >= 5, "progress does not vary"

    bookmarks = LessonBookmark.objects.select_related("enrollment")
    assert rows(first)["lesson_bookmark"] == (bookmarks.count(), 0)
    assert bookmarks.filter(enrollment=mine).exclude(note="").count() == 2
    assert bookmarks.exclude(enrollment=mine).exists(), "no classmate bookmarked anything"
    notes = LessonNote.objects.all()
    assert rows(first)["lesson_note"] == (notes.count(), 0)
    assert notes.filter(enrollment=mine).count() >= 2
    assert notes.exclude(enrollment__student=headline).exists()
    for row in list(bookmarks) + list(notes):
        assert row.lesson.module.course_id == row.enrollment.course_id
        assert row.created_at < now - timedelta(days=1), "not backdated"

    # --- Requirements: raised by trainers, answered, settled ----------------
    requirements = TrainerRequirement.objects.select_related("raised_by", "fulfilled_by__user")
    assert requirements.count() == len(REQUIREMENTS)
    assert not TrainerRequirement.objects.exclude(details__startswith=f"{MARKER}[req/").exists()
    statuses = sorted(requirements.values_list("status", flat=True))
    assert statuses == [
        RequirementStatus.CLOSED,
        RequirementStatus.FULFILLED,
        RequirementStatus.OPEN,
        RequirementStatus.OPEN,
    ]
    for requirement in requirements:
        assert requirement.raised_by.role == UserRole.TRAINER
        assert requirement.branch_id == requirement.raised_by.branch_id
        assert requirement.needed_by is not None and requirement.needed_by >= today
        assert requirement.created_at < now - timedelta(days=2), "raised today"
        if requirement.is_open:
            assert requirement.closed_at is None
        else:
            assert requirement.closed_at is not None
            assert requirement.closed_at > requirement.created_at
            assert requirement.closed_by is not None and requirement.closing_note
    on_batch = requirements.filter(batch__isnull=False)
    assert on_batch.count() == 1 and on_batch.get().batch_id == batches["a2"].pk
    fulfilled = requirements.get(status=RequirementStatus.FULFILLED)
    assert fulfilled.fulfilled_by.user.email == "rohit.kumawat@grras.com"
    assert requirements.get(status=RequirementStatus.CLOSED).fulfilled_by is None
    replies = RequirementReply.objects.select_related("author", "requirement")
    assert replies.count() == sum(len(spec.replies) for spec in REQUIREMENTS)
    assert {r.author.role for r in replies} >= {UserRole.MANAGER, UserRole.ADMIN}
    for reply in replies:
        assert reply.created_at > reply.requirement.created_at
    assert (
        AuditLog.objects.filter(action=AuditAction.REQUIREMENT_RAISED).count()
        == requirements.count()
    )

    # --- Risk: one recompute per student on a register, at commit ----------
    on_register = set(marks.values_list("enrollment_id", flat=True))
    assert RiskState.objects.filter(enrollment_id__in=on_register).count() == len(on_register)
    levels = set(RiskState.objects.values_list("level", flat=True))
    assert levels == {"none", "warning", "critical"}, levels
    critical = RiskState.objects.filter(level="critical").count()
    assert critical < RiskState.objects.count() * 0.4, "most of the institute is critical"
    assert "risk recomputes:" in first
    assert "risk recomputes:" not in second, "a second run recomputed with nothing changed"
