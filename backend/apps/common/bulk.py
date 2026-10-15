"""One action across many rows: "resend these 14 invitations", "move all
matching to Pune".

Every bulk endpoint takes the same two shapes of target and answers in the
same shape, so a list screen wires its selection bar once:

* ``{"ids": [...]}`` — the rows somebody ticked, or
* ``{"filters": {...}}`` — "every row this filter matches", the list's own
  FilterSet and search applied to the caller's visible set, exactly as the
  screen did.

Either way the rows are resolved out of a queryset the caller may already see,
so an id outside it is skipped as "not found", never acted on. Each row then
goes through the same service the single-row screen uses, one at a time, so
every rule and every audit entry still applies; a row a rule refuses is
reported back with the reason in words, and the rest carry on. The answer says
how many were done and which were skipped and why — never a bare "OK" over a
partial result.

Bounded (`MAX_BULK_TARGETS`): past that, a filter is too broad to act on
blindly, and the caller is told to narrow it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils.module_loading import import_string
from rest_framework import serializers

from apps.common.exceptions import ApplicationError
from apps.common.serializers import StrictSerializer

#: The most rows one bulk request may touch.
MAX_BULK_TARGETS = 500


class BulkTargetSerializer(StrictSerializer):
    """The target half of every bulk request; actions add their own fields."""

    ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=MAX_BULK_TARGETS
    )
    filters = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)

    def validate(self, attrs):
        has_ids = bool(attrs.get("ids"))
        has_filters = "filters" in attrs
        if has_ids == has_filters:
            raise serializers.ValidationError(
                {"ids": ["Choose the rows, or apply the action to every row the filter matches."]}
            )
        return attrs


class BulkSkipSerializer(StrictSerializer):
    id = serializers.CharField()
    label = serializers.CharField()
    reason = serializers.CharField()


class BulkResultSerializer(StrictSerializer):
    """What happened: how many rows were acted on, and why the others were not."""

    action = serializers.CharField()
    total = serializers.IntegerField()
    done = serializers.IntegerField()
    skipped = BulkSkipSerializer(many=True)


@dataclass
class BulkResult:
    action: str
    total: int = 0
    done: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)

    def skip(self, row_id: Any, label: str, reason: str) -> None:
        self.skipped.append({"id": str(row_id), "label": label, "reason": reason})


def message_of(error: Exception) -> str:
    """The first human sentence inside an `ApplicationError`'s detail."""
    detail: Any = getattr(error, "detail", None) or str(error)
    while isinstance(detail, dict | list):
        if not detail:
            return "This row could not be changed."
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail)


def resolve_targets(
    visible: QuerySet,
    target: dict[str, Any],
    *,
    filterset: str,
    search_fields: Iterable[str],
) -> tuple[list[Any], list[str]]:
    """The rows to act on, and the ticked ids that named nothing visible.

    `visible` is the caller's whole reachable set; ticked ids outside it come
    back in the second list so they are reported, not silently dropped.
    """
    if target.get("ids"):
        wanted = [str(value) for value in dict.fromkeys(target["ids"])]
        rows = list(visible.filter(pk__in=wanted))
        found = {str(row.pk) for row in rows}
        return rows, [value for value in wanted if value not in found]

    filters = dict(target.get("filters") or {})
    search = filters.pop("search", "")
    rows = visible
    if any(value not in (None, "") for value in filters.values()):
        data = {key: value for key, value in filters.items() if value not in (None, "")}
        filtered = import_string(filterset)(data=data, queryset=rows)
        if not filtered.is_valid():
            raise ApplicationError({"filters": ["One of the filters is not valid."]})
        rows = filtered.qs
    # The list's own search: every term must match one of its fields.
    for term in str(search).split():
        match = Q()
        for name in search_fields:
            match |= Q(**{f"{name}__icontains": term})
        rows = rows.filter(match)
    rows = rows.distinct()
    count = rows.count()
    if count > MAX_BULK_TARGETS:
        raise ApplicationError(
            {
                "filters": [
                    f"That filter matches {count:,} rows; at most {MAX_BULK_TARGETS:,} can be "
                    "changed at once. Narrow it and try again."
                ]
            }
        )
    return list(rows), []


def apply_each(
    result: BulkResult,
    rows: Iterable[Any],
    missing: Iterable[str],
    act: Callable[[Any], str | None],
    label: Callable[[Any], str],
) -> BulkResult:
    """Run `act` on every row; a returned string is a reason to skip it.

    A domain refusal (`ApplicationError`) skips that row with its own message
    and the rest carry on. Anything else is a fault and propagates.
    """
    for row_id in missing:
        result.total += 1
        result.skip(row_id, "", "Not found, or not yours to change.")
    for row in rows:
        result.total += 1
        try:
            # A savepoint per row: a refusal half-way through one row leaves
            # nothing of it behind, and never undoes the rows before it.
            with transaction.atomic():
                reason = act(row)
        except ApplicationError as error:
            reason = message_of(error)
        if reason:
            result.skip(row.pk, label(row), reason)
        else:
            result.done += 1
    return result
