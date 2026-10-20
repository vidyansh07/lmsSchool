"""Hand-picked rows for an export: "export these 37", not "export the filter".

A list screen can already export everything its filters match. What it could
not do was export the rows somebody ticked, and the obvious way — the ids in
the export URL — does not survive contact with the server: gunicorn refuses a
request line over 4 KB, which is about a hundred ids, and the CSV download,
the print view and the preflight count are all plain GETs.

So the ids go up once, in a POST body, and come back as a short token that
the GETs carry instead (`?selection=…`). The token is held in the cache for a
little while, and only for the person who made it: somebody else's token is
indistinguishable from an expired one. It names rows, never permission — the
export still resolves the caller's visible set and only narrows it to these
ids, so a token full of ids the caller cannot see exports nothing.
"""

from __future__ import annotations

import secrets
import uuid

from django.core.cache import cache

from apps.common.exceptions import ApplicationError

#: How many rows can be ticked and exported by hand. Past this, "select all
#: matching" and the filter export are the right tool.
MAX_SELECTED = 1000

#: Long enough to choose a format and confirm; short enough that a stale
#: selection is not exported tomorrow by a bookmarked link.
SELECTION_TTL = 30 * 60

_PREFIX = "report-selection"


def _key(user, token: str) -> str:
    return f"{_PREFIX}:{user.pk}:{token}"


def remember_selection(user, ids) -> str:
    """Store `ids` for `user` and return the token that names them."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        try:
            value = str(uuid.UUID(str(raw)))
        except (TypeError, ValueError, AttributeError):
            raise ApplicationError({"ids": ["One of the selected rows is not valid."]}) from None
        if value not in seen:
            seen.add(value)
            cleaned.append(value)
    if not cleaned:
        raise ApplicationError({"ids": ["Select at least one row."]})
    if len(cleaned) > MAX_SELECTED:
        raise ApplicationError(
            {
                "ids": [
                    f"At most {MAX_SELECTED:,} rows can be exported by hand. "
                    "Use the list's filters and export everything they match."
                ]
            }
        )
    token = secrets.token_urlsafe(16)
    cache.set(_key(user, token), cleaned, SELECTION_TTL)
    return token


def recall_selection(user, token: str) -> list[str]:
    """The ids behind `token`, or a 400 saying to select again."""
    found = cache.get(_key(user, str(token)[:64])) if token else None
    if not found:
        raise ApplicationError(
            {"selection": ["This selection has expired. Select the rows again and export."]}
        )
    return list(found)
