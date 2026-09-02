"""Seed Phase 4 academic operations: classes, attendance, work and tests.

Same safety rules as the other seeders — refuses to run anywhere demo data is
not allowed, and is idempotent.

What it produces, and why each piece is here:

* **Class sessions** for every active batch, generated from its timetable, plus
  one class **today that has already started** — because the register cannot be
  taken before a class begins, and a demo environment where the main screen is
  disabled demonstrates nothing.
* **A marked register** on an earlier class, and an **unmarked** one today, so
  both the "take it" and the "review it" paths are reachable.
* **Assignments** in draft and published, one already submitted and graded and
  one still open, so the marking queue and the student's hand-in form both have
  something in them.
* **A weekly test** delivered as an external link with no results yet, which is
  what the result-import journey starts from.
* **Academic rules**, set explicitly rather than left to the code defaults, so
  the configuration screen shows real values.
* **Projects** — one published and assigned, one already handed in and awaiting
  review, so both sides of the review loop have something in them.
* **A question bank and a published examination**, because an examination that
  cannot draw a paper is an examination nobody can demonstrate.
* **A certificate template**, and completion rules relaxed enough that a seeded
  student is actually eligible — the approval-and-certificate journey cannot be
  shown against a cohort nobody can complete.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.assessments.models import AssessmentDelivery, AssessmentStatus
from apps.assessments.services import create_assessment, set_assessment_status
from apps.assignments.models import Assignment, AssignmentStatus
from apps.assignments.services import (
    create_assignment,
    grade_submission,
    set_assignment_status,
    submit_assignment,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.attendance.services import mark_attendance, roster_for
from apps.batches.models import Batch, BatchStatus
from apps.common.exceptions import ApplicationError
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.sessions.models import ClassSession, SessionStatus
from apps.sessions.services import create_session, generate_sessions

#: A rotation, so a seeded register does not look like everyone was present.
ATTENDANCE_ROTATION = [
    AttendanceStatus.PRESENT,
    AttendanceStatus.PRESENT,
    AttendanceStatus.LATE,
    AttendanceStatus.ABSENT,
    AttendanceStatus.PRESENT,
    AttendanceStatus.EXCUSED,
]


#: Enough for a paper, and varied enough that the bank screen is worth looking
#: at. Written out rather than generated so the text reads sensibly.
QUESTION_SEEDS: list[tuple[str, list[str], int]] = [
    ("Which command lists the files in a directory?", ["ls", "cd", "rm", "mv"], 0),
    ("Which command changes directory?", ["cd", "ls", "cat", "cp"], 0),
    ("Which command shows the current directory?", ["pwd", "dir", "here", "loc"], 0),
    ("Which command copies a file?", ["cp", "mv", "rm", "ln"], 0),
    ("Which command moves or renames a file?", ["mv", "cp", "touch", "stat"], 0),
    ("Which command creates an empty file?", ["touch", "mkdir", "echo", "make"], 0),
    ("Which command reports disk usage?", ["du", "ps", "top", "id"], 0),
    ("Which command shows running processes?", ["ps", "ls", "df", "wc"], 0),
    ("Which command counts lines in a file?", ["wc", "cut", "tr", "sed"], 0),
    ("Which command searches text in files?", ["grep", "find", "which", "type"], 0),
]


class Command(BaseCommand):
    help = "Create or refresh fake classes, attendance, assignments and tests (local/staging only)."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Academic seeding is disabled in the "
                f"{getattr(settings, 'ENVIRONMENT', 'unknown')} environment. "
                "This command must never run against production data."
            )

        admin = User.objects.filter(role=UserRole.ADMIN).order_by("email").first()
        if admin is None:
            raise CommandError("Run seed_demo_data, seed_courses and seed_batches first.")

        batches = list(
            Batch.objects.filter(status=BatchStatus.ACTIVE)
            .select_related("course", "trainer")
            .order_by("code")
        )
        if not batches:
            raise CommandError("No active batches. Run seed_batches first.")

        self._seed_rules(admin)
        generated = self._seed_sessions(admin, batches)
        marked = self._seed_attendance(admin, batches)
        assignments = self._seed_assignments(admin, batches)
        tests = self._seed_tests(admin, batches)
        projects = self._seed_projects(admin, batches)
        questions = self._seed_questions(admin, batches)
        exams = self._seed_exams(admin, batches)
        templates = self._seed_certificate_template(admin)
        results = self._seed_results(admin, batches)
        eligible = self._seed_completions(admin, batches)
        certificates = self._seed_certificates(admin, batches)
        announcements, threads = self._seed_communication(admin, batches)

        self.stdout.write(self.style.SUCCESS("Academic demo data ready."))
        self.stdout.write(f"  classes generated  : {generated}")
        self.stdout.write(f"  registers marked   : {marked}")
        self.stdout.write(f"  assignments        : {assignments}")
        self.stdout.write(f"  weekly tests       : {tests}")
        self.stdout.write(f"  projects           : {projects}")
        self.stdout.write(f"  questions          : {questions}")
        self.stdout.write(f"  examinations       : {exams}")
        self.stdout.write(f"  cert templates     : {templates}")
        self.stdout.write(f"  results recorded   : {results}")
        self.stdout.write(f"  completion-eligible: {eligible}")
        self.stdout.write(f"  certificates       : {certificates}")
        self.stdout.write(f"  announcements      : {announcements}")
        self.stdout.write(f"  discussions        : {threads}")

    # -- rules --------------------------------------------------------------

    def _seed_rules(self, admin) -> None:
        from apps.academics.services import get_or_create_policy, update_policy

        update_policy(
            policy=get_or_create_policy(),
            actor=admin,
            minimum_attendance_percent=Decimal("75.00"),
            passing_percent=Decimal("40.00"),
            assignment_default_max_marks=Decimal("100.00"),
            assignment_default_max_attempts=1,
            assignment_allow_late=True,
            minimum_assignment_completion_percent=Decimal("80.00"),
            test_default_max_marks=Decimal("20.00"),
            minimum_test_average_percent=Decimal("40.00"),
            minimum_lesson_completion_percent=Decimal("80.00"),
            # Deliberately permissive for the demo: an approval queue nobody can
            # reach demonstrates nothing. An institution sets its own on the
            # academic-rules screen.
            lessons_required_for_completion=False,
            attendance_required_for_completion=False,
            assignment_required_for_completion=False,
            tests_required_for_completion=False,
            projects_required_for_completion=False,
            final_exam_required_for_completion=False,
        )

    # -- classes ------------------------------------------------------------

    def _seed_sessions(self, admin, batches) -> int:
        """Generate classes for every batch that has a timetable to generate from.

        A batch without one is skipped rather than fatal. `generate_sessions`
        refuses it — correctly, since there is nothing to generate — and letting
        that refusal escape means one batch with no weekly pattern stops the
        whole seed part-way through, leaving an environment that is neither
        empty nor complete. A seeder has to be re-runnable, and a re-run that
        dies at batch three is not.
        """
        created = 0
        skipped = 0
        today = timezone.localdate()

        for batch in batches:
            try:
                result = generate_sessions(
                    batch=batch,
                    actor=admin,
                    start=max(batch.start_date, today - timedelta(days=28)),
                    end=min(batch.end_date, today + timedelta(days=28)),
                )
            except ApplicationError:
                skipped += 1
                continue
            created += result["created"]
            created += int(self._ensure_class_today(admin, batch, today))

        if skipped:
            self.stdout.write(f"  ({skipped} batch(es) have no timetable; no classes generated)")
        return created

    def _ensure_class_today(self, admin, batch: Batch, today) -> bool:
        """Give every active batch a class that has already started today.

        The register opens once a class begins, so a demo without one leaves the
        main trainer screen permanently disabled. The start time is derived from
        the clock at seed time rather than fixed, so this holds whenever it runs.
        """
        if ClassSession.objects.filter(batch=batch, session_date=today).exists():
            # Make sure at least one of today's classes is actually markable.
            started = ClassSession.objects.filter(
                batch=batch, session_date=today, status=SessionStatus.SCHEDULED
            ).order_by("start_time")
            for session in started:
                if session.starts_at <= timezone.now():
                    return False
            # All of today's classes are still in the future; add an early one.

        now = timezone.localtime()
        start_hour = max(0, min(now.hour - 2, 21))
        start = time(start_hour, 0)
        end = time(min(start_hour + 2, 23), 30 if start_hour + 2 > 23 else 0)

        try:
            create_session(
                batch=batch,
                actor=admin,
                session_date=today,
                start_time=start,
                end_time=end,
                topic=f"{batch.course.title}: today's class",
                location="Lab 1",
            )
        except ApplicationError:
            # A class already occupies that slot. Nothing to do.
            return False
        return True

    # -- attendance ---------------------------------------------------------

    def _seed_attendance(self, admin, batches) -> int:
        """Mark past registers, and leave today's unmarked for the demo."""
        marked = 0
        today = timezone.localdate()

        for batch in batches:
            past = ClassSession.objects.filter(
                batch=batch, session_date__lt=today, status=SessionStatus.SCHEDULED
            ).order_by("-session_date")[:6]
            actor = batch.trainer.user if batch.trainer else admin

            for offset, session in enumerate(past):
                if AttendanceRecord.objects.filter(session=session).exists():
                    continue
                roster = list(roster_for(session))
                if not roster:
                    continue
                entries = [
                    {
                        "enrollment_id": str(enrollment.pk),
                        "status": ATTENDANCE_ROTATION[(offset + index) % len(ATTENDANCE_ROTATION)],
                        "note": "",
                    }
                    for index, enrollment in enumerate(roster)
                ]
                mark_attendance(session=session, actor=actor, entries=entries)
                marked += 1

        return marked

    # -- assignments --------------------------------------------------------

    def _seed_assignments(self, admin, batches) -> int:
        created = 0
        now = timezone.now()

        for batch in batches[:3]:
            actor = batch.trainer.user if batch.trainer else admin

            open_work = self._assignment(
                actor=actor,
                batch=batch,
                title=f"{batch.course.title}: practical exercise",
                instructions=(
                    "Write a short script that solves the problem discussed in class, "
                    "and hand in the source file."
                ),
                due_at=now + timedelta(days=5),
                publish=True,
            )
            if open_work is not None:
                created += 1

            graded_work = self._assignment(
                actor=actor,
                batch=batch,
                title=f"{batch.course.title}: week one worksheet",
                instructions="Answer every question and hand in your working.",
                due_at=now - timedelta(days=3),
                publish=True,
            )
            if graded_work is not None:
                created += 1
                self._seed_submissions(graded_work, actor)

            draft = self._assignment(
                actor=actor,
                batch=batch,
                title=f"{batch.course.title}: draft brief (not yet published)",
                instructions="Still being written.",
                due_at=None,
                publish=False,
            )
            if draft is not None:
                created += 1

        return created

    def _assignment(self, *, actor, batch, title, instructions, due_at, publish):
        if Assignment.objects.filter(title=title, batch=batch).exists():
            return None
        work = create_assignment(
            actor=actor,
            course=batch.course,
            batch=batch,
            title=title,
            instructions=instructions,
            max_marks=Decimal("100.00"),
            due_at=due_at,
        )
        if publish:
            set_assignment_status(assignment=work, actor=actor, status=AssignmentStatus.PUBLISHED)
            work.refresh_from_db()
        return work

    def _seed_submissions(self, assignment, actor) -> None:
        """Hand in for a couple of students, and grade one of them."""
        enrollments = list(
            Enrollment.objects.filter(
                batch=assignment.batch, status=EnrollmentStatus.ACTIVE
            ).select_related("student", "student__user")[:3]
        )
        for index, enrollment in enumerate(enrollments):
            body = (
                f"# Submitted by {enrollment.student.student_id}\n"
                "def solve(values):\n    return sorted(values)\n"
            ).encode()
            upload = ContentFile(body, name="solution.py")
            upload.size = len(body)
            try:
                submission = submit_assignment(
                    assignment=assignment,
                    enrollment=enrollment,
                    actor=enrollment.student.user,
                    files=[upload],
                )
            except ApplicationError:
                continue
            if index == 0:
                grade_submission(
                    submission=submission,
                    actor=actor,
                    marks=Decimal("78.00"),
                    feedback="Clear and correct. Add a docstring next time.",
                )

    # -- weekly tests -------------------------------------------------------

    def _seed_tests(self, admin, batches) -> int:
        created = 0
        now = timezone.now()

        for batch in batches[:3]:
            actor = batch.trainer.user if batch.trainer else admin
            title = f"{batch.course.title}: week 1 test"
            if batch.assessments.filter(title=title).exists():
                continue

            test = create_assessment(
                actor=actor,
                batch=batch,
                title=title,
                description=(
                    "Taken on the linked form. Results are imported from the spreadsheet "
                    "the form produces."
                ),
                delivery=AssessmentDelivery.EXTERNAL_LINK,
                external_url="https://docs.google.com/forms/d/e/demo-weekly-test/viewform",
                external_provider="Google Forms",
                scheduled_for=now - timedelta(days=2),
                duration_minutes=45,
                max_marks=Decimal("20.00"),
            )
            set_assessment_status(assessment=test, actor=actor, status=AssessmentStatus.PUBLISHED)
            created += 1

        return created

    # -- projects -----------------------------------------------------------

    def _seed_projects(self, admin, batches) -> int:
        from apps.projects.models import Project, ProjectKind, ProjectStatus, WorkStatus
        from apps.projects.services import (
            assign_project,
            create_project,
            set_project_status,
            student_project_for,
            submit_project,
        )

        created = 0
        for batch in batches[:2]:
            actor = batch.trainer.user if batch.trainer else admin
            title = f"{batch.course.title}: build a small tool"
            if Project.objects.filter(title=title, batch=batch).exists():
                continue

            project = create_project(
                actor=actor,
                course=batch.course,
                batch=batch,
                title=title,
                description="A command-line tool that solves a real problem from the course.",
                instructions="Work alone. Hand in the source and a short README.",
                deliverables="Source code, a README, and a repository URL.",
                kind=ProjectKind.MAJOR,
                is_required=True,
                start_date=timezone.localdate() - timedelta(days=7),
                end_date=timezone.localdate() + timedelta(days=21),
                max_marks=Decimal("100.00"),
                passing_marks=Decimal("40.00"),
            )
            set_project_status(project=project, actor=actor, status=ProjectStatus.PUBLISHED)
            assign_project(project=project, actor=actor)
            created += 1

            # One student has already handed something in, so the review queue
            # is not empty on the first visit.
            enrollment = (
                Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.ACTIVE)
                .select_related("student__user")
                .first()
            )
            if enrollment is None:
                continue
            work = student_project_for(project=project, student=enrollment.student)
            if work is None or work.status != WorkStatus.ASSIGNED:
                continue
            body = b"#!/usr/bin/env python3\nprint('tool')\n"
            upload = ContentFile(body, name="tool.py")
            upload.size = len(body)
            try:
                submit_project(
                    work=work,
                    actor=enrollment.student.user,
                    repository_url="https://git.example.test/demo/tool",
                    notes="First cut. Tests to follow.",
                    files=[upload],
                )
            except ApplicationError:
                pass

        return created

    # -- question bank ------------------------------------------------------

    def _seed_questions(self, admin, batches) -> int:
        from apps.questions.models import Difficulty, Question, QuestionType
        from apps.questions.services import create_question

        created = 0
        for batch in batches[:2]:
            actor = batch.trainer.user if batch.trainer else admin
            course = batch.course

            for index, (text, options, correct) in enumerate(QUESTION_SEEDS):
                if Question.objects.filter(course=course, text=text).exists():
                    continue
                create_question(
                    actor=actor,
                    course=course,
                    question_type=QuestionType.MCQ,
                    text=text,
                    difficulty=Difficulty.EASY if index % 2 == 0 else Difficulty.MEDIUM,
                    marks=Decimal("2.00"),
                    negative_marks=Decimal("0.50"),
                    tags=["basics"],
                    explanation=f"'{options[correct]}' is the command that does this.",
                    options=[
                        {"text": option, "is_correct": position == correct}
                        for position, option in enumerate(options)
                    ],
                )
                created += 1

            essay = "Explain, in your own words, what a shell does."
            if not Question.objects.filter(course=course, text=essay).exists():
                create_question(
                    actor=actor,
                    course=course,
                    question_type=QuestionType.LONG_ANSWER,
                    text=essay,
                    difficulty=Difficulty.MEDIUM,
                    marks=Decimal("10.00"),
                    tags=["basics"],
                )
                created += 1

        return created

    # -- examinations -------------------------------------------------------

    def _seed_exams(self, admin, batches) -> int:
        from apps.exams.models import Exam, ExamStatus
        from apps.exams.services import create_exam, set_exam_status
        from apps.questions.models import QuestionType

        created = 0
        for batch in batches[:2]:
            actor = batch.trainer.user if batch.trainer else admin
            title = f"{batch.course.title}: final examination"
            if Exam.objects.filter(title=title, batch=batch).exists():
                continue

            exam = create_exam(
                actor=actor,
                batch=batch,
                title=title,
                instructions=(
                    "Answer every question. Your answers save as you go, so a lost "
                    "connection will not cost you your work."
                ),
                duration_minutes=45,
                max_attempts=1,
                negative_marking=False,
                opens_at=timezone.now() - timedelta(hours=1),
                closes_at=timezone.now() + timedelta(days=14),
                sections=[
                    {
                        "title": "Multiple choice",
                        "question_count": 5,
                        "question_type": QuestionType.MCQ,
                    }
                ],
            )
            set_exam_status(exam=exam, actor=actor, status=ExamStatus.PUBLISHED)
            created += 1

        return created

    # -- certificates and completion ---------------------------------------

    def _seed_certificate_template(self, admin) -> int:
        from apps.certificates.models import CertificateTemplate
        from apps.certificates.services import save_template

        if CertificateTemplate.objects.exists():
            return 0
        save_template(
            actor=admin,
            name="Grras standard",
            is_default=True,
            institution_name="Grras Solutions",
            title="Certificate of Completion",
            signatory_name="Course Director",
            signatory_title="Grras Solutions",
        )
        return 1

    def _seed_completions(self, admin, batches) -> int:
        """Evaluate every active student, so the approval queue is not empty."""
        from apps.progress.models import CompletionStatus
        from apps.progress.services import refresh_completion

        eligible = 0
        for batch in batches:
            rows = Enrollment.objects.with_related().filter(
                batch=batch, status=EnrollmentStatus.ACTIVE
            )
            for enrollment in rows:
                completion = refresh_completion(enrollment=enrollment, actor=admin)
                eligible += int(completion.status == CompletionStatus.ELIGIBLE)
        return eligible

    # -- recorded results ---------------------------------------------------

    def _seed_results(self, admin, batches) -> int:
        """Marks for the *first* weekly test only.

        Deliberately one: the result-import journey needs a published test with
        nothing recorded against it, so the other tests are left untouched. This
        one exists so a fresh environment shows what a marked test looks like —
        including the two rows people get wrong.

        The edge cases are the point:

        * a student marked **absent**, which must carry no mark at all rather
          than a zero (a zero is a fail; an absence is not a sitting);
        * a mark **exactly on the passing boundary**, because "at least" and
          "more than" are one character apart and both look right in review.
        """
        from apps.assessments.models import Assessment, AssessmentStatus
        from apps.assessments.services import cohort_for, record_result

        test = (
            Assessment.objects.filter(status=AssessmentStatus.PUBLISHED)
            .order_by("created_at")
            .first()
        )
        if test is None or test.results.exists():
            return 0

        actor = test.batch.trainer.user if test.batch and test.batch.trainer else admin
        pass_mark = test.passing_marks or (test.max_marks / 2)

        recorded = 0
        for index, enrollment in enumerate(cohort_for(test)):
            if index == 0:
                record_result(
                    assessment=test,
                    enrollment=enrollment,
                    actor=actor,
                    is_absent=True,
                    remarks="Absent (demo record).",
                )
            elif index == 1:
                record_result(
                    assessment=test,
                    enrollment=enrollment,
                    actor=actor,
                    marks=pass_mark,
                    remarks="Exactly on the pass mark (demo record).",
                )
            else:
                marks = min(test.max_marks, pass_mark + Decimal(index % 5))
                record_result(assessment=test, enrollment=enrollment, actor=actor, marks=marks)
            recorded += 1
        return recorded

    # -- issued certificates ------------------------------------------------

    def _seed_certificates(self, admin, batches) -> int:
        """One issued certificate, and one revoked.

        A demo environment with a template and no certificate shows the setup
        screen and none of the outcome. The revoked one matters just as much:
        public verification of a revoked certificate is its own path — it still
        verifies, and it says it was withdrawn — and nobody exercises it if the
        only certificate in the environment is valid.
        """
        from apps.certificates.models import Certificate
        from apps.certificates.services import (
            default_template,
            issue_certificate,
            revoke_certificate,
        )
        from apps.progress.models import CompletionStatus, CourseCompletion
        from apps.progress.services import approve_completion

        if Certificate.objects.exists():
            return 0
        template = default_template()
        if template is None:
            return 0

        eligible = list(
            CourseCompletion.objects.filter(status=CompletionStatus.ELIGIBLE)
            .select_related("enrollment")
            .order_by("created_at")[:2]
        )
        issued = 0
        for index, completion in enumerate(eligible):
            approved = approve_completion(
                enrollment=completion.enrollment,
                actor=admin,
                note="Approved as demo data.",
            )
            certificate = issue_certificate(completion=approved, actor=admin, template=template)
            issued += 1
            if index == 1:
                revoke_certificate(
                    certificate=certificate,
                    actor=admin,
                    reason="Issued against demo data in error (demo record).",
                )
        return issued

    # -- communication ------------------------------------------------------

    def _seed_communication(self, admin, batches) -> tuple[int, int]:
        """A published announcement and a live discussion on each active batch.

        Both sides of each feature: an announcement students can already read,
        and a question with a trainer's answer, so the screens are not empty on
        a first visit.
        """
        from apps.announcements.models import Announcement, Audience
        from apps.announcements.services import create_announcement, publish
        from apps.discussions.models import Thread
        from apps.discussions.services import create_thread, reply

        announcements = threads = 0
        for batch in batches[:3]:
            actor = batch.trainer.user if batch.trainer else admin

            title = f"{batch.code}: welcome to the course"
            if not Announcement.objects.filter(title=title).exists():
                notice = create_announcement(
                    actor=actor,
                    title=title,
                    body=(
                        "Classes run to the timetable on your batch page. "
                        "Bring a laptop; the labs have power at every desk."
                    ),
                    audience=Audience.BATCH,
                    batch=batch,
                    is_pinned=True,
                )
                publish(announcement=notice, actor=actor)
                announcements += 1

            question = f"{batch.code}: how do I set up my environment?"
            if Thread.objects.filter(title=question).exists():
                continue

            student = (
                Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.ACTIVE)
                .select_related("student__user")
                .first()
            )
            if student is None:
                continue

            thread = create_thread(
                batch=batch,
                actor=student.student.user,
                title=question,
                body="I have installed the tools but the command is not found.",
            )
            reply(
                thread=thread,
                actor=actor,
                body="Add the install directory to your PATH and open a new terminal.",
            )
            threads += 1

        return announcements, threads
