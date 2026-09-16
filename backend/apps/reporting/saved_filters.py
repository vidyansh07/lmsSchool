"""Saved filter business rules (ERP Phase 11).

Kept out of `views.py` per the standing rule (business logic lives in a
services module, not a view) even though this app spreads its own logic
across several purpose-named files (`exports.py`, `importers.py`, …) rather
than one `services.py` — this one is small enough to earn its own.
"""

from __future__ import annotations

from django.db import transaction

from apps.audit.services import AuditAction, record

from .models import SavedFilter


def visible_saved_filters(user, *, screen: str | None = None):
    """Every saved filter this caller may see — which is only ever their own.

    Not a `visible_*` capability tier: a saved filter is personal data, so
    "scope" is `user=request.user` and nothing else, for every role
    including an administrator.
    """
    qs = SavedFilter.objects.filter(user=user)
    if screen:
        qs = qs.filter(screen=screen)
    return qs


@transaction.atomic
def save_filter(*, user, screen: str, name: str, filters: dict) -> SavedFilter:
    """Create or replace the caller's own `(screen, name)` preset.

    Upsert, not a hard duplicate-name error: `API_CONTRACTS.md` gives this
    endpoint one terse line ("`POST` … per user") and no explicit conflict
    rule, and a saved filter is a personal, disposable preset a person
    names themselves — re-saving "My batch" with today's tweaked filters is
    the ordinary way someone expects a named preset to behave (the same way
    a browser's saved search or a spreadsheet's named view updates in place),
    not a 409 telling them to delete the old one first. The unique
    constraint on `(user, screen, name)` is what makes this safe to express
    as `update_or_create` rather than a check-then-act race.
    """
    row, created = SavedFilter.objects.update_or_create(
        user=user, screen=screen, name=name, defaults={"filters": filters}
    )
    record(
        action=AuditAction.SAVED_FILTER_CREATED,
        actor=user,
        resource_type="saved_filter",
        resource_id=row.pk,
        context={"screen": screen, "replaced_existing": not created},
        durable=False,
    )
    return row


@transaction.atomic
def delete_saved_filter(*, user, saved_filter: SavedFilter) -> None:
    resource_id = saved_filter.pk
    screen = saved_filter.screen
    saved_filter.delete()
    record(
        action=AuditAction.SAVED_FILTER_DELETED,
        actor=user,
        resource_type="saved_filter",
        resource_id=resource_id,
        context={"screen": screen},
        durable=False,
    )
