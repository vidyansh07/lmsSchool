"""Evaluating conditions against a trigger's context (ERP Phase 14, ADR-13).

Two things live here, and nothing else does:

``evaluate_conditions`` — a pure function over plain data. It never touches
the database and never raises for a condition that turns out false; the one
thing it refuses is an operator it does not recognise, which is a
programming error (a rule that got past `services._validate_rule_shape`
should never reach here with a bad operator).

``context_for`` — turns a trigger name and its triggering object into the
allowlisted dict `AUTOMATION_CATALOG.md`'s "Triggers and their context"
table describes. This is the *only* place that table is implemented; a
condition's path is checked against `ALLOWED_PATHS` (see `services.py`) at
save time, and resolved against exactly this dict at run time — the two
never drift because both read the same table.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

MISSING = object()

Condition = dict[str, Any]

#: `student.*` always means these six, per the catalog's own footnote.
_STUDENT_PATHS = frozenset(
    {
        "student.id",
        "student.name",
        "student.batch",
        "student.branch",
        "student.trainer",
        "student.counsellor",
        "student.risk_level",
    }
)

#: `enquiry.*`: the lead an occurrence is about, when there is one.
_ENQUIRY_PATHS = frozenset(
    {
        "enquiry.id",
        "enquiry.full_name",
        "enquiry.mobile",
        "enquiry.email",
        "enquiry.stage",
        "enquiry.previous_stage",
        "enquiry.changed",
        "enquiry.source",
        "enquiry.course",
        "enquiry.track",
        "enquiry.city",
        "enquiry.state",
        "enquiry.preferred_centre",
        "enquiry.mode",
        "enquiry.qualification",
        "enquiry.owner",
        "enquiry.has_owner",
        "enquiry.lead_quality",
        "enquiry.lost_reason",
        "enquiry.branch",
    }
)

#: The literal allowlist from `AUTOMATION_CATALOG.md`'s "Triggers and their
#: context" table — the single source of truth for which condition paths a
#: rule may reference per trigger. `ACTIVITY_COMPLETED` and `FORM_SUBMITTED`
#: additionally allow any `form.<key>` path (checked by prefix, below) since
#: the set of keys depends on which form the rule is written against — there
#: is no fixed list to enumerate.
ALLOWED_PATHS: dict[str, frozenset[str]] = {
    "ACTIVITY_COMPLETED": frozenset(
        {
            "activity.id",
            "activity.type",
            "activity.category",
            "activity.score",
            "activity.result",
            "activity.performed_by_role",
            "student.id",
            "student.batch",
            "student.branch",
            "student.risk_level",
        }
        | _ENQUIRY_PATHS
    ),
    "ACTIVITY_OVERDUE": frozenset(
        {"activity.id", "activity.type", "activity.assigned_to_role", "activity.days_overdue"}
        | _STUDENT_PATHS
        | _ENQUIRY_PATHS
    ),
    "ASSESSMENT_FAILED": frozenset(
        {"assessment.id", "assessment.percent", "assessment.attempt_number", "batch.trainer"}
        | _STUDENT_PATHS
    ),
    "ATTENDANCE_THRESHOLD": frozenset(
        {"attendance.percent", "attendance.absent_streak"} | _STUDENT_PATHS
    ),
    "PROJECT_OVERDUE": frozenset({"project.id", "project.days_overdue"} | _STUDENT_PATHS),
    "ASSIGNMENT_OVERDUE": frozenset({"assignment.id", "assignment.days_overdue"} | _STUDENT_PATHS),
    "RISK_CHANGED": frozenset(
        {"risk.level", "risk.previous_level", "risk.triggered", "risk.newly_triggered"}
        | _STUDENT_PATHS
    ),
    "FORM_SUBMITTED": frozenset(
        {
            "submission.id",
            "submission.form",
            "submission.submitted_by_role",
            "submission.assigned_to",
            "submission.requested_by",
            "submission.self_filled",
            "submission.on_time",
            "submission.from_automation",
        }
        | _STUDENT_PATHS
        | _ENQUIRY_PATHS
    ),
    "ENQUIRY_CREATED": _ENQUIRY_PATHS,
    "ENQUIRY_STAGE_CHANGED": _ENQUIRY_PATHS,
    "ENQUIRY_UPDATED": _ENQUIRY_PATHS,
}

#: Triggers whose context carries the answers of a form as `form.<key>` —
#: any key, since which keys exist depends on the form the rule is about.
FORM_PATH_TRIGGERS = frozenset({"ACTIVITY_COMPLETED", "FORM_SUBMITTED"})


def path_allowed(trigger: str, path: str) -> bool:
    if trigger in FORM_PATH_TRIGGERS and path.startswith("form.") and len(path) > len("form."):
        return True
    return path in ALLOWED_PATHS.get(trigger, frozenset())


def _get_path(context: dict[str, Any], path: str) -> Any:
    """Dotted lookup into a plain dict. Returns ``MISSING`` — never raises —
    the moment any segment is absent, exactly the "missing path is false,
    never an error" rule the catalog states for conditions."""
    node: Any = context
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def _comparable(value: Any) -> Any:
    """Numbers compare as numbers even when one side came off a `Decimal`
    (model field) and the other off a JSON literal (`int`/`float`)."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _op_eq(value, target) -> bool:
    return _comparable(value) == _comparable(target)


def _op_ne(value, target) -> bool:
    return _comparable(value) != _comparable(target)


def _op_lt(value, target) -> bool:
    return value is not None and _comparable(value) < _comparable(target)


def _op_lte(value, target) -> bool:
    return value is not None and _comparable(value) <= _comparable(target)


def _op_gt(value, target) -> bool:
    return value is not None and _comparable(value) > _comparable(target)


def _op_gte(value, target) -> bool:
    return value is not None and _comparable(value) >= _comparable(target)


def _op_in(value, target) -> bool:
    return value in target if isinstance(target, (list, tuple, set)) else False


def _op_not_in(value, target) -> bool:
    return value not in target if isinstance(target, (list, tuple, set)) else True


def _op_contains(value, target) -> bool:
    """List or string, per the catalog. ``target`` is the needle either way."""
    if isinstance(value, (list, tuple, set)):
        return target in value
    if isinstance(value, str):
        return isinstance(target, str) and target in value
    return False


def _is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _op_is_empty(value, target) -> bool:
    return _is_empty(value)


def _op_is_not_empty(value, target) -> bool:
    return not _is_empty(value)


OPERATORS = {
    "eq": _op_eq,
    "ne": _op_ne,
    "lt": _op_lt,
    "lte": _op_lte,
    "gt": _op_gt,
    "gte": _op_gte,
    "in": _op_in,
    "not_in": _op_not_in,
    "contains": _op_contains,
    "is_empty": _op_is_empty,
    "is_not_empty": _op_is_not_empty,
}

#: Operators that test the answer alone and take no comparison value.
VALUELESS_OPERATORS = frozenset({"is_empty", "is_not_empty"})


def evaluate_condition(condition: Condition, context: dict[str, Any]) -> bool:
    path = condition["path"]
    op = condition["op"]
    target = condition.get("value")
    value = _get_path(context, path)
    if value is MISSING:
        # A form question nobody answered is still a question: for the two
        # emptiness checks, "not there" is an answer. Every other operator
        # keeps the catalog's rule — a missing path is a false condition.
        if op == "is_empty":
            return True
        return False
    handler = OPERATORS.get(op)
    if handler is None:
        raise ValueError(f"Unknown condition operator: {op!r}")
    try:
        return bool(handler(value, target))
    except TypeError:
        # A shape mismatch (e.g. `lt` between a string and a number) is a
        # false condition, not a crashed dispatch — the same "never an
        # error" posture the catalog gives a missing path.
        return False


def evaluate_conditions(conditions: list[Condition], context: dict[str, Any]) -> bool:
    """ANDs every condition. An empty list is vacuously true — a rule with
    no conditions fires on every occurrence of its trigger, which is a
    legitimate (if blunt) rule a builder may save."""
    return all(evaluate_condition(condition, context) for condition in conditions)


#: Public alias — `apps.automation.actions.render_template` reuses the same
#: dotted-path lookup for `{{path.to.value}}` substitution rather than a
#: second copy of "walk a dict, return MISSING instead of raising".
get_path = _get_path


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

#: Form field types that never carry an answer, so never appear as `form.<key>`.
_FORM_CONTEXT_SKIPPED_TYPES = frozenset({"heading"})

#: The field types whose stored value must be compared as a number.
#: `apps.forms.validation._validate_decimal` persists a `decimal` field's
#: cleaned value as a `str` (so `FormResponse.values`, a plain `JSONField`,
#: never carries a `Decimal` Python cannot serialise) — read back verbatim,
#: `"3"` compared against a condition's JSON-literal `6` raises `TypeError`
#: inside `_op_lt`/`_op_gt`/etc., which `evaluate_condition` then treats as
#: "condition false" (its own documented, deliberate behaviour for a genuine
#: shape mismatch). Left uncoerced here, that turned every numeric condition
#: against a `decimal` field — including the seeded "Communication practice
#: after a weak mock" rule's `form.communication < 6` — into one that could
#: never fire, silently: not a crash, just a rule that looked active and
#: never once matched. Coercing back to `float` here, the one place this
#: context is built, is the fix; `number` fields are already a Python
#: `int`/`float` from `_validate_number` and pass through unchanged.
_FORM_CONTEXT_NUMERIC_FIELD_TYPES = frozenset({"number", "decimal", "rating"})


def _student_context(*, student=None, enrollment=None) -> dict[str, Any]:
    """`student.*` per the catalog: id, name, batch, branch, trainer (user
    id), counsellor (user id), risk_level. Resolved once per dispatch and
    reused — every trigger's `context_for` call below builds this from
    whichever of `student`/`enrollment` it already has in hand, never a
    second query for the same fact.

    `counsellor` is documented as "user id of `created_by` on the profile";
    `StudentProfile` itself carries no such column (it is not a soft-
    deletable, audited model), so this reads `Enrollment.created_by` instead
    — the closest real field to "who brought this student in", and the one
    `apps.students`/`apps.enrollments` actually populate at admission time.
    """
    if student is None and enrollment is not None:
        student = enrollment.student
    if student is None:
        return {}

    batch = enrollment.batch if enrollment is not None else None
    branch = getattr(student, "branch", None) or (batch.branch if batch else None)
    trainer_user_id = None
    if batch is not None and batch.trainer_id:
        trainer_user_id = batch.trainer.user_id
    counsellor_user_id = enrollment.created_by_id if enrollment is not None else None
    risk_level = None
    if enrollment is not None:
        risk_state = getattr(enrollment, "risk_state", None)
        risk_level = risk_state.level if risk_state is not None else None

    return {
        "id": str(student.pk),
        "name": student.user.get_full_name() if student.user_id else "",
        "batch": str(batch.pk) if batch is not None else None,
        "branch": str(branch.pk) if branch is not None else None,
        "trainer": str(trainer_user_id) if trainer_user_id else None,
        "counsellor": str(counsellor_user_id) if counsellor_user_id else None,
        "risk_level": risk_level,
    }


def _enquiry_context(enquiry, *, previous_stage: str = "", changed=None) -> dict[str, Any]:
    """`enquiry.*`: the lead's own fields, plus — for an enquiry event — the
    stage it left and which fields changed."""
    if enquiry is None:
        return {}
    return {
        "id": str(enquiry.pk),
        "full_name": enquiry.full_name,
        "mobile": enquiry.mobile,
        "email": enquiry.email or None,
        "stage": enquiry.stage,
        "previous_stage": previous_stage or None,
        "changed": list(changed or []),
        "source": enquiry.source or None,
        "course": enquiry.course or None,
        "track": enquiry.track or None,
        "city": enquiry.city or None,
        "state": enquiry.state or None,
        "preferred_centre": enquiry.preferred_centre or None,
        "mode": enquiry.mode or None,
        "qualification": enquiry.qualification or None,
        "owner": str(enquiry.owner_id) if enquiry.owner_id else None,
        "has_owner": enquiry.owner_id is not None,
        "lead_quality": enquiry.lead_quality,
        "lost_reason": enquiry.lost_reason or None,
        "branch": str(enquiry.branch_id) if enquiry.branch_id else None,
    }


def _activity_context(activity, *, days_overdue: int | None = None) -> dict[str, Any]:
    context = {
        "id": str(activity.pk),
        "type": activity.activity_type.slug,
        "category": activity.activity_type.category,
        "score": _normalised_score(activity.score, activity.max_score),
        "result": activity.result,
        "performed_by_role": activity.performed_by.role if activity.performed_by_id else None,
        "assigned_to": str(activity.assigned_to_id) if activity.assigned_to_id else None,
    }
    if days_overdue is not None:
        context["days_overdue"] = days_overdue
    return context


def _normalised_score(score, max_score) -> float | None:
    if score is None or max_score in (None, 0):
        return None
    return round(float(score) * 100 / float(max_score), 1)


def _form_context(form_version, form_response) -> dict[str, Any]:
    """`form.<key>` for every answer-carrying field of the form — reads
    `FormVersion.fields`/`FormResponse.values` (Phase 8), never a second copy
    of what a form field or a response looks like. Every field is present,
    an unanswered one as ``None``, so `is_empty` can see it was skipped.

    Text compares with `eq`/`contains`, a multi-choice answer is a list for
    `contains`, a yes/no or consent is a bool for `eq`. A `decimal` field's
    value is coerced back to a `float` here — see
    `_FORM_CONTEXT_NUMERIC_FIELD_TYPES`'s own docstring for why a condition
    against one would otherwise never match."""
    if form_version is None or form_response is None:
        return {}
    fields = form_version.fields.exclude(type__in=_FORM_CONTEXT_SKIPPED_TYPES)
    values = form_response.values or {}
    context: dict[str, Any] = {}
    for field in fields:
        raw = values.get(field.key)
        if field.type in _FORM_CONTEXT_NUMERIC_FIELD_TYPES and raw is not None:
            try:
                raw = float(raw)
            except (TypeError, ValueError):
                pass
        context[field.key] = raw
    return context


def context_for_activity_completed(activity) -> dict[str, Any]:
    context = {"activity": _activity_context(activity)}
    context["form"] = _form_context(activity.form_version, activity.form_response)
    context["student"] = _student_context(student=activity.student, enrollment=activity.enrollment)
    context["enquiry"] = _enquiry_context(activity.enquiry if activity.enquiry_id else None)
    return context


def context_for_activity_overdue(activity, *, days_overdue: int) -> dict[str, Any]:
    activity_ctx = _activity_context(activity, days_overdue=days_overdue)
    activity_ctx["assigned_to_role"] = (
        activity.assigned_to.role if activity.assigned_to_id else None
    )
    return {
        "activity": activity_ctx,
        "student": _student_context(student=activity.student, enrollment=activity.enrollment),
        "enquiry": _enquiry_context(activity.enquiry if activity.enquiry_id else None),
    }


def context_for_assessment_failed(result, *, percent: float, attempt_number: int) -> dict[str, Any]:
    enrollment = result.enrollment
    return {
        "assessment": {
            "id": str(result.assessment_id),
            "percent": percent,
            "attempt_number": attempt_number,
        },
        "student": _student_context(enrollment=enrollment),
        "batch": {
            "trainer": str(enrollment.batch.trainer.user_id)
            if enrollment.batch_id and enrollment.batch.trainer_id
            else None
        },
    }


def context_for_attendance_threshold(
    *, enrollment, percent: float, absent_streak: int
) -> dict[str, Any]:
    return {
        "attendance": {"percent": percent, "absent_streak": absent_streak},
        "student": _student_context(enrollment=enrollment),
    }


def context_for_project_overdue(student_project, *, days_overdue: int) -> dict[str, Any]:
    return {
        "project": {"id": str(student_project.project_id), "days_overdue": days_overdue},
        "student": _student_context(enrollment=student_project.enrollment),
    }


def context_for_assignment_overdue(assignment, enrollment, *, days_overdue: int) -> dict[str, Any]:
    return {
        "assignment": {"id": str(assignment.pk), "days_overdue": days_overdue},
        "student": _student_context(enrollment=enrollment),
    }


def context_for_risk_changed(
    *, enrollment, level, previous_level, triggered, previous_triggered
) -> dict[str, Any]:
    triggered = triggered or []
    previous_triggered = previous_triggered or []
    return {
        "risk": {
            "level": level,
            "previous_level": previous_level or None,
            "triggered": list(triggered),
            "newly_triggered": sorted(set(triggered) - set(previous_triggered)),
        },
        "student": _student_context(enrollment=enrollment),
    }


def context_for_form_submitted(assignment, *, enrollment=None) -> dict[str, Any]:
    submitted_at = assignment.submitted_at
    on_time = assignment.due_at is None or (
        submitted_at is not None and submitted_at <= assignment.due_at
    )
    return {
        "submission": {
            "id": str(assignment.pk),
            "form": assignment.definition.slug,
            "submitted_by_role": assignment.assigned_to.role,
            "assigned_to": str(assignment.assigned_to_id),
            "requested_by": str(assignment.requested_by_id) if assignment.requested_by_id else None,
            "self_filled": assignment.requested_by_id == assignment.assigned_to_id,
            "on_time": on_time,
            "from_automation": assignment.automation_run_id is not None,
        },
        "form": _form_context(assignment.version, assignment.response),
        "student": _student_context(student=assignment.student, enrollment=enrollment),
        "enquiry": _enquiry_context(assignment.enquiry if assignment.enquiry_id else None),
    }


def context_for_enquiry_event(enquiry, *, previous_stage: str = "", changed=None) -> dict[str, Any]:
    return {"enquiry": _enquiry_context(enquiry, previous_stage=previous_stage, changed=changed)}


def context_for(trigger: str, obj, **extra: Any) -> dict[str, Any]:
    """Route to the trigger-specific builder above.

    Every trigger needs more than just `obj` to build its context (a
    per-occurrence number — `days_overdue`, `percent`, `attempt_number`,
    `absent_streak` — or, for `ASSIGNMENT_OVERDUE`, the specific enrolment
    `obj` (an `Assignment`, shared by every enrolled student) is being
    evaluated for). `services.dispatch` computes those once per occurrence
    and passes them through as keyword arguments; this function only
    dispatches on `trigger`, it never re-derives them.
    """
    from .models import AutomationTrigger

    if trigger == AutomationTrigger.ACTIVITY_COMPLETED:
        return context_for_activity_completed(obj)
    if trigger == AutomationTrigger.ACTIVITY_OVERDUE:
        return context_for_activity_overdue(obj, days_overdue=extra["days_overdue"])
    if trigger == AutomationTrigger.ASSESSMENT_FAILED:
        return context_for_assessment_failed(
            obj, percent=extra["percent"], attempt_number=extra["attempt_number"]
        )
    if trigger == AutomationTrigger.ATTENDANCE_THRESHOLD:
        return context_for_attendance_threshold(
            enrollment=obj, percent=extra["percent"], absent_streak=extra["absent_streak"]
        )
    if trigger == AutomationTrigger.PROJECT_OVERDUE:
        return context_for_project_overdue(obj, days_overdue=extra["days_overdue"])
    if trigger == AutomationTrigger.ASSIGNMENT_OVERDUE:
        return context_for_assignment_overdue(
            obj, extra["enrollment"], days_overdue=extra["days_overdue"]
        )
    if trigger == AutomationTrigger.RISK_CHANGED:
        return context_for_risk_changed(
            enrollment=extra["enrollment"],
            level=extra["level"],
            previous_level=extra["previous_level"],
            triggered=extra["triggered"],
            previous_triggered=extra["previous_triggered"],
        )
    if trigger == AutomationTrigger.FORM_SUBMITTED:
        return context_for_form_submitted(obj, enrollment=extra.get("enrollment"))
    if trigger in (
        AutomationTrigger.ENQUIRY_CREATED,
        AutomationTrigger.ENQUIRY_STAGE_CHANGED,
        AutomationTrigger.ENQUIRY_UPDATED,
    ):
        return context_for_enquiry_event(
            obj,
            previous_stage=extra.get("previous_stage", ""),
            changed=extra.get("changed"),
        )
    raise ValueError(f"Unknown trigger: {trigger!r}")
