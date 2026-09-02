"""Secret redaction in logs."""

from __future__ import annotations

import logging

from apps.common.logging import REDACTED, JSONFormatter, RedactSecretsFilter, scrub


def test_scrub_redacts_known_sensitive_keys():
    scrubbed = scrub({"password": "hunter2", "email": "a@b.test", "AUTHORIZATION": "Bearer x"})
    assert scrubbed["password"] == REDACTED
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
