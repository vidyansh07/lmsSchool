"""Risk rules — turning numbers plus configurable thresholds into a verdict.

Shaped exactly like :mod:`apps.progress.rules`, because it is solving the same
kind of problem: read the numbers :mod:`apps.performance.engine` gathered and
the thresholds :mod:`apps.academics.policies` resolved, and return a small
verdict per rule — is this a concern, how bad, what were the numbers.

Two of that module's decisions apply here without change, and are worth
restating because getting them wrong here is worse, not better:

**A rule with nothing to measure does not trigger.** A student with no
assessments yet is not an academic risk; a student on a batch that starts
tomorrow is not behind schedule. Flagging either would mean every new student
is at risk on day one, which teaches everyone downstream to ignore the flag.

**Every rule reports its numbers, triggered or not.** A screen should be able
to say "attendance 78% (no risk)" as easily as "attendance 40% (at risk)" —
silence about a number that was actually computed is how a dashboard ends up
less informative than the API backing it.

Severity
--------
A triggered rule is also given a rough magnitude — ``"warning"`` or
``"critical"`` — computed from how far the number sits past its threshold,
relative to the threshold itself. It is deliberately coarse: this is a sorting
aid for a caseload list, not a second scoring system standing next to the risk
flag itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

NONE = "none"
WARNING = "warning"
CRITICAL = "critical"

#: Past this fraction of the threshold, a triggered rule reads as critical
#: rather than a warning. One and a half times the threshold's own size is a
#: generous margin — it takes a lot to go from "flagged" to "critical".
_CRITICAL_RATIO = Decimal("0.5")


@dataclass(frozen=True)
class RiskOutcome:
    """One risk condition, and how this student stands against it."""

    key: str
    label: str
    triggered: bool
    severity: str
    detail: str
    numbers: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "triggered": self.triggered,
            "severity": self.severity,
            "detail": self.detail,
            "numbers": self.numbers,
        }


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _severity_for_deficit(value, threshold) -> str:
    """Severity for a "lower is worse" rule (attendance, assessment average)."""
    threshold = _decimal(threshold)
    if threshold <= 0:
        return WARNING
    ratio = (threshold - _decimal(value)) / threshold
    return CRITICAL if ratio >= _CRITICAL_RATIO else WARNING


def _severity_for_excess(value, threshold) -> str:
    """Severity for a "higher is worse" rule (missed assignments, variance)."""
    threshold = _decimal(threshold)
    if threshold <= 0:
        return CRITICAL if _decimal(value) > 0 else WARNING
    ratio = (_decimal(value) - threshold) / threshold
    return CRITICAL if ratio >= _CRITICAL_RATIO else WARNING


def _attendance_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    data = numbers["attendance"]
    threshold = policy.risk_attendance_percent
    percent = data["percent"]
    # No classes registered yet: there is nothing to be behind on.
    triggered = data["has_records"] and _decimal(percent) < _decimal(threshold)
    return RiskOutcome(
        key="attendance",
        label="Attendance",
        triggered=triggered,
        severity=_severity_for_deficit(percent, threshold) if triggered else NONE,
        detail=(
            "No classes have been registered yet."
            if not data["has_records"]
            else f"{percent}% attended, below the {threshold}% risk threshold."
            if triggered
            else f"{percent}% attended, at or above the {threshold}% risk threshold."
        ),
        numbers={"percent": percent, "threshold": str(threshold)},
    )


def _academic_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    data = numbers["assessment"]
    threshold = policy.risk_assessment_average_percent
    average = data["average_percent"]
    # Nothing scored yet: a student cannot fail an average that does not exist.
    triggered = average is not None and _decimal(average) < _decimal(threshold)
    return RiskOutcome(
        key="academic",
        label="Assessment average",
        triggered=triggered,
        severity=_severity_for_deficit(average, threshold) if triggered else NONE,
        detail=(
            "No weekly-test marks recorded yet."
            if average is None
            else f"{average}% average, below the {threshold}% risk threshold."
            if triggered
            else f"{average}% average, at or above the {threshold}% risk threshold."
        ),
        numbers={"percent": average, "threshold": str(threshold)},
    )


def _assignment_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    data = numbers["assignments"]
    threshold = policy.risk_missed_assignments
    missed = data["missed"]
    # Threshold is the count of overdue, never-submitted assignments that
    # starts to matter — reaching it, not merely approaching it, triggers.
    triggered = missed >= threshold
    return RiskOutcome(
        key="assignments",
        label="Missed assignments",
        triggered=triggered,
        severity=_severity_for_excess(missed, threshold) if triggered else NONE,
        detail=(
            "No overdue assignments."
            if missed == 0
            else f"{missed} assignment(s) overdue with no submission at all "
            f"({threshold} is the risk threshold)."
        ),
        numbers={"missed": missed, "threshold": threshold},
    )


def _progress_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    data = numbers["progress"]
    threshold = policy.risk_progress_variance_percent
    variance = data["variance"]
    # No published lessons, or the batch has not started: nothing to fall
    # behind on yet.
    triggered = variance is not None and _decimal(variance) > _decimal(threshold)
    return RiskOutcome(
        key="progress",
        label="Course progress",
        triggered=triggered,
        severity=_severity_for_excess(variance, threshold) if triggered else NONE,
        detail=(
            "Not enough to measure yet."
            if variance is None
            else f"{variance} percentage points behind where the batch's schedule "
            f"puts them ({threshold} is the risk threshold)."
            if triggered
            else f"{variance} percentage points behind schedule, within the "
            f"{threshold}-point risk threshold."
        ),
        numbers={
            "actual_percent": data["actual_percent"],
            "expected_percent": data["expected_percent"],
            "variance": variance,
            "threshold": str(threshold),
        },
    )


#: Every risk condition, in the order a person would want to read them.
RULES = (_attendance_risk, _academic_risk, _assignment_risk, _progress_risk)


def evaluate(numbers: dict[str, Any], policy) -> dict[str, Any]:
    """Run every rule against one student's numbers.

    Unlike :func:`apps.progress.rules.evaluate`, there is no "required"
    distinction — every rule always applies, because risk is an observation,
    not a gate a course can opt out of. What a course-level toggle would even
    mean for "is this student falling behind" is not a real question.
    """
    outcomes = [rule(numbers, policy) for rule in RULES]
    triggered = [outcome for outcome in outcomes if outcome.triggered]

    return {
        "at_risk": bool(triggered),
        "outcomes": [outcome.as_dict() for outcome in outcomes],
        "triggered": [outcome.key for outcome in triggered],
        "triggered_count": len(triggered),
    }
