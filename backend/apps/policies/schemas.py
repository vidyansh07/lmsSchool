"""The policy schema registry (ERP Phase 3, ADR-04).

`POLICY_SCHEMAS[category][key]` is the one place a policy value's shape is
declared: its type, its default (what a fresh install and a reset both
answer), its bounds, and whether changing it is `critical` — critical keys
require a step-up and an explicit `confirm` naming the key (ADR-04,
SECURITY_DECISIONS "Destructive and expensive actions").

Categories `academic` and `institution` are *not* here: they are
`AcademicPolicy` and `SystemSetting`, chosen on purpose to keep named
columns (D-024, D-032). Nothing in this module may duplicate a key either of
those tables already owns.

Defaults are chosen to change nothing on the day this ships:

* `risk.*`'s first four keys mirror `AcademicPolicy`'s four `risk_*` fields'
  own defaults — additive, not a replacement for the academic table; those
  four fields remain what `apps.performance.risk`'s legacy four rules
  actually read (`apps.academics.policies.policy_for`), so this mirrored
  copy alone changing nothing is the point. The four ERP Phase 13 keys
  (`risk_activity_overdue_count`, `risk_activity_score_percent`,
  `risk_project_overdue`, `risk_placement_score_percent` — one rule,
  `activity`, needs two) have no
  `AcademicPolicy` column to mirror — they are new rules with no "today" to
  hold equal to, so their defaults are chosen fresh; see each key's own
  `description` for the reasoning.
* `performance.weights` is equal across every component `student_performance`
  already computes, which is exactly today's plain mean (ADR-10).
* `export.retention_days` and `file_upload.max_mb` mirror
  `SystemSetting.export_retention_days` / `resource_upload_max_mb`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.common.exceptions import ApplicationError

#: The components `apps.performance.engine.student_performance` weighs into
#: `overall_score` (ADR-10). The first five are the ones it already averaged
#: pre-ERP (attendance, assessment, assignments, projects, progress-vs-plan);
#: `activity` is Phase 12's addition, read from `apps.work.Activity` via
#: `ActivityType.performance_weight`. Adding it here is additive: the
#: `performance.weights` default below (`dict.fromkeys(...)`) picks it up
#: automatically, and with every weight equal — the default — a fixture with
#: no completed activities still lands on exactly today's plain mean, since
#: `activity` then has nothing to measure and is excluded like any other
#: component with no data.
PERFORMANCE_COMPONENTS: tuple[str, ...] = (
    "attendance",
    "assessment",
    "assignments",
    "projects",
    "progress",
    "activity",
)

POLICY_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "authentication": {
        "lockout_after": {
            "type": "integer",
            "default": 10,
            "min": 3,
            "max": 50,
            "critical": False,
            "description": (
                "Failed logins within 15 minutes before the account locks for 15 minutes."
            ),
        },
        "step_up_minutes": {
            "type": "integer",
            "default": 10,
            "min": 1,
            "max": 120,
            "critical": False,
            "description": "How long a step-up (ADR-05/06) stays fresh before it must be repeated.",
        },
        "mfa_required_roles": {
            "type": "role_list",
            "default": [],
            "critical": True,
            "description": (
                "Roles that must complete MFA to sign in, once past their own account's "
                "mfa_grace_days (ADR-05). Empty means nobody is forced into MFA without "
                "a device of their own choosing."
            ),
        },
        "mfa_grace_days": {
            "type": "integer",
            "default": 7,
            "min": 0,
            "max": 90,
            "critical": False,
            "description": (
                "Days a required role's account may sign in without MFA, counted from its "
                "own date_joined, before enforcement begins (ADR-05)."
            ),
        },
    },
    "password": {
        "min_length": {
            "type": "integer",
            "default": 10,
            "min": 8,
            "max": 128,
            "critical": True,
            "description": (
                "Shortest password Django's validators accept. Never below the floor of 8."
            ),
        },
        "require_classes": {
            "type": "integer",
            "default": 2,
            "min": 1,
            "max": 4,
            "critical": True,
            "description": (
                "How many of upper-case, lower-case, digit and symbol a password must mix."
            ),
        },
        "history_count": {
            "type": "integer",
            "default": 5,
            "min": 0,
            "max": 24,
            "critical": True,
            "description": "How many of a user's previous passwords cannot be reused.",
        },
    },
    "session": {
        "max_age_hours": {
            "type": "integer",
            "default": 12,
            "min": 1,
            "max": 168,
            "critical": True,
            "description": "How long a session stays valid since login.",
        },
        "idle_minutes": {
            "type": "integer",
            "default": 0,
            "min": 0,
            "max": 1440,
            "critical": False,
            "description": "Idle timeout in minutes. 0 means no idle timeout.",
        },
    },
    "risk": {
        "risk_attendance_percent": {
            "type": "decimal",
            "default": "75.00",
            "min": "0",
            "max": "100",
            "critical": False,
            "description": (
                "Attendance % below which the attendance risk rule fires. Mirrors "
                "AcademicPolicy.risk_attendance_percent's default; additive, not a replacement."
            ),
        },
        "risk_assessment_average_percent": {
            "type": "decimal",
            "default": "50.00",
            "min": "0",
            "max": "100",
            "critical": False,
            "description": "Assessment average % below which the assessment risk rule fires.",
        },
        "risk_missed_assignments": {
            "type": "integer",
            "default": 2,
            "min": 0,
            "max": 50,
            "critical": False,
            "description": "Missed assignments at or above which the assignment risk rule fires.",
        },
        "risk_progress_variance_percent": {
            "type": "decimal",
            "default": "15.00",
            "min": "0",
            "max": "100",
            "critical": False,
            "description": "Progress variance % at or above which the progress risk rule fires.",
        },
        # --- ERP Phase 13 (ADR-11): no `AcademicPolicy` equivalent, so these
        # four are the first `risk.*` keys with a genuinely fresh default
        # rather than a mirrored one.
        "risk_activity_overdue_count": {
            "type": "integer",
            "default": 3,
            "min": 0,
            "max": 50,
            "critical": False,
            "description": (
                "Overdue activities past which the activity risk rule fires. Higher than "
                "risk_missed_assignments' default (2): the activity catalog spans everything "
                "from a single mock interview to routine, low-stakes mentoring check-ins, so a "
                "little more tolerance avoids flagging a student the moment one gets away."
            ),
        },
        "risk_activity_score_percent": {
            "type": "decimal",
            "default": "50.00",
            "min": "0",
            "max": "100",
            "critical": False,
            "description": (
                "Normalised score (score/max_score x 100) below which a student's most recent "
                "completed or approved activity trips the activity risk rule. Matches "
                "risk_assessment_average_percent's default — the same half-marks bar, applied "
                "to the same 0-100 scale an activity's score is normalised onto."
            ),
        },
        "risk_project_overdue": {
            "type": "integer",
            "default": 0,
            "min": 0,
            "max": 10,
            "critical": False,
            "description": (
                "Overdue, unfinished projects past which the project risk rule fires. 0 means "
                "any single overdue project triggers it, matching the plain product reading "
                "('a required project ran past its deadline unfinished') rather than tolerating "
                "a backlog first; raise it for a course with a deliberately loose project cadence."
            ),
        },
        "risk_placement_score_percent": {
            "type": "decimal",
            "default": "50.00",
            "min": "0",
            "max": "100",
            "critical": False,
            "description": (
                "Average normalised score on placement-category activities below which the "
                "placement risk rule fires. Same half-marks bar as risk_activity_score_percent "
                "and risk_assessment_average_percent, for the same 0-100 scale."
            ),
        },
        # --- ERP Phase 14 (ADR-13): the automation `flag_risk` action writes
        # a manual override onto `RiskState`, and this is how long it stands
        # before lapsing back to whatever the engine itself computes — a
        # human (or a rule acting for one) flagged this today, but a stale
        # flag from months ago should not outlive its relevance forever.
        "manual_flag_days": {
            "type": "integer",
            "default": 14,
            "min": 1,
            "max": 180,
            "critical": False,
            "description": (
                "Days a manual risk flag (automation's flag_risk action) stands before expiring."
            ),
        },
    },
    "performance": {
        "weights": {
            "type": "weights",
            "default": dict.fromkeys(PERFORMANCE_COMPONENTS, 1),
            "min": "0",
            "max": "10",
            "critical": False,
            "description": (
                "Relative weight of each performance component. Equal by default, "
                "which reproduces today's plain-mean overall score (ADR-10)."
            ),
        },
    },
    "communication": {
        "guardian_alerts": {
            "type": "boolean",
            "default": False,
            "critical": False,
            "description": "Send a guardian an alert when a student trips a risk rule.",
        },
    },
    "export": {
        "retention_days": {
            "type": "integer",
            "default": 14,
            "min": 1,
            "max": 365,
            "critical": False,
            "description": (
                "How long a finished export stays downloadable. Mirrors "
                "SystemSetting.export_retention_days by default."
            ),
        },
    },
    "deletion": {
        "require_reason": {
            "type": "boolean",
            "default": True,
            "critical": True,
            "description": "Whether a soft delete must carry a reason.",
        },
        "purge_grace_days": {
            "type": "integer",
            "default": 0,
            "min": 0,
            "max": 90,
            "critical": True,
            "description": (
                "Days a record must stay soft-deleted before it may be purged. 0 means no wait."
            ),
        },
    },
    "approval": {
        "completion_requires_approval": {
            "type": "boolean",
            "default": True,
            "critical": False,
            "description": "Whether a course completion needs an explicit approval step.",
        },
    },
    "file_upload": {
        "max_mb": {
            "type": "integer",
            "default": 25,
            "min": 1,
            "max": 25,
            "critical": False,
            "description": (
                "Largest file a form upload accepts. Mirrors "
                "SystemSetting.resource_upload_max_mb by default; 25 MB is a hard "
                "ceiling no policy value may exceed (SECURITY_DECISIONS)."
            ),
        },
    },
    "notification": {
        "digest_frequency": {
            "type": "choice",
            "default": "immediate",
            "choices": ["immediate", "daily", "weekly"],
            "critical": False,
            "description": (
                "How often notification digests are sent, instead of one message per event."
            ),
        },
    },
    # --- ERP Phase 14 (ADR-13): the automation engine's own guards.
    "automation": {
        "max_runs_per_object_per_day": {
            "type": "integer",
            "default": 10,
            "min": 1,
            "max": 200,
            "critical": False,
            "description": (
                "At most this many AutomationRun rows per (rule, object) pair per day — the "
                "catalog's rate guard against a rule (or a chain of rules) firing without bound "
                "on one record."
            ),
        },
    },
}


def categories() -> list[str]:
    return sorted(POLICY_SCHEMAS)


def schema_for(category: str, key: str) -> dict[str, Any] | None:
    return POLICY_SCHEMAS.get(category, {}).get(key)


def iter_schema():
    """Every `(category, key, schema)` triple, in a stable order."""
    for category in sorted(POLICY_SCHEMAS):
        for key in sorted(POLICY_SCHEMAS[category]):
            yield category, key, POLICY_SCHEMAS[category][key]


def _to_decimal(value: Any, *, field: str | None = None) -> Decimal:
    label = f"{field}: " if field else ""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ApplicationError({"value": [f"{label}Must be a number."]}) from None


def _check_range(entry: dict[str, Any], value: Any, *, field: str | None = None) -> None:
    label = f"{field}: " if field else ""
    minimum, maximum = entry.get("min"), entry.get("max")
    if minimum is not None:
        bound = Decimal(str(minimum)) if isinstance(value, Decimal) else minimum
        if value < bound:
            raise ApplicationError({"value": [f"{label}Must be at least {minimum}."]})
    if maximum is not None:
        bound = Decimal(str(maximum)) if isinstance(value, Decimal) else maximum
        if value > bound:
            raise ApplicationError({"value": [f"{label}Must be at most {maximum}."]})


def validate_value(category: str, key: str, value: Any) -> Any:
    """The value, normalised to its stored shape — or an `ApplicationError`
    naming exactly what is wrong, the same way a serializer field would."""
    entry = schema_for(category, key)
    if entry is None:
        raise ApplicationError({"key": [f"Unknown policy: {category}.{key}."]})
    kind = entry["type"]

    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApplicationError({"value": ["Must be a whole number."]})
        _check_range(entry, value)
        return value

    if kind == "decimal":
        decimal_value = _to_decimal(value)
        _check_range(entry, decimal_value)
        return str(decimal_value)

    if kind == "boolean":
        if not isinstance(value, bool):
            raise ApplicationError({"value": ["Must be true or false."]})
        return value

    if kind == "choice":
        choices = entry.get("choices") or []
        if value not in choices:
            raise ApplicationError({"value": [f"Must be one of: {', '.join(choices)}."]})
        return value

    if kind == "weights":
        wanted = set(entry["default"])
        if not isinstance(value, dict) or set(value) != wanted:
            raise ApplicationError(
                {"value": [f"Must set exactly these components: {', '.join(sorted(wanted))}."]}
            )
        normalised: dict[str, str] = {}
        for component, weight in value.items():
            decimal_weight = _to_decimal(weight, field=component)
            _check_range(entry, decimal_weight, field=component)
            normalised[component] = str(decimal_weight)
        return normalised

    if kind == "role_list":
        # Deliberately does not check each entry against `UserRole` — this
        # module is self-contained and does not import `apps.accounts`
        # (see the module docstring's boundary). An unrecognised role name
        # here just never matches anyone at login, which fails safe: it is
        # a misconfiguration an administrator notices, not a privilege gap.
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ApplicationError({"value": ["Must be a list of role names."]})
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            slug = item.strip().lower()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            cleaned.append(slug)
        return cleaned

    raise ApplicationError({"value": ["Unsupported policy type."]})  # pragma: no cover - defensive


__all__ = [
    "PERFORMANCE_COMPONENTS",
    "POLICY_SCHEMAS",
    "categories",
    "iter_schema",
    "schema_for",
    "validate_value",
]
