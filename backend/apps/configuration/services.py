"""Writing the institution's settings.

One entry point, because a settings change is the one write in this system that
alters what every other screen renders: the name at the foot of an email,
whether email goes out at all, how long an export survives. Every write is
audited, and the row is created on demand rather than by a migration — a
migration that creates a row must be reversed, and it races a second worker on
a multi-worker deploy.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError

from .models import SETTING_FIELDS, SystemSetting
from .settings_resolver import forget_resolved_settings

#: Everything an operator may write. Identical to `SETTING_FIELDS` today, and a
#: separate name because `singleton` and `updated_by` are the service's business
#: and must never become somebody's request body.
WRITABLE_FIELDS = frozenset(SETTING_FIELDS)


def get_or_create_settings() -> SystemSetting:
    """The stored row, created with its defaults if it does not exist yet.

    A row of defaults is the same behaviour as no row at all — the resolver
    answers identically either way — so creating one on first read changes
    nothing about the settings in force.
    """
    settings_row, _created = SystemSetting.objects.get_or_create(singleton=True)
    return settings_row


@transaction.atomic
def update_settings(*, settings_row: SystemSetting, actor: User, **fields: Any) -> SystemSetting:
    """Change the institution's settings. Records which of them moved."""
    unknown = sorted(set(fields) - WRITABLE_FIELDS)
    if unknown:
        raise ApplicationError(
            {field: ["This is not a configurable setting."] for field in unknown}
        )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(settings_row, field) != value:
            setattr(settings_row, field, value)
            changed.append(field)

    if not changed:
        return settings_row

    settings_row.updated_by = actor if getattr(actor, "pk", None) else None
    try:
        settings_row.full_clean(exclude=["updated_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    settings_row.save(update_fields=[*changed, "updated_by", "updated_at"])

    # The memo is per request; drop it so anything serialised later in this same
    # response shows the new value rather than the one read a moment ago.
    forget_resolved_settings()

    record(
        action=AuditAction.SYSTEM_SETTINGS_UPDATED,
        actor=actor,
        resource_type="system_setting",
        resource_id=settings_row.pk,
        # Field names only, never the values — unlike `update_policy`, which
        # records both. An academic threshold is institutional policy; a
        # support phone number and address are somebody's contact details, and
        # `apps.common.logging.scrub` redacts by key name rather than by
        # content, so a `{"from": …, "to": …}` context would persist them
        # verbatim for the life of the audit trail. The names on their own
        # answer who changed what, when.
        context={"fields": sorted(changed)},
        durable=False,
    )
    return settings_row
