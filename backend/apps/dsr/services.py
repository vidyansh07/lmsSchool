"""Daily status report services.

Every status change is one function, wrapped in a transaction that also writes
the audit entry — the same discipline `apps.assignments.services` and
`apps.projects.services` use for their own workflows, and for the same
reason: a report's status is read by people deciding whether training is on
track, so how it got there has to be reconstructable.

The transition table
---------------------
::

    DRAFT ──────────────▸ SUBMITTED ─┬─▸ UNDER_REVIEW ─┬─▸ APPROVED
                                      ├─▸ APPROVED       ├─▸ REJECTED
                                      ├─▸ REJECTED        └─▸ REVISION_REQUIRED
                                      └─▸ REVISION_REQUIRED
    REVISION_REQUIRED ──▸ SUBMITTED

A reviewer may decide straight from ``SUBMITTED`` — ``UNDER_REVIEW`` is a
courtesy, not a checkpoint everything must pass through, matching how
`apps.projects.services.review_project` treats its own in-review state.
``APPROVED`` and ``REJECTED`` are terminal: a mistake is corrected by a fresh
report, not by reopening one a decision was already made on.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import COUNTS_AS_PRESENT, AttendanceRecord, AttendanceStatus
from apps.attendance.services import roster_for
from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.batches.models import DeliveryMode
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.sessions.models import ClassSession

from .models import DSR, EDITABLE_STATUSES, DSRStatus

#: Allowed status moves. See the module docstring for the shape of this.
TRANSITIONS: dict[str, frozenset[str]] = {
    DSRStatus.DRAFT: frozenset({DSRStatus.SUBMITTED}),
    DSRStatus.SUBMITTED: frozenset(
        {
            DSRStatus.UNDER_REVIEW,
            DSRStatus.APPROVED,
            DSRStatus.REJECTED,
            DSRStatus.REVISION_REQUIRED,
        }
    ),
    DSRStatus.UNDER_REVIEW: frozenset(
        {DSRStatus.APPROVED, DSRStatus.REJECTED, DSRStatus.REVISION_REQUIRED}
    ),
    DSRStatus.REVISION_REQUIRED: frozenset({DSRStatus.SUBMITTED}),
    DSRStatus.APPROVED: frozenset(),
    # Back to the trainer as a draft, not a dead end. A rejected report used to
    # have no outgoing transition at all, and `start_dsr` refuses a second
    # report for a class, so the class was left permanently unreportable.
    #
    # Rewriting is what distinguishes this from `REVISION_REQUIRED`, which keeps
    # the submission and asks for an amendment. Both end up resubmittable, which
    # they must — the class happened either way — but one says "change this" and
    # the other says "do it again".
    DSRStatus.REJECTED: frozenset({DSRStatus.DRAFT}),
}

#: The audit action each review decision writes.
_REVIEW_ACTIONS: dict[str, str] = {
    DSRStatus.UNDER_REVIEW: AuditAction.DSR_REVIEW_STARTED,
    DSRStatus.APPROVED: AuditAction.DSR_APPROVED,
    DSRStatus.REJECTED: AuditAction.DSR_REJECTED,
    DSRStatus.REVISION_REQUIRED: AuditAction.DSR_REVISION_REQUESTED,
}

#: Decisions a reviewer must explain. Approving needs no reason; sending work
#: back or rejecting it without one leaves the trainer nothing to act on —
#: the same rule `apps.assignments.services.return_submission` enforces.
_DECISIONS_REQUIRING_COMMENTS = frozenset({DSRStatus.REJECTED, DSRStatus.REVISION_REQUIRED})

#: Fields a trainer's own write may touch. ``status``, the workflow timestamps
#: and everything reviewer-owned are absent on purpose — they move only
#: through :func:`submit_dsr` and :func:`review_dsr`.
WRITABLE_FIELDS = frozenset(
    {
        "report_date",
        "start_time",
        "end_time",
        "module",
        "planned_topic",
        "actual_topic",
        "student_count",
        "present_count",
        "absent_count",
        "online_count",
        "offline_count",
        "teaching_notes",
        "issues",
        "student_concerns",
        "assignment_given",
        "assessment_conducted",
    }
)


def _validate(dsr: DSR) -> None:
    from django.core.exceptions import ValidationError as DjangoValidationError

    try:
        dsr.full_clean()
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


def prefill_counts(session: ClassSession) -> dict[str, int]:
    """Today's numbers from the register, not recomputed by hand.

    `apps.attendance.models.attendance_summary` answers a different question —
    how this *student* has done across every class they have ever attended.
    What a report needs is how *this* class went, so the roster and the status
    classification (`COUNTS_AS_PRESENT`) are the pieces reused from attendance;
    the grouping itself is scoped to the one session, which no existing
    attendance function does.

    A class with no register taken yet — the common case, since a report is
    usually started around the same time as the register — still gets a
    sensible roster count and zero present/absent, rather than an empty
    section the trainer has to fill in from memory.

    Online and offline are counted the same way, from each enrolment's
    `effective_delivery_mode` — their own setting when they have one, the
    batch's otherwise. They were previously left at zero for the trainer to
    type, which is a number a person should never be asked for: the system
    already knows how each student on the roster is taught, and asking anyway
    means the report is only as accurate as somebody's memory at the end of a
    long day. A hybrid student counts as online, because the question the field
    answers is "who was not in the room".

    The counts are of the *roster*, not of who turned up — the two are
    different questions, and the present and absent figures above already
    answer the second one.
    """
    roster = list(roster_for(session).select_related("batch"))
    student_count = len(roster)

    marks = AttendanceRecord.objects.filter(session=session).values_list("status", flat=True)
    present_count = sum(1 for status in marks if status in COUNTS_AS_PRESENT)
    absent_count = sum(1 for status in marks if status == AttendanceStatus.ABSENT)

    online_count = sum(
        1 for enrolment in roster if enrolment.effective_delivery_mode != DeliveryMode.OFFLINE
    )

    return {
        "student_count": student_count,
        "present_count": present_count,
        "absent_count": absent_count,
        "online_count": online_count,
        "offline_count": student_count - online_count,
    }


def resolve_trainer(session: ClassSession, actor: User):
    """Whose report this is.

    Ordinarily the trainer starting it — the common case, a trainer opening
    the report for a class they just took. A holder of `dsr.manage_any` may
    start one on somebody else's behalf (catching up a backlog, say), in which
    case there is no sensible trainer to infer from the actor, so it falls
    back to whoever is on record for the class: the trainer frozen onto the
    session, or failing that the batch's current trainer.
    """
    trainer = batch_access.trainer_profile(actor)
    if trainer is not None:
        return trainer
    if session.trainer_id:
        return session.trainer
    if session.batch.trainer_id:
        return session.batch.trainer
    raise ApplicationError(
        {"session": ["This class has no trainer assigned — there is nobody to write this report."]}
    )


@transaction.atomic
def start_dsr(*, session: ClassSession, actor: User, **fields: Any) -> DSR:
    """Create the draft for one class, prefilled from its register.

    This is written at the end of class, on the way out of the room, not as a
    considered report drafted later — so the form has to arrive mostly filled
    in. Everything that already exists somewhere else is copied in rather than
    asked for a second time: the times and topic come from the session record
    the trainer already keeps, the counts from the register they just took.
    What is left to type is only what nothing else captured — teaching notes,
    issues, concerns — and a trainer with nothing to add should be able to
    submit without typing anything at all.

    One report per class is enforced at the database level (`session` is a
    `OneToOneField`); this checks it first, against every report including
    soft-deleted ones, so a stale report on a session does not surface as an
    opaque integrity error.
    """
    if DSR.all_objects.filter(session=session).exists():
        raise ConflictError({"session": ["A daily status report already exists for this class."]})

    fields.pop("status", None)
    fields.setdefault("report_date", session.session_date)
    fields.setdefault("start_time", session.start_time)
    fields.setdefault("end_time", session.end_time)
    # `ClassSession.topic` is "what was covered", filled in by the trainer at
    # the same moment — there is no separate record of what was *planned*, so
    # both start from it. A trainer correcting either afterwards is editing a
    # prefilled value, not typing from a blank field.
    fields.setdefault("planned_topic", session.topic)
    fields.setdefault("actual_topic", session.topic)
    for key, value in prefill_counts(session).items():
        fields.setdefault(key, value)

    dsr = DSR(
        session=session,
        batch=session.batch,
        trainer=resolve_trainer(session, actor),
        status=DSRStatus.DRAFT,
        **{key: value for key, value in fields.items() if key in WRITABLE_FIELDS},
    )
    _validate(dsr)
    dsr.save()

    record(
        action=AuditAction.DSR_CREATED,
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"session_id": str(session.pk), "batch_code": session.batch.code},
        durable=False,
    )
    return dsr


@transaction.atomic
def update_dsr(*, dsr: DSR, actor: User, force: bool = False, **fields: Any) -> DSR:
    """Edit a report's content. Refused once it has left the trainer's hands.

    ``force`` is what lets `dsr.manage_any` do what `access.can_write_dsr`
    promises it can: correct a report after the fact without first sending it
    back through the workflow. A view sets it from that same capability check
    rather than every caller re-deciding when a status guard applies —
    ordinary trainer writes never pass it, so the guard still holds for them
    even if a future call site forgets to check `can_write_dsr` first.
    """
    if not force and dsr.status not in EDITABLE_STATUSES:
        raise ConflictError({"status": ["This report can no longer be edited."]})

    changed: list[str] = []
    for field, value in fields.items():
        if field not in WRITABLE_FIELDS:
            continue
        if getattr(dsr, field) != value:
            setattr(dsr, field, value)
            changed.append(field)

    if not changed:
        return dsr

    _validate(dsr)
    dsr.save()

    record(
        action=AuditAction.DSR_UPDATED,
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"fields": changed},
        durable=False,
    )
    return dsr


@transaction.atomic
def submit_dsr(*, dsr: DSR, actor: User) -> DSR:
    """Hand a report to its reviewer. Draft or sent-back, never anything else."""
    if DSRStatus.SUBMITTED not in TRANSITIONS.get(dsr.status, frozenset()):
        raise ConflictError({"status": [f"A report cannot move from {dsr.status} to submitted."]})

    previous = dsr.status
    dsr.status = DSRStatus.SUBMITTED
    dsr.submitted_at = timezone.now()
    dsr.save(update_fields=["status", "submitted_at", "updated_at"])

    record(
        action=AuditAction.DSR_SUBMITTED,
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"from": previous},
        durable=False,
    )
    return dsr


@transaction.atomic
def reopen_dsr(*, dsr: DSR, actor: User) -> DSR:
    """Take a rejected report back to a draft, so it can be written again.

    The way out of a rejection. Without it a rejected report is a dead end: it
    cannot be revised, and `start_dsr` refuses a second report for the class, so
    the class is left permanently unreportable — by anybody, at any level.

    Deliberately its own service rather than a side effect of editing. A report
    going from "the manager rejected this" back to "the trainer is writing it"
    is a real event in the class's history, and it should be findable in the
    audit trail rather than inferred from a later edit.

    The manager's comments are kept. They are the reason this is being rewritten
    and the trainer needs to read them; clearing them here would delete the only
    explanation at the moment it becomes useful.
    """
    if DSRStatus.DRAFT not in TRANSITIONS.get(dsr.status, frozenset()):
        raise ConflictError({"status": [f"A {dsr.status} report cannot be taken back to a draft."]})

    previous = dsr.status
    dsr.status = DSRStatus.DRAFT
    dsr.submitted_at = None
    dsr.save(update_fields=["status", "submitted_at", "updated_at"])

    record(
        action=AuditAction.DSR_UPDATED,
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"from": previous, "to": DSRStatus.DRAFT, "reason": "reopened_after_rejection"},
        durable=False,
    )
    return dsr


@transaction.atomic
def review_dsr(*, dsr: DSR, actor: User, decision: str, comments: str = "") -> DSR:
    """Take a submitted report under review, or rule on it.

    ``decision`` is one of `DSRStatus.UNDER_REVIEW`, `APPROVED`, `REJECTED` or
    `REVISION_REQUIRED`. The self-review refusal is repeated here rather than
    left to `access.can_review_dsr` alone, for the same "do not trust the
    caller" reason `update_dsr` repeats its own status check.
    """
    if decision not in _REVIEW_ACTIONS:
        raise ApplicationError({"decision": [f"'{decision}' is not a review decision."]})
    if decision not in TRANSITIONS.get(dsr.status, frozenset()):
        raise ConflictError({"status": [f"A report cannot move from {dsr.status} to {decision}."]})

    trainer = batch_access.trainer_profile(actor)
    if trainer is not None and trainer.pk == dsr.trainer_id:
        raise AuthorityError({"dsr": ["You cannot review your own daily status report."]})

    if decision in _DECISIONS_REQUIRING_COMMENTS and not comments.strip():
        raise ApplicationError(
            {"manager_comments": ["Say why, so the trainer knows what to change."]}
        )

    previous = dsr.status
    dsr.status = decision
    dsr.reviewed_at = timezone.now()
    dsr.reviewed_by = actor if getattr(actor, "pk", None) else None
    dsr.manager_comments = comments
    dsr.save(
        update_fields=["status", "reviewed_at", "reviewed_by", "manager_comments", "updated_at"]
    )

    record(
        action=_REVIEW_ACTIONS[decision],
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"from": previous, "to": decision},
        durable=False,
    )
    return dsr
