"""Completion rules — §6.4.

    "Use a configurable rule system that can express required and optional
    activities. Do not force every course to use every condition."

Each of the seven conditions §6.4 names is a rule here. A rule reads the numbers
:mod:`apps.progress.reports` produced and the thresholds
:mod:`apps.academics.policies` resolved, and returns a small verdict: is it
required, was it met, what were the numbers.

Two design points worth stating:

**A rule that is switched off is reported, not hidden.** It comes back with
``required: False`` and its numbers intact, so a screen can show "attendance
78% (not required on this course)" rather than pretending attendance does not
exist. Silence about a condition is how students end up surprised.

**A rule with nothing to measure passes.** A course with no projects cannot fail
its project requirement. That is not leniency; it is the only defensible answer,
and the alternative — blocking everybody on a course that sets no projects — is
a bug that would take months to notice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RuleOutcome:
    """One condition, and how this student stands against it."""

    key: str
    label: str
    required: bool
    met: bool
    detail: str
    numbers: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "required": self.required,
            "met": self.met,
            "detail": self.detail,
            "numbers": self.numbers,
        }


def _at_least(value, threshold) -> bool:
    return Decimal(str(value)) >= Decimal(str(threshold))


def _lessons(report, policy) -> RuleOutcome:
    numbers = report["lessons"]
    required = bool(policy.lessons_required_for_completion)
    threshold = policy.minimum_lesson_completion_percent
    # Nothing published to complete: there is no bar to clear.
    met = numbers["total"] == 0 or _at_least(numbers["percent"], threshold)
    return RuleOutcome(
        key="lessons",
        label="Course content",
        required=required,
        met=met,
        detail=(
            "No published lessons on this course."
            if numbers["total"] == 0
            else f"{numbers['completed']} of {numbers['total']} lessons "
            f"({numbers['percent']}%), {threshold}% required."
        ),
        numbers={"percent": numbers["percent"], "threshold": str(threshold)},
    )


def _attendance(report, policy) -> RuleOutcome:
    numbers = report["attendance"]
    required = bool(policy.attendance_required_for_completion)
    threshold = policy.minimum_attendance_percent
    met = not numbers["has_records"] or _at_least(numbers["percent"], threshold)
    return RuleOutcome(
        key="attendance",
        label="Attendance",
        required=required,
        met=met,
        detail=(
            "No classes have been registered yet."
            if not numbers["has_records"]
            else f"{numbers['percent']}% attended, {threshold}% required."
        ),
        numbers={"percent": numbers["percent"], "threshold": str(threshold)},
    )


def _assignments(report, policy) -> RuleOutcome:
    numbers = report["assignments"]
    required = bool(policy.assignment_required_for_completion)
    threshold = policy.minimum_assignment_completion_percent
    met = numbers["total"] == 0 or _at_least(numbers["percent"], threshold)
    return RuleOutcome(
        key="assignments",
        label="Assignments",
        required=required,
        met=met,
        detail=(
            "No assignments have been set."
            if numbers["total"] == 0
            else f"{numbers['submitted']} of {numbers['total']} handed in "
            f"({numbers['percent']}%), {threshold}% required."
        ),
        numbers={"percent": numbers["percent"], "threshold": str(threshold)},
    )


def _tests_taken(report, policy) -> RuleOutcome:
    numbers = report["tests"]
    required = bool(policy.tests_required_for_completion)
    threshold = policy.minimum_test_completion_percent
    met = numbers["total"] == 0 or _at_least(numbers["percent"], threshold)
    return RuleOutcome(
        key="tests_taken",
        label="Weekly tests sat",
        required=required,
        met=met,
        detail=(
            "No tests have been set."
            if numbers["total"] == 0
            else f"{numbers['recorded']} of {numbers['total']} results recorded "
            f"({numbers['percent']}%), {threshold}% required."
        ),
        numbers={"percent": numbers["percent"], "threshold": str(threshold)},
    )


def _test_score(report, policy) -> RuleOutcome:
    numbers = report["tests"]
    required = bool(policy.tests_required_for_completion)
    threshold = policy.minimum_test_average_percent
    average = numbers["average_percent"]
    met = average is None or _at_least(average, threshold)
    return RuleOutcome(
        key="test_score",
        label="Weekly test average",
        required=required,
        met=met,
        detail=(
            "No marks recorded yet."
            if average is None
            else f"{average}% average, {threshold}% required."
        ),
        numbers={"percent": average, "threshold": str(threshold)},
    )


def _projects(report, policy) -> RuleOutcome:
    numbers = report["projects"]
    required = bool(policy.projects_required_for_completion)
    met = numbers["required"] == 0 or numbers["finished"] >= numbers["required"]
    outstanding = ", ".join(item["title"] for item in numbers["outstanding"])
    return RuleOutcome(
        key="projects",
        label="Required projects",
        required=required,
        met=met,
        detail=(
            "No required projects on this course."
            if numbers["required"] == 0
            else f"{numbers['finished']} of {numbers['required']} finished."
            + (f" Outstanding: {outstanding}." if outstanding else "")
        ),
        numbers={"finished": numbers["finished"], "required": numbers["required"]},
    )


def _final_exam(report, policy) -> RuleOutcome:
    numbers = report["exam"]
    required = bool(policy.final_exam_required_for_completion)
    met = (not numbers["exists"]) or bool(numbers["passed"])
    return RuleOutcome(
        key="final_exam",
        label="Final examination",
        required=required,
        met=met,
        detail=(
            "No final examination on this course."
            if not numbers["exists"]
            else "Not sat yet."
            if not numbers["sat"]
            else f"Best attempt {numbers['best_percent']}%, "
            + ("passed." if numbers["passed"] else "below the pass mark.")
        ),
        numbers={"percent": numbers["best_percent"], "passed": numbers["passed"]},
    )


#: Every condition §6.4 names, in the order a person would read them.
RULES = (_lessons, _attendance, _assignments, _tests_taken, _test_score, _projects, _final_exam)


def evaluate(report: dict[str, Any], policy) -> dict[str, Any]:
    """Run every rule. Returns the outcomes and whether the student is eligible.

    Eligibility is "every *required* rule is met". Optional rules are still
    evaluated and still reported — a student is entitled to see where they stand
    on a condition even when it does not gate anything.
    """
    outcomes = [rule(report, policy) for rule in RULES]
    unmet = [outcome for outcome in outcomes if outcome.required and not outcome.met]

    return {
        "eligible": not unmet,
        "rules": [outcome.as_dict() for outcome in outcomes],
        "unmet": [outcome.key for outcome in unmet],
        "required_count": sum(1 for outcome in outcomes if outcome.required),
        "met_count": sum(1 for outcome in outcomes if outcome.required and outcome.met),
    }
