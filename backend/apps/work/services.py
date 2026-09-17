"""The activity engine's business rules (ERP Phase 9).

Every state change funnels through here: `services.py` is the only module
that writes an `Activity`'s `status` (or an `ActivityHistory` row), so the
audit trail, the notification and the lifecycle rule can never be forgotten
by a future call site. Views resolve *which* record a URL names
(`access.visible_activities` and friends); this module never re-derives
that, it is handed the row.

The extension point later phases read
------------------------------------
`apps.work.signals.activity_changed` is sent after `create_activity`,
`transition_activity`, `complete_activity` and `delete_activity` (not
`review_activity` — see its own docstring) with `(activity, event, actor)`.
Phase 13 (risk) listens for `event="completed"`; Phase 14 (automation) can
listen for any of them, including `"deleted"`, without this module importing
a single line from either app.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts.roles import UserRole
from apps.audit.services import AuditAction, record
from apps.common.caching import forget
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.forms import services as forms_services
from apps.forms.models import FormVersion, FormVersionStatus
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify

from . import access
from .models import (
    Activity,
    ActivityHistory,
    ActivityPriority,
    ActivityResult,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
)
from .signals import activity_changed
from .transitions import Actor, edge_for, legal_targets

#: A person's own role never has to appear in an `ActivityType`'s
#: `allowed_creator_roles`/`allowed_assignee_roles` list — the catalog is
#: authored by an administrator narrowing what the *day-to-day* roles may
#: do, and it would be a strange and fragile catalog if every one of the 18
#: seeded rows also had to spell out "superadmin, admin" to remain usable by
#: the very rung that maintains the catalog. Capability + scope
#: (`access.can_create_for`/`can_be_assigned`) still applies in full.
_PRIVILEGED_ROLES = frozenset({UserRole.SUPERADMIN, UserRole.ADMIN})

#: No policy key exists for this yet (`docs/erp/DATA_MODEL.md` §5 names only
#: `risk.activity_score_below`, for Phase 13). A reasonable, documented
#: default: an assigned activity whose planned time plus an hour has passed
#: with nobody having started it is missed.
MISSED_GRACE_MINUTES = 60

#: How wide a window `send_activity_reminders` treats as "just crossed the
#: reminder threshold" — wide enough that a beat tick running a little late
#: does not skip a reminder, narrow enough (matching the beat cadence
#: `config/settings/base.py` schedules this task at) that the same tick
#: cannot fire it twice. `reminder_sent_at` is the real guard against a
#: double-send; this just bounds how far back a sweep looks.
REMINDER_WINDOW_MINUTES = 15

TYPES_CACHE_PREFIX = "work:types"


def validate_assignee(activity_type: ActivityType, assigned_to, *, branch_id, batch_id) -> None:
    """Is `assigned_to` a legitimate assignee for this type in this
    branch/batch context? The type's `allowed_assignee_roles` allowlist
    narrows who *may* be handed this kind of activity; `access.can_be_assigned`
    then checks the concrete scope. `create_activity` enforces both when an
    activity is first assigned; `views.ActivityDetailView.patch` calls this
    same function when reassigning an existing one, so a PATCH can never hand
    an activity to someone the create path would have refused."""
    assignee_allowed = assigned_to.role in _PRIVILEGED_ROLES or assigned_to.role in (
        activity_type.allowed_assignee_roles or []
    )
    if not assignee_allowed:
        raise ApplicationError(
            {"assigned_to": ["This role may not be assigned this activity type."]}
        )
    if not access.can_be_assigned(assigned_to, branch_id=branch_id, batch_id=batch_id):
        raise ApplicationError(
            {"assigned_to": ["This person is outside the scope for this student."]}
        )


class TransitionError(ConflictError):
    """An illegal move through `transitions.TRANSITIONS`."""

    default_detail = "That status change is not allowed."
    default_code = "invalid_transition"


# ---------------------------------------------------------------------------
# Activity types
# ---------------------------------------------------------------------------


def _forget_types() -> None:
    forget(TYPES_CACHE_PREFIX)


@transaction.atomic
def create_activity_type(*, actor, **fields: Any) -> ActivityType:
    if not access.can_manage_activity_types(actor):
        raise AuthorityError("You do not have authority to manage the activity catalog.")
    slug = fields.get("slug")
    if ActivityType.objects.filter(slug=slug).exists():
        raise ConflictError({"slug": ["An activity type with this slug already exists."]})
    try:
        with transaction.atomic():
            activity_type = ActivityType.objects.create(**fields)
    except IntegrityError:
        # A concurrent create won the slug race between the check above and
        # this insert — same translation `apps.forms.services.create_definition`
        # gives its own slug race, confined to its own savepoint so the outer
        # transaction stays usable.
        raise ConflictError({"slug": ["An activity type with this slug already exists."]}) from None
    _forget_types()
    record(
        action=AuditAction.ACTIVITY_TYPE_CREATED,
        actor=actor,
        resource_type="activity_type",
        resource_id=activity_type.pk,
        context={"slug": slug, "category": activity_type.category},
        durable=False,
    )
    return activity_type


@transaction.atomic
def update_activity_type(*, actor, activity_type: ActivityType, **fields: Any) -> ActivityType:
    """Change any column except `slug` — the serializer never offers it."""
    if not access.can_manage_activity_types(actor):
        raise AuthorityError("You do not have authority to manage the activity catalog.")
    changed: list[str] = []
    for name, value in fields.items():
        if getattr(activity_type, name) != value:
            setattr(activity_type, name, value)
            changed.append(name)
    if changed:
        activity_type.save(update_fields=[*changed, "updated_at"])
        _forget_types()
        record(
            action=AuditAction.ACTIVITY_TYPE_UPDATED,
            actor=actor,
            resource_type="activity_type",
            resource_id=activity_type.pk,
            context={"changed": changed},
            durable=False,
        )
    return activity_type


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _advisory_lock_key(*parts: str) -> int:
    """A deterministic signed 64-bit key for `pg_advisory_xact_lock`, the
    same technique `apps.accounts.otp._advisory_lock_key` uses for its own
    check-then-act race — never derived from anything secret, only from
    identifiers that are already fine to compute on."""
    digest = sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _lock_client_key(created_by_id: Any, client_key: str) -> None:
    key = _advisory_lock_key("work:create_activity", str(created_by_id), client_key)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _recent_by_client_key(created_by, client_key: str) -> Activity | None:
    cutoff = timezone.now() - timedelta(hours=24)
    return (
        Activity.objects.filter(
            created_by=created_by, client_key=client_key, created_at__gte=cutoff
        )
        .order_by("-created_at")
        .first()
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@transaction.atomic
def create_activity(
    *,
    actor,
    student,
    activity_type: ActivityType,
    enrollment=None,
    title: str | None = None,
    assigned_to=None,
    planned_at=None,
    due_at=None,
    priority: str | None = None,
    student_visible: bool | None = None,
    client_key: str | None = None,
) -> Activity:
    if client_key:
        # Serialises identical concurrent retries on this (creator, key)
        # pair before either has read whether the other already won —
        # exactly the check-then-act shape `AGENT_PLAYBOOK.md` calls out.
        _lock_client_key(getattr(actor, "pk", None), client_key)
        existing = _recent_by_client_key(actor, client_key)
        if existing is not None:
            return existing

    if activity_type.status != ActivityTypeStatus.ACTIVE:
        raise ApplicationError({"activity_type": ["This activity type is disabled."]})

    if enrollment is not None:
        if enrollment.student_id != student.pk:
            raise ApplicationError(
                {"enrollment": ["This enrolment does not belong to the student."]}
            )
        batch = enrollment.batch
        branch = batch.branch
    else:
        batch = None
        branch = student.branch

    # The type's allowlist narrows the capability; it never replaces it.
    role_allowed = actor.role in _PRIVILEGED_ROLES or actor.role in (
        activity_type.allowed_creator_roles or []
    )
    if not role_allowed:
        raise AuthorityError("Your role may not create this kind of activity.")
    if not access.can_create_for(actor, branch_id=branch.pk, batch_id=batch.pk if batch else None):
        raise AuthorityError("You do not have authority to create an activity for this student.")

    if assigned_to is not None:
        validate_assignee(
            activity_type, assigned_to, branch_id=branch.pk, batch_id=batch.pk if batch else None
        )

    if student_visible is True and not activity_type.visible_to_student:
        # An activity may override the type's default to *hidden*, never to
        # *visible* — the type sets the ceiling.
        raise ApplicationError(
            {"student_visible": ["This activity type is not visible to students."]}
        )
    resolved_visible = (
        activity_type.visible_to_student if student_visible is None else student_visible
    )

    form_version = None
    if activity_type.form_id:
        form_version = FormVersion.objects.filter(
            definition_id=activity_type.form_id, status=FormVersionStatus.PUBLISHED
        ).first()
        if form_version is None:
            raise ApplicationError(
                {"activity_type": ["This activity type's form has no published version yet."]}
            )

    activity = Activity.objects.create(
        student=student,
        enrollment=enrollment,
        batch=batch,
        branch=branch,
        activity_type=activity_type,
        title=(title or activity_type.name)[:160],
        status=ActivityStatus.DRAFT,
        priority=priority or ActivityPriority.NORMAL,
        created_by=actor,
        assigned_to=assigned_to,
        planned_at=planned_at,
        due_at=due_at,
        form_version=form_version,
        student_visible=resolved_visible,
        client_key=client_key or "",
    )

    record(
        action=AuditAction.ACTIVITY_CREATED,
        actor=actor,
        resource_type="activity",
        resource_id=activity.pk,
        context={
            "activity_type": activity_type.slug,
            "student": str(student.pk),
            "assigned_to": str(assigned_to.pk) if assigned_to else None,
        },
        durable=False,
    )
    if assigned_to is not None:
        notify(
            recipient=assigned_to,
            kind=NotificationKind.ACTIVITY_ASSIGNED,
            title=f"New activity: {activity.title}",
            body=activity.summary,
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )
    activity_changed.send(sender=Activity, activity=activity, event="created", actor=actor)
    return activity


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


def _actor_satisfies(kind: str, actor, activity: Activity) -> bool:
    if kind == Actor.SYSTEM:
        return actor is None
    if actor is None or not getattr(actor, "pk", None):
        return False
    if kind == Actor.CREATOR:
        return activity.created_by_id == actor.pk
    if kind == Actor.ASSIGNEE:
        return activity.assigned_to_id == actor.pk
    if kind == Actor.ASSIGN_HOLDER:
        return access.can_assign(actor, activity)
    if kind == Actor.REVIEW_HOLDER:
        return access.can_review(actor, activity)
    if kind == Actor.REOPEN_HOLDER:
        return access.can_reopen(actor, activity)
    return False


@transaction.atomic
def transition_activity(
    *, actor, activity: Activity, to_status: str, note: str | None = None
) -> Activity:
    edge = edge_for(activity.status, to_status)
    if edge is None:
        raise TransitionError(
            {
                "non_field_errors": [
                    f"An activity in '{activity.status}' cannot move to '{to_status}'."
                ],
                "allowed": sorted(legal_targets(activity.status)),
            }
        )

    if not _actor_satisfies(edge.actor, actor, activity):
        if edge.actor == Actor.SYSTEM:
            raise AuthorityError("This transition can only be made by the system.")
        raise AuthorityError("You do not have authority to make this transition.")

    if edge.requires_note and not (note or "").strip():
        raise ApplicationError({"note": ["A note is required for this transition."]})
    if edge.precondition == "planned_at" and activity.planned_at is None:
        raise ApplicationError({"planned_at": ["Set a planned time before moving to planned."]})
    if edge.precondition == "assigned_to" and activity.assigned_to_id is None:
        raise ApplicationError({"assigned_to": ["Assign somebody before moving to assigned."]})

    from_status = activity.status
    activity.status = to_status
    update_fields = ["status", "updated_at"]

    if to_status == ActivityStatus.IN_PROGRESS and activity.started_at is None:
        activity.started_at = timezone.now()
        update_fields.append("started_at")
    if to_status == ActivityStatus.REOPENED:
        # A fresh lap: clear the previous review's verdict so the record
        # does not read as both "reopened" and "approved" at once.
        activity.completed_at = None
        activity.reviewed_at = None
        activity.reviewed_by = None
        activity.review_note = ""
        update_fields += ["completed_at", "reviewed_at", "reviewed_by", "review_note"]

    activity.save(update_fields=update_fields)

    ActivityHistory.objects.create(
        activity=activity,
        actor=actor if getattr(actor, "pk", None) else None,
        from_status=from_status,
        to_status=to_status,
        note=note or "",
        changes={"status": {"from": from_status, "to": to_status}},
    )
    record(
        action=AuditAction.ACTIVITY_TRANSITIONED,
        actor=actor,
        resource_type="activity",
        resource_id=activity.pk,
        context={"from": from_status, "to": to_status, "note": note or ""},
        durable=False,
    )

    if to_status == ActivityStatus.ASSIGNED and activity.assigned_to_id:
        notify(
            recipient=activity.assigned_to,
            kind=NotificationKind.ACTIVITY_ASSIGNED,
            title=f"Activity assigned: {activity.title}",
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )

    activity_changed.send(sender=Activity, activity=activity, event="transitioned", actor=actor)
    return activity


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------

_COMPLETABLE_FROM = frozenset(
    {ActivityStatus.IN_PROGRESS, ActivityStatus.OVERDUE, ActivityStatus.ASSIGNED}
)

#: Placeholder rule, documented as such per the phase brief: pass at 60% of
#: the field's own max, fail below it. No per-type override exists yet;
#: later phases may replace this with something the catalog configures.
_PASS_THRESHOLD = Decimal("0.6")
_DEFAULT_MAX_SCORE = Decimal("100")


def _extract_score(
    form_version: FormVersion, cleaned_values: dict[str, Any]
) -> tuple[Decimal | None, Decimal | None]:
    field = form_version.performance_field()
    if field is None or field.key not in cleaned_values:
        return None, None
    try:
        score = Decimal(str(cleaned_values[field.key]))
    except (InvalidOperation, TypeError, ValueError):
        return None, None
    max_raw = field.validation.get("max") if isinstance(field.validation, dict) else None
    try:
        max_score = Decimal(str(max_raw)) if max_raw is not None else _DEFAULT_MAX_SCORE
    except (InvalidOperation, TypeError, ValueError):
        max_score = _DEFAULT_MAX_SCORE
    return score, max_score


def _derive_result(score: Decimal | None, max_score: Decimal | None) -> str:
    if score is None or max_score is None or max_score == 0:
        return ActivityResult.N_A
    return ActivityResult.PASS if (score / max_score) >= _PASS_THRESHOLD else ActivityResult.FAIL


@transaction.atomic
def complete_activity(
    *,
    actor,
    activity: Activity,
    form_values: dict[str, Any] | None = None,
    summary: str | None = None,
    duration_minutes: int | None = None,
    completed_at=None,
) -> Activity:
    if activity.status not in _COMPLETABLE_FROM:
        raise TransitionError(
            {
                "non_field_errors": ["This activity cannot be completed from its current status."],
                "allowed": sorted(_COMPLETABLE_FROM),
            }
        )
    if not access.can_complete(actor, activity):
        raise AuthorityError("You do not have authority to complete this activity.")

    form_values = form_values or {}
    response = None
    score = max_score = None
    if activity.form_version_id is not None:
        response = forms_services.submit_response(
            actor=actor, version=activity.form_version, values=form_values, content_object=activity
        )
        score, max_score = _extract_score(activity.form_version, response.values)
    elif form_values:
        raise ApplicationError({"form_values": ["This activity type has no form."]})

    from_status = activity.status
    requires_review = activity.activity_type.requires_review
    to_status = ActivityStatus.UNDER_REVIEW if requires_review else ActivityStatus.COMPLETED

    activity.form_response = response
    activity.score = score
    activity.max_score = max_score
    activity.result = _derive_result(score, max_score)
    if summary is not None:
        activity.summary = summary
    if duration_minutes is not None:
        activity.duration_minutes = duration_minutes
    activity.performed_by = actor if getattr(actor, "pk", None) else activity.performed_by
    activity.completed_at = completed_at or timezone.now()
    activity.status = to_status
    activity.save(
        update_fields=[
            "form_response",
            "score",
            "max_score",
            "result",
            "summary",
            "duration_minutes",
            "performed_by",
            "completed_at",
            "status",
            "updated_at",
        ]
    )

    ActivityHistory.objects.create(
        activity=activity,
        actor=actor if getattr(actor, "pk", None) else None,
        from_status=from_status,
        to_status=to_status,
        note="",
        changes={
            "result": activity.result,
            "score": str(score) if score is not None else None,
            "max_score": str(max_score) if max_score is not None else None,
        },
    )
    record(
        action=AuditAction.ACTIVITY_COMPLETED,
        actor=actor,
        resource_type="activity",
        resource_id=activity.pk,
        context={"result": activity.result, "requires_review": requires_review},
        durable=False,
    )

    if activity.student_visible and activity.activity_type.visible_to_student:
        notify(
            recipient=activity.student.user,
            kind=NotificationKind.ACTIVITY_COMPLETED,
            title=f"{activity.title} completed",
            body=activity.summary,
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )
    if activity.created_by_id and activity.created_by_id != activity.performed_by_id:
        notify(
            recipient=activity.created_by,
            kind=NotificationKind.ACTIVITY_COMPLETED,
            title=f"{activity.title} completed",
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )

    activity_changed.send(sender=Activity, activity=activity, event="completed", actor=actor)
    return activity


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@transaction.atomic
def review_activity(*, actor, activity: Activity, decision: str, note: str) -> Activity:
    """Only legal from `UNDER_REVIEW`. Does **not** send `activity_changed` —
    only completion recomputes risk (Phase 13); an approval or a send-back
    changes nothing a risk rule reads."""
    if activity.status != ActivityStatus.UNDER_REVIEW:
        raise TransitionError(
            {
                "non_field_errors": ["This activity is not awaiting review."],
                "allowed": [ActivityStatus.UNDER_REVIEW],
            }
        )
    if not access.can_review(actor, activity):
        raise AuthorityError(
            "You do not have authority to review this activity, or you performed it yourself."
        )
    if decision not in ("approved", "requires_action"):
        raise ApplicationError({"decision": ["Must be 'approved' or 'requires_action'."]})
    if decision == "requires_action" and not (note or "").strip():
        raise ApplicationError({"note": ["A note is required to send this back."]})

    to_status = (
        ActivityStatus.APPROVED if decision == "approved" else ActivityStatus.REQUIRES_ACTION
    )
    from_status = activity.status
    activity.status = to_status
    activity.reviewed_by = actor if getattr(actor, "pk", None) else None
    activity.reviewed_at = timezone.now()
    activity.review_note = note or ""
    activity.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
    )

    ActivityHistory.objects.create(
        activity=activity,
        actor=actor if getattr(actor, "pk", None) else None,
        from_status=from_status,
        to_status=to_status,
        note=note or "",
        changes={"decision": decision},
    )
    record(
        action=AuditAction.ACTIVITY_REVIEWED,
        actor=actor,
        resource_type="activity",
        resource_id=activity.pk,
        context={"decision": decision, "note": note or ""},
        durable=False,
    )

    if to_status == ActivityStatus.REQUIRES_ACTION and activity.assigned_to_id:
        notify(
            recipient=activity.assigned_to,
            kind=NotificationKind.ACTIVITY_ASSIGNED,
            title=f"Changes requested: {activity.title}",
            body=note or "",
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )
    return activity


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@transaction.atomic
def delete_activity(*, actor, activity: Activity, reason: str) -> Activity:
    if not access.can_delete(actor, activity):
        raise AuthorityError("You do not have authority to delete this activity.")
    soft_delete(instance=activity, actor=actor, reason=reason)
    record(
        action=AuditAction.ACTIVITY_DELETED,
        actor=actor,
        resource_type="activity",
        resource_id=activity.pk,
        context={"reason": reason},
        durable=False,
    )
    activity_changed.send(sender=Activity, activity=activity, event="deleted", actor=actor)
    return activity


# ---------------------------------------------------------------------------
# Beat tasks' bodies
# ---------------------------------------------------------------------------


def mark_overdue_and_missed() -> dict[str, int]:
    """Both sweeps go through `transition_activity(actor=None, ...)` so the
    same audit/history code path runs for a system-driven move as for a
    person's — no separate status-write logic to keep in sync.

    Order matters when an activity satisfies both conditions at once (an
    `ASSIGNED` activity whose `due_at` has *also* passed the missed grace
    period): `OVERDUE` is applied first, so by the time the missed sweep's
    queryset runs the activity is no longer `ASSIGNED` and is left as
    `OVERDUE` — the more specific, due-date-driven signal wins.
    """
    now = timezone.now()
    overdue = 0
    for activity in Activity.objects.filter(
        status__in=[ActivityStatus.ASSIGNED, ActivityStatus.IN_PROGRESS],
        due_at__isnull=False,
        due_at__lt=now,
    ):
        try:
            transition_activity(actor=None, activity=activity, to_status=ActivityStatus.OVERDUE)
        except (ApplicationError, AuthorityError):
            continue
        overdue += 1

    missed = 0
    grace_cutoff = now - timedelta(minutes=MISSED_GRACE_MINUTES)
    for activity in Activity.objects.filter(
        status=ActivityStatus.ASSIGNED,
        planned_at__isnull=False,
        planned_at__lt=grace_cutoff,
        started_at__isnull=True,
    ):
        try:
            transition_activity(actor=None, activity=activity, to_status=ActivityStatus.MISSED)
        except (ApplicationError, AuthorityError):
            continue
        missed += 1

    _dispatch_overdue_automation()

    return {"overdue": overdue, "missed": missed}


def _dispatch_overdue_automation() -> None:
    """Enqueues `ACTIVITY_OVERDUE`, `PROJECT_OVERDUE` and
    `ASSIGNMENT_OVERDUE` automation dispatches for whatever this sweep finds
    overdue right now (ERP Phase 14, ADR-13).

    Called from `mark_overdue_and_missed` itself rather than wired through a
    signal: unlike `ACTIVITY_COMPLETED`/`RISK_CHANGED` (Phase 9/13's own
    extension points), there is no existing "this went overdue" event to
    attach a receiver to — the beat sweep *is* the detection. A local
    import, same discipline as everywhere else in this module: `apps.work`
    never depends on `apps.automation` existing at import time.

    Projects and assignments reuse exactly the "what's overdue" reading
    Phase 13's risk engine already established
    (`apps.projects.models.StudentProject.mark_late`,
    `apps.performance.engine._missed_assignments`'s own predicate) rather
    than a third definition of "overdue" for either.
    """
    from apps.automation.tasks import (
        dispatch_activity_overdue,
        dispatch_assignment_overdue,
        dispatch_project_overdue,
    )

    now = timezone.now()

    for stale in Activity.objects.filter(
        status=ActivityStatus.OVERDUE, due_at__isnull=False, due_at__lt=now
    ).only("id", "due_at"):
        dispatch_activity_overdue.delay(str(stale.pk), max((now - stale.due_at).days, 0))

    from apps.projects.models import FINISHED_STATUSES, StudentProject

    today = timezone.localdate()
    for student_project in (
        StudentProject.objects.exclude(status__in=list(FINISHED_STATUSES))
        .filter(project__end_date__isnull=False, project__end_date__lt=today)
        .select_related("project")
    ):
        if student_project.mark_late():
            days = (today - student_project.project.end_date).days
            dispatch_project_overdue.delay(str(student_project.pk), max(days, 0))

    from apps.assignments.models import Assignment, AssignmentSubmission
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    for assignment in Assignment.objects.filter(due_at__isnull=False, due_at__lt=now):
        submitted_ids = set(
            AssignmentSubmission.objects.filter(assignment=assignment).values_list(
                "enrollment_id", flat=True
            )
        )
        candidates = (
            Enrollment.objects.filter(
                course_id=assignment.course_id, status=EnrollmentStatus.ACTIVE
            )
            .exclude(pk__in=submitted_ids)
            .select_related("batch")
        )
        for enrollment in candidates:
            if enrollment.batch_id and not assignment.applies_to_batch(enrollment.batch_id):
                continue
            dispatch_assignment_overdue.delay(
                str(assignment.pk), str(enrollment.pk), max((now - assignment.due_at).days, 0)
            )


def send_activity_reminders() -> int:
    """One reminder per activity, guarded by `reminder_sent_at` so a re-run
    of the same beat tick — or a slightly late one — never double-sends."""
    now = timezone.now()
    window = timedelta(minutes=REMINDER_WINDOW_MINUTES)
    candidates = Activity.objects.filter(
        status__in=[ActivityStatus.ASSIGNED, ActivityStatus.PLANNED],
        reminder_sent_at__isnull=True,
        activity_type__reminder_minutes_before__isnull=False,
        assigned_to__isnull=False,
    ).select_related("activity_type", "assigned_to")
    sent = 0
    for activity in candidates:
        anchor = activity.due_at or activity.planned_at
        if anchor is None:
            continue
        remind_at = anchor - timedelta(minutes=activity.activity_type.reminder_minutes_before)
        if remind_at > now or remind_at < now - window:
            continue
        notify(
            recipient=activity.assigned_to,
            kind=NotificationKind.ACTIVITY_REMINDER,
            title=f"Reminder: {activity.title}",
            link_path=f"/activities/{activity.pk}",
            resource_type="activity",
            resource_id=activity.pk,
        )
        activity.reminder_sent_at = now
        activity.save(update_fields=["reminder_sent_at"])
        sent += 1
    return sent


__all__ = [
    "MISSED_GRACE_MINUTES",
    "REMINDER_WINDOW_MINUTES",
    "TransitionError",
    "complete_activity",
    "create_activity",
    "create_activity_type",
    "delete_activity",
    "mark_overdue_and_missed",
    "review_activity",
    "send_activity_reminders",
    "transition_activity",
    "update_activity_type",
    "validate_assignee",
]
