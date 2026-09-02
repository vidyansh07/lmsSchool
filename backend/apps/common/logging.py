"""Logging filters and formatters.

Two rules drive this module:

1. Every log line carries the request id so a user-visible error can be traced
   without asking the user for anything sensitive.
2. Secrets never reach the log stream, even when a careless caller passes a
   whole payload to ``logger.info``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .request_context import get_request_id

#: Keys whose values are replaced before anything is written or persisted.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password1",
        "password2",
        "new_password",
        "old_password",
        "current_password",
        "token",
        "access",
        "access_token",
        "refresh",
        "refresh_token",
        "secret",
        "secret_key",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "cookie",
        "csrfmiddlewaretoken",
        "session",
        "sessionid",
        "private_key",
        "client_secret",
        "otp",
        "pin",
    }
)

REDACTED = "[redacted]"
_MAX_DEPTH = 6

#: Credentials embedded in free text, e.g. an SMTP driver reporting
#: ``auth failed for password=hunter2``. Scrubbing by key only catches a secret
#: that arrived as a key; this catches one that arrived as a sentence, which is
#: how a third-party error message usually carries it.
_INLINE_SECRET = re.compile(
    r"\b(" + "|".join(sorted(SENSITIVE_KEYS)) + r")\b\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)

#: Anything shaped like a bearer credential, whatever it is called.
_BEARER = re.compile(r"\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)


def scrub_text(text: str) -> str:
    """Redact credentials embedded in a free-text string.

    Used on anything that came from outside — a provider's exception message, a
    driver's diagnostic — before it is logged or stored.
    """
    if not text:
        return text
    # Bearer first: `Authorization: Bearer <token>` otherwise matches the
    # key rule on "Authorization" and leaves the token itself in the string.
    redacted = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    return _INLINE_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", redacted)


def scrub(value: Any, _depth: int = 0) -> Any:
    """Recursively replace sensitive values in a structure.

    Depth-limited so a hostile or cyclic payload cannot exhaust the stack.
    """
    if _depth >= _MAX_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS
                else scrub(item, _depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [scrub(item, _depth + 1) for item in value]
    if isinstance(value, str):
        # A value that is not under a sensitive key can still *contain* a
        # secret. This is the case that a key-based scrubber misses.
        return scrub_text(value)
    return value


class RequestIDFilter(logging.Filter):
    """Attach the current request id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


class RedactSecretsFilter(logging.Filter):
    """Scrub structured extras attached to a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            record.context = scrub(context)
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line, for log aggregation in deployed environments."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = scrub(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
