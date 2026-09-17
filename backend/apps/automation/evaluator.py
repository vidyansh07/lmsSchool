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

#: The literal allowlist from `AUTOMATION_CATALOG.md`'s "Triggers and their
#: context" table — the single source of truth for which condition paths a
#: rule may reference per trigger. `ACTIVITY_COMPLETED` additionally allows
#: any `form.<key>` path (checked by prefix, below) since the set of keys
#: depends on whichever form is pinned to whichever activity type a rule is
#: written against — there is no fixed list to enumerate.
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
    ),
    "ACTIVITY_OVERDUE": frozenset(
        {"activity.id", "activity.type", "activity.assigned_to_role", "activity.days_overdue"}
        | _STUDENT_PATHS
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
}


def path_allowed(trigger: str, path: str) -> bool:
    if trigger == "ACTIVITY_COMPLETED" and path.startswith("form."):
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
}


def evaluate_condition(condition: Condition, context: dict[str, Any]) -> bool:
    path = condition["path"]
    op = condition["op"]
    target = condition.get("value")
    value = _get_path(context, path)
    if value is MISSING:
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

#: Form field types the catalog's "numeric/select field of the pinned form"
#: covers — a number/decimal is numeric, a select/radio is a single-choice
#: field. Multi-select and free text are not: a condition operator here
#: (`eq`, `lt`, …) has no useful meaning against either.
_FORM_CONTEXT_FIELD_TYPES = frozenset({"number", "decimal", "select", "radio"})


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
    """`form.<key>` for every numeric/select field of the pinned form —
    reads `FormVersion.fields`/`FormResponse.values` (Phase 8), never a
    second copy of what a form field or a response looks like."""
    if form_version is None or form_response is None:
        return {}
    fields = form_version.fields.filter(type__in=_FORM_CONTEXT_FIELD_TYPES)
    values = form_response.values or {}
    return {field.key: values.get(field.key) for field in fields}


def context_for_activity_completed(activity) -> dict[str, Any]:
    context = {"activity": _activity_context(activity)}
    context["form"] = _form_context(activity.form_version, activity.form_response)
    context["student"] = _student_context(student=activity.student, enrollment=activity.enrollment)
    return context


def context_for_activity_overdue(activity, *, days_overdue: int) -> dict[str, Any]:
    activity_ctx = _activity_context(activity, days_overdue=days_overdue)
    activity_ctx["assigned_to_role"] = (
        activity.assigned_to.role if activity.assigned_to_id else None
    )
    return {
        "activity": activity_ctx,
        "student": _student_context(student=activity.student, enrollment=activity.enrollment),
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
    raise ValueError(f"Unknown trigger: {trigger!r}")
