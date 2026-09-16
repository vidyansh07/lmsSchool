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

#: Ordering for "worse of two severities" (`_worse`, `level_for`) — the only
#: comparison this module ever makes between severities, so it is the only
#: place that needs to know `CRITICAL` outranks `WARNING` outranks `NONE`.
_SEVERITY_RANK = {NONE: 0, WARNING: 1, CRITICAL: 2}


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


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


def _activity_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    """ADR-11's activity rule: two independent conditions, either one fires it.

    An overdue-count threshold (a workload that is not being kept up with —
    the same "count that starts to matter at N" shape as `_assignment_risk`)
    and a last-score threshold (the most recent completed/approved activity
    came in weak — the same "percentage below a bar" shape as
    `_academic_risk`). They measure different things, so both are always
    reported; when both trigger, the *worse* of the two severities is the
    outcome's severity and its detail — a student who is both behind and
    scoring badly is not less at risk for one of those being merely a
    warning.
    """
    data = numbers["activity"]
    overdue = data["overdue_count"]
    overdue_threshold = policy.risk_activity_overdue_count
    last_score = data["last_score"]
    score_threshold = policy.risk_activity_score_percent

    # Overdue count is a plain non-negative count — zero is a real, fully
    # measured answer, never "nothing to measure" (the same reasoning
    # `_assignment_risk` gives for `missed`).
    overdue_triggered = _decimal(overdue) > _decimal(overdue_threshold)
    # A last score only exists once something has actually been scored.
    score_triggered = last_score is not None and _decimal(last_score) < _decimal(score_threshold)
    triggered = overdue_triggered or score_triggered

    severity = NONE
    if overdue_triggered:
        severity = _severity_for_excess(overdue, overdue_threshold)
    if score_triggered:
        severity = _worse(severity, _severity_for_deficit(last_score, score_threshold))

    overdue_clause = f"{overdue} activity(ies) overdue ({overdue_threshold} is the risk threshold)."
    score_clause = (
        "No completed or approved activity has been scored yet."
        if last_score is None
        else f"Last scored activity {last_score}%, "
        f"{'below' if score_triggered else 'at or above'} the {score_threshold}% risk threshold."
    )
    return RiskOutcome(
        key="activity",
        label="Activity engagement",
        triggered=triggered,
        severity=severity,
        detail=f"{overdue_clause} {score_clause}",
        numbers={
            "overdue_count": overdue,
            "overdue_threshold": overdue_threshold,
            "last_score": last_score,
            "score_threshold": str(score_threshold),
        },
    )


def _project_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    """Triggers on any project that ran past its own due date still unfinished
    (`apps.projects.models.StudentProject.mark_late`'s own date comparison,
    read via the already-batched `ProgressInputs.student_projects` group —
    see `apps.performance.engine._project_risk_numbers`). A count, not a
    percentage, so — like `_assignment_risk` — zero is a fully measured
    "no risk" answer, never "nothing to measure"."""
    data = numbers["project"]
    overdue = data["overdue_count"]
    threshold = policy.risk_project_overdue
    triggered = _decimal(overdue) > _decimal(threshold)
    return RiskOutcome(
        key="project",
        label="Project deadlines",
        triggered=triggered,
        severity=_severity_for_excess(overdue, threshold) if triggered else NONE,
        detail=(
            "No overdue projects."
            if overdue == 0
            else f"{overdue} project(s) overdue and not yet finished "
            f"({threshold} is the risk threshold)."
        ),
        numbers={"overdue_count": overdue, "threshold": threshold},
    )


def _placement_risk(numbers: dict[str, Any], policy) -> RiskOutcome:
    """Mirrors `_activity_risk`'s score half exactly, narrowed to
    placement-category activities (`ActivityType.category == "placement"`,
    `ACTIVITY_CATALOG.md`) — a student can be doing fine on coursework
    activity and still be cold on placement calls, which is exactly the
    distinction this separate rule exists to surface."""
    data = numbers["placement"]
    average = data["average_percent"]
    threshold = policy.risk_placement_score_percent
    # No placement-category activity scored yet: nothing to be behind on,
    # the same "no weekly-test marks recorded yet" reasoning as `_academic_risk`.
    triggered = average is not None and _decimal(average) < _decimal(threshold)
    return RiskOutcome(
        key="placement",
        label="Placement readiness",
        triggered=triggered,
        severity=_severity_for_deficit(average, threshold) if triggered else NONE,
        detail=(
            "No placement activity scored yet."
            if average is None
            else f"{average}% average on placement activities, below the "
            f"{threshold}% risk threshold."
            if triggered
            else f"{average}% average on placement activities, at or above the "
            f"{threshold}% risk threshold."
        ),
        numbers={"percent": average, "threshold": str(threshold)},
    )


#: Every risk condition, in the order a person would want to read them.
#: Append-only: the first four are ERP Phase 6's, and `evaluate()`'s callers
#: read `outcomes` by `key`, never by position (`apps.performance.engine`,
#: this module's own tests) — nothing here relies on the order beyond "the
#: legacy four come first", so growing this tuple is safe.
RULES = (
    _attendance_risk,
    _academic_risk,
    _assignment_risk,
    _progress_risk,
    _activity_risk,
    _project_risk,
    _placement_risk,
)


def level_for(outcomes: list[RiskOutcome]) -> str:
    """The one-word verdict a triggered rule set adds up to: `"none"` if
    nothing triggered, else the worse of `WARNING`/`CRITICAL` among whatever
    did. The natural reading of the severity concept `_severity_for_*`
    already computes per rule — not a second scoring system standing next to
    it, per this module's own docstring."""
    severity = NONE
    for outcome in outcomes:
        if outcome.triggered:
            severity = _worse(severity, outcome.severity)
    return severity


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
        # ERP Phase 13 addition (ADR-11) — extends this dict, does not
        # replace anything `apps.performance.engine` already reads from it.
        "level": level_for(outcomes),
    }
