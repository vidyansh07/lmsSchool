"""Turning a read batch sheet into batches, students and enrolments.

The sheet reader (`apps.batches.sheets`) refuses to guess; this refuses to
write anything the services would not accept. Everything goes through them —
`courses.services`, `batches.services.create_batch`,
`students.services.create_student`, `enrollments.services.enrol_student` —
so an imported record obeys the same validation as one typed in and lands in
the audit log under whoever ran the import.

Four decisions worth stating, because each is the kind an importer gets
wrong:

* **A course is matched, never invented.** A banner naming a course the
  catalogue does not have is a problem on the report, not a new course: a
  typo would otherwise create "Phyton Django" and nobody would see it until a
  student asked why their course is misspelled.
* **A student is matched by email, then by phone.** Re-importing a corrected
  sheet enrols nobody twice. Somebody with neither gets a placeholder address
  on a reserved domain that cannot receive mail (RFC 2606), which is how the
  SITP import already handles the same gap.
* **A batch is matched by its course, its start date and its name**, so a
  re-run adds the students who were added to the sheet rather than opening a
  second batch beside the first.
* **Dry run is the real run, rolled back.** The report a preview prints is
  the report the import would print, because it is produced by the same code
  inside a transaction that is then abandoned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import User
from apps.batches.models import Batch, BatchKind, DeliveryMode
from apps.batches.sheets import BatchSheet, SheetBatch, SheetStudent
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.courses.models import Course, PublishStatus

#: Addresses for people the sheet names without one. The domain is reserved
#: and cannot receive mail, which is the point: nothing is sent to it, and it
#: can never collide with somebody's real address.
PLACEHOLDER_DOMAIN = "batch.grras.invalid"

#: How long a batch runs when the sheet says only when it starts. Every sheet
#: so far gives a start and no end; the date is editable afterwards, and a
#: guess that is visibly a guess beats refusing the whole import.
DEFAULT_WEEKS = 12

#: Seats, when the sheet does not say. The roster it came with is the real
#: number; this leaves room for the two people who join in week one, and a
#: capacity that refused the import would be a worse guess than a generous
#: one.
SPARE_SEATS = 10


@dataclass
class ImportReport:
    """What the import did, or would do. Every row is accounted for."""

    batches_created: int = 0
    batches_matched: int = 0
    students_created: int = 0
    students_matched: int = 0
    enrolments_created: int = 0
    enrolments_existing: int = 0
    problems: list[dict[str, Any]] = field(default_factory=list)
    batch_names: list[str] = field(default_factory=list)

    def problem(self, sheet: str, row: int | None, message: str) -> None:
        self.problems.append({"sheet": sheet, "row": row, "message": message})

    def as_dict(self) -> dict[str, Any]:
        return {
            "batches_created": self.batches_created,
            "batches_matched": self.batches_matched,
            "students_created": self.students_created,
            "students_matched": self.students_matched,
            "enrolments_created": self.enrolments_created,
            "enrolments_existing": self.enrolments_existing,
            "batches": self.batch_names,
            "problems": self.problems,
        }


def _find_course(name: str) -> Course | None:
    """Exact title, then case-insensitive, then slug. Nothing fuzzier: a
    near-match that silently picks the wrong course is worse than a problem
    on the report."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    courses = Course.objects.exclude(status=PublishStatus.ARCHIVED)
    found = courses.filter(title=cleaned).first() or courses.filter(title__iexact=cleaned).first()
    if found is not None:
        return found
    return courses.filter(slug=slugify(cleaned)).first()


def _find_student(email: str, phone: str):
    from apps.students.models import StudentProfile

    if email:
        found = StudentProfile.objects.filter(user__email__iexact=email).first()
        if found is not None:
            return found
    digits = "".join(character for character in phone if character.isdigit())[-10:]
    if len(digits) == 10:
        return StudentProfile.objects.filter(user__phone__endswith=digits).first()
    return None


def _placeholder_email(name: str, phone: str) -> str:
    digits = "".join(character for character in phone if character.isdigit())[-10:]
    stem = digits or slugify(name) or "student"
    return f"{stem}@{PLACEHOLDER_DOMAIN}"


def _split_name(name: str) -> tuple[str, str]:
    parts = [part for part in name.replace(",", " ").split() if part]
    if not parts:
        return ("Student", "")
    if len(parts) == 1:
        return (parts[0].title(), "")
    return (parts[0].title(), " ".join(parts[1:]).title())


def _mode_for(students: list[SheetStudent]) -> str:
    """A batch's delivery mode, from what its roster says. Mixed rosters are
    hybrid, which is a real answer rather than a tie-break."""
    from apps.batches.sheets import parse_mode

    modes = {parse_mode(student.mode) for student in students} - {""}
    if modes == {DeliveryMode.ONLINE}:
        return DeliveryMode.ONLINE
    if modes == {DeliveryMode.OFFLINE}:
        return DeliveryMode.OFFLINE
    if len(modes) > 1:
        return DeliveryMode.HYBRID
    return DeliveryMode.OFFLINE


def _batch_name(sheet_batch: SheetBatch) -> str:
    when = sheet_batch.start_time.strftime("%I:%M %p").lstrip("0") if sheet_batch.start_time else ""
    started = sheet_batch.starts_on.strftime("%b %Y") if sheet_batch.starts_on else ""
    parts = [part for part in (when, started) if part]
    return " · ".join(parts) or sheet_batch.course_name[:60]


@transaction.atomic
def import_batch_sheet(
    *, actor: User, sheet: BatchSheet, dry_run: bool = False, branch=None
) -> ImportReport:
    """Apply a read sheet. With `dry_run`, roll the whole thing back.

    The rollback is deliberate rather than a separate code path: a preview
    that ran different code from the import would eventually disagree with
    it, and the disagreement would be found by whoever trusted the preview.
    """
    from apps.accounts.roles import Capability, has_capability
    from apps.enrollments.models import Enrollment
    from apps.enrollments.services import enrol_student
    from apps.students.services import create_student

    if not (
        has_capability(actor, Capability.BATCH_CREATE)
        and has_capability(actor, Capability.STUDENT_CREATE)
    ):
        raise AuthorityError("Importing a batch sheet needs the right to add batches and students.")

    report = ImportReport(problems=list(sheet.problems))

    for sheet_batch in sheet.batches:
        course = _find_course(sheet_batch.course_name)
        if course is None:
            report.problem(
                "Import",
                sheet_batch.row,
                f"No course in the catalogue is called {sheet_batch.course_name!r}; "
                "add the course first, or correct the spelling in the sheet.",
            )
            continue
        if sheet_batch.starts_on is None:
            # Already reported by the reader; skipped here so the counts stay
            # honest rather than inventing a start date.
            continue

        name = _batch_name(sheet_batch)
        batch = Batch.objects.filter(
            course=course, start_date=sheet_batch.starts_on, name=name
        ).first()
        if batch is None:
            batch = _open_batch(
                actor=actor,
                branch=branch,
                course=course,
                sheet_batch=sheet_batch,
                name=name,
                report=report,
            )
            if batch is None:
                continue
            report.batches_created += 1
        else:
            report.batches_matched += 1
        report.batch_names.append(f"{batch.code} {batch.name}")

        for student_row in sheet_batch.students:
            profile = _find_student(student_row.email, student_row.phone)
            if profile is None:
                first, last = _split_name(student_row.name)
                try:
                    profile = create_student(
                        email=student_row.email
                        or _placeholder_email(student_row.name, student_row.phone),
                        first_name=first,
                        last_name=last,
                        phone=student_row.phone,
                        actor=actor,
                        branch=branch or batch.branch,
                        # Nothing is emailed to an imported roster: the sheet
                        # is a record of who is in the room, and half of them
                        # have a placeholder address.
                        send_invitation=False,
                    )
                except (ApplicationError, AuthorityError) as refused:
                    report.problem("Import", student_row.row, _reason(refused, student_row.name))
                    continue
                report.students_created += 1
            else:
                report.students_matched += 1

            if Enrollment.objects.filter(student=profile, batch=batch).exists():
                report.enrolments_existing += 1
                continue
            try:
                enrol_student(student=profile, batch=batch, actor=actor)
            except (ApplicationError, AuthorityError) as refused:
                report.problem("Import", student_row.row, _reason(refused, student_row.name))
                continue
            report.enrolments_created += 1

    if dry_run:
        transaction.set_rollback(True)
    return report


def _open_batch(*, actor, branch, course, sheet_batch, name, report) -> Batch | None:
    from apps.batches.services import create_batch

    starts_on: date = sheet_batch.starts_on
    try:
        return create_batch(
            actor=actor,
            branch=branch,
            course=course,
            name=name,
            delivery_mode=_mode_for(sheet_batch.students),
            kind=BatchKind.REGULAR,
            start_date=starts_on,
            end_date=starts_on + timedelta(weeks=DEFAULT_WEEKS),
            capacity=len(sheet_batch.students) + SPARE_SEATS,
        )
    except (ApplicationError, AuthorityError) as refused:
        report.problem("Import", sheet_batch.row, _reason(refused, sheet_batch.course_name))
        return None


def _reason(error: Exception, subject: str) -> str:
    detail = getattr(error, "detail", None) or str(error)
    return f"{subject}: {detail}"
