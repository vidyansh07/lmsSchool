"""Application caching, in one place (20a).

Two shapes, and only two:

* **Per-person, short-lived.** A dashboard or an overview costs a dozen
  queries and is opened on every page load. `remember()` holds the computed
  value for a minute under a key that names the person, so two loads in a
  row cost one computation and nobody ever sees somebody else's figures.

* **Institution-wide, until changed.** Branding and the public settings are
  the same for everyone and change a few times a year. `remember()` with a
  long TTL, and `forget()` from the service that writes them, so the cache
  never outlives the truth by more than the write itself.

Keys are namespaced by a version number per prefix; `forget(prefix)` bumps
the version instead of hunting for keys, which works on every backend.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.core.cache import cache

MINUTE = 60
DAY = 24 * 60 * 60

_VERSION_TTL = 30 * DAY


def _version(prefix: str) -> int:
    key = f"cachever:{prefix}"
    found = cache.get(key)
    if found is None:
        cache.set(key, 1, _VERSION_TTL)
        return 1
    return int(found)


def key_for(prefix: str, *parts: Any) -> str:
    return f"{prefix}:v{_version(prefix)}:" + ":".join(str(part) for part in parts)


def remember(prefix: str, parts: tuple[Any, ...], ttl: int, compute: Callable[[], Any]) -> Any:
    """The cached value under `prefix`+`parts`, computing and storing it if absent."""
    key = key_for(prefix, *parts)
    found = cache.get(key)
    if found is not None:
        return found
    value = compute()
    cache.set(key, value, ttl)
    return value


def forget(prefix: str) -> None:
    """Invalidate every key under `prefix` by moving to the next version."""
    key = f"cachever:{prefix}"
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, _VERSION_TTL)
