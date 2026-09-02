"""Build a dataset large enough for performance work to mean anything.

§14.9 asks for realistic staging volume: hundreds of students, dozens of
courses, multiple batches, thousands of progress, attendance and assessment
records. A demo dataset of twelve students proves nothing — every query plan
looks fine on twelve rows, and an N+1 that issues one query per student is
invisible until there are four hundred of them.

Relationship to `seed_demo_data`
--------------------------------
That command creates the *named* fixtures the demo and the end-to-end suite
depend on. Everything here is created under its own email domain and its own
batch-code prefix, so ``--flush`` removes a scale run without touching a single
demo record.

**Run this against a database dedicated to performance work, not the demo
one.** The two datasets do not corrupt each other, but they do share the
paginated catalogue: twenty-four generated courses push the demo courses off the
first page, and the end-to-end suite — which looks for them by name — fails.
That was discovered the direct way. Flush before running the demo or the E2E
suite against the same database.

Safety
------
Gated on ``ALLOW_DEMO_SEED`` like every other seeder, so it cannot run in
production. Every name is generated, every address is on a reserved
``.invalid`` domain, and no real learner data is involved.

Speed
-----
Bulk inserts throughout, in batches. Creating twenty thousand rows one
``save()`` at a time takes minutes and teaches nothing; the point of this
command is the shape of the data, not the path that writes it.
"""

from __future__ import annotations

import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultSource,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.batches.models import Batch, BatchStatus
from apps.courses.models import Category, Course, Lesson, Module, PublishStatus
from apps.enrollments.models import (
    Enrollment,
    EnrollmentStatus,
    LessonProgress,
    LessonProgressStatus,
)
from apps.sessions.models import ClassSession, SessionStatus
from apps.students.models import FeeStatus, StudentProfile
from apps.trainers.models import TrainerProfile

#: Distinct from `seed_demo_data`'s domain so the two datasets never collide.
SCALE_DOMAIN = "scale.grras.invalid"
#: Every batch this command makes starts with this, which is how `--flush`
#: knows what it may delete.
SCALE_PREFIX = "SCALE-"

_rng = secrets.SystemRandom()

FIRST = [
    "Aarav",
    "Diya",
    "Vivaan",
    "Ananya",
    "Aditya",
    "Ishita",
    "Arjun",
    "Kavya",
    "Rohan",
    "Meera",
]
LAST = ["Sharma", "Verma", "Patel", "Gupta", "Nair", "Reddy", "Joshi", "Mehta", "Iyer", "Khan"]


class Command(BaseCommand):
    help = "Create a large, obviously fake dataset for performance testing."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--students", type=int, default=400)
        parser.add_argument("--courses", type=int, default=24)
        parser.add_argument("--batches", type=int, default=12)
        parser.add_argument("--sessions", type=int, default=40, help="class sessions per batch")
        parser.add_argument("--lessons", type=int, default=12, help="lessons per course")
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete a previous scale dataset first. Never touches demo data.",
        )
        parser.add_argument(
            "--flush-only",
            action="store_true",
            help="Delete the scale dataset and stop. Leaves demo data untouched.",
        )

    def handle(self, *args, **options) -> None:
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError("Seeding is disabled in this environment (ALLOW_DEMO_SEED is off).")

        if options["flush_only"]:
            self._flush()
            return

        password = self._password()
        counts = {
            key: options[key] for key in ("students", "courses", "batches", "sessions", "lessons")
        }
        for key, value in counts.items():
            if value < 1:
                raise CommandError(f"--{key} must be at least 1.")

        if options["flush"]:
            self._flush()

        with transaction.atomic():
            category = self._category()
            courses = self._courses(category, counts["courses"], counts["lessons"])
            trainers = self._trainers(max(3, counts["batches"] // 2), password)
            batches = self._batches(courses, trainers, counts["batches"])
            students = self._students(counts["students"], password)
            enrollments = self._enrollments(students, batches)
            sessions = self._sessions(batches, counts["sessions"])
            attendance = self._attendance(sessions, enrollments)
            progress = self._progress(enrollments, courses)
            results = self._results(batches, enrollments)

        self.stdout.write(
            self.style.SUCCESS(
                "Scale dataset ready: "
                f"{len(students)} students, {len(courses)} courses, {len(batches)} batches, "
                f"{len(enrollments)} enrolments, {len(sessions)} sessions, "
                f"{attendance} attendance records, {progress} lesson-progress records, "
                f"{results} assessment results."
            )
        )

    # -- helpers ------------------------------------------------------------

    def _password(self) -> str:
        import os

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        password = os.environ.get("DEMO_USER_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_USER_PASSWORD; this command will not invent one.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                f"DEMO_USER_PASSWORD is too weak: {'; '.join(exc.messages)}"
            ) from exc
        return password

    def _flush(self) -> None:
        """Remove a previous scale run. Scoped by domain and code prefix.

        Ordered by hand because `Enrollment.batch` is ``PROTECT``: an enrolment
        is educational history, and the database refuses to let a batch take one
        with it. That is the right rule — it is why deleting a batch out from
        under a student is impossible in the product — and it means a cleanup
        has to work inwards from the leaves.
        """
        batches = Batch.objects.filter(code__startswith=SCALE_PREFIX)
        Enrollment.objects.filter(batch__in=batches).delete()
        batches.delete()
        Course.objects.filter(slug__startswith="scale-").delete()
        User.objects.filter(email__endswith=f"@{SCALE_DOMAIN}").delete()
        self.stdout.write("Previous scale dataset removed.")

    def _category(self) -> Category:
        category, _ = Category.objects.get_or_create(
            slug="scale-performance",
            defaults={"name": "Performance Testing", "description": "Generated at scale."},
        )
        return category

    def _courses(self, category, count: int, lessons_each: int) -> list[Course]:
        from apps.common.identifiers import next_course_code

        courses = Course.objects.bulk_create(
            Course(
                code=next_course_code(),
                title=f"Scale Course {index + 1:02d}",
                slug=f"scale-course-{index + 1:02d}",
                category=category,
                short_description="Generated for performance testing.",
                description="Generated for performance testing.",
                status=PublishStatus.PUBLISHED,
                estimated_duration_minutes=2400,
            )
            for index in range(count)
        )
        modules = Module.objects.bulk_create(
            Module(
                course=course,
                title=f"Module {number}",
                position=number,
                status=PublishStatus.PUBLISHED,
            )
            for course in courses
            for number in (1, 2)
        )
        per_module = max(1, lessons_each // 2)
        Lesson.objects.bulk_create(
            Lesson(
                module=module,
                title=f"Lesson {number}",
                slug=f"lesson-{number}",
                position=number,
                status=PublishStatus.PUBLISHED,
                text_content="Generated lesson body.",
            )
            for module in modules
            for number in range(1, per_module + 1)
        )
        return courses

    def _trainers(self, count: int, password: str) -> list[TrainerProfile]:
        from apps.common.identifiers import next_trainer_id

        profiles = []
        for index in range(count):
            user = User.objects.create_user(
                email=f"scale-trainer-{index + 1:03d}@{SCALE_DOMAIN}",
                password=password,
                first_name=_rng.choice(FIRST),
                last_name=_rng.choice(LAST),
                role=UserRole.TRAINER,
            )
            profiles.append(
                TrainerProfile(
                    user=user,
                    trainer_id=next_trainer_id(),
                    professional_title="Generated Trainer",
                )
            )
        return TrainerProfile.objects.bulk_create(profiles)

    def _batches(self, courses, trainers, count: int) -> list[Batch]:
        start = date.today() - timedelta(days=60)
        return Batch.objects.bulk_create(
            Batch(
                code=f"{SCALE_PREFIX}{index + 1:03d}",
                name=f"Scale Batch {index + 1:02d}",
                course=courses[index % len(courses)],
                trainer=trainers[index % len(trainers)],
                start_date=start,
                end_date=start + timedelta(days=120),
                capacity=200,
                status=BatchStatus.ACTIVE,
            )
            for index in range(count)
        )

    def _students(self, count: int, password: str) -> list[StudentProfile]:
        from apps.common.identifiers import next_student_id

        # `create_user` hashes a password per call, which dominates the runtime
        # of this command. One hash, reused: these accounts all share the same
        # generated password by design, and nothing here is a security boundary.
        template = User(email="x@x.invalid")
        template.set_password(password)
        hashed = template.password

        users = User.objects.bulk_create(
            User(
                email=f"scale-student-{index + 1:04d}@{SCALE_DOMAIN}",
                password=hashed,
                first_name=_rng.choice(FIRST),
                last_name=_rng.choice(LAST),
                role=UserRole.STUDENT,
                is_active=True,
            )
            for index in range(count)
        )
        return StudentProfile.objects.bulk_create(
            StudentProfile(
                user=user,
                student_id=next_student_id(),
                fee_status=_rng.choice([FeeStatus.PAID, FeeStatus.PARTIAL, FeeStatus.PENDING]),
            )
            for user in users
        )

    def _enrollments(self, students, batches) -> list[Enrollment]:
        from apps.common.identifiers import next_enrolment_code

        return Enrollment.objects.bulk_create(
            Enrollment(
                code=next_enrolment_code(),
                student=student,
                batch=batches[index % len(batches)],
                course=batches[index % len(batches)].course,
                status=EnrollmentStatus.ACTIVE,
                start_date=date.today() - timedelta(days=45),
            )
            for index, student in enumerate(students)
        )

    def _sessions(self, batches, per_batch: int) -> list[ClassSession]:
        first = date.today() - timedelta(days=per_batch)
        rows = []
        for batch in batches:
            for day in range(per_batch):
                session_date = first + timedelta(days=day)
                rows.append(
                    ClassSession(
                        batch=batch,
                        session_date=session_date,
                        start_time="10:00",
                        end_time="12:00",
                        topic=f"Session {day + 1}",
                        status=(
                            SessionStatus.COMPLETED
                            if session_date < date.today()
                            else SessionStatus.SCHEDULED
                        ),
                    )
                )
        return ClassSession.objects.bulk_create(rows, batch_size=500)

    def _attendance(self, sessions, enrollments) -> int:
        by_batch: dict = {}
        for enrollment in enrollments:
            by_batch.setdefault(enrollment.batch_id, []).append(enrollment)

        rows = []
        for session in sessions:
            if session.status != SessionStatus.COMPLETED:
                continue
            for enrollment in by_batch.get(session.batch_id, []):
                rows.append(
                    AttendanceRecord(
                        session=session,
                        enrollment=enrollment,
                        # Roughly the real shape: mostly present, a tail of
                        # absences. A dataset where everyone attends everything
                        # hides every query that filters on status.
                        status=_rng.choices(
                            [
                                AttendanceStatus.PRESENT,
                                AttendanceStatus.ABSENT,
                                AttendanceStatus.LATE,
                            ],
                            weights=[80, 15, 5],
                        )[0],
                        marked_at=timezone.now(),
                    )
                )
        AttendanceRecord.objects.bulk_create(rows, batch_size=1000)
        return len(rows)

    def _progress(self, enrollments, courses) -> int:
        lessons_by_course: dict = {}
        for lesson in Lesson.objects.filter(module__course__in=courses).select_related("module"):
            lessons_by_course.setdefault(lesson.module.course_id, []).append(lesson)

        rows = []
        for enrollment in enrollments:
            lessons = lessons_by_course.get(enrollment.course_id, [])
            # A partly-finished course per student: the realistic case, and the
            # one where completion percentages actually have to be computed.
            reached = _rng.randint(0, len(lessons))
            for index, lesson in enumerate(lessons[:reached]):
                done = index < reached - 1
                rows.append(
                    LessonProgress(
                        enrollment=enrollment,
                        lesson=lesson,
                        status=(
                            LessonProgressStatus.COMPLETED
                            if done
                            else LessonProgressStatus.IN_PROGRESS
                        ),
                        completed_at=timezone.now() if done else None,
                    )
                )
        LessonProgress.objects.bulk_create(rows, batch_size=1000)
        return len(rows)

    def _results(self, batches, enrollments) -> int:
        from apps.common.identifiers import next_assessment_code

        assessments = Assessment.objects.bulk_create(
            Assessment(
                code=next_assessment_code(),
                batch=batch,
                course=batch.course,
                title=f"Weekly Test {week}",
                category=AssessmentCategory.WEEKLY_TEST,
                delivery=AssessmentDelivery.OFFLINE,
                status=AssessmentStatus.PUBLISHED,
                max_marks=Decimal("50.00"),
                passing_marks=Decimal("20.00"),
                scheduled_for=timezone.now() - timedelta(days=7 * (9 - week)),
            )
            for batch in batches
            for week in range(1, 9)
        )
        by_batch: dict = {}
        for enrollment in enrollments:
            by_batch.setdefault(enrollment.batch_id, []).append(enrollment)

        rows = []
        for assessment in assessments:
            for enrollment in by_batch.get(assessment.batch_id, []):
                absent = _rng.random() < 0.05
                rows.append(
                    AssessmentResult(
                        assessment=assessment,
                        enrollment=enrollment,
                        marks_obtained=None if absent else Decimal(_rng.randint(10, 50)),
                        is_absent=absent,
                        source=ResultSource.MANUAL,
                    )
                )
        AssessmentResult.objects.bulk_create(rows, batch_size=1000)
        return len(rows)
