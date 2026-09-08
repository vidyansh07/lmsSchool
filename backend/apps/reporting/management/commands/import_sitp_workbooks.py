"""Feed the SITP ACE workbooks into the LMS.

    python manage.py import_sitp_workbooks "SITP ACE 2026 1st Year" ... \\
        --actor admin@example.test [--dry-run] [--report report.json]

One workbook becomes one batch on one course, with its roster enrolled, a
class for every date on the attendance grid, the register marked for each,
a submitted daily status report for every DSR row that matches a class, and
an assessment with results for every marked column.

Three rules, and the reason for each:

* **Everything goes through the services.** Students are created by
  ``students.services.create_student``, registers by
  ``attendance.services.mark_attendance``, and so on — never by writing rows.
  That is what makes every imported record obey the same validation as one
  typed in, and what puts every one of them in the audit log under the actor
  who ran this.
* **Nothing is dropped quietly.** A cell the reader cannot understand, a
  student who cannot be enrolled, a mark over the maximum: each is a line in
  the report with the sheet and row it came from. The counts at the top of
  the report add up to the rows in the file.
* **Running it twice changes nothing.** Every lookup is by a stable key —
  roll number, batch name, class date, assessment title — so a re-run after
  a corrected spreadsheet updates rather than duplicates.

``--dry-run`` does the whole import inside a transaction and rolls it back,
so the report it prints is the report the real run would print.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import User
from apps.reporting.sitp import Workbook, read_workbook

#: Where these cohorts come from. Every sheet says so in its own header.
COLLEGE = "Arya College of Engineering"
PROGRAMME = "SITP ACE 2026"

#: Accounts made for people the spreadsheet names but gives no address for.
#: The domain is reserved by RFC 2606 and cannot receive mail, which is the
#: point: nothing is sent, and the address can never collide with a real one.
PLACEHOLDER_DOMAIN = "sitp.grras.invalid"

#: The sheets carry no times; the programme ran as a morning class.
CLASS_START = time(10, 0)
CLASS_END = time(12, 0)

#: Which catalogue category a course belongs to, by words in its name.
CATEGORY_BY_KEYWORD: list[tuple[tuple[str, ...], str, str]] = [
    (("aws", "azure", "cloud"), "cloud-devops", "Cloud & DevOps"),
    (("cyber", "soc", "security"), "cyber-security", "Cyber Security"),
    (("data", "analytics", "power bi", "pl300", "ml", "science"), "data-analytics", "Data & Analytics"),
    (("agentic", "ai"), "ai-engineering", "AI Engineering"),
    (("mern", "web", "stack"), "programming", "Programming"),
]


@dataclass
class FileReport:
    file: str
    batch: str = ""
    course: str = ""
    trainer: str = ""
    counts: Counter = field(default_factory=Counter)
    problems: list[dict[str, Any]] = field(default_factory=list)
    not_imported: dict[str, str] = field(default_factory=dict)

    def problem(self, sheet: str, row: int | None, reason: str) -> None:
        self.problems.append({"sheet": sheet, "row": row, "reason": reason})

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "batch": self.batch,
            "course": self.course,
            "trainer": self.trainer,
            "counts": dict(self.counts),
            "problems": self.problems,
            "not_imported": self.not_imported,
        }


class Command(BaseCommand):
    help = "Import the SITP ACE workbooks (one batch per file) through the domain services."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Workbook files or folders of them.")
        parser.add_argument("--actor", required=True, help="Email of the staff account doing the import.")
        parser.add_argument("--dry-run", action="store_true", help="Do everything, then roll it all back.")
        parser.add_argument("--report", help="Write the JSON report here as well as printing a summary.")

    def handle(self, *args, **options):
        actor = User.objects.filter(email__iexact=options["actor"]).first()
        if actor is None:
            raise CommandError(f"No account with email {options['actor']!r}.")

        files = sorted({path for raw in options["paths"] for path in _expand(Path(raw))})
        if not files:
            raise CommandError("No .xlsx files found.")

        reports: list[FileReport] = []
        with transaction.atomic():
            for path in files:
                self.stdout.write(f"• {path.name}")
                report = FileReport(file=str(path))
                try:
                    book = read_workbook(path)
                    for problem in book.problems:
                        report.problem(problem.sheet, problem.row, problem.reason)
                    report.not_imported = dict(book.not_imported)
                    if book.non_class_rows:
                        report.counts["report rows that were Sundays or holidays"] += book.non_class_rows
                    Importer(actor=actor, book=book, report=report).run()
                except Exception as exc:  # noqa: BLE001 — one bad file must not hide the rest
                    report.problem("workbook", None, f"Import stopped: {exc}")
                    self.stderr.write(f"  ✗ {exc}")
                reports.append(report)
                self.stdout.write(
                    "  "
                    + ", ".join(f"{key} {value}" for key, value in sorted(report.counts.items()))
                    + (f"  ({len(report.problems)} problems)" if report.problems else "")
                )
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: nothing was written."))

        totals = Counter()
        for report in reports:
            totals.update(report.counts)
        self.stdout.write(self.style.SUCCESS("Totals: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items()))))
        problems = sum(len(r.problems) for r in reports)
        if problems:
            self.stdout.write(self.style.WARNING(f"{problems} rows or cells were not imported; see the report."))

        if options["report"]:
            Path(options["report"]).write_text(
                json.dumps({"dry_run": options["dry_run"], "files": [r.as_dict() for r in reports]}, indent=2, default=str)
            )
            self.stdout.write(f"Report written to {options['report']}")


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*.xlsx") if not p.name.startswith("~$"))
    if path.suffix.lower() == ".xlsx":
        return [path]
    return []


# ---------------------------------------------------------------------------
# One workbook → one batch
# ---------------------------------------------------------------------------


class Importer:
    def __init__(self, *, actor: User, book: Workbook, report: FileReport):
        self.actor = actor
        self.book = book
        self.report = report

    def run(self) -> None:
        if not self.book.students:
            self.report.problem("Attendance", None, "No students could be read, so nothing else was imported.")
            return
        course = self.course()
        trainer = self.trainer()
        batch = self.batch(course, trainer)
        enrollments = self.roster(batch)
        sessions = self.sessions(batch, trainer)
        self.registers(sessions, enrollments)
        self.reports(sessions, trainer)
        self.assessments(batch, enrollments)

    # --- course ----------------------------------------------------------

    def course(self):
        from apps.courses.models import Category, Course, CourseDifficulty, LessonContentType, PublishStatus
        from apps.courses.services import (
            create_category,
            create_course,
            create_lesson,
            create_module,
            set_course_status,
        )

        title = f"{PROGRAMME} — {self.book.batch_name}"
        if self.book.year_label:
            title += f" ({self.book.year_label})"
        course = Course.objects.filter(title=title).first()
        if course is None:
            lowered = self.book.batch_name.lower()
            slug, name = "internship-training", "Internship Training"
            for keywords, candidate_slug, candidate_name in CATEGORY_BY_KEYWORD:
                if any(word in lowered for word in keywords):
                    slug, name = candidate_slug, candidate_name
                    break
            category = Category.objects.filter(slug=slug).first() or create_category(
                actor=self.actor, name=name, slug=slug
            )
            course = create_course(
                actor=self.actor,
                title=title,
                # "AI_ML" would slugify with an underscore, which the course
                # slug refuses; spell the slug out from words only.
                slug=slugify(re.sub(r"[_—–]+", " ", title))[:60].strip("-"),
                category=category,
                short_description=f"{self.book.batch_name} — summer industrial training for {COLLEGE}, {self.book.year_label or 'B.Tech'}.",
                difficulty=CourseDifficulty.BEGINNER if "1st" in self.book.year_label else CourseDifficulty.INTERMEDIATE,
            )
            # A batch may only run a course that is published or in review, and
            # publishing needs real lesson content, which these sheets do not
            # carry. One outline lesson and "in review" is the honest state: the
            # batches ran, the course text is still to be written.
            module = create_module(course=course, actor=self.actor, title="Syllabus")
            create_lesson(
                module=module,
                actor=self.actor,
                title="Course outline",
                content_type=LessonContentType.TEXT,
                text_content=(
                    f"{self.book.batch_name} was delivered as {PROGRAMME} at {COLLEGE}. "
                    "The lecture-by-lecture syllabus is in the batch's workbook; "
                    "lesson content is still to be authored here."
                ),
            )
            set_course_status(
                course=course,
                target=PublishStatus.IN_REVIEW,
                actor=self.actor,
                may_publish=True,
                note=f"Imported from {self.book.path.name}.",
            )
            self.report.counts["courses created"] += 1
        self.report.course = course.code
        return course

    # --- trainer ---------------------------------------------------------

    def trainer(self):
        """Whoever wrote most of the DSR rows, as an account.

        Matched by name against existing trainers; created with a placeholder
        address otherwise, and reported as such so somebody can give them a
        real one. A batch needs a trainer for its reports to belong to anyone.
        """
        from apps.trainers.models import TrainerProfile
        from apps.trainers.services import create_trainer

        names = Counter(
            _clean_name(row.trainer_name) for row in self.book.dsr if _clean_name(row.trainer_name)
        )
        name = names.most_common(1)[0][0] if names else "SITP Trainer"

        for profile in TrainerProfile.objects.select_related("user"):
            if _same_person(profile.user.full_name, name):
                self.report.trainer = profile.trainer_id
                return profile

        first, _, last = name.partition(" ")
        email = f"trainer.{slugify(name) or 'sitp'}@{PLACEHOLDER_DOMAIN}"
        existing = TrainerProfile.objects.filter(user__email=email).select_related("user").first()
        if existing is not None:
            self.report.trainer = existing.trainer_id
            return existing
        profile = create_trainer(
            email=email,
            first_name=first.title(),
            last_name=last.title(),
            actor=self.actor,
            profile_fields={"professional_title": "Trainer, SITP ACE 2026"},
            send_invitation=False,
        )
        self.report.counts["trainers created"] += 1
        self.report.problem(
            "DSR", None, f"Trainer {name!r} has no account; created {email} with no way to sign in until a real address is set."
        )
        self.report.trainer = profile.trainer_id
        return profile

    # --- batch -----------------------------------------------------------

    def batch(self, course, trainer):
        from apps.batches.models import Batch, BatchKind, BatchStatus, DeliveryMode
        from apps.batches.services import create_batch

        name = f"{PROGRAMME} {self.book.year_label} — {self.book.batch_name}".replace("  ", " ").strip()
        # The batch spans every day anything happened: a register was taken or
        # a report was written. Reports often start a day or two before the
        # first register, and a class must fall inside its batch.
        dates = sorted(set(self.book.class_dates) | {row.on for row in self.book.dsr}) or [date.today()]
        batch = Batch.objects.filter(name=name).first()
        if batch is None:
            online = sum(1 for row in self.book.dsr if row.online)
            offline = sum(1 for row in self.book.dsr if row.offline)
            mode = (
                DeliveryMode.HYBRID if online and offline else DeliveryMode.ONLINE if online else DeliveryMode.OFFLINE
            )
            batch = create_batch(
                actor=self.actor,
                name=name,
                course=course,
                trainer=trainer,
                delivery_mode=mode,
                kind=BatchKind.INTERNSHIP,
                start_date=min(dates),
                end_date=max(dates),
                capacity=max(len(self.book.students) + 10, 20),
                status=BatchStatus.ACTIVE,
                description=f"Imported from {self.book.path.name}. {COLLEGE}, {self.book.year_label}.",
            )
            self.report.counts["batches created"] += 1
        self.report.batch = batch.code
        return batch

    # --- students and enrolments ------------------------------------------

    def roster(self, batch) -> dict[str, Any]:
        """Roll number → enrolment, creating students and enrolments as needed."""
        from apps.enrollments.models import Enrollment
        from apps.enrollments.services import DuplicateEnrollmentError, enrol_student
        from apps.students.models import InstitutionKind, StudentProfile
        from apps.students.services import create_student

        enrollments: dict[str, Any] = {}
        for student in self.book.students:
            profile = StudentProfile.objects.filter(roll_number=student.roll_number).select_related("user").first()
            if profile is None and student.email:
                profile = StudentProfile.objects.filter(user__email__iexact=student.email).select_related("user").first()
                if profile is not None and not profile.roll_number:
                    profile.roll_number = student.roll_number
                    profile.save(update_fields=["roll_number", "updated_at"])

            if profile is None:
                first, _, last = student.name.strip().partition(" ")
                nameless = student.name.startswith("Student ") and last == student.roll_number
                if nameless:
                    # The sheet gave a roll number and nothing else. A name
                    # field must hold a name, so the account is "Student" until
                    # somebody fills it in, and the record says why.
                    first, last = "Student", ""
                email = student.email or f"rtu-{student.roll_number.lower()}@{PLACEHOLDER_DOMAIN}"
                try:
                    profile = create_student(
                        email=email,
                        first_name=first.title()[:100],
                        last_name=last.title()[:100],
                        actor=self.actor,
                        send_invitation=False,
                        profile_fields={
                            "roll_number": student.roll_number,
                            "institution": COLLEGE,
                            "institution_kind": InstitutionKind.COLLEGE,
                            "notes": " ".join(
                                part
                                for part in (
                                    "" if student.email else "No email in the SITP sheet; placeholder address, cannot sign in until one is set.",
                                    f"Name not in the SITP sheet; known only by roll number {student.roll_number}." if nameless else "",
                                )
                                if part
                            ),
                        },
                    )
                except Exception as exc:  # noqa: BLE001 — reported per row
                    self.report.problem("Attendance", student.row, f"{student.name!r}: {_message(exc)}")
                    continue
                self.report.counts["students created"] += 1
                if not student.email:
                    self.report.counts["students without an email"] += 1
            else:
                self.report.counts["students already present"] += 1

            enrollment = Enrollment.objects.filter(student=profile, batch=batch).first()
            if enrollment is None:
                try:
                    enrollment = enrol_student(
                        student=profile, batch=batch, actor=self.actor, start_date=batch.start_date
                    )
                    self.report.counts["enrolments created"] += 1
                except DuplicateEnrollmentError:
                    enrollment = Enrollment.objects.filter(student=profile, batch=batch).first()
                except Exception as exc:  # noqa: BLE001
                    self.report.problem("Attendance", student.row, f"{student.name!r} could not be enrolled: {_message(exc)}")
                    continue
            enrollments[student.roll_number] = enrollment
        return enrollments

    # --- classes ------------------------------------------------------------

    def sessions(self, batch, trainer) -> dict[date, Any]:
        from apps.sessions.models import ClassSession
        from apps.sessions.services import create_session

        sessions: dict[date, Any] = {}
        topic_limit = ClassSession._meta.get_field("topic").max_length or 255
        topics = {row.on: row.topic[:topic_limit] for row in self.book.dsr if row.topic}
        # A class exists on every day the register was taken *and* every day a
        # report was written. A report on a day with no register is still a
        # class that happened — it gets a session with no attendance, rather
        # than the report being dropped.
        dsr_only = sorted({row.on for row in self.book.dsr} - set(self.book.class_dates))
        if dsr_only:
            self.report.counts["classes known only from a report"] += len(dsr_only)
        for when in sorted(set(self.book.class_dates) | set(dsr_only)):
            session = ClassSession.objects.filter(batch=batch, session_date=when, start_time=CLASS_START).first()
            if session is None:
                try:
                    session = create_session(
                        batch=batch,
                        actor=self.actor,
                        trainer=trainer,
                        session_date=when,
                        start_time=CLASS_START,
                        end_time=CLASS_END,
                        topic=topics.get(when, ""),
                    )
                    self.report.counts["classes created"] += 1
                except Exception as exc:  # noqa: BLE001
                    self.report.problem("Attendance", None, f"Class on {when} could not be created: {_message(exc)}")
                    continue
            sessions[when] = session
        return sessions

    # --- registers ----------------------------------------------------------

    def registers(self, sessions: dict[date, Any], enrollments: dict[str, Any]) -> None:
        from apps.attendance.models import AttendanceRecord
        from apps.attendance.services import mark_attendance

        by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for roll, register in self.book.attendance.items():
            enrollment = enrollments.get(roll)
            if enrollment is None:
                continue
            for when, status in register.items():
                by_date[when].append({"enrollment_id": str(enrollment.pk), "status": status, "note": ""})

        for when, entries in sorted(by_date.items()):
            session = sessions.get(when)
            if session is None:
                continue
            existing = {
                str(row.enrollment_id): row.status
                for row in AttendanceRecord.objects.filter(session=session)
            }
            if existing and all(existing.get(e["enrollment_id"]) == e["status"] for e in entries):
                self.report.counts["registers unchanged"] += 1
                continue
            try:
                mark_attendance(session=session, actor=self.actor, entries=entries)
                self.report.counts["registers marked"] += 1
                self.report.counts["attendance records"] += len(entries)
            except Exception as exc:  # noqa: BLE001
                self.report.problem("Attendance", None, f"Register for {when} refused: {_message(exc)}")

    # --- daily status reports ------------------------------------------------

    def reports(self, sessions: dict[date, Any], trainer) -> None:
        from apps.dsr.models import DSR
        from apps.dsr.services import start_dsr, submit_dsr

        for row in self.book.dsr:
            session = sessions.get(row.on)
            if session is None:
                self.report.problem("DSR", row.row, f"No class on {row.on} in the attendance sheet; report skipped.")
                continue
            if DSR.all_objects.filter(session=session).exists():
                self.report.counts["reports already present"] += 1
                continue
            present = row.present if row.present is not None else (row.online or 0) + (row.offline or 0)
            roster = row.roster_size or session.batch.enrollments.count()
            note = f"Imported from {self.book.path.name}, DSR row {row.row}."
            if row.online is None and row.offline is None and row.present is not None:
                note += " The sheet gave a head count only; online/offline split not recorded."
            topic_limit = DSR._meta.get_field("actual_topic").max_length or 255
            fields: dict[str, Any] = {
                "actual_topic": row.topic[:topic_limit],
                "planned_topic": row.topic[:topic_limit],
                "trainer": trainer,
                "student_count": roster,
                "present_count": present,
                "absent_count": max(roster - present, 0),
                "online_count": row.online or 0,
                "offline_count": row.offline or 0,
                "teaching_notes": note,
            }
            if row.assignment_given is not None:
                fields["assignment_given"] = row.assignment_given
            try:
                dsr = start_dsr(session=session, actor=self.actor, **fields)
                submit_dsr(dsr=dsr, actor=self.actor)
                self.report.counts["reports submitted"] += 1
            except Exception as exc:  # noqa: BLE001
                self.report.problem("DSR", row.row, f"Report for {row.on} refused: {_message(exc)}")

    # --- assessments ------------------------------------------------------------

    def assessments(self, batch, enrollments: dict[str, Any]) -> None:
        from apps.assessments.models import (
            Assessment,
            AssessmentCategory,
            AssessmentDelivery,
            AssessmentStatus,
            ResultSource,
        )
        from apps.assessments.services import create_assessment, record_result, set_assessment_status

        for column in self.book.assessments:
            title = f"{column.index}. {column.title}"[:200]
            assessment = Assessment.objects.filter(batch=batch, title=title).first()
            if assessment is None:
                try:
                    assessment = create_assessment(
                        actor=self.actor,
                        batch=batch,
                        title=title,
                        category=AssessmentCategory.WEEKLY_TEST,
                        delivery=AssessmentDelivery.OFFLINE,
                        max_marks=column.max_marks,
                    )
                    # A test whose marks exist has been sat: publish, then close.
                    set_assessment_status(assessment=assessment, actor=self.actor, status=AssessmentStatus.PUBLISHED)
                    set_assessment_status(assessment=assessment, actor=self.actor, status=AssessmentStatus.CLOSED)
                    self.report.counts["assessments created"] += 1
                except Exception as exc:  # noqa: BLE001
                    self.report.problem("Assessment", None, f"{title!r} could not be created: {_message(exc)}")
                    continue

            for roll, marks in self.book.marks.items():
                enrollment = enrollments.get(roll)
                if enrollment is None:
                    self.report.problem("Assessment", None, f"Roll {roll} has marks but is not on the attendance roster; skipped.")
                    continue
                value = marks.get(column.index)
                if value is None:
                    continue
                try:
                    if value == "absent":
                        _, created = record_result(
                            assessment=assessment, enrollment=enrollment, actor=self.actor, is_absent=True, source=ResultSource.IMPORT
                        )
                    else:
                        _, created = record_result(
                            assessment=assessment, enrollment=enrollment, actor=self.actor, marks=Decimal(value), source=ResultSource.IMPORT
                        )
                    self.report.counts["results created" if created else "results updated"] += 1
                except Exception as exc:  # noqa: BLE001
                    self.report.problem("Assessment", None, f"{roll} on {title!r}: {_message(exc)}")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value or "").strip()
    if name.lower() in ("sunday", "monday", "holiday", "", "-"):
        return ""
    return name


def _same_person(a: str, b: str) -> bool:
    """"Kapil Jangid" and "kapil jangid" are one person; so are "Vidyansh"
    and "Vidyansh Sharma" — a first name alone matches a trainer whose first
    name it is, when nothing else does."""
    left = _clean_name(a).lower().split()
    right = _clean_name(b).lower().split()
    if not left or not right:
        return False
    return left == right or (len(right) == 1 and right[0] == left[0]) or (len(left) == 1 and left[0] == right[0])


def _message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return "; ".join(f"{key}: {' '.join(map(str, value)) if isinstance(value, list) else value}" for key, value in detail.items())
    if hasattr(exc, "message_dict"):
        return "; ".join(f"{key}: {' '.join(map(str, value))}" for key, value in exc.message_dict.items())
    return str(detail or exc)
