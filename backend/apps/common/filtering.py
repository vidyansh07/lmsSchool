"""Letting a person ask a list a question of their own.

Every list screen in this product shipped a handful of fixed filters: a status
dropdown, a city box, whatever the screen was first built for. That answers the
questions somebody thought of in advance, and an operations team spends its day
on the ones nobody thought of — "students from any college whose name contains
'Arya', with no enrolment, registered this month".

So a field can now be asked more than one question. `city=Jaipur` still works
exactly as it did; `city__icontains=jai` and `created_at__gte=2026-10-01` work
as well, and nothing else does.

Why an allowlist, and why it is built from the model
----------------------------------------------------
The obvious shape for this is a generic filter endpoint that takes a field name
and a lookup from the request. That hands a caller the ORM: `?f=user__password
__startswith=a` is a password oracle, and `?f=student__referred_by__user__email`
walks relations the caller may not read at all.

So nothing here reads a field name from a request. Each screen declares the
fields it is willing to be asked about, this builds the filters for them, and
django-filter refuses every parameter that is not one of them. A field that is
not declared does not become filterable by being spelled correctly.

Scoping is unaffected and comes first: these narrow a queryset that
`visible_students` and its siblings have already narrowed to the caller's own
centre, so a filter can only ever subtract from what somebody could already
see — never add to it.
"""

from __future__ import annotations

import django_filters
from django.db import models

#: The questions worth asking of each kind of field.
#:
#: Deliberately short. Every lookup here is one an operations person would
#: recognise from a spreadsheet, and the ones left out — `regex`, `search`,
#: `iregex` — are either a denial-of-service waiting to happen on a large table
#: or need an index this database does not have.
OPERATORS: dict[str, tuple[str, ...]] = {
    "text": ("exact", "icontains", "istartswith", "isnull"),
    "choice": ("exact", "in", "isnull"),
    "number": ("exact", "gt", "gte", "lt", "lte", "isnull"),
    "date": ("exact", "gt", "gte", "lt", "lte", "isnull"),
    "boolean": ("exact",),
    "uuid": ("exact", "in", "isnull"),
}

#: How each kind is described to the browser, so one screen's filter bar can be
#: built from the same declaration the server enforces. A client that offers an
#: operator the server does not accept is a button that does nothing.
OPERATOR_LABELS: dict[str, str] = {
    "exact": "is",
    "icontains": "contains",
    "istartswith": "starts with",
    "in": "is one of",
    "isnull": "is empty",
    "gt": "is after",
    "gte": "is on or after",
    "lt": "is before",
    "lte": "is on or before",
}

#: The number comparisons read differently from the date ones.
NUMBER_LABELS: dict[str, str] = {
    "gt": "is more than",
    "gte": "is at least",
    "lt": "is less than",
    "lte": "is at most",
}


class FilterField:
    """One field a screen is willing to be asked about.

    ``path`` is the ORM path, which is not always the public name: a screen
    offers "Account active" and the model stores it on the related user. The
    public name is what a caller sends and what appears in the schema; the path
    never leaves the server.
    """

    def __init__(
        self,
        name: str,
        *,
        kind: str,
        path: str | None = None,
        label: str = "",
        choices: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        if kind not in OPERATORS:
            raise ValueError(f"Unknown filter kind {kind!r}.")
        self.name = name
        self.kind = kind
        self.path = path or name
        self.label = label or name.replace("_", " ").capitalize()
        self.choices = choices

    def operators(self) -> tuple[str, ...]:
        return OPERATORS[self.kind]

    def describe(self) -> dict[str, object]:
        """What the browser needs to build a control for this field."""
        labels = NUMBER_LABELS if self.kind == "number" else {}
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "operators": [
                {
                    "value": operator,
                    "label": labels.get(operator) or OPERATOR_LABELS[operator],
                }
                for operator in self.operators()
            ],
            "choices": (
                [{"value": value, "label": label} for value, label in self.choices]
                if self.choices
                else None
            ),
        }


#: Which django-filter class handles each kind.
_FILTER_CLASSES: dict[str, type[django_filters.Filter]] = {
    "text": django_filters.CharFilter,
    "choice": django_filters.CharFilter,
    "number": django_filters.NumberFilter,
    "date": django_filters.DateFilter,
    "boolean": django_filters.BooleanFilter,
    "uuid": django_filters.UUIDFilter,
}


def build_filters(fields: tuple[FilterField, ...]) -> dict[str, django_filters.Filter]:
    """The declared filters, as django-filter attributes.

    One per field per operator, named `<field>__<operator>` — except `exact`,
    which keeps the bare field name so every URL, saved view and bookmark that
    already exists goes on working untouched.
    """
    built: dict[str, django_filters.Filter] = {}
    for field in fields:
        for operator in field.operators():
            if operator == "isnull":
                # "is empty" is a yes/no question whatever the field holds.
                built[f"{field.name}__isnull"] = django_filters.BooleanFilter(
                    field_name=field.path, lookup_expr="isnull"
                )
                continue
            if operator == "in":
                built[f"{field.name}__in"] = django_filters.BaseInFilter(
                    field_name=field.path, lookup_expr="in"
                )
                continue
            parameter = field.name if operator == "exact" else f"{field.name}__{operator}"
            built[parameter] = _FILTER_CLASSES[field.kind](
                field_name=field.path, lookup_expr=operator
            )
    return built


def filterset_for(
    model: type[models.Model],
    fields: tuple[FilterField, ...],
    *,
    extra: dict[str, django_filters.Filter] | None = None,
) -> type[django_filters.FilterSet]:
    """A FilterSet for ``model`` answering every declared question.

    ``extra`` carries the filters a screen writes by hand — the ones with real
    logic behind them, like "holds no seat on any batch" — which belong with
    their screen rather than in a table of operators.
    """
    attributes: dict[str, object] = build_filters(fields)
    if extra:
        attributes.update(extra)
    attributes["Meta"] = type("Meta", (), {"model": model, "fields": ()})
    return type(f"{model.__name__}GeneratedFilterSet", (django_filters.FilterSet,), attributes)


def describe(fields: tuple[FilterField, ...]) -> list[dict[str, object]]:
    """The whole declaration, for the browser to build a filter bar from."""
    return [field.describe() for field in fields]
