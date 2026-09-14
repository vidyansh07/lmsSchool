"""Resolving the institution's settings.

Everything that needs a setting asks :func:`effective_settings`. Nothing reads
:class:`~apps.configuration.models.SystemSetting` directly, so the fallback
order — the stored row, then the code default — exists in exactly one place,
and a caller cannot accidentally save through the answer it got back.

"Unset" is the empty string, never ``NULL``
-------------------------------------------
The text columns are ``blank=True, default=""`` and nothing here treats a value
as missing by truthiness. ``notification_email_enabled=False`` and a numeric
zero are answers an operator gave, and a truthiness test would quietly replace
both with the defaults — which for the mail switch means an operator who turned
notification email off would find it still on.

No cached read path, yet
------------------------
The memo is per request and nothing more. A shared cache would delay an
operator's change by its TTL, and "I changed the support address an hour ago
and the footer still shows the old one" is a support ticket, not a performance
win — the same reasoning as D-032 for the academic policy. The caching
workstream's seam does not exist yet; :func:`_resolve` is the function to
reconsider when it lands, and the branch segment its key rules require applies
here only if this table ever grows a branch, which it deliberately has not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from apps.common.request_context import clear_scope, scoped

from .models import DEFAULT_SETTINGS, SETTING_FIELDS, SystemSetting

#: The request-scope key. Keyed rather than global so dropping the settings memo
#: cannot throw away somebody else's.
_SCOPE_KEY = "system-settings"


@dataclass(frozen=True)
class EffectiveSettings:
    """The settings actually in force, after the stored row and the defaults."""

    institution_name: str
    support_email: str
    support_phone: str
    notification_email_enabled: bool
    export_retention_days: int
    resource_upload_max_mb: int

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in SETTING_FIELDS}


def forget_resolved_settings() -> None:
    """Drop the memo after a write, so the same request sees the new value.

    Keyed, unlike :func:`apps.academics.policies.forget_resolved_policies`,
    which clears the whole scope. That one predates any second consumer of the
    request scope and is the counter-example rather than the model: copying it
    would make a settings write silently discard the academic-policy memo, and
    the request would then pay to resolve it again.
    """
    clear_scope(_SCOPE_KEY)


def effective_settings() -> EffectiveSettings:
    """The institution's settings, resolved once per request.

    Memoised for the life of one request because a page can ask this question
    from several places — the email footer, a serializer, an upload check — and
    the answer cannot change mid-response.
    """
    return scoped(_SCOPE_KEY, _resolve)


def resolve_from(row: SystemSetting | None) -> EffectiveSettings:
    """The fallback order applied to a row the caller already holds.

    Exposed so the settings screen — which reads the row anyway, for its "last
    changed by" line — does not pay for a second read of the same table, and
    does not get a second definition of "in force" in exchange.
    :func:`effective_settings` is this function over a row it fetches itself.
    """
    resolved: dict[str, Any] = {}
    for field in SETTING_FIELDS:
        value = getattr(row, field, None) if row is not None else None
        # Membership, never truthiness: `False` and `0` are configured answers.
        resolved[field] = DEFAULT_SETTINGS[field] if value in (None, "") else value
    return EffectiveSettings(**resolved)


def _resolve() -> EffectiveSettings:
    return resolve_from(SystemSetting.objects.first())


# ---------------------------------------------------------------------------
# Derived answers
# ---------------------------------------------------------------------------
#
# Stored as the unit an operator types and read as the unit the code needs, so
# no consumer repeats the arithmetic and none of them can get it wrong
# separately.


def resource_upload_limit_bytes() -> int:
    """The largest upload accepted right now, in bytes."""
    return effective_settings().resource_upload_max_mb * 1024 * 1024


def export_retention() -> timedelta:
    """How long a finished export stays downloadable."""
    return timedelta(days=effective_settings().export_retention_days)
