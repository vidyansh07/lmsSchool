"""Enrolment and progress services.

The rules §5 asks for live here, in one place, so they hold whoever calls:
the API, an administrator in the Django admin, or the staging seeder.

Capacity
--------
Capacity cannot be a column constraint — it is a count of *other* rows. Two
requests arriving together would both read "one seat left" and both succeed, so
the batch row is locked with ``select_for_update`` before the count is taken.
The lock is held for the length of the transaction, which is one insert.

History
-------
Nothing here deletes. Cancelling and suspending change ``status`` and record
why; progress rows are never touched. A student who returns finds their history
intact, and a question months later can still be answered.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.batches.models import Batch
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_enrolment_code
from apps.courses.models import Lesson

from .models import (
    LIVE_STATUSES,
    Enrollment,
    EnrollmentStatus,
    LessonProgress,
    LessonProgressStatus,
)

#: Allowed enrolment status transitions.
TRANSITIONS: dict[str, frozenset[str]] = {
    EnrollmentStatus.PENDING: frozenset({EnrollmentStatus.ACTIVE, EnrollmentStatus.CANCELLED}),
    EnrollmentStatus.ACTIVE: frozenset(
        {EnrollmentStatus.SUSPENDED, EnrollmentStatus.COMPLETED, EnrollmentStatus.CANCELLED}
    ),
    EnrollmentStatus.SUSPENDED: frozenset({EnrollmentStatus.ACTIVE, EnrollmentStatus.CANCELLED}),
    # Terminal. Re-joining means a new enrolment, so the old record — and the
    # progress attached to it — stays exactly as it was.
    EnrollmentStatus.COMPLETED: frozenset(),
    EnrollmentStatus.CANCELLED: frozenset(),
}


class CapacityError(ApplicationError):
    status_code = 409
    default_detail = "This batch is full."
    default_code = "batch_full"


class DuplicateEnrollmentError(ConflictError):
    default_detail = "This student is already enrolled on this batch."
    default_code = "duplicate_enrollment"


# ---------------------------------------------------------------------------
# Enrolling
# ---------------------------------------------------------------------------


def _validate_enrollable(*, student, batch: Batch) -> None:
    """The §5 checklist, in one place."""
    problems: dict[str, list[str]] = {}

    if not student.user.is_active:
        problems["student"] = ["That student's account is not active."]

    if not batch.is_enrollable:
        problems["batch"] = [
            f"A {batch.get_status_display().lower()} batch is not accepting students."
        ]

    if problems:
        raise ApplicationError(problems)


@transaction.atomic
def enrol_student(
    *,
    student,
    batch: Batch,
    actor: User,
    status: str = EnrollmentStatus.ACTIVE,
    start_date=None,
    access_end_date=None,
    note: str = "",
) -> Enrollment:
    """Place a student on a batch.

    The batch row is locked first so the capacity check and the insert cannot be
    interleaved with another enrolment: without the lock, two concurrent
    requests would both see the final seat as free.
    """
    locked = Batch.objects.select_for_update().get(pk=batch.pk)
    _validate_enrollable(student=student, batch=locked)

    if Enrollment.objects.filter(student=student, batch=locked, status__in=LIVE_STATUSES).exists():
        raise DuplicateEnrollmentError()

    if status in (EnrollmentStatus.PENDING, EnrollmentStatus.ACTIVE):
        taken = locked.seats_taken()
        if taken >= locked.capacity:
            raise CapacityError(f"This batch is full ({taken} of {locked.capacity} seats taken).")

    enrollment = Enrollment(
        code=next_enrolment_code(),
        student=student,
        batch=locked,
        # Derived, never client-supplied: the course is whatever the batch runs.
        course=locked.course,
        status=status,
        start_date=start_date or locked.start_date,
        access_end_date=access_end_date,
        status_changed_at=timezone.now(),
        status_note=note,
        created_by=actor,
    )
    enrollment.full_clean(exclude=["code"])

    try:
        enrollment.save()
    except IntegrityError as exc:
        # The partial unique index is the real guard; the check above is only
        # there to produce a friendlier message first.
        raise DuplicateEnrollmentError() from exc

    record(
        action=AuditAction.ENROLLMENT_CREATED,
        actor=actor,
        resource_type="enrollment",
        resource_id=enrollment.pk,
        context={
            "code": enrollment.code,
            "student": student.student_id,
            "batch": locked.code,
            "course": locked.course.code,
            "status": status,
        },
    )
    return enrollment


@transaction.atomic
def set_enrollment_status(
    *, enrollment: Enrollment, target: str, actor: User, note: str = ""
) -> Enrollment:
    """Move an enrolment through its lifecycle.

    Access follows from the status on the very next request — there is nothing
    to invalidate, because :meth:`Enrollment.grants_access` is consulted live.
    """
    if enrollment.status == target:
        raise ApplicationError({"status": [f"The enrolment is already {target}."]})
    if target not in TRANSITIONS.get(enrollment.status, frozenset()):
        allowed = ", ".join(sorted(TRANSITIONS.get(enrollment.status, []))) or "nothing"
        raise ApplicationError(
            {
                "status": [
                    f"A {enrollment.status} enrolment cannot move to {target}. Allowed: {allowed}."
                ]
            }
        )

    # Re-activating must not push the batch over capacity.
    if target == EnrollmentStatus.ACTIVE and enrollment.status == EnrollmentStatus.SUSPENDED:
        locked = Batch.objects.select_for_update().get(pk=enrollment.batch_id)
        if locked.seats_taken() > locked.capacity:
            raise CapacityError("This batch is full; free a seat before reactivating.")

    previous = enrollment.status
    enrollment.status = target
    enrollment.status_changed_at = timezone.now()
    enrollment.status_note = note
    fields = ["status", "status_changed_at", "status_note", "updated_at"]

    if target == EnrollmentStatus.COMPLETED and enrollment.completed_at is None:
        enrollment.completed_at = timezone.now()
        fields.append("completed_at")

    enrollment.save(update_fields=fields)

    action = {
        EnrollmentStatus.CANCELLED: AuditAction.ENROLLMENT_CANCELLED,
        EnrollmentStatus.SUSPENDED: AuditAction.ENROLLMENT_SUSPENDED,
        EnrollmentStatus.COMPLETED: AuditAction.ENROLLMENT_COMPLETED,
    }.get(target, AuditAction.ENROLLMENT_STATUS_CHANGED)

    record(
        action=action,
        actor=actor,
        resource_type="enrollment",
        resource_id=enrollment.pk,
        context={
            "code": enrollment.code,
            "student": enrollment.student.student_id,
            "batch": enrollment.batch.code,
            "from": previous,
            "to": target,
            "note": note,
            # Stated explicitly so an auditor can see the intent: the row and
            # its progress survive.
            "history_preserved": True,
        },
    )
    return enrollment


@transaction.atomic
def cancel_enrollments_for_batch(*, batch: Batch, actor: User, reason: str) -> int:
    """Cancel every live enrolment on a batch. Used when a batch is cancelled."""
    cancelled = 0
    for enrollment in batch.enrollments.filter(status__in=LIVE_STATUSES).select_related(
        "student", "batch"
    ):
        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=actor, note=reason
        )
        cancelled += 1
    return cancelled


@transaction.atomic
def complete_enrollments_for_batch(*, batch: Batch, actor: User) -> int:
    """Mark active enrolments complete when a batch finishes.

    Suspended and pending enrolments are left alone — they did not finish the
    course, and recording that they did would be a false statement in a record
    a certificate may later be issued from.
    """
    completed = 0
    for enrollment in batch.enrollments.filter(status=EnrollmentStatus.ACTIVE).select_related(
        "student", "batch"
    ):
        set_enrollment_status(
            enrollment=enrollment,
            target=EnrollmentStatus.COMPLETED,
            actor=actor,
            note="The batch was completed.",
        )
        completed += 1
    return completed


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def _active_enrollment_for(student, course) -> Enrollment | None:
    candidates = (
        Enrollment.objects.granting_access()
        .filter(student=student, course=course)
        .select_related("batch")
        .order_by("-enrolled_at")
    )
    return next((row for row in candidates if row.grants_access()), None)


@transaction.atomic
def touch_lesson(*, student, lesson: Lesson) -> LessonProgress | None:
    """Record that a student opened a lesson.

    Returns ``None`` when the student has no enrolment granting access, so a
    preview lesson read by a browsing visitor creates no progress row. Progress
    is a record of study, not of curiosity.
    """
    enrollment = _active_enrollment_for(student, lesson.module.course)
    if enrollment is None:
        return None

    now = timezone.now()
    progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
        defaults={
            "status": LessonProgressStatus.IN_PROGRESS,
            "first_accessed_at": now,
            "last_accessed_at": now,
        },
    )
    if not created:
        progress.last_accessed_at = now
        progress.save(update_fields=["last_accessed_at", "updated_at"])
    return progress


@transaction.atomic
def set_lesson_completion(*, student, lesson: Lesson, completed: bool) -> LessonProgress:
    """Mark a lesson finished, or reopen it."""
    enrollment = _active_enrollment_for(student, lesson.module.course)
    if enrollment is None:
        raise ApplicationError(
            {"lesson": ["You need an active enrolment on this course to track progress."]}
        )

    now = timezone.now()
    progress, _ = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
        defaults={"first_accessed_at": now, "last_accessed_at": now},
    )
    progress.status = (
        LessonProgressStatus.COMPLETED if completed else LessonProgressStatus.IN_PROGRESS
    )
    progress.completed_at = now if completed else None
    progress.last_accessed_at = now
    progress.save(update_fields=["status", "completed_at", "last_accessed_at", "updated_at"])
    return progress


def course_progress(enrollment: Enrollment) -> dict[str, Any]:
    """A summary of how far a student has got.

    Counts published lessons only: a draft lesson an author is still writing
    should not make a student's progress bar go backwards.
    """
    from apps.courses.models import PublishStatus

    total = Lesson.objects.filter(
        module__course_id=enrollment.course_id,
        module__status=PublishStatus.PUBLISHED,
        status=PublishStatus.PUBLISHED,
    ).count()

    completed = enrollment.lesson_progress.filter(
        status=LessonProgressStatus.COMPLETED,
        lesson__status=PublishStatus.PUBLISHED,
        lesson__module__status=PublishStatus.PUBLISHED,
    ).count()

    last = (
        enrollment.lesson_progress.select_related("lesson", "lesson__module")
        .order_by("-last_accessed_at")
        .first()
    )

    return {
        "total_lessons": total,
        "completed_lessons": completed,
        "percent": round(completed * 100 / total) if total else 0,
        "last_lesson_id": str(last.lesson_id) if last else None,
        "last_lesson_title": last.lesson.title if last else None,
        "last_accessed_at": last.last_accessed_at if last else None,
    }
