"""The automation engine's dispatcher and the rule builder's own business
rules (ERP Phase 14, ADR-13). Every state change here is audited (rule 5);
every rule write is authorized at save time, not at run time (see
``_require_author_permissions``) — a run always executes "as the system",
so save time is the only moment a human's own authority is actually in the
room.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.policies.resolver import policy

from .actions import ACTIONS
from .evaluator import (
    OPERATORS,
    VALUELESS_OPERATORS,
    context_for,
    evaluate_conditions,
    path_allowed,
)
from .models import AutomationRule, AutomationRuleStatus, AutomationRun, AutomationRunStatus
from .resolve import RunContext

logger = logging.getLogger("grras.automation")

#: An action fired by a run at this depth or deeper is skipped, never
#: executed (ADR-13: "an action's own trigger runs at most 3 levels deep" —
#: depths 0, 1 and 2 are the three levels; depth 3 is the would-be fourth).
MAX_DEPTH = 3

#: The permission each action type needs its rule's *author* to hold, checked
#: at save time (`AUTOMATION_CATALOG.md`'s "Actions" table, "Permission the
#: rule's author must hold" column). `send_email`/`send_whatsapp` name the
#: same capability as `send_notification` — they always skip until Phase 19
#: exists, but a rule using either is still save-time-checked exactly like a
#: real send, so a rule that later starts actually sending (once Phase 19
#: ships) was never saved by someone who could not have authorized it.
ACTION_PERMISSIONS: dict[str, str] = {
    "create_activity": Capability.ACTIVITY_CREATE,
    "assign_form": Capability.FORM_ASSIGN,
    "update_enquiry": Capability.ENQUIRY_MANAGE,
    "send_notification": Capability.COMMUNICATION_SEND,
    "send_email": Capability.COMMUNICATION_SEND,
    "send_whatsapp": Capability.COMMUNICATION_SEND,
    "create_review": Capability.REVIEW_MANAGE_ANY,
    # `PERFORMANCE_VIEW_ANY` is read-only ("view any student's or trainer's
    # performance") — `flag_risk` writes a manual `RiskState` override, the
    # same kind of write `create_review` makes, so it is gated the same way:
    # the capability that actually authorizes writing a performance verdict.
    "flag_risk": Capability.REVIEW_MANAGE_ANY,
}

#: The three enquiry events, which share one context builder.
ENQUIRY_TRIGGERS = frozenset({"ENQUIRY_CREATED", "ENQUIRY_STAGE_CHANGED", "ENQUIRY_UPDATED"})

RULE_EDITABLE_FIELDS = frozenset(
    {"name", "description", "trigger", "conditions", "actions", "branch"}
)


# ---------------------------------------------------------------------------
# Save-time validation (never at run time — the rule already passed this gate)
# ---------------------------------------------------------------------------


def _validate_rule_shape(trigger: str, conditions: list[dict], actions: list[dict]) -> None:
    """Refuses an operator, path or action type outside the fixed vocabulary
    `AUTOMATION_CATALOG.md` defines. This is a shape check only — whether a
    *particular* occurrence can actually run a *particular* action (an
    unknown activity type slug, an unresolvable recipient) is decided at run
    time, in `apps/automation/actions.py`, because it depends on data that
    does not exist yet when the rule is merely being saved.
    """
    from .models import AutomationTrigger

    if trigger not in AutomationTrigger.values:
        raise ApplicationError({"trigger": [f"Unknown trigger: {trigger!r}."]})

    errors: list[str] = []
    for index, condition in enumerate(conditions or []):
        if not isinstance(condition, dict):
            errors.append(f"Condition {index}: must be an object.")
            continue
        path = condition.get("path")
        op = condition.get("op")
        if "value" not in condition and op not in VALUELESS_OPERATORS:
            errors.append(f"Condition {index}: missing 'value'.")
        if op not in OPERATORS:
            errors.append(f"Condition {index}: unknown operator {op!r}.")
        if not path or not path_allowed(trigger, path):
            errors.append(f"Condition {index}: path {path!r} is not allowed for {trigger}.")

    for index, action in enumerate(actions or []):
        if not isinstance(action, dict):
            errors.append(f"Action {index}: must be an object.")
            continue
        action_type = action.get("type")
        if action_type not in ACTIONS:
            errors.append(f"Action {index}: unknown action type {action_type!r}.")
        params = action.get("params") or {}
        if not isinstance(params, dict):
            errors.append(f"Action {index}: 'params' must be an object.")
        elif action_type == "assign_form":
            errors.extend(_assign_form_problems(index, params))
        elif action_type == "update_enquiry":
            errors.extend(_update_enquiry_problems(index, params))
        elif action_type == "create_activity":
            errors.extend(_create_activity_problems(index, params))

    if errors:
        raise ApplicationError({"conditions_actions": errors})


def _whole_days_or_hours(index: int, params: dict, *keys: str) -> list[str]:
    problems: list[str] = []
    for key in keys:
        value = params.get(key)
        if value in (None, ""):
            continue
        try:
            if int(value) < 0:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"Action {index}: {key} must be a whole number, 0 or more.")
    return problems


def _create_activity_problems(index: int, params: dict) -> list[str]:
    """The activity type must exist; prefilled answers must be a mapping of
    question key to text. Time offsets are whole numbers."""
    from apps.work.models import ActivityType

    problems = _whole_days_or_hours(
        index, params, "due_in_days", "due_in_hours", "planned_in_hours"
    )
    slug = params.get("type")
    if not slug or not ActivityType.objects.filter(slug=slug).exists():
        problems.append(f"Action {index}: choose an activity type.")
    prefill = params.get("form_prefill") or {}
    if not isinstance(prefill, dict) or not all(
        isinstance(key, str) and isinstance(value, (str, int, float, bool))
        for key, value in prefill.items()
    ):
        problems.append(
            f"Action {index}: prefilled answers must be question keys with text values."
        )
    return problems


def _update_enquiry_problems(index: int, params: dict) -> list[str]:
    from apps.enquiries.models import EnquiryStage

    problems = _whole_days_or_hours(index, params, "next_follow_up_in_days")
    stage = params.get("stage")
    if stage not in (None, "") and stage not in EnquiryStage.values:
        problems.append(f"Action {index}: unknown enquiry stage {stage!r}.")
    quality = params.get("lead_quality")
    if quality not in (None, ""):
        try:
            if not 1 <= int(quality) <= 5:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"Action {index}: lead quality must be 1 to 5.")
    if not any(
        params.get(key) not in (None, "")
        for key in ("stage", "owner", "lost_reason", "lead_quality", "next_follow_up_in_days")
    ):
        problems.append(f"Action {index}: choose at least one thing to change on the enquiry.")
    return problems


def _assign_form_problems(index: int, params: dict) -> list[str]:
    """`assign_form` names a form by slug; one that does not exist, or that
    only reaches people through an activity, would fail on every run, so it
    is refused when the rule is saved instead."""
    from apps.forms.models import FormDefinition, FormEntity

    problems: list[str] = []
    slug = params.get("form")
    definition = FormDefinition.objects.filter(slug=slug).first() if slug else None
    if definition is None:
        problems.append(f"Action {index}: choose a form to send.")
    elif definition.entity == FormEntity.ACTIVITY:
        problems.append(
            f"Action {index}: {slug!r} is an activity form; "
            "create an activity of that type instead."
        )
    if not params.get("to"):
        problems.append(f"Action {index}: choose who should fill in the form.")
    due = params.get("due_in_days")
    if due not in (None, ""):
        try:
            if int(due) < 0:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"Action {index}: due_in_days must be a whole number of days.")
    return problems


def _require_author_permissions(actor, actions: list[dict]) -> None:
    """ "An action that needs a permission the author lacks cannot be saved"
    (the catalog, verbatim) — the one real authorization check standing
    between a rule and a privilege-escalation path, since every action
    executes as "the system", not as whoever is looking at the builder right
    now."""
    missing = sorted(
        {
            action.get("type")
            for action in actions or []
            if (capability := ACTION_PERMISSIONS.get(action.get("type")))
            and not has_capability(actor, capability)
        }
    )
    if missing:
        raise AuthorityError(f"You do not hold the permission required for: {', '.join(missing)}.")


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


@transaction.atomic
def create_rule(
    *,
    actor,
    name: str,
    trigger: str,
    description: str = "",
    conditions: list[dict] | None = None,
    actions: list[dict] | None = None,
    status: str = AutomationRuleStatus.DRAFT,
    branch=None,
) -> AutomationRule:
    conditions = conditions or []
    actions = actions or []
    if status not in AutomationRuleStatus.values:
        raise ApplicationError({"status": ["Invalid status."]})
    _validate_rule_shape(trigger, conditions, actions)
    _require_author_permissions(actor, actions)

    rule = AutomationRule.objects.create(
        name=name,
        description=description,
        trigger=trigger,
        conditions=conditions,
        actions=actions,
        status=status,
        branch=branch,
        created_by=actor if getattr(actor, "pk", None) else None,
        updated_by=actor if getattr(actor, "pk", None) else None,
    )
    record(
        action=AuditAction.AUTOMATION_RULE_CREATED,
        actor=actor,
        resource_type="automation.automationrule",
        resource_id=rule.pk,
        context={"name": name, "trigger": trigger, "status": status},
        durable=False,
    )
    return rule


@transaction.atomic
def update_rule(*, rule: AutomationRule, actor, **fields: Any) -> AutomationRule:
    unknown = sorted(set(fields) - RULE_EDITABLE_FIELDS)
    if unknown:
        raise ApplicationError({field: ["This field cannot be edited."] for field in unknown})

    trigger = fields.get("trigger", rule.trigger)
    conditions = fields.get("conditions", rule.conditions)
    actions = fields.get("actions", rule.actions)
    _validate_rule_shape(trigger, conditions, actions)
    _require_author_permissions(actor, actions)

    # A rule that has already left `draft` at least once carries a version a
    # `run` may already reference (ADR-13); one still being drafted has not,
    # so editing it is not yet "a new version" of anything.
    bump_version = rule.status != AutomationRuleStatus.DRAFT

    for field, value in fields.items():
        setattr(rule, field, value)
    rule.updated_by = actor if getattr(actor, "pk", None) else None
    if bump_version:
        rule.version += 1
    rule.save()

    record(
        action=AuditAction.AUTOMATION_RULE_UPDATED,
        actor=actor,
        resource_type="automation.automationrule",
        resource_id=rule.pk,
        context={"fields": sorted(fields), "version": rule.version},
        durable=False,
    )
    return rule


@transaction.atomic
def activate_rule(*, rule: AutomationRule, actor) -> AutomationRule:
    if rule.status == AutomationRuleStatus.ACTIVE:
        return rule
    # Checked against the activator's own identity, not `rule.created_by`:
    # activating a rule is the act that actually lets it start executing,
    # so it is the activator's authority being spent, not the original
    # author's (who may hold none of it, or may no longer). Re-checking
    # `created_by` here let anyone holding only `automation.manage` flip on
    # someone else's draft and have it start running actions that person was
    # never themselves entitled to authorize.
    _require_author_permissions(actor, rule.actions)
    rule.status = AutomationRuleStatus.ACTIVE
    rule.updated_by = actor if getattr(actor, "pk", None) else None
    rule.save(update_fields=["status", "updated_by", "updated_at"])
    record(
        action=AuditAction.AUTOMATION_RULE_ACTIVATED,
        actor=actor,
        resource_type="automation.automationrule",
        resource_id=rule.pk,
        context={"trigger": rule.trigger},
        durable=False,
    )
    return rule


@transaction.atomic
def pause_rule(*, rule: AutomationRule, actor, reason: str = "") -> AutomationRule:
    if rule.status == AutomationRuleStatus.PAUSED:
        return rule
    rule.status = AutomationRuleStatus.PAUSED
    rule.updated_by = actor if getattr(actor, "pk", None) else None
    rule.save(update_fields=["status", "updated_by", "updated_at"])
    record(
        action=AuditAction.AUTOMATION_RULE_PAUSED,
        actor=actor,
        resource_type="automation.automationrule",
        resource_id=rule.pk,
        context={"reason": reason},
        durable=False,
    )
    return rule


@transaction.atomic
def delete_rule(*, rule: AutomationRule, actor, reason: str = "") -> AutomationRule:
    soft_delete(instance=rule, actor=actor, reason=reason)
    record(
        action=AuditAction.AUTOMATION_RULE_DELETED,
        actor=actor,
        resource_type="automation.automationrule",
        resource_id=rule.pk,
        context={"reason": reason},
        durable=False,
    )
    return rule


def sync_rule_authors() -> int:
    """Pauses any active rule whose author has since lost a permission one of
    its own actions needs (the catalog: "a rule whose author later loses the
    permission is paused by sync and shown as such"). Safe to call often —
    a management command for an ops cron, and a cheap pass from the rule
    list view on every read (`views.AutomationRuleListCreateView`).

    A rule with no author at all (the 9 seeded rows, never authored by any
    one person) is never touched here — there is no
    individual permission to have lapsed, and pausing it just because
    nobody in particular vouches for it would contradict the catalog's own
    "none is locked" (they remain editable and pausable, exactly like any
    other rule, by an administrator's own action instead).
    """
    paused = 0
    for rule in AutomationRule.objects.active().select_related("created_by"):
        if rule.created_by_id is None:
            continue
        missing = sorted(
            {
                action.get("type")
                for action in rule.actions or []
                if (capability := ACTION_PERMISSIONS.get(action.get("type")))
                and not has_capability(rule.created_by, capability)
            }
        )
        if missing:
            pause_rule(
                rule=rule,
                actor=None,
                reason=f"Author lost permission for: {', '.join(missing)}.",
            )
            paused += 1
    return paused


# ---------------------------------------------------------------------------
# Building context + a RunContext for one occurrence
# ---------------------------------------------------------------------------


def _batch_branch(enrollment) -> Any:
    return enrollment.batch.branch if enrollment is not None and enrollment.batch_id else None


def _build(trigger: str, obj: Any, extra: dict[str, Any]) -> tuple[dict[str, Any], RunContext, Any]:
    """Returns ``(context, run_context, generic_target)`` for one occurrence.

    ``generic_target`` is the record `AutomationRun.content_type`/
    `object_id` point at — the same as ``obj`` for every trigger except
    `ASSIGNMENT_OVERDUE`, where ``obj`` (an `Assignment`) is shared by every
    enrolled student: the run is about *this student's* overdue assignment,
    so the generic reference (and the compact occurrence key below) is
    keyed off the enrolment instead, matching how `ATTENDANCE_THRESHOLD` and
    `PROJECT_OVERDUE` are already keyed off a per-student record.
    """
    from .models import AutomationTrigger

    if trigger == AutomationTrigger.ACTIVITY_COMPLETED:
        activity = obj
        context = context_for(trigger, activity)
        rctx = RunContext(
            student=activity.student,
            enrollment=activity.enrollment,
            activity=activity,
            branch=activity.branch,
            enquiry=activity.enquiry if activity.enquiry_id else None,
        )
        return context, rctx, activity

    if trigger == AutomationTrigger.ACTIVITY_OVERDUE:
        activity = obj
        context = context_for(trigger, activity, days_overdue=extra["days_overdue"])
        rctx = RunContext(
            student=activity.student,
            enrollment=activity.enrollment,
            activity=activity,
            branch=activity.branch,
            enquiry=activity.enquiry if activity.enquiry_id else None,
        )
        return context, rctx, activity

    if trigger == AutomationTrigger.ASSESSMENT_FAILED:
        result = obj
        enrollment = result.enrollment
        context = context_for(
            trigger, result, percent=extra["percent"], attempt_number=extra["attempt_number"]
        )
        rctx = RunContext(
            student=enrollment.student, enrollment=enrollment, branch=_batch_branch(enrollment)
        )
        return context, rctx, result

    if trigger == AutomationTrigger.ATTENDANCE_THRESHOLD:
        enrollment = obj
        context = context_for(
            trigger, enrollment, percent=extra["percent"], absent_streak=extra["absent_streak"]
        )
        rctx = RunContext(
            student=enrollment.student, enrollment=enrollment, branch=_batch_branch(enrollment)
        )
        return context, rctx, enrollment

    if trigger == AutomationTrigger.PROJECT_OVERDUE:
        student_project = obj
        enrollment = student_project.enrollment
        context = context_for(trigger, student_project, days_overdue=extra["days_overdue"])
        rctx = RunContext(
            student=enrollment.student, enrollment=enrollment, branch=_batch_branch(enrollment)
        )
        return context, rctx, student_project

    if trigger == AutomationTrigger.ASSIGNMENT_OVERDUE:
        assignment = obj
        enrollment = extra["enrollment"]
        context = context_for(
            trigger, assignment, enrollment=enrollment, days_overdue=extra["days_overdue"]
        )
        rctx = RunContext(
            student=enrollment.student, enrollment=enrollment, branch=_batch_branch(enrollment)
        )
        return context, rctx, enrollment

    if trigger == AutomationTrigger.RISK_CHANGED:
        risk_state = obj
        enrollment = extra["enrollment"]
        context = context_for(
            trigger,
            risk_state,
            enrollment=enrollment,
            level=extra["level"],
            previous_level=extra["previous_level"],
            triggered=extra["triggered"],
            previous_triggered=extra["previous_triggered"],
        )
        rctx = RunContext(
            student=enrollment.student, enrollment=enrollment, branch=_batch_branch(enrollment)
        )
        return context, rctx, risk_state

    if trigger == AutomationTrigger.FORM_SUBMITTED:
        assignment = obj
        enrollment = _current_enrollment(assignment.student)
        context = context_for(trigger, assignment, enrollment=enrollment)
        branch = assignment.branch or _batch_branch(enrollment)
        rctx = RunContext(
            student=assignment.student,
            enrollment=enrollment,
            branch=branch,
            form_assignment=assignment,
            enquiry=assignment.enquiry if assignment.enquiry_id else None,
        )
        return context, rctx, assignment

    if trigger in ENQUIRY_TRIGGERS:
        enquiry = obj
        context = context_for(
            trigger,
            enquiry,
            previous_stage=extra.get("previous_stage", ""),
            changed=extra.get("changed"),
        )
        rctx = RunContext(enquiry=enquiry, branch=enquiry.branch)
        return context, rctx, enquiry

    raise ValueError(f"Unknown trigger: {trigger!r}")


def _current_enrollment(student) -> Any:
    """The enrolment a form about ``student`` is read against: the active
    one, else the most recent. `batch_trainer`/`counsellor` resolve through
    it; a form about no student has none."""
    if student is None:
        return None
    from apps.enrollments.models import Enrollment, EnrollmentStatus

    rows = Enrollment.objects.filter(student=student).select_related(
        "batch", "batch__branch", "batch__trainer", "student", "student__user"
    )
    return (
        rows.filter(status=EnrollmentStatus.ACTIVE).order_by("-created_at").first()
        or rows.order_by("-created_at").first()
    )


def _compact_date(moment=None) -> str:
    day = moment or timezone.localdate()
    if hasattr(day, "date"):
        day = timezone.localtime(day).date()
    return day.strftime("%Y%m%d")


def _compact_datetime(moment) -> str:
    return timezone.localtime(moment).strftime("%Y%m%dT%H%M%S")


def _occurrence_for(trigger: str, target: Any, extra: dict[str, Any], depth: int = 0) -> str:
    """The catalog's own recipe: "the activity completion id / the overdue
    day / the risk computed_at, whichever fits the trigger". Datetimes are
    rendered compactly (`YYYYMMDD`/`YYYYMMDDTHHMMSS`), not `.isoformat()`,
    so the composed ``f"{trigger}:{object_id}:{occurrence}"`` stays inside
    `AutomationRun.occurrence_key`'s `char(80)` even for the longest trigger
    name (`ATTENDANCE_THRESHOLD`) paired with a UUID `object_id`.
    """
    from .models import AutomationTrigger

    if trigger == AutomationTrigger.ACTIVITY_COMPLETED:
        completed_at = getattr(target, "completed_at", None)
        return _compact_datetime(completed_at) if completed_at else str(target.pk)[:8]

    if trigger in (AutomationTrigger.ACTIVITY_OVERDUE, AutomationTrigger.PROJECT_OVERDUE):
        return _compact_date()

    if trigger == AutomationTrigger.ASSESSMENT_FAILED:
        return f"attempt-{extra['attempt_number']}"

    if trigger == AutomationTrigger.ATTENDANCE_THRESHOLD:
        return _compact_date()

    if trigger == AutomationTrigger.ASSIGNMENT_OVERDUE:
        # `target` here is the enrolment (see `_build`'s docstring); the
        # assignment id still needs to be in the key, or every assignment
        # overdue for the same student on the same day would collapse into
        # one occurrence. A 12-hex-char prefix of the assignment's own UUID
        # is unique enough among the handful of assignments any one student
        # could plausibly have overdue at once, and keeps the composed key
        # short.
        assignment_id = extra["assignment_id"]
        return f"{assignment_id.replace('-', '')[:12]}-{_compact_date()}"

    if trigger == AutomationTrigger.RISK_CHANGED:
        # A depth suffix, not just `computed_at`: a `flag_risk`-triggered
        # chain (the one path that can re-dispatch `RISK_CHANGED` for the
        # *same* `RiskState` row within the same request) can easily land
        # two levels of the chain in the same truncated second. Depth is
        # genuinely part of "which occurrence, in this chain" — the normal,
        # non-chained case is always depth 0, so this changes nothing there.
        computed_at = getattr(target, "computed_at", None)
        stamp = _compact_datetime(computed_at) if computed_at else _compact_datetime(timezone.now())
        return f"{stamp}-{depth}"

    if trigger == AutomationTrigger.FORM_SUBMITTED:
        submitted_at = getattr(target, "submitted_at", None)
        return _compact_datetime(submitted_at) if submitted_at else str(target.pk)[:8]

    if trigger == AutomationTrigger.ENQUIRY_CREATED:
        return "created"

    if trigger == AutomationTrigger.ENQUIRY_STAGE_CHANGED:
        moment = getattr(target, "stage_changed_at", None) or timezone.now()
        return f"{_compact_datetime(moment)}-{depth}"

    if trigger == AutomationTrigger.ENQUIRY_UPDATED:
        moment = getattr(target, "updated_at", None) or timezone.now()
        return f"{_compact_datetime(moment)}-{depth}"

    raise ValueError(f"Unknown trigger: {trigger!r}")


# ---------------------------------------------------------------------------
# The dispatcher
# ---------------------------------------------------------------------------


def _finish_run(
    run: AutomationRun, *, status: str, result: dict[str, Any], error: str = ""
) -> None:
    run.status = status
    run.result = result
    run.error = error[:2000]
    run.save(update_fields=["status", "result", "error", "updated_at"])
    action_map = {
        AutomationRunStatus.RAN: AuditAction.AUTOMATION_RAN,
        AutomationRunStatus.SKIPPED: AuditAction.AUTOMATION_SKIPPED,
        AutomationRunStatus.FAILED: AuditAction.AUTOMATION_FAILED,
    }
    record(
        action=action_map[status],
        actor=None,
        resource_type="automation.automationrun",
        resource_id=run.pk,
        context={
            "rule": str(run.rule_id),
            "rule_version": run.rule_version,
            "trigger": run.trigger,
            "depth": run.depth,
        },
        durable=False,
    )


def dispatch(trigger: str, obj: Any, *, depth: int = 0, **extra: Any) -> None:
    """The one entry point every receiver, beat task and chained action
    calls (ADR-13). Signals and beat tasks always enqueue a Celery task
    (``tasks.py``) that resolves real objects and calls this at ``depth=0``;
    an action whose own effect is itself a trigger occurrence (only
    `actions.flag_risk`, today) calls this directly, in-process, one depth
    deeper — already running inside a worker, so there is nothing to
    enqueue.

    Never raises: every action's failure is caught and recorded on its own
    run (ADR-13: "a failed action is a failed run, never a failed request").
    A rule whose conditions do not hold leaves no trace at all — only a
    match gets an `AutomationRun` row, per the catalog's own dispatch
    recipe.
    """
    context, rctx, target = _build(trigger, obj, extra)
    content_type = ContentType.objects.get_for_model(target)
    branch_id = rctx.branch.pk if rctx.branch is not None else None

    from django.db.models import Q

    rules = AutomationRule.objects.active().for_trigger(trigger)
    rules = (
        rules.filter(Q(branch__isnull=True) | Q(branch_id=branch_id))
        if branch_id
        else rules.filter(branch__isnull=True)
    )

    for rule in rules:
        if not evaluate_conditions(rule.conditions, context):
            continue

        occurrence = _occurrence_for(trigger, target, extra, depth)
        occurrence_key = f"{trigger}:{target.pk}:{occurrence}"[:80]

        try:
            with transaction.atomic():
                # Locks this rule's own row for the rate guard below: the
                # guard is a plain "count, then act", and it has no unique
                # key of its own to hang a `IntegrityError` check on the way
                # the idempotency guard does — a `SELECT ... FOR UPDATE` on
                # the rule is the equivalent guarantee, serializing two
                # dispatches racing for the same (rule, object) pair so the
                # second one counts the first one's just-created row instead
                # of a stale, pre-commit count that would let both through.
                AutomationRule.objects.select_for_update().get(pk=rule.pk)

                max_runs = policy("automation", "max_runs_per_object_per_day")
                today_count = (
                    AutomationRun.objects.today()
                    .filter(rule=rule, content_type=content_type, object_id=target.pk)
                    .count()
                )
                rate_limited = today_count >= max_runs

                run = AutomationRun.objects.create(
                    rule=rule,
                    trigger=trigger,
                    content_type=content_type,
                    object_id=target.pk,
                    occurrence_key=occurrence_key,
                    depth=depth,
                    status=AutomationRunStatus.QUEUED,
                    rule_version=rule.version,
                )
        except IntegrityError:
            # The idempotency guard itself: this exact occurrence already
            # ran for this rule. Not a second in-code check — the database
            # constraint is the check.
            continue
        except Exception:
            # Never raises (ADR-13): a bad policy value or a DB hiccup here
            # rolls back this whole atomic block with it, including the run
            # row above, so nothing is left `QUEUED` forever for the
            # idempotency guard to later swallow silently on a retry — the
            # occurrence simply was not claimed yet, and the next attempt
            # tries again from scratch.
            logger.exception(
                "Automation rate guard failed for rule %s on %s", rule.pk, occurrence_key
            )
            continue

        if depth >= MAX_DEPTH:
            _finish_run(
                run,
                status=AutomationRunStatus.SKIPPED,
                result={"reason": "max automation depth reached"},
            )
            continue

        if rate_limited:
            _finish_run(
                run,
                status=AutomationRunStatus.SKIPPED,
                result={"reason": "automation.max_runs_per_object_per_day reached"},
            )
            continue

        results: list[dict[str, Any]] = []
        any_failed = False
        for action in rule.actions:
            action_type = action.get("type")
            handler = ACTIONS.get(action_type)
            params = action.get("params") or {}
            try:
                outcome = handler(
                    rule=rule, run=run, rctx=rctx, context=context, params=params, depth=depth
                )
                results.append({"type": action_type, **(outcome or {})})
            except Exception as exc:
                any_failed = True
                results.append({"type": action_type, "error": str(exc)})
                logger.exception("Automation action %r failed for rule %s", action_type, rule.pk)

        _finish_run(
            run,
            status=AutomationRunStatus.FAILED if any_failed else AutomationRunStatus.RAN,
            result={"actions": results},
        )


# ---------------------------------------------------------------------------
# Dry run — "Test against a recent event" (never executes an action, never
# writes an AutomationRun row)
# ---------------------------------------------------------------------------


def _recent_events(trigger: str, *, limit: int = 20) -> list[tuple[Any, dict[str, Any]]]:
    """Up to ``limit`` real, already-happened occurrences of ``trigger``, an
    ``(obj, extra)`` pair per event, newest first — exactly what
    `_build`/`context_for` need to build the same context a live dispatch
    would have built for that same event, so the builder's "Test" preview
    reads on genuine data, never a fabricated example.
    """
    from .models import AutomationTrigger

    events: list[tuple[Any, dict[str, Any]]] = []

    if trigger == AutomationTrigger.ACTIVITY_COMPLETED:
        from apps.work.models import Activity

        for activity in Activity.objects.filter(completed_at__isnull=False).order_by(
            "-completed_at"
        )[:limit]:
            events.append((activity, {}))

    elif trigger == AutomationTrigger.ACTIVITY_OVERDUE:
        from apps.work.models import Activity, ActivityStatus

        now = timezone.now()
        for activity in Activity.objects.filter(
            status=ActivityStatus.OVERDUE, due_at__isnull=False
        ).order_by("-due_at")[:limit]:
            events.append((activity, {"days_overdue": max((now - activity.due_at).days, 0)}))

    elif trigger == AutomationTrigger.ASSESSMENT_FAILED:
        from apps.assessments.models import AssessmentResult

        candidates = (
            AssessmentResult.objects.filter(is_absent=False, marks_obtained__isnull=False)
            .select_related("assessment", "enrollment")
            .order_by("-created_at")[: limit * 4]
        )
        for result in candidates:
            if result.is_passing is False:
                events.append(
                    (
                        result,
                        {
                            "percent": _percent(result.marks_obtained, result.assessment.max_marks),
                            "attempt_number": _failed_attempt_number(
                                result.enrollment, result.assessment
                            ),
                        },
                    )
                )
            if len(events) >= limit:
                break

    elif trigger == AutomationTrigger.ATTENDANCE_THRESHOLD:
        # No standalone log of "crossing" events exists (`RiskState` holds
        # only each enrolment's current verdict) — the closest real
        # approximation is the most recently recomputed states whose stored
        # attendance number is currently below its own threshold.
        from apps.performance.models import RiskState

        for state in RiskState.objects.select_related("enrollment").order_by("-computed_at")[
            : limit * 4
        ]:
            attendance = (state.numbers or {}).get("attendance") or {}
            percent, threshold = attendance.get("percent"), attendance.get("threshold")
            if percent is None or threshold is None or float(percent) >= float(threshold):
                continue
            events.append(
                (
                    state.enrollment,
                    {"percent": percent, "absent_streak": _absent_streak(state.enrollment)},
                )
            )
            if len(events) >= limit:
                break

    elif trigger == AutomationTrigger.PROJECT_OVERDUE:
        from apps.projects.models import FINISHED_STATUSES, StudentProject

        candidates = (
            StudentProject.objects.exclude(status__in=list(FINISHED_STATUSES))
            .select_related("project", "enrollment")
            .order_by("-created_at")[: limit * 4]
        )
        for student_project in candidates:
            if student_project.mark_late():
                end = student_project.project.end_date
                days = (timezone.localdate() - end).days if end else 0
                events.append((student_project, {"days_overdue": max(days, 0)}))
            if len(events) >= limit:
                break

    elif trigger == AutomationTrigger.ASSIGNMENT_OVERDUE:
        from apps.assignments.models import Assignment, AssignmentSubmission
        from apps.enrollments.models import Enrollment

        now = timezone.now()
        for assignment in Assignment.objects.filter(due_at__isnull=False, due_at__lt=now).order_by(
            "-due_at"
        )[: limit * 2]:
            submitted_ids = set(
                AssignmentSubmission.objects.filter(assignment=assignment).values_list(
                    "enrollment_id", flat=True
                )
            )
            enrollments = Enrollment.objects.filter(
                course_id=assignment.course_id, batch__isnull=False
            ).exclude(pk__in=submitted_ids)[:1]
            for enrollment in enrollments:
                events.append(
                    (
                        assignment,
                        {
                            "enrollment": enrollment,
                            "assignment_id": str(assignment.pk),
                            "days_overdue": max((now - assignment.due_at).days, 0),
                        },
                    )
                )
            if len(events) >= limit:
                break

    elif trigger == AutomationTrigger.RISK_CHANGED:
        from apps.performance.models import RiskState

        for state in (
            RiskState.objects.exclude(previous_level="")
            .select_related("enrollment")
            .order_by("-computed_at")[:limit]
        ):
            events.append(
                (
                    state,
                    {
                        "enrollment": state.enrollment,
                        "level": state.level,
                        "previous_level": state.previous_level,
                        "triggered": state.triggered,
                        "previous_triggered": state.previous_triggered,
                    },
                )
            )

    elif trigger in ENQUIRY_TRIGGERS:
        from apps.enquiries.models import Enquiry

        order = (
            "-stage_changed_at"
            if trigger == AutomationTrigger.ENQUIRY_STAGE_CHANGED
            else "-updated_at"
        )
        for enquiry in Enquiry.objects.with_related().order_by(order)[:limit]:
            events.append((enquiry, {"previous_stage": "", "changed": []}))

    elif trigger == AutomationTrigger.FORM_SUBMITTED:
        from apps.forms.models import FormAssignment, FormAssignmentStatus

        for assignment in (
            FormAssignment.objects.with_related()
            .filter(status=FormAssignmentStatus.SUBMITTED)
            .order_by("-submitted_at")[:limit]
        ):
            events.append((assignment, {}))

    return events[:limit]


def _percent(marks, max_marks) -> float | None:
    if marks is None or not max_marks:
        return None
    return round(float(marks) * 100 / float(max_marks), 1)


def _failed_attempt_number(enrollment, assessment) -> int:
    """How many-th failed assessment this is for this student in this
    course, counting from 1 — the reading `AUTOMATION_CATALOG.md`'s "Failed
    a test twice" seeded rule (`assessment.attempt_number gte 2`) implies,
    since a single `AssessmentResult` row (one per assessment/enrolment
    pair, never a retake sequence) has no attempt counter of its own."""
    from apps.academics.policies import passing_mark_for_assessment
    from apps.assessments.models import AssessmentResult

    count = 0
    rows = AssessmentResult.objects.filter(
        enrollment=enrollment,
        assessment__course_id=assessment.course_id,
        is_absent=False,
        marks_obtained__isnull=False,
    ).select_related("assessment")
    for row in rows:
        if row.marks_obtained < passing_mark_for_assessment(row.assessment):
            count += 1
    return count


def _absent_streak(enrollment) -> int:
    """Consecutive most-recent sessions marked absent for this enrolment,
    capped at 60 records back — bounded, and far more than any realistic
    streak, so the cap never changes the answer for a real student."""
    from apps.attendance.models import COUNTS_AS_PRESENT, AttendanceRecord

    streak = 0
    records = AttendanceRecord.objects.filter(enrollment=enrollment).order_by(
        "-session__session_date"
    )[:60]
    for record_row in records:
        if record_row.status in COUNTS_AS_PRESENT:
            break
        streak += 1
    return streak


def dry_run(rule: AutomationRule) -> list[dict[str, Any]]:
    """ "Test against a recent event" (`AUTOMATION_CATALOG.md`'s builder
    contract): evaluates ``rule.conditions`` against up to the last 20 real
    events of ``rule.trigger`` and reports would-fire/would-not for each —
    never executes an action, never writes an `AutomationRun` row."""
    results: list[dict[str, Any]] = []
    for obj, extra in _recent_events(rule.trigger, limit=20):
        context, _rctx, target = _build(rule.trigger, obj, extra)
        results.append(
            {
                "object_id": str(target.pk),
                "would_fire": evaluate_conditions(rule.conditions, context),
                "context": context,
            }
        )
    return results
