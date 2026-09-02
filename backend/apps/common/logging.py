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
