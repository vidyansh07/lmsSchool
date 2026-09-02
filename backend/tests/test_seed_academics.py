"""The academic seeder is safe, converges, and produces a usable demo.

"Usable" is the point of most of these: a demo environment where the register
cannot be taken, or where nothing has been handed in, demonstrates nothing.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.academics.models import AcademicPolicy, PolicyScope
from apps.assessments.models import Assessment, AssessmentDelivery, AssessmentStatus
from apps.assignments.models import Assignment, AssignmentStatus, AssignmentSubmission
from apps.attendance.models import AttendanceRecord
from apps.sessions.models import ClassSession

SEED_PASSWORD = "Staging-Demo-Passw0rd!"


def _prerequisites() -> None:
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")
    call_command("seed_courses")
    call_command("seed_batches")


@pytest.mark.django_db
def test_the_seeder_creates_classes_attendance_work_and_tests():
    _prerequisites()
    call_command("seed_academics")

    assert ClassSession.objects.exists()
    assert AttendanceRecord.objects.exists()
    assert Assignment.objects.exists()
    assert AssignmentSubmission.objects.exists()
    assert Assessment.objects.exists()


@pytest.mark.django_db
def test_every_active_batch_has_a_class_today_that_can_be_marked():
    """Otherwise the trainer's main screen is disabled in the demo."""
    _prerequisites()
    call_command("seed_academics")

    today = timezone.localdate()
    todays = ClassSession.objects.filter(session_date=today)
    assert todays.exists()
    assert any(session.can_take_attendance for session in todays)


@pytest.mark.django_db
def test_todays_register_is_left_unmarked_for_the_demo():
    """The point of the demo is taking a register, not reading one."""
    _prerequisites()
    call_command("seed_academics")

    today = timezone.localdate()
    markable = [
        session
        for session in ClassSession.objects.filter(session_date=today)
        if session.can_take_attendance
    ]
    assert markable
    assert any(not session.attendance.exists() for session in markable)


@pytest.mark.django_db
def test_both_marking_paths_have_something_in_them():
    _prerequisites()
    call_command("seed_academics")

    # Something published and open, so a student can hand in.
    assert Assignment.objects.filter(status=AssignmentStatus.PUBLISHED).exists()
    # Something already graded, so the student's grade view is not empty.
    assert AssignmentSubmission.objects.filter(status="graded").exists()
    # And a draft, so the publish step is demonstrable.
    assert Assignment.objects.filter(status=AssignmentStatus.DRAFT).exists()


@pytest.mark.django_db
def test_a_weekly_test_is_ready_for_a_result_import():
    _prerequisites()
    call_command("seed_academics")

    test = Assessment.objects.filter(delivery=AssessmentDelivery.EXTERNAL_LINK).first()
    assert test is not None
    assert test.status == AssessmentStatus.PUBLISHED
    assert test.external_url.startswith("https://")
    # No results yet — importing them is the journey being demonstrated.
    assert not test.results.exists()


@pytest.mark.django_db
def test_the_academic_rules_are_set_explicitly():
    _prerequisites()
    call_command("seed_academics")

    policy = AcademicPolicy.objects.get(scope=PolicyScope.GLOBAL)
    assert policy.minimum_attendance_percent is not None
    assert policy.passing_percent is not None


@pytest.mark.django_db
def test_the_seeder_converges_and_never_double_marks():
    _prerequisites()
    call_command("seed_academics")
    call_command("seed_academics")
    call_command("seed_academics")

    assignments = Assignment.objects.count()
    call_command("seed_academics")
    assert Assignment.objects.count() == assignments

    # One record per student per class, always.
    pairs = AttendanceRecord.objects.values_list("session_id", "enrollment_id")
    assert len(set(pairs)) == len(pairs)


@pytest.mark.django_db
def test_the_seeder_requires_its_prerequisites():
    with pytest.raises(CommandError, match="seed_demo_data"):
        call_command("seed_academics")


@pytest.mark.django_db
def test_the_seeder_is_blocked_where_demo_data_is_not_allowed(settings):
    _prerequisites()
    settings.ALLOW_DEMO_SEED = False
    with pytest.raises(CommandError, match="must never run against production"):
        call_command("seed_academics")


@pytest.mark.django_db
def test_a_seeded_student_can_read_their_own_attendance(api_client_no_csrf):
    _prerequisites()
    call_command("seed_academics")

    record = AttendanceRecord.objects.select_related("enrollment__student__user").first()
    assert record is not None

    api_client_no_csrf.force_login(record.enrollment.student.user)
    body = api_client_no_csrf.get("/api/v1/attendance/mine/").json()

    assert body
    from apps.academics.policies import policy_for

    summary = body[0]["summary"]
    # The requirement travels with the counts, and reflects the configured rule
    # rather than a constant — the seeder relaxes it so the approval queue is
    # reachable in a demo.
    policy = policy_for(record.enrollment.course_id)
    assert "minimum_percent" in summary
    assert summary["required"] == policy.attendance_required_for_completion


# ---------------------------------------------------------------------------
# Phase 5 additions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_seeder_leaves_a_project_waiting_to_be_reviewed():
    """Both sides of the review loop need something in them to demonstrate."""
    from apps.projects.models import Project, ProjectStatus, StudentProject, WorkStatus

    _prerequisites()
    call_command("seed_academics")

    assert Project.objects.filter(status=ProjectStatus.PUBLISHED).exists()
    # Assigned to a cohort, and at least one already handed in.
    assert StudentProject.objects.filter(status=WorkStatus.ASSIGNED).exists()
    assert StudentProject.objects.filter(status=WorkStatus.SUBMITTED).exists()


@pytest.mark.django_db
def test_the_seeder_stocks_the_question_bank_and_publishes_an_exam():
    from apps.exams.models import Exam, ExamStatus
    from apps.exams.services import check_readiness
    from apps.questions.models import Question, QuestionType

    _prerequisites()
    call_command("seed_academics")

    assert Question.objects.filter(question_type=QuestionType.MCQ).count() >= 10
    assert Question.objects.filter(question_type=QuestionType.LONG_ANSWER).exists()

    exam = Exam.objects.filter(status=ExamStatus.PUBLISHED).first()
    assert exam is not None
    # An examination that cannot draw a paper demonstrates nothing.
    assert check_readiness(exam)["ready"] is True
    assert exam.is_open is True
    # Results are withheld, because releasing them is part of the journey.
    assert exam.results_published is False


# ---------------------------------------------------------------------------
# Phase 6 additions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_seeder_creates_a_certificate_template():
    """Nothing can be issued without one, so the demo would dead-end."""
    from apps.certificates.models import CertificateTemplate

    _prerequisites()
    call_command("seed_academics")

    template = CertificateTemplate.objects.get(is_default=True)
    assert template.institution_name
    assert "{student_name}" in template.body


@pytest.mark.django_db
def test_the_seeder_leaves_students_waiting_for_approval():
    """Both halves of the completion story have to be present.

    An approval queue nobody can reach demonstrates nothing — so most students
    are left eligible and undecided, and approving one is the journey being
    demonstrated.

    §15.5 also asks for issued certificates, which cannot exist without an
    approved completion behind them. So exactly the two needed for those are
    approved, and the queue still has people waiting in it. Asserting "nothing
    is approved" would have been simpler and would have meant a demo
    environment with a certificate template and no certificate.
    """
    from apps.certificates.models import Certificate
    from apps.progress.models import CompletionStatus, CourseCompletion

    _prerequisites()
    call_command("seed_academics")

    waiting = CourseCompletion.objects.filter(status=CompletionStatus.ELIGIBLE).count()
    approved = CourseCompletion.objects.filter(status=CompletionStatus.APPROVED).count()

    assert waiting > 0, "nobody is left in the approval queue"
    assert approved == Certificate.objects.count(), (
        "every approval should be there to carry a certificate"
    )
    assert waiting > approved, "the queue should still be the bigger half"


# ---------------------------------------------------------------------------
# Phase 7 additions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_seeder_puts_something_on_the_noticeboard():
    from apps.announcements.models import Announcement, AnnouncementStatus

    _prerequisites()
    call_command("seed_academics")

    assert Announcement.objects.filter(status=AnnouncementStatus.PUBLISHED).exists()


@pytest.mark.django_db
def test_the_seeder_leaves_an_answered_discussion():
    """Both sides of the feature, so neither screen is empty on a first visit."""
    from apps.discussions.models import Thread

    _prerequisites()
    call_command("seed_academics")

    thread = Thread.objects.filter(has_trainer_reply=True).first()
    assert thread is not None
    assert thread.reply_count >= 1


@pytest.mark.django_db
def test_the_seeder_survives_a_batch_with_no_timetable():
    """A seeder that dies part-way leaves an environment nobody can trust.

    `generate_sessions` refuses a batch with no weekly pattern — correctly,
    there is nothing to generate from. Letting that refusal escape meant one
    such batch stopped the whole command at batch three, leaving a database that
    was neither empty nor seeded, and a re-run that failed in the same place.
    """
    from apps.batches.models import Batch, BatchSchedule

    _prerequisites()

    # Strip every timetable, which is the shape that broke it.
    BatchSchedule.objects.all().delete()
    assert Batch.objects.exists()

    call_command("seed_academics")  # must not raise

    # And the rest of the seed still happened.
    from apps.assessments.models import Assessment

    assert Assessment.objects.exists(), "the seeder gave up before the weekly tests"
