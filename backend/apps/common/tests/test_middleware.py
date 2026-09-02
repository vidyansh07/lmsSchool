"""Client IP resolution honours the configured proxy depth."""

from __future__ import annotations

from django.test import RequestFactory

from apps.common.middleware import client_ip


def test_forwarded_header_is_ignored_without_a_trusted_proxy(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="10.0.0.1")
    assert client_ip(request) == "10.0.0.1"


def test_forwarded_header_is_used_behind_one_proxy(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    request = RequestFactory().get(
        "/", HTTP_X_FORWARDED_FOR="9.9.9.9, 10.0.0.5", REMOTE_ADDR="10.0.0.1"
    )
    # With one proxy the last entry is the one the proxy itself appended.
    assert client_ip(request) == "10.0.0.5"
