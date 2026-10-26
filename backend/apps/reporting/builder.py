"""A report somebody builds themselves: pick a thing, pick what to show, ask
it questions, group it.

The twenty reports beside this one answer questions somebody thought of in
advance. An operations team spends its day on the ones nobody thought of --
"RHCSA and AWS admissions at Jaipur between April and June, by course, with
what was collected against each" -- and the honest answer to that is not a
twenty-first fixed report.

What this is NOT
----------------
It is not a query endpoint. The obvious shape -- take a model name, a field
list and a filter string from the request -- hands a caller the ORM:
`student__user__password__startswith` is a password oracle, and
`student__referred_by__user__email` walks relations the caller may not read
at all. `apps.common.filtering` already makes that argument at length and
answers it with an allowlist; this is the same answer, applied to a whole
dataset rather than one screen.

So nothing here reads a field name and trusts it. A dataset declares the
columns it is willing to show, the fields it is willing to be asked about and
the measures it is willing to total. A path that is not declared does not
become reachable by being spelled correctly, and the ORM paths never leave
the server -- a caller sends `course`, not `batch__course__title`.

Where the rows come from
------------------------
`_queryset_for_user`, the same resolver the fixed reports, the synchronous
downloads and the background exports already share. Every run therefore
starts from the caller's own visible set, and a filter can only subtract from
what they could already see.

That applies to the totals as much as the rows. A count is as much a
disclosure as a row -- "3 students at Pune match" tells you Pune students
exist -- so grouping runs inside the scoped queryset and a group with no
visible rows does not appear at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Count, Sum, Value
from django.db.models.functions import Concat, Trim

from apps.common.exceptions import ApplicationError
from apps.common.filtering import OPERATORS


def person_name(prefix: str) -> Any:
    """A person's name as one column, from the three fields that hold it.

    `Trim` because a missing middle name would otherwise leave a double
    space in the middle of every name in the report.
    """
    return Trim(
        Concat(
            f"{prefix}__first_name",
            Value(" "),
            f"{prefix}__middle_name",
            Value(" "),
            f"{prefix}__last_name",
        )
    )


#: The most rows one built report will return in a response. Past this the
#: answer is an export, which streams and does not hold the institution in
#: memory.
MAX_ROWS = 1000


@dataclass(frozen=True)
class Column:
    """One thing a dataset is willing to show.

    `path` is the ORM path and never leaves the server; `name` is what a
    caller asks for and what comes back.

    `expression` is for the columns that are not a field. A person's name is
    the obvious one: `User.full_name` is a property, so "Student" is three
    columns in the database and one column to anybody reading a report.
    Declaring the expression here keeps that a dataset's business rather than
    making every report split a name in two.
    """

    name: str
    label: str
    path: str
    expression: Any = None


@dataclass(frozen=True)
class Measure:
    """One thing a dataset is willing to total. `count` needs no path."""

    name: str
    label: str
    kind: str  # "count" | "sum"
    path: str | None = None


@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    description: str
    #: The `source` string `_queryset_for_user` understands.
    source: str
    columns: tuple[Column, ...]
    #: `FilterField`s, reusing the kinds and operators every list screen uses.
    filters: tuple[Any, ...]
    measures: tuple[Measure, ...]

    def column(self, name: str) -> Column:
        for column in self.columns:
            if column.name == name:
                return column
        raise ApplicationError({"columns": [f"This report has no column called {name!r}."]})

    def measure(self, name: str) -> Measure:
        for measure in self.measures:
            if measure.name == name:
                return measure
        raise ApplicationError({"measures": [f"This report has no total called {name!r}."]})

    def describe(self) -> dict[str, Any]:
        """Everything a browser needs to build the form, and no ORM path."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "columns": [{"name": c.name, "label": c.label} for c in self.columns],
            "filters": [field.describe() for field in self.filters],
            "measures": [{"name": m.name, "label": m.label, "kind": m.kind} for m in self.measures],
        }


def _filter_field(dataset: Dataset, name: str):
    for field in dataset.filters:
        if field.name == name:
            return field
    raise ApplicationError({"filters": [f"This report cannot be asked about {name!r}."]})


def apply_filters(dataset: Dataset, rows, filters: list[dict[str, Any]]):
    """Narrow `rows` by what was asked, refusing anything not declared.

    An undeclared field or an operator the field's kind does not offer is a
    400 naming it, never an empty result: a filter that silently matches
    nothing is indistinguishable from a question with no answer, and somebody
    will read the empty report as fact.
    """
    for clause in filters or []:
        name = clause.get("field")
        operator = clause.get("op") or "exact"
        value = clause.get("value")
        field = _filter_field(dataset, name)
        if operator not in OPERATORS[field.kind]:
            raise ApplicationError(
                {"filters": [f"{name!r} cannot be asked {operator!r}."]},
            )
        lookup = field.path if operator == "exact" else f"{field.path}__{operator}"
        if operator == "in" and not isinstance(value, list):
            raise ApplicationError({"filters": [f"{name!r} with 'in' needs a list of values."]})
        rows = rows.filter(**{lookup: value})
    return rows


def run(
    *,
    dataset: Dataset,
    rows,
    columns: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    measures: list[str] | None = None,
    limit: int = MAX_ROWS,
) -> dict[str, Any]:
    """Build and run one report, returning `{columns, rows, truncated}`.

    Grouped and ungrouped are deliberately different shapes rather than one
    shape with empty cells: a grouped report's rows are one per group with
    totals, and pretending they are the same rows with some columns missing
    is how a sum ends up next to a record it does not describe.
    """
    rows = apply_filters(dataset, rows, filters or [])

    if group_by:
        grouping = dataset.column(group_by)
        if grouping.expression is not None:
            rows = rows.annotate(**{grouping.path: grouping.expression})
        wanted = [dataset.measure(name) for name in (measures or ["count"])]
        annotations = {}
        for measure in wanted:
            if measure.kind == "count":
                annotations[measure.name] = Count("id")
            elif measure.kind == "sum":
                annotations[measure.name] = Sum(measure.path)
        grouped = (
            rows.values(grouping.path).annotate(**annotations).order_by(grouping.path)[: limit + 1]
        )
        produced = list(grouped)
        return {
            "columns": [{"name": grouping.name, "label": grouping.label}]
            + [{"name": m.name, "label": m.label} for m in wanted],
            "rows": [
                {grouping.name: row[grouping.path], **{m.name: row[m.name] for m in wanted}}
                for row in produced[:limit]
            ],
            "truncated": len(produced) > limit,
            "grouped": True,
        }

    chosen = [dataset.column(name) for name in (columns or [c.name for c in dataset.columns])]
    computed = {c.path: c.expression for c in chosen if c.expression is not None}
    if computed:
        rows = rows.annotate(**computed)
    values = rows.values(*[column.path for column in chosen])[: limit + 1]
    produced = list(values)
    return {
        "columns": [{"name": c.name, "label": c.label} for c in chosen],
        "rows": [{column.name: row[column.path] for column in chosen} for row in produced[:limit]],
        "truncated": len(produced) > limit,
        "grouped": False,
    }
