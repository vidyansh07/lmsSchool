"""Create fake batches, schedules and enrolments for local and staging use.

Same safety rules as the other seeders: refuses to run where demo data is not
allowed, and is idempotent.

Produces the shape §20 asks for, including the edge cases that are worth having
in a demo environment because they are the ones that break:

* a **full** batch, so the capacity refusal is reachable in a browser;
* a **cancelled** batch, whose students lost access;
* a **completed** batch, whose students kept it;
* a **suspended** enrolment;
* a **trainer schedule conflict attempt**, which the seeder tries and reports
  as refused — proving the guard works in the seeded environment, not only in
  the test suite.
"""

from __future__ import annotations

from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.batches.models import Batch, BatchStatus, Weekday
from apps.batches.services import ScheduleConflictError, create_batch, create_schedule
from apps.courses.models import Course, PublishStatus
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.enrollments.services import (
    CapacityError,
    DuplicateEnrollmentError,
    enrol_student,
    set_enrollment_status,
    touch_lesson,
)
from apps.students.models import StudentProfile
from apps.trainers.models import TrainerProfile

#: Weekly slots, cycled across batches. Chosen so two batches taught by the same
#: trainer never land on the same day — the conflict guard is exercised
#: deliberately at the end instead.
SLOT_PATTERNS = [
    [(Weekday.MONDAY, time(9, 0), time(11, 0)), (Weekday.WEDNESDAY, time(9, 0), time(11, 0))],
    [(Weekday.TUESDAY, time(14, 0), time(16, 0)), (Weekday.THURSDAY, time(14, 0), time(16, 0))],
    [(Weekday.SATURDAY, time(10, 0), time(13, 0))],
    [(Weekday.MONDAY, time(18, 0), time(20, 0)), (Weekday.FRIDAY, time(18, 0), time(20, 0))],
]

LOCATIONS = ["Lab 1", "Lab 2", "Seminar Room", "Online"]

#: (name suffix, status, offset from today in days, duration in days, capacity)
BATCH_PLAN = [
    ("Morning", BatchStatus.ACTIVE, -30, 90, 12),
    ("Afternoon", BatchStatus.ACTIVE, -14, 90, 10),
    ("Weekend", BatchStatus.ACTIVE, -7, 120, 8),
    ("Evening", BatchStatus.UPCOMING, 21, 90, 10),
    ("Fast track", BatchStatus.UPCOMING, 35, 45, 6),
    # The edge cases.
    ("Full cohort", BatchStatus.ACTIVE, -21, 60, 2),
    ("Completed cohort", BatchStatus.COMPLETED, -180, 120, 10),
    ("Cancelled cohort", BatchStatus.CANCELLED, -60, 90, 10),
]


class Command(BaseCommand):
    help = "Create or refresh fake batches, schedules and enrolments (local/staging only)."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Batch seeding is disabled in the "
                f"{getattr(settings, 'ENVIRONMENT', 'unknown')} environment. "
                "This command must never run against production data."
            )

        admin = User.objects.filter(role=UserRole.ADMIN).order_by("email").first()
        if admin is None:
            raise CommandError("No administrator exists. Run `manage.py seed_demo_data` first.")

        courses = list(Course.objects.filter(status=PublishStatus.PUBLISHED).order_by("code"))
        trainers = list(TrainerProfile.objects.select_related("user").order_by("trainer_id"))
        students = list(StudentProfile.objects.select_related("user").order_by("student_id"))

        if not courses:
            raise CommandError("No published courses. Run `manage.py seed_courses` first.")
        if not trainers or not students:
            raise CommandError("No trainers or students. Run `manage.py seed_demo_data` first.")

        batches = self._seed_batches(admin, courses, trainers)
        counts = self._seed_enrollments(admin, batches, students)
        conflict = self._demonstrate_conflict_guard(admin, batches, trainers)

        self.stdout.write(
            self.style.SUCCESS(
                f"Batch data ready: {len(batches)} batches, {counts['schedules']} classes, "
                f"{counts['enrollments']} enrolments "
                f"({counts['suspended']} suspended, {counts['cancelled']} cancelled)."
            )
        )
        self.stdout.write(f"Trainer conflict guard: {conflict}")

    # -- batches ------------------------------------------------------------

    def _seed_batches(self, admin, courses, trainers) -> list[Batch]:
        today = timezone.localdate()
        batches: list[Batch] = []

        for index, (suffix, status, offset, duration, capacity) in enumerate(BATCH_PLAN):
            course = courses[index % len(courses)]
            trainer = trainers[index % len(trainers)]
            name = f"{course.title} — {suffix}"

            batch = Batch.objects.filter(name=name).first()
            if batch is None:
                batch = create_batch(
                    actor=admin,
                    name=name,
                    course=course,
                    trainer=trainer,
                    description=f"Demo batch for {course.title}. Placeholder data only.",
                    start_date=today + timedelta(days=offset),
                    end_date=today + timedelta(days=offset + duration),
                    capacity=capacity,
                )
                self._seed_schedules(admin, batch, index)

            # Status is set directly: the seeder is building a fixed picture,
            # not walking each batch through its lifecycle.
            Batch.objects.filter(pk=batch.pk).update(status=status)
            batch.refresh_from_db()
            batches.append(batch)

        return batches

    def _seed_schedules(self, admin, batch: Batch, index: int) -> None:
        pattern = SLOT_PATTERNS[index % len(SLOT_PATTERNS)]
        for slot_index, (weekday, start, end) in enumerate(pattern):
            try:
                create_schedule(
                    batch=batch,
                    actor=admin,
                    weekday=weekday,
                    start_time=start,
                    end_time=end,
                    timezone_name="Asia/Kolkata",
                    location=LOCATIONS[(index + slot_index) % len(LOCATIONS)],
                )
            except ScheduleConflictError:
                # Expected for a few combinations as the demo timetable fills
                # up. The guard doing its job is not a seeding failure.
                self.stdout.write(
                    self.style.WARNING(
                        f"  skipped a clashing slot for {batch.code} ({weekday}, {start:%H:%M})"
                    )
                )

    # -- enrolments ---------------------------------------------------------

    def _seed_enrollments(self, admin, batches, students) -> dict[str, int]:
        counts = {"enrollments": 0, "schedules": 0, "suspended": 0, "cancelled": 0}
        counts["schedules"] = sum(batch.schedules.count() for batch in batches)

        cursor = 0
        for batch in batches:
            if batch.status == BatchStatus.CANCELLED:
                # Its students were cancelled with it; seed them so the state is
                # visible, then cancel them the way the service would.
                target = students[cursor : cursor + 3]
                cursor += 3
                for student in target:
                    created = self._enrol(admin, student, batch, force_status=True)
                    if created:
                        set_enrollment_status(
                            enrollment=created,
                            target=EnrollmentStatus.CANCELLED,
                            actor=admin,
                            note="The batch was cancelled.",
                        )
                        counts["enrollments"] += 1
                        counts["cancelled"] += 1
                continue

            if batch.status == BatchStatus.COMPLETED:
                target = students[cursor : cursor + 4]
                cursor += 4
                for student in target:
                    created = self._enrol(admin, student, batch, force_status=True)
                    if created:
                        set_enrollment_status(
                            enrollment=created,
                            target=EnrollmentStatus.COMPLETED,
                            actor=admin,
                            note="The batch was completed.",
                        )
                        counts["enrollments"] += 1
                continue

            # Fill the batch: the "Full cohort" one has capacity 2, so this
            # deliberately reaches the capacity refusal.
            wanted = min(batch.capacity, 5)
            target = students[cursor : cursor + wanted]
            cursor = (cursor + wanted) % max(len(students) - wanted, 1)

            for position, student in enumerate(target):
                created = self._enrol(admin, student, batch)
                if created is None:
                    continue
                counts["enrollments"] += 1

                # The first student on each batch gets progress, so the demo's
                # headline account shows the happy path on opening.
                if position == 0:
                    self._seed_progress(created)
                # A later student is suspended, so that state is reachable in a
                # browser without breaking the happy path.
                elif (
                    position == 2 and batch.status == BatchStatus.ACTIVE and counts["suspended"] < 2
                ):
                    set_enrollment_status(
                        enrollment=created,
                        target=EnrollmentStatus.SUSPENDED,
                        actor=admin,
                        note="Demo: fees outstanding.",
                    )
                    counts["suspended"] += 1

        return counts

    def _enrol(self, admin, student, batch, *, force_status: bool = False):
        """Enrol, tolerating the refusals the demo data is meant to produce."""
        existing = Enrollment.objects.filter(student=student, batch=batch).first()
        if existing is not None:
            return None
        try:
            if force_status:
                # A completed or cancelled batch will not accept enrolments, so
                # place the row directly and let the caller set its status.
                original = batch.status
                Batch.objects.filter(pk=batch.pk).update(status=BatchStatus.ACTIVE)
                batch.refresh_from_db()
                created = enrol_student(student=student, batch=batch, actor=admin)
                Batch.objects.filter(pk=batch.pk).update(status=original)
                batch.refresh_from_db()
                return created
            return enrol_student(student=student, batch=batch, actor=admin)
        except (CapacityError, DuplicateEnrollmentError):
            # Expected for the deliberately-full cohort.
            return None

    def _seed_progress(self, enrollment) -> None:
        """Give one student some progress, so the dashboard is not empty.

        Only for an enrolment that actually opens the course. A batch that has
        not started yet grants no access, and manufacturing progress on it would
        be inventing study that could not have happened.
        """
        if not enrollment.grants_access():
            return

        from apps.courses.models import Lesson

        lessons = list(
            Lesson.objects.filter(
                module__course_id=enrollment.course_id,
                module__status=PublishStatus.PUBLISHED,
                status=PublishStatus.PUBLISHED,
            ).order_by("module__position", "position")[:3]
        )
        from apps.enrollments.services import set_lesson_completion

        for index, lesson in enumerate(lessons):
            if index < 2:
                set_lesson_completion(student=enrollment.student, lesson=lesson, completed=True)
            else:
                touch_lesson(student=enrollment.student, lesson=lesson)

    # -- the conflict guard -------------------------------------------------

    def _demonstrate_conflict_guard(self, admin, batches, trainers) -> str:
        """Try to double-book a trainer, and report that it was refused.

        §20 asks for a "trainer schedule conflict attempt" in the seed data. An
        accepted clash cannot be seeded — that is the point — so what is seeded
        is the proof that the attempt fails.
        """
        active = [batch for batch in batches if batch.status == BatchStatus.ACTIVE]
        if len(active) < 2:
            return "not attempted (too few active batches)"

        source, target = active[0], active[1]
        slot = source.schedules.filter(is_active=True).first()
        if slot is None:
            return "not attempted (no class to clash with)"

        # Put the same trainer on both, then try to add an identical slot.
        Batch.objects.filter(pk=target.pk).update(trainer=source.trainer)
        target.refresh_from_db()
        try:
            create_schedule(
                batch=target,
                actor=admin,
                weekday=slot.weekday,
                start_time=slot.start_time,
                end_time=slot.end_time,
                timezone_name=slot.timezone_name,
                location="Conflict test",
            )
        except ScheduleConflictError:
            return f"refused as expected ({source.code} vs {target.code})"
        finally:
            # Leave the timetable as it was.
            Batch.objects.filter(pk=target.pk).update(
                trainer=trainers[1 % len(trainers)] if trainers else None
            )
        return "NOT refused — investigate"
