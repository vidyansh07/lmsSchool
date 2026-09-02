"""Assessment and result services.

The rule that shapes this module: **a mark is written in exactly one place.**
Manual entry, file import and the grading of a backing assignment all end in
:func:`record_result`, so the bound check against ``max_marks``, the absence
rule and the audit entry cannot be skipped by arriving through a different
door.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_assessment_code
from apps.enrollments.models import Enrollment, EnrollmentStatus

from .models import (
    Assessment,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultSource,
)

TRANSITIONS: dict[str, frozenset[str]] = {
    AssessmentStatus.DRAFT: frozenset({AssessmentStatus.PUBLISHED, AssessmentStatus.ARCHIVED}),
    AssessmentStatus.PUBLISHED: frozenset({AssessmentStatus.CLOSED, AssessmentStatus.ARCHIVED}),
    AssessmentStatus.CLOSED: frozenset({AssessmentStatus.PUBLISHED, AssessmentStatus.ARCHIVED}),
    AssessmentStatus.ARCHIVED: frozenset(),
}

#: Enrolment statuses that put a student in an assessment cohort. Same rule as
#: the attendance register: a cancelled student is not sitting the test.
ASSESSABLE_STATUSES = frozenset(
    {EnrollmentStatus.ACTIVE, EnrollmentStatus.SUSPENDED, EnrollmentStatus.COMPLETED}
)


def cohort_for(assessment: Assessment):
    """Who this assessment is for, ordered by student id."""
    return (
        Enrollment.objects.filter(batch_id=assessment.batch_id, status__in=ASSESSABLE_STATUSES)
        .select_related("student", "student__user")
        .order_by("student__student_id")
    )


# ---------------------------------------------------------------------------
# The assessment
# ---------------------------------------------------------------------------


@transaction.atomic
def create_assessment(*, actor: User, batch, **fields: Any) -> Assessment:
    """Create a test in draft, on a batch.

    A file-upload assessment gets a backing assignment here, so the file
    security, attempt rules and grading path of §4.3/§4.4 are reused rather
    than reimplemented against a second upload model.
    """
    fields.pop("status", None)
    fields.pop("backing_assignment", None)
    if fields.get("max_marks") is None:
        # §4.7: what a weekly test is marked out of is configuration.
        from apps.academics.policies import policy_for

        fields["max_marks"] = policy_for(batch.course_id).test_default_max_marks

    assessment = Assessment(
        code=next_assessment_code(),
        batch=batch,
        course=batch.course,
        created_by=actor if getattr(actor, "pk", None) else None,
        status=AssessmentStatus.DRAFT,
        **fields,
    )
    _validate(assessment)
    assessment.save()

    if assessment.delivery == AssessmentDelivery.FILE_UPLOAD:
        assessment.backing_assignment = _create_backing_assignment(assessment, actor)
        assessment.save(update_fields=["backing_assignment", "updated_at"])

    record(
        action=AuditAction.ASSESSMENT_CREATED,
        actor=actor,
        resource_type="assessment",
        resource_id=assessment.pk,
        context={
            "code": assessment.code,
            "batch": str(batch.pk),
            "delivery": assessment.delivery,
            "category": assessment.category,
        },
        durable=False,
    )
    return assessment


def _create_backing_assignment(assessment: Assessment, actor: User):
    from apps.assignments.models import SubmissionKind
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=actor,
        course=assessment.course,
        batch=assessment.batch,
        title=assessment.title,
        instructions=assessment.description,
        submission_kind=SubmissionKind.FILE,
        max_marks=assessment.max_marks,
        passing_marks=assessment.passing_marks,
        due_at=assessment.closes_at,
    )


@transaction.atomic
def update_assessment(*, assessment: Assessment, actor: User, **fields: Any) -> Assessment:
    """Edit a test.

    The delivery mechanism is fixed once results exist — changing a file-upload
    test into an external link afterwards would orphan the submissions it was
    marked from.
    """
    fields.pop("status", None)
    fields.pop("backing_assignment", None)

    if assessment.results.exists():
        locked = {"delivery", "max_marks"}
        blocked = sorted(locked & set(fields))
        if blocked:
            raise ConflictError(
                {
                    field: ["This cannot change once results have been recorded."]
                    for field in blocked
                }
            )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(assessment, field) != value:
            setattr(assessment, field, value)
            changed.append(field)
    if not changed:
        return assessment

    _validate(assessment)
    assessment.save()

    record(
        action=AuditAction.ASSESSMENT_UPDATED,
        actor=actor,
        resource_type="assessment",
        resource_id=assessment.pk,
        context={"code": assessment.code, "fields": changed},
        durable=False,
    )
    return assessment


@transaction.atomic
def set_assessment_status(*, assessment: Assessment, actor: User, status: str) -> Assessment:
    """Move a test through its lifecycle.

    Publishing a file-upload test publishes its backing assignment too, so the
    student sees one thing rather than a test they cannot hand anything in for.
    """
    if status == assessment.status:
        return assessment
    if status not in TRANSITIONS.get(assessment.status, frozenset()):
        raise ConflictError(
            {"status": [f"An assessment cannot go from {assessment.status} to {status}."]}
        )

    previous = assessment.status
    assessment.status = status
    if status == AssessmentStatus.PUBLISHED and assessment.published_at is None:
        assessment.published_at = timezone.now()
    assessment.save(update_fields=["status", "published_at", "updated_at"])

    _mirror_status_to_backing_assignment(assessment, actor, status)

    if status == AssessmentStatus.PUBLISHED:
        from apps.notifications.models import NotificationKind
        from apps.notifications.services import notify_many, students_of_batch

        notify_many(
            recipients=students_of_batch(assessment.batch),
            kind=NotificationKind.TEST_SCHEDULED,
            title=f"Test scheduled: {assessment.title}",
            body=assessment.description[:300],
            link_path="/my-results",
            resource_type="assessment",
            resource_id=assessment.pk,
        )

    record(
        action=AuditAction.ASSESSMENT_STATUS_CHANGED,
        actor=actor,
        resource_type="assessment",
        resource_id=assessment.pk,
        context={"code": assessment.code, "from": previous, "to": status},
        durable=False,
    )
    return assessment


def _mirror_status_to_backing_assignment(assessment: Assessment, actor: User, status: str) -> None:
    if assessment.backing_assignment_id is None:
        return

    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import set_assignment_status

    mirror = {
        AssessmentStatus.PUBLISHED: AssignmentStatus.PUBLISHED,
        AssessmentStatus.CLOSED: AssignmentStatus.CLOSED,
        AssessmentStatus.ARCHIVED: AssignmentStatus.ARCHIVED,
    }.get(status)
    if mirror is None:
        return
    backing = assessment.backing_assignment
    if mirror in {AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED, AssignmentStatus.ARCHIVED}:
        try:
            set_assignment_status(assignment=backing, actor=actor, status=mirror)
        except ConflictError:
            # The assignment is already past that point (archived, say). The
            # assessment's own lifecycle is what matters; do not fail the
            # request over a mirror that has nowhere to go.
            pass


@transaction.atomic
def delete_assessment(*, assessment: Assessment, actor: User) -> None:
    if assessment.results.exists():
        raise ConflictError(
            {"assessment": ["Results have been recorded. Archive it instead of deleting."]}
        )
    code, pk = assessment.code, assessment.pk
    assessment.delete()
    record(
        action=AuditAction.ASSESSMENT_DELETED,
        actor=actor,
        resource_type="assessment",
        resource_id=pk,
        context={"code": code},
        durable=False,
    )


def _validate(assessment: Assessment) -> None:
    try:
        assessment.full_clean(exclude=["code", "backing_assignment"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def validate_mark(assessment: Assessment, marks, *, is_absent: bool) -> Decimal | None:
    """The single definition of an acceptable mark.

    Used by manual entry and by the importer, so a spreadsheet cannot express
    something the API would refuse.
    """
    if is_absent:
        if marks is not None:
            raise ApplicationError(
                {"marks_obtained": ["An absent student has no mark. Send one or the other."]}
            )
        return None
    if marks is None:
        raise ApplicationError(
            {"marks_obtained": ["A mark is required unless the student was absent."]}
        )
    value = Decimal(marks)
    if value < 0:
        raise ApplicationError({"marks_obtained": ["A mark cannot be negative."]})
    if value > assessment.max_marks:
        raise ApplicationError(
            {"marks_obtained": [f"The maximum for this assessment is {assessment.max_marks}."]}
        )
    return value


@transaction.atomic
def record_result(
    *,
    assessment: Assessment,
    enrollment: Enrollment,
    actor: User,
    marks: Decimal | None = None,
    is_absent: bool = False,
    remarks: str = "",
    source: str = ResultSource.MANUAL,
    import_run=None,
) -> tuple[AssessmentResult, bool]:
    """Write one student's outcome. Returns ``(result, created)``.

    Every path to a stored mark ends here.
    """
    if enrollment.batch_id != assessment.batch_id:
        raise ApplicationError({"enrollment": ["That student is not in this assessment's cohort."]})

    value = validate_mark(assessment, marks, is_absent=is_absent)

    result, created = AssessmentResult.objects.update_or_create(
        assessment=assessment,
        enrollment=enrollment,
        defaults={
            "marks_obtained": value,
            "is_absent": is_absent,
            "remarks": remarks[:500],
            "source": source,
            "import_run": import_run,
            "recorded_by": actor if getattr(actor, "pk", None) else None,
        },
    )

    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=enrollment.student.user,
        kind=NotificationKind.RESULT_PUBLISHED,
        title=assessment.title,
        body=("Recorded as absent." if is_absent else f"{value} out of {assessment.max_marks}."),
        link_path="/my-results",
        resource_type="assessment",
        resource_id=assessment.pk,
    )

    record(
        action=AuditAction.RESULT_RECORDED if created else AuditAction.RESULT_UPDATED,
        actor=actor,
        resource_type="assessment_result",
        resource_id=result.pk,
        context={
            "assessment": assessment.code,
            "enrollment": str(enrollment.pk),
            "marks": None if value is None else str(value),
            "absent": is_absent,
            "source": source,
        },
        durable=False,
    )
    return result, created


def sync_result_from_submission(submission) -> AssessmentResult | None:
    """Mirror a graded file-upload submission into the result table.

    Called from ``assignments.services.grade_submission``. Returns ``None`` when
    the assignment does not back an assessment, which is the usual case — an
    ordinary assignment is not a test.
    """
    assessment = getattr(submission.assignment, "backed_assessment", None)
    if assessment is None:
        return None

    result, _ = record_result(
        assessment=assessment,
        enrollment=submission.enrollment,
        actor=submission.graded_by,
        marks=submission.marks_awarded,
        remarks=f"Graded from submission attempt {submission.attempt}.",
        source=ResultSource.GRADED,
    )
    return result
