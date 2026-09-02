"""Assignment services.

Everything that decides *whether* something may happen lives here — the
submission window, the attempt count, the mark range — so the same rule holds
whether the request arrived from the API, a management command or a future
background job.

Two rules deserve stating outright, because both are places this kind of system
usually goes wrong:

**The server owns the clock.** Whether a submission is late is decided from
``timezone.now()`` against the assignment's due date. The client never sends a
timestamp, so a wound-back device clock changes nothing.

**The server owns the marks.** ``grade_submission`` takes one raw mark for one
attempt and checks it against ``assignment.max_marks``. It never accepts a
total, a percentage or a pass/fail flag from the browser — those are derived on
read, from stored values.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_assignment_code
from apps.common.uploads import (
    MAX_SUBMISSION_FILES,
    MAX_SUBMISSION_TOTAL_BYTES,
    validate_resource_upload,
    validate_submission_upload,
)
from apps.enrollments.models import Enrollment

from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionFile,
    SubmissionKind,
    SubmissionStatus,
)

#: Allowed status moves. Reopening a closed assignment is deliberate: a trainer
#: who closed the work early has to be able to undo that without losing the
#: submissions already made. Archiving is one-way.
TRANSITIONS: dict[str, frozenset[str]] = {
    AssignmentStatus.DRAFT: frozenset({AssignmentStatus.PUBLISHED, AssignmentStatus.ARCHIVED}),
    AssignmentStatus.PUBLISHED: frozenset({AssignmentStatus.CLOSED, AssignmentStatus.ARCHIVED}),
    AssignmentStatus.CLOSED: frozenset({AssignmentStatus.PUBLISHED, AssignmentStatus.ARCHIVED}),
    AssignmentStatus.ARCHIVED: frozenset(),
}


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------


@transaction.atomic
def create_assignment(*, actor: User, course, **fields: Any) -> Assignment:
    """Create an assignment in draft.

    New work always starts as a draft, whatever the caller asked for: a brief
    that appears to students the instant it is created leaves no room to finish
    writing it.
    """
    fields.pop("status", None)
    _apply_policy_defaults(course, fields)

    assignment = Assignment(
        code=next_assignment_code(),
        course=course,
        created_by=actor if getattr(actor, "pk", None) else None,
        status=AssignmentStatus.DRAFT,
        **fields,
    )
    _validate(assignment)
    assignment.save()

    record(
        action=AuditAction.ASSIGNMENT_CREATED,
        actor=actor,
        resource_type="assignment",
        resource_id=assignment.pk,
        context={"code": assignment.code, "course_id": str(course.pk), "title": assignment.title},
        durable=False,
    )
    return assignment


@transaction.atomic
def update_assignment(*, assignment: Assignment, actor: User, **fields: Any) -> Assignment:
    """Edit a brief.

    Tightening the rules under students who have already submitted is refused:
    once work is in, the terms it was set under stop being editable. Everything
    else — wording, instructions, extending a deadline — stays open.
    """
    fields.pop("status", None)
    has_submissions = assignment.submissions.exists()

    if has_submissions:
        locked = {"max_marks", "submission_kind"}
        blocked = sorted(locked & set(fields))
        if blocked:
            raise ConflictError(
                {field: ["This cannot change once students have submitted."] for field in blocked}
            )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(assignment, field) != value:
            setattr(assignment, field, value)
            changed.append(field)

    if not changed:
        return assignment

    _validate(assignment)
    assignment.save()

    record(
        action=AuditAction.ASSIGNMENT_UPDATED,
        actor=actor,
        resource_type="assignment",
        resource_id=assignment.pk,
        context={"code": assignment.code, "fields": changed},
        durable=False,
    )
    return assignment


@transaction.atomic
def set_assignment_status(*, assignment: Assignment, actor: User, status: str) -> Assignment:
    """Move an assignment through its lifecycle."""
    if status == assignment.status:
        return assignment
    if status not in TRANSITIONS.get(assignment.status, frozenset()):
        raise ConflictError(
            {"status": [f"An assignment cannot go from {assignment.status} to {status}."]}
        )

    previous = assignment.status
    assignment.status = status
    if status == AssignmentStatus.PUBLISHED and assignment.published_at is None:
        assignment.published_at = timezone.now()
    assignment.save(update_fields=["status", "published_at", "updated_at"])

    record(
        action=AuditAction.ASSIGNMENT_STATUS_CHANGED,
        actor=actor,
        resource_type="assignment",
        resource_id=assignment.pk,
        context={"code": assignment.code, "from": previous, "to": status},
        durable=False,
    )
    return assignment


@transaction.atomic
def delete_assignment(*, assignment: Assignment, actor: User) -> None:
    """Remove a brief that nobody has answered.

    Once a submission exists the assignment is part of a student's record;
    archive it instead, which hides it without destroying the marks attached
    to it.
    """
    if assignment.submissions.exists():
        raise ConflictError(
            {"assignment": ["Work has already been submitted. Archive it instead of deleting."]}
        )
    code, pk = assignment.code, assignment.pk
    assignment.delete()
    record(
        action=AuditAction.ASSIGNMENT_DELETED,
        actor=actor,
        resource_type="assignment",
        resource_id=pk,
        context={"code": code},
        durable=False,
    )


@transaction.atomic
def add_attachment(
    *, assignment: Assignment, actor: User, uploaded_file, title: str
) -> AssignmentAttachment:
    """Attach a brief document or starter files.

    Trainer-supplied, so it goes through the course-resource rules: extension
    allowlist paired with a magic-byte family, server-generated path.
    """
    try:
        _, content_type = validate_resource_upload(uploaded_file)
    except DjangoValidationError as exc:
        raise ApplicationError({"file": list(exc.messages)}) from exc

    attachment = AssignmentAttachment(
        assignment=assignment,
        title=title,
        original_filename=(getattr(uploaded_file, "name", "") or "")[:255],
        content_type=content_type,
        size_bytes=uploaded_file.size,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
    )
    attachment.file = uploaded_file
    attachment.save()

    record(
        action=AuditAction.ASSIGNMENT_ATTACHMENT_ADDED,
        actor=actor,
        resource_type="assignment_attachment",
        resource_id=attachment.pk,
        context={"assignment": assignment.code, "size_bytes": attachment.size_bytes},
        durable=False,
    )
    return attachment


@transaction.atomic
def remove_attachment(*, attachment: AssignmentAttachment, actor: User) -> None:
    pk, code = attachment.pk, attachment.assignment.code
    attachment.file.delete(save=False)
    attachment.delete()
    record(
        action=AuditAction.ASSIGNMENT_ATTACHMENT_REMOVED,
        actor=actor,
        resource_type="assignment_attachment",
        resource_id=pk,
        context={"assignment": code},
        durable=False,
    )


def _apply_policy_defaults(course, fields: dict[str, Any]) -> None:
    """Fill in what the trainer did not say from the academic configuration.

    §4.7: the marks-out-of, the late policy and the attempt limit are rules an
    administrator sets, not constants in this module. A trainer who states one
    explicitly still wins — the configuration is a default, not a ceiling.
    """
    from apps.academics.policies import policy_for

    policy = policy_for(course)
    defaults = {
        "max_marks": policy.assignment_default_max_marks,
        "allow_late": policy.assignment_allow_late,
        "max_attempts": policy.assignment_default_max_attempts,
    }
    for field, value in defaults.items():
        if fields.get(field) is None:
            fields[field] = value


def _validate(assignment: Assignment) -> None:
    try:
        assignment.full_clean(exclude=["code"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


def enrollment_for(*, assignment: Assignment, student) -> Enrollment | None:
    """The enrolment through which this student may answer this assignment.

    A student can hold several enrolments; only one of them puts this
    assignment in front of them. Returning it — rather than a boolean — means
    the submission row is tied to the right batch from the start.
    """
    rows = (
        Enrollment.objects.granting_access()
        .filter(student=student, course_id=assignment.course_id)
        .select_related("batch")
    )
    for enrollment in rows:
        if enrollment.grants_access() and assignment.applies_to_batch(enrollment.batch_id):
            return enrollment
    return None


def _check_window(assignment: Assignment, moment) -> bool:
    """Whether the window is open, and whether this counts as late.

    Returns ``is_late``; raises when nothing is accepted at all.
    """
    if assignment.status != AssignmentStatus.PUBLISHED:
        raise ApplicationError({"assignment": ["This assignment is not open for submission."]})

    if assignment.late_cutoff_at and moment > assignment.late_cutoff_at:
        raise ApplicationError({"assignment": ["The submission window has closed."]})

    late = assignment.is_late_at(moment)
    if late and not assignment.allow_late:
        raise ApplicationError({"assignment": ["The deadline has passed."]})
    return late


def _next_attempt(assignment: Assignment, enrollment: Enrollment) -> int:
    """Which attempt this submission is, refusing when no attempt is left.

    A returned attempt always earns one more try — that is what "returned for
    rework" means, and a trainer who asks for a rework should not have to raise
    the attempt limit to allow it.
    """
    previous = list(
        AssignmentSubmission.objects.filter(assignment=assignment, enrollment=enrollment).order_by(
            "-attempt"
        )[:1]
    )
    if not previous:
        return 1

    latest = previous[0]
    if latest.status == SubmissionStatus.RETURNED:
        return latest.attempt + 1
    if latest.status == SubmissionStatus.GRADED:
        raise ConflictError(
            {"assignment": ["This work has been graded and cannot be resubmitted."]}
        )
    if not assignment.allow_resubmission:
        raise ConflictError({"assignment": ["You have already submitted this assignment."]})
    if latest.attempt >= assignment.max_attempts:
        raise ConflictError(
            {
                "assignment": [
                    f"You have used all {assignment.max_attempts} attempts for this assignment."
                ]
            }
        )
    return latest.attempt + 1


def _check_content(assignment: Assignment, files, text: str, link: str) -> None:
    """Refuse an empty hand-in, and one that ignores what was asked for."""
    kind = assignment.submission_kind
    if kind == SubmissionKind.FILE and not files:
        raise ApplicationError({"files": ["This assignment requires at least one file."]})
    if kind == SubmissionKind.TEXT and not text.strip():
        raise ApplicationError({"text_answer": ["This assignment requires a written answer."]})
    if kind == SubmissionKind.LINK and not link.strip():
        raise ApplicationError({"link_url": ["This assignment requires a link."]})
    if kind == SubmissionKind.ANY and not (files or text.strip() or link.strip()):
        raise ApplicationError({"files": ["Submit a file, a written answer or a link."]})


def _validate_files(files) -> list[tuple[Any, str, str]]:
    """Validate every file before any of them is written.

    All-or-nothing on purpose: a submission that stored three of five files and
    then failed would look complete to the student and be incomplete to the
    trainer.
    """
    if len(files) > MAX_SUBMISSION_FILES:
        raise ApplicationError(
            {"files": [f"Submit at most {MAX_SUBMISSION_FILES} files in one attempt."]}
        )

    total = 0
    problems: dict[str, list[str]] = {}
    checked: list[tuple[Any, str, str]] = []

    for uploaded in files:
        try:
            extension, checksum = validate_submission_upload(uploaded)
        except DjangoValidationError as exc:
            # Reported under `files`, the field the student actually sees, with
            # the filename in the message. Keying by index instead would hide
            # the problem behind a field name no form renders.
            name = (getattr(uploaded, "name", "") or "this file")[:120]
            problems.setdefault("files", []).extend(
                f"{name}: {message}" for message in exc.messages
            )
            continue
        total += uploaded.size
        checked.append((uploaded, extension, checksum))

    if problems:
        raise ApplicationError(problems)
    if total > MAX_SUBMISSION_TOTAL_BYTES:
        raise ApplicationError(
            {
                "files": [
                    "The files add up to more than "
                    f"{MAX_SUBMISSION_TOTAL_BYTES // (1024 * 1024)} MB in one attempt."
                ]
            }
        )
    return checked


@transaction.atomic
def submit_assignment(
    *,
    assignment: Assignment,
    enrollment: Enrollment,
    actor: User,
    files: list | None = None,
    text_answer: str = "",
    link_url: str = "",
) -> AssignmentSubmission:
    """Record one attempt, with its files."""
    files = list(files or [])
    now = timezone.now()

    is_late = _check_window(assignment, now)
    _check_content(assignment, files, text_answer, link_url)
    attempt = _next_attempt(assignment, enrollment)
    checked = _validate_files(files)

    submission = AssignmentSubmission(
        assignment=assignment,
        enrollment=enrollment,
        attempt=attempt,
        status=SubmissionStatus.SUBMITTED,
        text_answer=text_answer,
        link_url=link_url,
        submitted_at=now,
        is_late=is_late,
    )
    try:
        submission.save()
    except IntegrityError as exc:
        # Two tabs, one deadline. The unique index on (assignment, enrollment,
        # attempt) is what actually prevents the double row; this turns it into
        # an answer the student can act on.
        raise ConflictError(
            {"assignment": ["Another submission was recorded a moment ago. Reload and check."]}
        ) from exc

    for uploaded, extension, checksum in checked:
        stored = SubmissionFile(
            submission=submission,
            original_filename=(getattr(uploaded, "name", "") or "")[:255],
            extension=extension,
            size_bytes=uploaded.size,
            checksum=checksum,
        )
        stored.file = uploaded
        stored.save()

    record(
        action=AuditAction.SUBMISSION_CREATED,
        actor=actor,
        resource_type="assignment_submission",
        resource_id=submission.pk,
        context={
            "assignment": assignment.code,
            "attempt": attempt,
            "late": is_late,
            "file_count": len(checked),
        },
        durable=False,
    )
    return submission


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


@transaction.atomic
def grade_submission(
    *,
    submission: AssignmentSubmission,
    actor: User,
    marks: Decimal,
    feedback: str = "",
) -> AssignmentSubmission:
    """Award marks for one attempt.

    The bound is the assignment's own ``max_marks``, read from the database —
    not a limit sent with the request. Awarding 500 out of 100 is refused here
    even if every layer above were bypassed.
    """
    if marks is None:
        raise ApplicationError({"marks": ["A mark is required."]})
    if marks < 0:
        raise ApplicationError({"marks": ["A mark cannot be negative."]})
    if marks > submission.assignment.max_marks:
        raise ApplicationError(
            {"marks": [f"The maximum for this assignment is {submission.assignment.max_marks}."]}
        )

    superseded = AssignmentSubmission.objects.filter(
        assignment_id=submission.assignment_id,
        enrollment_id=submission.enrollment_id,
        attempt__gt=submission.attempt,
    ).exists()
    if superseded:
        raise ConflictError({"submission": ["A later attempt exists. Grade the most recent one."]})

    submission.marks_awarded = marks
    submission.feedback = feedback
    submission.status = SubmissionStatus.GRADED
    submission.graded_by = actor if getattr(actor, "pk", None) else None
    submission.graded_at = timezone.now()
    submission.save(
        update_fields=[
            "marks_awarded",
            "feedback",
            "status",
            "graded_by",
            "graded_at",
            "updated_at",
        ]
    )

    record(
        action=AuditAction.SUBMISSION_GRADED,
        actor=actor,
        resource_type="assignment_submission",
        resource_id=submission.pk,
        context={
            "assignment": submission.assignment.code,
            "attempt": submission.attempt,
            "marks": str(marks),
            "max_marks": str(submission.assignment.max_marks),
        },
        durable=False,
    )

    # A file-upload assessment is backed by an assignment (see
    # `apps.assessments.models`), so grading one is also recording a result.
    # Imported inline, as `batches.services` does, to keep the dependency
    # one-directional at module load.
    from apps.assessments.services import sync_result_from_submission

    sync_result_from_submission(submission)

    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=submission.enrollment.student.user,
        kind=NotificationKind.ASSIGNMENT_GRADED,
        title=f"Graded: {submission.assignment.title}",
        body=f"{marks} out of {submission.assignment.max_marks}.",
        link_path="/my-assignments",
        resource_type="assignment",
        resource_id=submission.assignment_id,
    )
    return submission


@transaction.atomic
def return_submission(
    *, submission: AssignmentSubmission, actor: User, feedback: str
) -> AssignmentSubmission:
    """Send work back for rework, which opens one further attempt."""
    if not feedback.strip():
        raise ApplicationError(
            {
                "feedback": [
                    "Say what needs reworking — returning work without a reason is not useful."
                ]
            }
        )
    if submission.status == SubmissionStatus.RETURNED:
        return submission

    submission.status = SubmissionStatus.RETURNED
    submission.feedback = feedback
    submission.graded_by = actor if getattr(actor, "pk", None) else None
    submission.graded_at = timezone.now()
    submission.save(update_fields=["status", "feedback", "graded_by", "graded_at", "updated_at"])

    record(
        action=AuditAction.SUBMISSION_RETURNED,
        actor=actor,
        resource_type="assignment_submission",
        resource_id=submission.pk,
        context={"assignment": submission.assignment.code, "attempt": submission.attempt},
        durable=False,
    )
    return submission
