"""The action types `AUTOMATION_CATALOG.md`'s "Actions" table names
(ERP Phase 14, ADR-13), plus `assign_form` (send a form to someone to fill).

Every function here has the same shape: ``(rule, run, rctx, context,
params) -> dict``. It returns a small JSON-safe dict describing what
happened (folded into `AutomationRun.result["actions"]` by
`services.dispatch`) or raises — any exception at all, not a narrow list —
which the dispatcher catches and records as that one action's failure
without stopping the rest of the run (ADR-13: "a failed action is a failed
run, never a failed request"; the catalog's own wording is "one action
failing does not stop the others").

``params`` is a rule's own, already-shape-checked-at-save-time JSON dict for
this action (`services._validate_actions`); nothing here re-validates the
shape a rule was refused for in the builder, only what depends on the record
being acted on right now (an unknown activity type slug, an unresolvable
recipient — a rule can be perfectly well-formed and still find nothing to
act on for one particular occurrence).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import UserRole
from apps.common.exceptions import ApplicationError

from .evaluator import MISSING, get_path
from .resolve import RunContext, resolve_user

_VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def render_template(template: str, context: dict[str, Any]) -> str:
    """``{{student.name}}``-style substitution only — never `.format()` or an
    f-string over caller-supplied text, and never `eval`. A path that is
    missing or resolves to `None` renders as an empty string; anything else
    is stringified plainly."""

    def _replace(match: re.Match[str]) -> str:
        value = get_path(context, match.group(1))
        if value is MISSING or value is None:
            return ""
        return str(value)

    return _VARIABLE_RE.sub(_replace, template or "")


def _system_actor(rule) -> User | None:
    """Who `create_activity`/`create_review` act *as*.

    `apps.work.services.create_activity` (unlike `transition_activity`)
    dereferences `actor.role` and asks `access.can_create_for(actor, ...)`,
    so it cannot take `actor=None` the way
    `apps.work.services.mark_overdue_and_missed`'s system-driven transitions
    do — read before deciding, per this phase's own instruction. A rule's
    `created_by` already passed the save-time permission check
    (`services._require_author_permissions`), so it is always a legitimate,
    real actor to write the record as. The one gap is a rule with no author
    at all — the 9 rows this phase seeds (`0002_seed_rules.py`), which exist
    before any administrator account is guaranteed to have logged in and
    authored anything. For those, the first active superadmin stands in —
    the same "no single natural owner; pick the first active holder of the
    rung that can always act" answer `resolve._first_manager` already gives
    for `send_notification`'s `manager` strategy, just one rung higher,
    since creating a record (unlike being notified about one) needs a real,
    capable actor to exist at all.
    """
    if rule.created_by_id:
        return rule.created_by
    return User.objects.filter(role=UserRole.SUPERADMIN, is_active=True).order_by("pk").first()


def _offset(params: dict[str, Any], *, days: str | None = None, hours: str | None = None):
    """``now + N days + M hours`` from whichever of the two params is set, or
    ``None`` when neither is."""
    total = timedelta()
    found = False
    for key, unit in ((days, "days"), (hours, "hours")):
        if key is None:
            continue
        value = params.get(key)
        if value in (None, ""):
            continue
        total += timedelta(**{unit: int(value)})
        found = True
    return timezone.now() + total if found else None


def create_activity(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    """Create an activity about this occurrence's student — or, for a type
    whose subject is an enquiry, about its enquiry — with its content filled
    in: title, notes, when it is planned and due, and answers to its form.
    Every text param is a template over the trigger's context."""
    from apps.work.models import ActivitySubject, ActivityType, ActivityTypeStatus
    from apps.work.services import create_activity as create_activity_service

    slug = params.get("type")
    activity_type = ActivityType.objects.filter(slug=slug, status=ActivityTypeStatus.ACTIVE).first()
    if activity_type is None:
        raise ApplicationError({"type": [f"Unknown or inactive activity type: {slug!r}."]})

    about_enquiry = activity_type.subject == ActivitySubject.ENQUIRY
    if about_enquiry and rctx.enquiry is None:
        return {"skipped": True, "reason": "No enquiry in context for this occurrence."}
    if not about_enquiry and rctx.student is None:
        return {"skipped": True, "reason": "No student in context for this occurrence."}

    actor = _system_actor(rule)
    if actor is None:
        return {"skipped": True, "reason": "No active superadmin available to act as."}

    assignee = resolve_user(params.get("assign_to"), rctx=rctx)
    due_at = _offset(params, days="due_in_days", hours="due_in_hours")
    planned_at = _offset(params, hours="planned_in_hours")
    prefill = {
        key: render_template(value, context) if isinstance(value, str) else value
        for key, value in (params.get("form_prefill") or {}).items()
    }

    activity = create_activity_service(
        actor=actor,
        student=None if about_enquiry else rctx.student,
        enquiry=rctx.enquiry if about_enquiry else None,
        activity_type=activity_type,
        enrollment=None if about_enquiry else rctx.enrollment,
        title=render_template(params.get("title") or "", context) or None,
        summary=render_template(params.get("summary") or "", context),
        assigned_to=assignee,
        planned_at=planned_at,
        due_at=due_at,
        priority=params.get("priority") or None,
        form_prefill=prefill,
    )
    # `parent`/`automation_run` are provenance this phase populates (see
    # `Activity`'s own module docstring) — set directly, once, after the
    # service call, rather than widening `create_activity`'s own signature
    # for a concern only this caller has.
    activity.parent = rctx.activity
    activity.automation_run_id = run.pk
    activity.save(update_fields=["parent", "automation_run", "updated_at"])
    return {
        "activity_id": str(activity.pk),
        "assigned_to": str(assignee.pk) if assignee else None,
    }


def update_enquiry(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    """Move the occurrence's enquiry along: its stage, owner, lost reason,
    lead quality or next follow-up. A change is itself an enquiry event,
    dispatched here one depth deeper (never through the signal, which would
    start again at depth 0) — the depth guard bounds a rule that changes the
    enquiry it was triggered by."""
    from apps.enquiries.services import update as update_enquiry_service

    if rctx.enquiry is None:
        return {"skipped": True, "reason": "No enquiry in context for this occurrence."}

    fields: dict[str, Any] = {}
    if params.get("stage"):
        fields["stage"] = params["stage"]
    if params.get("lost_reason"):
        fields["lost_reason"] = render_template(str(params["lost_reason"]), context)
    if params.get("lead_quality") not in (None, ""):
        fields["lead_quality"] = params["lead_quality"]
    if params.get("next_follow_up_in_days") not in (None, ""):
        fields["next_follow_up_at"] = timezone.now() + timedelta(
            days=int(params["next_follow_up_in_days"])
        )
    keep_owner = bool(params.get("only_if_unowned")) and rctx.enquiry.owner_id is not None
    if params.get("owner") and not keep_owner:
        owner = resolve_user(params["owner"], rctx=rctx)
        if owner is not None:
            fields["owner"] = owner

    enquiry, changed, previous_stage = update_enquiry_service(
        actor=_system_actor(rule), enquiry=rctx.enquiry, fields=fields, emit=False
    )
    # Later actions of this same rule (assign the call to `enquiry_owner`)
    # must see the enquiry as it is now, not as it was when the run began.
    rctx.enquiry = enquiry
    result: dict[str, Any] = {"enquiry_id": str(enquiry.pk), "changed": changed}
    if not changed:
        return result

    from .models import AutomationTrigger
    from .services import dispatch

    dispatch(
        AutomationTrigger.ENQUIRY_UPDATED,
        enquiry,
        depth=depth + 1,
        previous_stage=previous_stage,
        changed=changed,
    )
    if "stage" in changed:
        dispatch(
            AutomationTrigger.ENQUIRY_STAGE_CHANGED,
            enquiry,
            depth=depth + 1,
            previous_stage=previous_stage,
            changed=changed,
        )
        result["stage_changed_dispatched"] = True
    return result


def send_notification(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify, notify_many

    kind = params.get("kind")
    if kind not in NotificationKind.values:
        raise ApplicationError({"kind": [f"Unknown notification kind: {kind!r}."]})

    title = render_template(params.get("title", ""), context)
    body = render_template(params.get("body", ""), context)
    to = params.get("to")

    recipient = resolve_user(to, rctx=rctx)
    if recipient is not None:
        notification = notify(recipient=recipient, kind=kind, title=title, body=body)
        return {
            "delivered_to": [str(recipient.pk)],
            "notification_id": str(notification.pk) if notification else None,
        }

    if to in UserRole.values:
        recipients = User.objects.filter(role=to, is_active=True)
        if rctx.branch is not None:
            recipients = recipients.filter(branch_id=rctx.branch.pk)
        count = notify_many(recipients=recipients, kind=kind, title=title, body=body)
        return {"delivered_count": count, "role": to}

    return {"skipped": True, "reason": f"Could not resolve a recipient for 'to': {to!r}."}


def send_email(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    """Send through a published `MessageTemplate` (ERP Phase 19, ADR-12).

    `params["template"]` names a published *key*, exactly the catalog's own
    "published template key" — resolved by
    `apps.communication.services.resolve_published_template`, the same
    function `POST /communication/send/` resolves its own template through,
    so "which template does 'email' mean" has one answer everywhere. `to`
    is either a resolvable strategy/user id (`resolve_user`, as
    `send_notification` already uses) or, per the catalog, a literal
    address. A rule whose template was never published — or has since been
    unpublished — is a real, honestly-labelled `skipped` outcome, never a
    silent success and never a fabricated send.
    """
    from apps.communication.models import MessageChannel
    from apps.communication.services import create_deliveries, resolve_published_template

    key = params.get("template")
    version = resolve_published_template(key=key, channel=MessageChannel.EMAIL)
    if version is None:
        return {"skipped": True, "reason": f"No published email template for key {key!r}."}

    to = params.get("to")
    recipient = resolve_user(to, rctx=rctx)
    literal_address = to if recipient is None and isinstance(to, str) and "@" in to else None
    if recipient is None and literal_address is None:
        return {"skipped": True, "reason": f"Could not resolve a recipient for 'to': {to!r}."}

    deliveries = create_deliveries(
        channel=MessageChannel.EMAIL,
        template_version=version,
        recipients=[recipient] if recipient else [],
        literal_addresses=[literal_address] if literal_address else [],
        base_variables=context,
        related_object=rctx.activity or rctx.enrollment,
        requested_by=_system_actor(rule),
    )
    if not deliveries:
        return {"skipped": True, "reason": "The resolved recipient has no usable email address."}
    return {"delivery_id": str(deliveries[0].pk), "template": key}


def send_whatsapp(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    """Send through a published, WhatsApp-channel `MessageTemplate` (ERP
    Phase 19, ADR-12). Skipped — with a real reason, on `AutomationRun`,
    never a fabricated success — when there is no published template for
    this key, the recipient cannot be resolved, or the recipient has not
    opted in (`User.whatsapp_opt_in`); an unconfigured provider (the Null
    provider) is a *failed* `Delivery`, not a skipped action, since the
    catalog's own row for this action names "requires ... a configured
    provider; otherwise the run is skipped" only for the template/opt-in
    gates checked here — once a real `Delivery` exists, what the provider
    does with it is that row's own state, not this action's.
    """
    from apps.communication.models import MessageChannel
    from apps.communication.services import create_deliveries, resolve_published_template

    key = params.get("template")
    version = resolve_published_template(key=key, channel=MessageChannel.WHATSAPP)
    if version is None:
        return {"skipped": True, "reason": f"No published WhatsApp template for key {key!r}."}

    recipient = resolve_user(params.get("to"), rctx=rctx)
    if recipient is None:
        return {
            "skipped": True,
            "reason": f"Could not resolve a recipient for 'to': {params.get('to')!r}.",
        }
    if not recipient.whatsapp_opt_in:
        return {"skipped": True, "reason": "Recipient has not opted in to WhatsApp."}

    deliveries = create_deliveries(
        channel=MessageChannel.WHATSAPP,
        template_version=version,
        recipients=[recipient],
        base_variables=context,
        related_object=rctx.activity or rctx.enrollment,
        requested_by=_system_actor(rule),
    )
    if not deliveries:
        return {"skipped": True, "reason": "The recipient has no WhatsApp number on file."}
    return {"delivery_id": str(deliveries[0].pk), "template": key}


def create_review(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    from apps.performance.models import ReviewType
    from apps.performance.services import create_review as create_review_service

    if rctx.student is None:
        return {"skipped": True, "reason": "No student in context for this occurrence."}

    reviewer = resolve_user(params.get("reviewer"), rctx=rctx)
    if reviewer is None:
        return {"skipped": True, "reason": "Could not resolve a reviewer."}

    today = timezone.localdate()
    due_in_days = params.get("due_in_days")
    next_review_at = today + timedelta(days=int(due_in_days)) if due_in_days is not None else None
    review_type = params.get("review_type") or ReviewType.AD_HOC

    review = create_review_service(
        actor=reviewer,
        student=rctx.student,
        period_start=today,
        period_end=today,
        # A draft an automation opens is a placeholder for a human judgement,
        # never one of its own — the neutral midpoint of the 1-5 scale, never
        # exposed as a real rating until the reviewer named above edits it.
        rating=3,
        review_type=review_type,
        summary=(
            f"Draft opened automatically by the automation rule '{rule.name}'. "
            "Pending the reviewer's own assessment."
        ),
        next_review_at=next_review_at,
    )
    return {"review_id": str(review.pk), "reviewer": str(reviewer.pk)}


def flag_risk(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    from apps.performance.models import RiskLevel
    from apps.performance.services import risk_state_for

    if rctx.enrollment is None:
        return {"skipped": True, "reason": "No enrolment in context for this occurrence."}

    level = params.get("level")
    if level not in RiskLevel.values or level == RiskLevel.NONE:
        raise ApplicationError(
            {"level": [f"flag_risk level must be 'warning' or 'critical', got {level!r}."]}
        )

    from apps.policies.resolver import policy

    days = policy("risk", "manual_flag_days")
    state = risk_state_for(rctx.enrollment)
    previous_level = state.level
    previous_triggered = state.triggered

    state.previous_level = state.level
    state.previous_triggered = state.triggered
    state.level = level
    # A manual flag is itself a fresh computation of sorts — stamping
    # `computed_at` gives each override its own `RISK_CHANGED` occurrence
    # (`services._occurrence_for` keys on it), the same way a real engine
    # recompute would. Without this, two overrides on the same enrolment
    # would share one occurrence key and the second would be silently
    # absorbed by the idempotency guard before the depth guard ever saw it
    # — the depth guard, not idempotency, is what must bound a flag_risk
    # chain (ADR-13's "an action's own trigger runs at most 3 levels deep").
    state.computed_at = timezone.now()
    state.manual_override = True
    state.manual_override_level = level
    state.manual_override_reason = str(params.get("reason") or "")[:2000]
    state.manual_override_expires_at = timezone.now() + timedelta(days=int(days))
    state.manual_override_set_by_id = getattr(rule.created_by, "pk", None)
    state.save(
        update_fields=[
            "previous_level",
            "previous_triggered",
            "level",
            "computed_at",
            "manual_override",
            "manual_override_level",
            "manual_override_reason",
            "manual_override_expires_at",
            "manual_override_set_by",
            "updated_at",
        ]
    )

    result: dict[str, Any] = {"enrollment_id": str(rctx.enrollment.pk), "level": level}

    changed = level != (previous_level or RiskLevel.NONE)
    if changed:
        # `flag_risk` is itself a `RISK_CHANGED` occurrence (ADR-13: "an
        # action's own trigger runs at most 3 levels deep") — dispatched
        # directly, in-process, one depth deeper, rather than through
        # `RISK_CHANGED` (that signal has no `depth` parameter to carry, and
        # would re-enter at depth 0 forever). This is the one path that can
        # actually chain a rule into itself or another rule, which is
        # exactly what the "loop" guard exists to bound.
        from .models import AutomationTrigger
        from .services import dispatch

        dispatch(
            AutomationTrigger.RISK_CHANGED,
            state,
            depth=depth + 1,
            enrollment=rctx.enrollment,
            level=level,
            previous_level=previous_level,
            triggered=state.triggered,
            previous_triggered=previous_triggered,
        )
        result["risk_changed_dispatched"] = True

    return result


def assign_form(
    *, rule, run, rctx: RunContext, context: dict[str, Any], params: dict[str, Any], depth: int = 0
) -> dict[str, Any]:
    """Send a published form to someone to fill (`apps.forms.services.
    assign_form`), about this occurrence's student when there is one. The
    rule author's `form.assign` was checked when the rule was saved; the
    send itself runs as the system (ADR-13), so the centre-reach check a
    person sending by hand gets is not repeated here."""
    from apps.forms.models import FormDefinition
    from apps.forms.services import assign_form as assign_form_service

    slug = params.get("form")
    definition = FormDefinition.objects.filter(slug=slug).first()
    if definition is None:
        raise ApplicationError({"form": [f"Unknown form: {slug!r}."]})

    recipient = resolve_user(params.get("to"), rctx=rctx)
    if recipient is None:
        return {"skipped": True, "reason": f"No one to send the form to for {params.get('to')!r}."}

    actor = _system_actor(rule)
    due_in_days = params.get("due_in_days")
    due_at = (
        timezone.now() + timedelta(days=int(due_in_days)) if due_in_days not in (None, "") else None
    )

    assignment = assign_form_service(
        actor=actor,
        definition=definition,
        assigned_to=recipient,
        student=rctx.student,
        enquiry=rctx.enquiry,
        due_at=due_at,
        title=render_template(params.get("title", ""), context),
        message=render_template(params.get("message", ""), context),
        automation_run=run,
        enforce_authority=False,
    )
    return {"form_assignment_id": str(assignment.pk), "assigned_to": str(recipient.pk)}


ACTIONS = {
    "create_activity": create_activity,
    "assign_form": assign_form,
    "update_enquiry": update_enquiry,
    "send_notification": send_notification,
    "send_email": send_email,
    "send_whatsapp": send_whatsapp,
    "create_review": create_review,
    "flag_risk": flag_risk,
}
