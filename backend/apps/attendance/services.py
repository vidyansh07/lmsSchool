"""Attendance services.

The design constraint is the real workflow: a trainer finishes a class and marks
twenty students in one go, on a phone, in under a minute. So the write path is
**bulk by default** — one request, one transaction, two queries — rather than a
row at a time.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.sessions.models import ClassSession, SessionStatus

from .models import AttendanceRecord, AttendanceStatus

#: Enrolment statuses that put a student on the register.
#:
#: A cancelled student is not in the room. A suspended one might be — suspension
#: is usually administrative (fees), not a bar from the classroom — so they stay
#: on the register and the trainer decides.
REGISTERABLE_STATUSES = frozenset(
    {EnrollmentStatus.ACTIVE, EnrollmentStatus.SUSPENDED, EnrollmentStatus.COMPLETED}
)


def roster_for(session: ClassSession):
    """Who should be on this class's register.

    Ordered by student id so the list is stable between page loads — a register
    that reorders itself is a register that gets mis-marked.
    """
    return (
        Enrollment.objects.filter(batch=session.batch, status__in=REGISTERABLE_STATUSES)
        .select_related("student", "student__user")
        .order_by("student__student_id")
    )


@transaction.atomic
def mark_attendance(
    *, session: ClassSession, actor: User, entries: list[dict[str, Any]]
) -> dict[str, int]:
    """Record a whole register in one go.

    ``entries`` is ``[{"enrollment_id": ..., "status": ..., "note": ...}, ...]``.

    Everything is validated before anything is written, so a single bad row
    rejects the request rather than leaving half a register saved. Re-marking an
    already-marked class is a **correction**, and is recorded as one.
    """
    if session.status == SessionStatus.CANCELLED:
        raise ApplicationError(
            {"session": ["A cancelled class has no attendance — nobody could attend it."]}
        )
    if not session.can_take_attendance:
        raise ApplicationError({"session": ["This class has not started yet."]})

    valid_statuses = set(AttendanceStatus.values)
    roster = {str(row.pk): row for row in roster_for(session)}

    # --- validate everything first
    seen: set[str] = set()
    problems: dict[str, list[str]] = {}
    for index, entry in enumerate(entries):
        enrollment_id = str(entry.get("enrollment_id", ""))
        status = entry.get("status")

        if enrollment_id in seen:
            problems.setdefault(f"entries[{index}]", []).append(
                "Duplicate student in the register."
            )
        seen.add(enrollment_id)

        if enrollment_id not in roster:
            # Either not on this batch, or not in a state that puts them on the
            # register. Either way it is not this trainer's row to write.
            problems.setdefault(f"entries[{index}]", []).append(
                "That student is not on this class's register."
            )
        if status not in valid_statuses:
            problems.setdefault(f"entries[{index}]", []).append(f"Unknown status {status!r}.")

    if problems:
        raise ApplicationError(problems)

    # --- then write
    now = timezone.now()
    existing = {
        str(row.enrollment_id): row for row in AttendanceRecord.objects.filter(session=session)
    }

    created: list[AttendanceRecord] = []
    updated: list[AttendanceRecord] = []
    corrections = 0

    for entry in entries:
        enrollment_id = str(entry["enrollment_id"])
        status = entry["status"]
        note = (entry.get("note") or "")[:255]
        row = existing.get(enrollment_id)

        if row is None:
            created.append(
                AttendanceRecord(
                    session=session,
                    enrollment=roster[enrollment_id],
                    status=status,
                    note=note,
                    marked_by=actor,
                    marked_at=now,
                )
            )
            continue

        if row.status == status and row.note == note:
            continue

        # Re-marking is a correction: the previous value is kept.
        if row.status != status:
            row.previous_status = row.status
            row.corrected_by = actor
            row.corrected_at = now
            corrections += 1
        row.status = status
        row.note = note
        updated.append(row)

    if created:
        AttendanceRecord.objects.bulk_create(created)
    if updated:
        AttendanceRecord.objects.bulk_update(
            updated,
            ["status", "note", "previous_status", "corrected_by", "corrected_at", "updated_at"],
        )

    session.attendance_taken_at = now
    session.attendance_taken_by = actor
    fields = ["attendance_taken_at", "attendance_taken_by", "updated_at"]
    # Taking the register is the natural moment a class becomes complete.
    if session.status == SessionStatus.SCHEDULED and session.has_ended:
        session.status = SessionStatus.COMPLETED
        fields.append("status")
    session.save(update_fields=fields)

    record(
        action=AuditAction.ATTENDANCE_CORRECTED if corrections else AuditAction.ATTENDANCE_MARKED,
        actor=actor,
        resource_type="class_session",
        resource_id=session.pk,
        context={
            "batch_code": session.batch.code,
            "date": session.session_date.isoformat(),
            "created": len(created),
            "updated": len(updated),
            "corrections": corrections,
        },
    )
    return {"created": len(created), "updated": len(updated), "corrections": corrections}


@transaction.atomic
def correct_record(
    *, record_row: AttendanceRecord, actor: User, status: str, reason: str
) -> AttendanceRecord:
    """Change one student's mark on one class, with a reason.

    Separate from bulk marking because a correction days later is a different
    act from taking a register, and should be answerable on its own.
    """
    if status not in set(AttendanceStatus.values):
        raise ApplicationError({"status": ["Unknown attendance status."]})
    if record_row.status == status:
        raise ApplicationError({"status": ["That is already the recorded status."]})

    previous = record_row.status
    record_row.previous_status = previous
    record_row.status = status
    record_row.corrected_by = actor
    record_row.corrected_at = timezone.now()
    record_row.correction_reason = reason
    record_row.save(
        update_fields=[
            "status",
            "previous_status",
            "corrected_by",
            "corrected_at",
            "correction_reason",
            "updated_at",
        ]
    )

    record(
        action=AuditAction.ATTENDANCE_CORRECTED,
        actor=actor,
        resource_type="attendance",
        resource_id=record_row.pk,
        context={
            "batch_code": record_row.session.batch.code,
            "date": record_row.session.session_date.isoformat(),
            "student": record_row.enrollment.student.student_id,
            "from": previous,
            "to": status,
            "reason": reason,
        },
    )
    return record_row
