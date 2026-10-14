"""Secret redaction in logs."""

from __future__ import annotations

import logging
import sys

from apps.common.logging import (
    REDACTED,
    JSONFormatter,
    RedactingFormatter,
    RedactSecretsFilter,
    scrub,
)


def test_scrub_redacts_known_sensitive_keys():
    scrubbed = scrub(
        {
            "password": "hunter2",
            "confirmPassword": "hunter2",
            "email": "a@b.test",
            "AUTHORIZATION": "Bearer x",
        }
    )
    assert scrubbed["password"] == REDACTED
    assert scrubbed["confirmPassword"] == REDACTED
    assert scrubbed["AUTHORIZATION"] == REDACTED
    assert scrubbed["email"] == "a@b.test"


def test_scrub_walks_nested_structures():
    scrubbed = scrub({"outer": [{"api_key": "k"}, {"safe": 1}]})
    assert scrubbed["outer"][0]["api_key"] == REDACTED
    assert scrubbed["outer"][1]["safe"] == 1


def test_scrub_is_depth_limited():
    payload = current = {}
    for _ in range(20):
        current["nested"] = {}
        current = current["nested"]
    assert scrub(payload) is not None  # terminates rather than recursing forever


def test_json_formatter_redacts_and_includes_request_id():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.context = {"token": "abc", "user": "u@example.test"}
    RedactSecretsFilter().filter(record)
    line = JSONFormatter().format(record)
    assert '"token": "[redacted]"' in line
    assert "abc" not in line
    assert "request_id" in line


def test_json_formatter_redacts_secrets_from_the_message_and_exception():
    try:
        raise ValueError("token=exception-secret")
    except ValueError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            __file__,
            1,
            "password=%s Authorization: Bearer abcdefghijklmnop",
            ("message-secret",),
            exc_info=sys.exc_info(),
        )

    RedactSecretsFilter().filter(record)
    line = JSONFormatter().format(record)

    assert "message-secret" not in line
    assert "abcdefghijklmnop" not in line
    assert "exception-secret" not in line
    assert line.count(REDACTED) >= 3


def test_console_formatter_redacts_message_arguments_and_exception_text():
    try:
        raise RuntimeError("recovery_code=do-not-print")
    except RuntimeError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            __file__,
            1,
            "api_key=%s",
            ("also-do-not-print",),
            exc_info=sys.exc_info(),
        )

    RedactSecretsFilter().filter(record)
    line = RedactingFormatter("%(levelname)s %(message)s").format(record)

    assert "also-do-not-print" not in line
    assert "do-not-print" not in line
    assert REDACTED in line


def test_filter_redacts_a_structured_payload_passed_as_a_message_argument():
    record = logging.LogRecord(
        "t",
        logging.INFO,
        __file__,
        1,
        "payload=%s",
        ({"password": "never-print", "safe": "visible"},),
        None,
    )

    RedactSecretsFilter().filter(record)
    line = RedactingFormatter("%(message)s").format(record)

    assert "never-print" not in line
    assert "visible" in line
    assert REDACTED in line


def test_json_formatter_emits_structured_security_fields():
    record = logging.LogRecord("grras.security", logging.WARNING, __file__, 1, "denied", (), None)
    record.event_type = "authorization.denied"
    record.actor_id = "user-123"
    record.resource_type = "student"
    record.resource_id = "student-456"

    line = JSONFormatter().format(record)

    assert '"event_type": "authorization.denied"' in line
    assert '"actor_id": "user-123"' in line
    assert '"resource_type": "student"' in line
    assert '"resource_id": "student-456"' in line


def test_console_formatter_escapes_log_injection_newlines():
    record = logging.LogRecord(
        "t",
        logging.WARNING,
        __file__,
        1,
        "invalid value\n2026-10-14 ERROR forged.entry",
        (),
        None,
    )

    line = RedactingFormatter("%(levelname)s %(message)s").format(record)

    assert "\n" not in line
    assert r"\n2026-10-14 ERROR forged.entry" in line
