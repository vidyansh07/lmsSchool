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

from .models import DONE_STATUSES, DSR, EDITABLE_STATUSES, DSRStatus

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
        "topic_status",
        "homework",
        "homework_due_on",
        "homework_assignment",
        "extra_answers",
    }
)

#: What a trainer may say about the planned lesson. Mirrors
#: `apps.sessions.models.TopicStatus`, minus `planned`/`rescheduled`, which
#: describe a class that has not happened.
TOPIC_STATUSES = frozenset({"completed", "in_progress", "skipped"})


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


def resolve_trainer(session: ClassSession, actor: User | None):
    """Whose report this is.

    Ordinarily the trainer starting it — the common case, a trainer opening
    the report for a class they just took. A holder of `dsr.manage_any` may
    start one on somebody else's behalf (catching up a backlog, say), in which
    case there is no sensible trainer to infer from the actor, so it falls
    back to whoever is on record for the class: the trainer frozen onto the
    session, or failing that the batch's current trainer.
    """
    trainer = batch_access.trainer_profile(actor) if actor is not None else None
    if trainer is not None:
        return trainer
    if session.trainer_id:
        return session.trainer
    if session.batch.trainer_id:
        return session.batch.trainer
    raise ApplicationError(
        {"session": ["This class has no trainer assigned — there is nobody to write this report."]}
    )


def due_at_for(session: ClassSession):
    """When this class's report is due: its end plus
    `notification.dsr_due_hours`, in the class's own time zone."""
    from datetime import timedelta

    from apps.policies.resolver import policy

    return session.ends_at + timedelta(hours=int(policy("notification", "dsr_due_hours")))


def recorded_lesson_id(session: ClassSession):
    """The lesson a new report starts with as covered: the one the class
    already records as taught, else the one it planned — offered, never
    forced. None for a class whose topic was skipped or moved to a later
    class."""
    if session.topic_status in ("skipped", "rescheduled"):
        return None
    return session.actual_lesson_id or session.planned_lesson_id


def extra_form_version():
    """The published version of the institution's own extra questions
    (`dsr-extra`), or None when there is none or it asks nothing."""
    from apps.forms.models import FormDefinitionStatus, FormVersion, FormVersionStatus

    version = (
        FormVersion.objects.filter(
            definition__slug="dsr-extra",
            definition__status=FormDefinitionStatus.ACTIVE,
            status=FormVersionStatus.PUBLISHED,
        )
        .prefetch_related("fields")
        .first()
    )
    if version is None or not version.fields.exclude(type="heading").exists():
        return None
    return version


@transaction.atomic
def start_dsr(*, session: ClassSession, actor: User | None, **fields: Any) -> DSR:
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
    # What the class already says it covered, when the trainer recorded it.
    if session.topic_status in TOPIC_STATUSES:
        fields.setdefault("topic_status", session.topic_status)

    dsr = DSR(
        session=session,
        batch=session.batch,
        trainer=resolve_trainer(session, actor),
        status=DSRStatus.DRAFT,
        due_at=due_at_for(session),
        form_version=extra_form_version(),
        **{key: value for key, value in fields.items() if key in WRITABLE_FIELDS},
    )
    _validate(dsr)
    dsr.save()
    lesson_id = recorded_lesson_id(session)
    if lesson_id:
        dsr.lessons_covered.add(lesson_id)

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
    if "topic_status" in fields and fields["topic_status"] not in TOPIC_STATUSES:
        raise ApplicationError({"topic_status": ["Choose completed, in progress or skipped."]})

    # `{field: {"from": ..., "to": ...}}`, the same shape
    # `apps.fees.services.update_fee_plan` and `apps.authorization.services`
    # already write for their own edits — this is what
    # `docs/erp/DATA_MODEL.md`'s "ChangeHistory" note means by "the shape the
    # fee, settings and DSR services already write": a `GET /dsr/{id}/history/`
    # renders exactly this per row.
    changes: dict[str, dict[str, str]] = {}
    for field, value in fields.items():
        if field not in WRITABLE_FIELDS:
            continue
        old_value = getattr(dsr, field)
        if old_value != value:
            changes[field] = {"from": str(old_value), "to": str(value)}
            setattr(dsr, field, value)

    if not changes:
        return dsr

    _validate(dsr)
    dsr.save()

    record(
        action=AuditAction.DSR_UPDATED,
        actor=actor,
        resource_type="dsr",
        resource_id=dsr.pk,
        context={"changes": changes},
        durable=False,
    )
    return dsr


@transaction.atomic
def set_details(
    *,
    dsr: DSR,
    actor: User,
    lessons_covered: list | None = None,
    student_notes: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> DSR:
    """Replace the report's lessons covered, student notes and attachments —
    each only when given. Same status guard as `update_dsr`.

    Lessons must belong to the batch's course; notes must name an enrolment
    on this class's roster; attachments must be uploads the caller made."""
    if not force and dsr.status not in EDITABLE_STATUSES:
        raise ConflictError({"status": ["This report can no longer be edited."]})
    changes: dict[str, Any] = {}

    if lessons_covered is not None:
        from apps.courses.models import Lesson

        ids = [str(item) for item in lessons_covered]
        lessons = list(Lesson.objects.filter(pk__in=ids, module__course_id=dsr.batch.course_id))
        if len(lessons) != len(set(ids)):
            raise ApplicationError({"lessons_covered": ["Pick lessons from this batch's course."]})
        dsr.lessons_covered.set(lessons)
        changes["lessons_covered"] = sorted(ids)

    if student_notes is not None:
        from .models import DSRStudentNote, StudentFlag

        roster = {str(row.pk): row for row in roster_for(dsr.session)}
        rows: list[DSRStudentNote] = []
        seen: set[tuple[str, str]] = set()
        for entry in student_notes:
            enrollment_id = str(entry.get("enrollment") or "")
            flag = entry.get("flag")
            if enrollment_id not in roster:
                raise ApplicationError(
                    {"student_notes": ["A note names a student not in this class."]}
                )
            if flag not in StudentFlag.values:
                raise ApplicationError({"student_notes": [f"Unknown flag: {flag!r}."]})
            if (enrollment_id, flag) in seen:
                continue
            seen.add((enrollment_id, flag))
            rows.append(
                DSRStudentNote(
                    dsr=dsr,
                    enrollment=roster[enrollment_id],
                    flag=flag,
                    note=str(entry.get("note") or "")[:500],
                )
            )
        dsr.student_notes.all().delete()
        DSRStudentNote.objects.bulk_create(rows)
        changes["student_notes"] = len(rows)

    if attachments is not None:
        from apps.forms.models import FormUpload

        from .models import DSRAttachment

        rows_a: list[DSRAttachment] = []
        kept = {str(row.upload_id): row for row in dsr.attachments.all()}
        for entry in attachments:
            upload_id = str(entry.get("upload") or "")
            upload = FormUpload.objects.filter(pk=upload_id).first() if upload_id else None
            if upload is None:
                raise ApplicationError({"attachments": ["An attached file could not be found."]})
            if upload_id not in kept and upload.uploaded_by_id != getattr(actor, "pk", None):
                raise ApplicationError({"attachments": ["An attached file could not be found."]})
            rows_a.append(
                DSRAttachment(dsr=dsr, upload=upload, caption=str(entry.get("caption") or "")[:150])
            )
        dsr.attachments.all().delete()
        DSRAttachment.objects.bulk_create(rows_a)
        changes["attachments"] = len(rows_a)

    if changes:
        dsr.save(update_fields=["updated_at"])
        record(
            action=AuditAction.DSR_UPDATED,
            actor=actor,
            resource_type="dsr",
            resource_id=dsr.pk,
            context={"details": changes},
            durable=False,
        )
    return dsr


def _check_extra_answers(dsr: DSR, actor: User) -> None:
    """The institution's extra questions are validated when the report is
    handed in, against the version pinned when it was started."""
    if dsr.form_version_id is None:
        return
    from apps.forms.validation import validate_payload

    cleaned = validate_payload(
        version=dsr.form_version, values=dsr.extra_answers or {}, actor=actor
    )
    if cleaned != dsr.extra_answers:
        dsr.extra_answers = cleaned
        dsr.save(update_fields=["extra_answers", "updated_at"])


def _sync_session(dsr: DSR) -> None:
    """The report is what the class covered: the session's topic, its actual
    lesson and its topic status follow it, so the batch's timeline progress
    (`apps.progress.reports.timeline_progress`) counts what was reported.

    The session's own invariant holds throughout: a skipped class has no
    actual lesson, and a finished (or partly finished) one has one."""
    session = dsr.session
    covered = list(dsr.lessons_covered.order_by("module__position", "position"))
    status = dsr.topic_status if dsr.topic_status in TOPIC_STATUSES else ""
    # The report's own answer, else what the class already records.
    target = status or session.topic_status
    skipped = target == "skipped"
    fields = []
    if dsr.actual_topic and session.topic != dsr.actual_topic:
        session.topic = dsr.actual_topic[:250]
        fields.append("topic")
    if skipped:
        if session.actual_lesson_id is not None:
            session.actual_lesson = None
            fields.append("actual_lesson")
    # A lesson the trainer already named as the class's actual one stays, as
    # long as the report covers it too; otherwise the first covered lesson.
    # A class with no answer either way (still `planned`) is left alone.
    elif (
        target in ("completed", "in_progress")
        and covered
        and session.actual_lesson_id not in {lesson.pk for lesson in covered}
    ):
        session.actual_lesson = covered[0]
        fields.append("actual_lesson")
    # Finished, or partly, means some lesson was taught; without one on the
    # class the report cannot say so, and the class's own record stands.
    if (
        status
        and session.topic_status != status
        and (skipped or session.actual_lesson_id is not None)
    ):
        session.topic_status = status
        fields.append("topic_status")
    if fields:
        session.save(update_fields=[*fields, "updated_at"])


@transaction.atomic
def submit_dsr(*, dsr: DSR, actor: User) -> DSR:
    """Hand the report in. Submitted is done: no manager has to approve it
    (the owner's call, 3 October 2026), though one may still ask for
    changes. Draft or sent-back, never anything else."""
    if DSRStatus.SUBMITTED not in TRANSITIONS.get(dsr.status, frozenset()):
        raise ConflictError({"status": [f"A report cannot move from {dsr.status} to submitted."]})
    _check_extra_answers(dsr, actor)

    previous = dsr.status
    dsr.status = DSRStatus.SUBMITTED
    dsr.submitted_at = timezone.now()
    dsr.save(update_fields=["status", "submitted_at", "updated_at"])
    _sync_session(dsr)

    from .signals import dsr_submitted

    dsr_submitted.send(sender=DSR, dsr=dsr, actor=actor)

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


def _trusted_to_self_review(actor: User) -> bool:
    """A manager who also teaches a batch reviews her own report.

    The owner's call (14 September 2026): "manager is always a trusted one by
    company". The refusal stays for a trainer-role account, which is the case
    the rule was written for; a manager, administrator or superadmin who took
    the class signs it off themselves, and the audit row still names them as
    both author and reviewer.
    """
    from apps.accounts.roles import UserRole

    return actor.role in (UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN)


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
    if trainer is not None and trainer.pk == dsr.trainer_id and not _trusted_to_self_review(actor):
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

    if decision == DSRStatus.REJECTED:
        _notify_rejected(dsr)
    return dsr


def _notify_rejected(dsr: DSR) -> None:
    """Tell the trainer their report was turned back, and why.

    The same shape `apps.performance.services._notify_risk_changed` and
    `apps.work.services.review_activity` use for their own review-style
    notifications: one recipient, a title naming what changed, the reason in
    the body so there is something to act on.
    """
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    if not dsr.trainer.user_id:
        return
    notify(
        recipient=dsr.trainer.user,
        kind=NotificationKind.DSR_REJECTED,
        title=f"Report rejected: {dsr.batch.code} on {dsr.report_date.isoformat()}",
        body=dsr.manager_comments,
        link_path=f"/dsr/{dsr.pk}",
        resource_type="dsr",
        resource_id=dsr.pk,
    )


# ---------------------------------------------------------------------------
# After class: drafts, reminders and the overdue notice
# ---------------------------------------------------------------------------

#: How far back the sweep looks for classes that ended without a report.
#: Bounded, so turning this on never creates a draft for every class in a
#: batch's history — only for the ones that ended recently.
SWEEP_LOOKBACK_HOURS = 24


def _notify_trainer(dsr: DSR, *, kind: str, title: str, body: str) -> None:
    from apps.notifications.services import notify

    if not dsr.trainer.user_id:
        return
    notify(
        recipient=dsr.trainer.user,
        kind=kind,
        title=title,
        body=body,
        link_path=f"/teaching/today?session={dsr.session_id}",
        resource_type="dsr",
        resource_id=dsr.pk,
    )


def _centre_managers(dsr: DSR):
    from apps.accounts.roles import UserRole

    qs = User.objects.filter(role=UserRole.MANAGER, is_active=True)
    branch_id = getattr(dsr.batch, "branch_id", None)
    return qs.filter(branch_id=branch_id) if branch_id else qs.none()


def sweep_after_class(now=None) -> dict[str, int]:
    """Run every few minutes (`dsr.sweep`):

    1. a class that ended in the last day with no report gets a prefilled
       draft, and its trainer is told to fill it in;
    2. a draft still open `notification.dsr_reminder_hours` after the class
       gets one reminder;
    3. a draft past its due time is overdue: the centre's managers are told
       once, and it is a `DSR_MISSING` automation occurrence.
    """
    from datetime import timedelta

    from apps.notifications.models import NotificationKind
    from apps.policies.resolver import policy
    from apps.sessions.models import SessionStatus

    now = now or timezone.now()
    counts = {"drafted": 0, "reminded": 0, "overdue": 0}

    # 1. Drafts for classes that just ended. Dates first (indexed), then the
    # exact end time in each class's own zone.
    window_start = now - timedelta(hours=SWEEP_LOOKBACK_HOURS)
    today = timezone.localtime(now).date()
    candidates = (
        ClassSession.objects.filter(
            session_date__gte=today - timedelta(days=2),
            session_date__lte=today + timedelta(days=1),
            dsr__isnull=True,
        )
        .exclude(status=SessionStatus.CANCELLED)
        .exclude(status=SessionStatus.RESCHEDULED)
        .select_related("batch", "batch__course", "trainer", "trainer__user", "batch__trainer")
    )
    for session in candidates:
        if not (window_start <= session.ends_at <= now):
            continue
        if not (session.trainer_id or session.batch.trainer_id):
            continue
        try:
            with transaction.atomic():
                dsr = start_dsr(session=session, actor=None)
        except (ConflictError, ApplicationError):
            continue
        counts["drafted"] += 1
        _notify_trainer(
            dsr,
            kind=NotificationKind.DSR_DUE,
            title=f"Fill in today's class report: {dsr.batch.code}",
            body=(
                f"Your {session.start_time:%H:%M} class has ended. Attendance and the "
                "planned lesson are already filled in."
            ),
        )

    open_statuses = list(EDITABLE_STATUSES)

    # 2. One reminder.
    reminder_hours = int(policy("notification", "dsr_reminder_hours"))
    if reminder_hours > 0:
        for dsr in DSR.objects.with_related().filter(
            status__in=open_statuses,
            reminded_at__isnull=True,
            due_at__gt=now,
            report_date__gte=today - timedelta(days=2),
        ):
            if now < dsr.session.ends_at + timedelta(hours=reminder_hours):
                continue
            dsr.reminded_at = now
            dsr.save(update_fields=["reminded_at", "updated_at"])
            counts["reminded"] += 1
            _notify_trainer(
                dsr,
                kind=NotificationKind.DSR_REMINDER,
                title=f"Class report still to fill: {dsr.batch.code}",
                body=f"Due by {timezone.localtime(dsr.due_at):%H:%M}.",
            )

    # 3. Overdue, once.
    for dsr in DSR.objects.with_related().filter(
        status__in=open_statuses,
        overdue_notified_at__isnull=True,
        due_at__lte=now,
        due_at__gte=now - timedelta(days=7),
    ):
        dsr.overdue_notified_at = now
        dsr.save(update_fields=["overdue_notified_at", "updated_at"])
        counts["overdue"] += 1
        from apps.notifications.services import notify

        who = dsr.trainer.user.get_full_name() if dsr.trainer.user_id else "The trainer"
        for manager in _centre_managers(dsr):
            notify(
                recipient=manager,
                kind=NotificationKind.DSR_OVERDUE,
                title=f"Class report overdue: {dsr.batch.code} on {dsr.report_date:%d %b}",
                body=f"{who} has not submitted it.",
                link_path=f"/dsr?batch={dsr.batch_id}",
                resource_type="dsr",
                resource_id=dsr.pk,
            )
        from .signals import dsr_missing

        dsr_missing.send(sender=DSR, dsr=dsr)
    return counts


def missing_sessions(user, *, days: int = 14):
    """Classes in the caller's reach that ended in the last ``days`` days
    without a submitted report — the "Missing reports" list."""
    from datetime import timedelta

    from django.db.models import Q

    from apps.sessions import access as session_access
    from apps.sessions.models import SessionStatus

    now = timezone.now()
    today = timezone.localdate(now)
    rows = (
        session_access.visible_sessions(user)
        .filter(session_date__gte=today - timedelta(days=days), session_date__lte=today)
        .exclude(status__in=[SessionStatus.CANCELLED, SessionStatus.RESCHEDULED])
        .filter(Q(dsr__isnull=True) | Q(dsr__status__in=list(EDITABLE_STATUSES)))
        .select_related("batch", "trainer", "trainer__user", "batch__trainer__user")
        .order_by("-session_date", "-start_time")
    )
    return [session for session in rows if session.ends_at <= now]


# ---------------------------------------------------------------------------
# A batch at a glance, and its export
# ---------------------------------------------------------------------------


def _batch_classes(batch, *, days: int):
    from datetime import timedelta

    from apps.sessions.models import SessionStatus

    today = timezone.localdate()
    return list(
        ClassSession.objects.filter(
            batch=batch,
            session_date__gte=today - timedelta(days=days),
            session_date__lte=today,
        )
        .exclude(status__in=[SessionStatus.CANCELLED, SessionStatus.RESCHEDULED])
        .select_related("trainer__user", "batch__trainer__user", "actual_lesson", "planned_lesson")
        .order_by("session_date", "start_time")
    )


def _report_state(session, report, now) -> str:
    """One word for the class strip: upcoming, missing, overdue, draft,
    submitted, approved or changes requested."""
    if report is None:
        return "upcoming" if session.ends_at > now else "missing"
    if report.status in DONE_STATUSES:
        return "approved" if report.status == DSRStatus.APPROVED else "submitted"
    if report.status == DSRStatus.REVISION_REQUIRED:
        return "changes_requested"
    if report.due_at is not None and report.due_at < now:
        return "overdue"
    return "draft"


def batch_summary(batch, *, days: int = 30) -> dict[str, Any]:
    """The batch's classes over the last ``days`` days, each with its report
    state; how much of the course the reports say was covered; and the
    on-time record."""
    from apps.courses.models import Lesson, PublishStatus
    from apps.progress.reports import timeline_progress

    now = timezone.now()
    sessions = _batch_classes(batch, days=days)
    reports = {
        report.session_id: report
        for report in DSR.objects.filter(session__in=sessions).prefetch_related(
            "lessons_covered", "student_notes"
        )
    }
    classes = []
    counts = {"held": 0, "submitted": 0, "on_time": 0, "missing": 0, "overdue": 0}
    for session in sessions:
        report = reports.get(session.pk)
        state = _report_state(session, report, now)
        if state != "upcoming":
            counts["held"] += 1
        if state in ("submitted", "approved"):
            counts["submitted"] += 1
            if report.due_at is None or (
                report.submitted_at and report.submitted_at <= report.due_at
            ):
                counts["on_time"] += 1
        if state in ("missing", "overdue", "draft", "changes_requested"):
            counts["missing"] += 1
        if state == "overdue":
            counts["overdue"] += 1
        trainer = session.trainer or session.batch.trainer
        classes.append(
            {
                "session": str(session.pk),
                "date": session.session_date.isoformat(),
                "start_time": session.start_time.strftime("%H:%M"),
                "end_time": session.end_time.strftime("%H:%M"),
                "trainer_name": trainer.user.get_full_name() if trainer and trainer.user_id else "",
                "state": state,
                "dsr": str(report.pk) if report is not None else None,
                "topic": (report.actual_topic if report is not None else session.topic) or "",
                "lessons": [lesson.title for lesson in report.lessons_covered.all()]
                if report is not None
                else [],
                "topic_status": report.topic_status if report is not None else None,
                "present": report.present_count if report is not None else None,
                "absent": report.absent_count if report is not None else None,
                "student_notes": len(report.student_notes.all()) if report is not None else 0,
                "homework": bool(report and (report.homework or report.homework_assignment_id)),
            }
        )

    published = list(
        Lesson.objects.filter(module__course_id=batch.course_id, status=PublishStatus.PUBLISHED)
        .order_by("module__position", "position")
        .values_list("id", flat=True)
    )
    reported = set(
        DSR.objects.filter(batch=batch, status__in=list(DONE_STATUSES)).values_list(
            "lessons_covered", flat=True
        )
    )
    timeline = timeline_progress(batch)
    covered = {lesson_id for lesson_id in published if lesson_id in reported}
    total = len(published)
    return {
        "batch": {"id": str(batch.pk), "code": batch.code},
        "days": days,
        "classes": classes,
        "counts": counts,
        "coverage": {
            "lessons_total": total,
            "lessons_covered": len(covered),
            "percent": round(len(covered) * 100 / total) if total else None,
            "next_lesson": timeline.get("next_lesson"),
        },
    }


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    """A CSV cell that a spreadsheet will never run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def batch_export_csv(batch, *, days: int = 7) -> str:
    """The batch's class reports for the last ``days`` days, one row per
    class, for a weekly report."""
    import csv
    import io

    summary = batch_summary(batch, days=days)
    reports = {
        str(report.pk): report
        for report in DSR.objects.filter(batch=batch).select_related("homework_assignment")
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Date",
            "Start",
            "End",
            "Trainer",
            "Report",
            "Topic",
            "Lessons covered",
            "Topic status",
            "Present",
            "Absent",
            "Homework",
            "Issues",
            "Student concerns",
        ]
    )
    for row in summary["classes"]:
        report = reports.get(row["dsr"]) if row["dsr"] else None
        writer.writerow(
            [
                _cell(value)
                for value in (
                    row["date"],
                    row["start_time"],
                    row["end_time"],
                    row["trainer_name"],
                    row["state"],
                    row["topic"],
                    "; ".join(row["lessons"]),
                    row["topic_status"] or "",
                    row["present"] if row["present"] is not None else "",
                    row["absent"] if row["absent"] is not None else "",
                    report.homework if report is not None else "",
                    report.issues if report is not None else "",
                    report.student_concerns if report is not None else "",
                )
            ]
        )
    return buffer.getvalue()
