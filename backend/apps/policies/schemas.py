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

* `risk.*` mirrors `AcademicPolicy`'s four `risk_*` fields' own defaults —
  additive, not a replacement for the academic table.
* `performance.weights` is equal across every component `student_performance`
  already computes, which is exactly today's plain mean (ADR-10).
* `export.retention_days` and `file_upload.max_mb` mirror
  `SystemSetting.export_retention_days` / `resource_upload_max_mb`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.common.exceptions import ApplicationError

#: The components `apps.performance.engine.student_performance` averages
#: today (attendance, assessment, assignments, projects, progress-vs-plan).
#: Phase 12 wires `performance.weights` into that calculation without
#: changing the current plain mean while every weight stays equal.
PERFORMANCE_COMPONENTS: tuple[str, ...] = (
    "attendance",
    "assessment",
    "assignments",
    "projects",
    "progress",
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

    raise ApplicationError({"value": ["Unsupported policy type."]})  # pragma: no cover - defensive


__all__ = [
    "PERFORMANCE_COMPONENTS",
    "POLICY_SCHEMAS",
    "categories",
    "iter_schema",
    "schema_for",
    "validate_value",
]
