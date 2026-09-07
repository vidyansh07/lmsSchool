"""Branding services."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record

from .models import BrandingSetting


@transaction.atomic
def update_branding(*, actor: User, **fields: Any) -> BrandingSetting:
    """Change how the institution's interface looks.

    Audited like any other configuration change. It is tempting to treat a
    colour as too trivial to record, but this is a setting that changes what
    every user sees on every screen, and "when did the app turn blue and who did
    it" is a question somebody eventually asks.
    """
    branding = BrandingSetting.current()

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(branding, field) != value:
            setattr(branding, field, value)
            changed.append(field)

    if not changed:
        return branding

    branding.updated_by = actor
    branding.full_clean(exclude=["updated_by"])
    branding.save(update_fields=[*changed, "updated_by", "updated_at"])

    record(
        action=AuditAction.BRANDING_UPDATED,
        actor=actor,
        resource_type="branding",
        resource_id=branding.pk,
        context={"changed_fields": sorted(changed), "brand_color": branding.brand_color or None},
    )
    return branding
