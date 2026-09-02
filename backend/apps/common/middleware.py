"""Request-scoped middleware."""

from __future__ import annotations

import re
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from .request_context import (
    get_request_id,
    new_request_id,
    reset,
    set_request_id,
    set_request_meta,
    take_deferred_audits,
)

#: Only accept a caller-supplied id that looks like one, so the value can be
#: safely echoed into headers and logs (no header injection, no log forging).
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_UA_MAX_LENGTH = 512


class RequestIDMiddleware:
    """Assign a request id and capture non-sensitive request metadata.

    The id is echoed in ``X-Request-ID`` and included in error responses so a
    user can quote it in a support ticket without revealing anything private.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else new_request_id()
        set_request_id(request_id)
        request.request_id = request_id
        set_request_meta(
            {
                "ip_address": client_ip(request),
                "user_agent": request.headers.get("User-Agent", "")[:_UA_MAX_LENGTH],
                "method": request.method,
                "path": request.path,
            }
        )
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            # Runs outside the ATOMIC_REQUESTS transaction, so audit entries
            # recorded during a failed request survive its rollback.
            self._flush_audit_queue()
            reset()

    @staticmethod
    def _flush_audit_queue() -> None:
        entries = take_deferred_audits()
        if not entries:
            return
        # Imported lazily: this middleware loads before the app registry is
        # ready, and the audit app imports models.
        from apps.audit.services import flush_deferred

        flush_deferred(entries)


class SecurityHeadersMiddleware:
    """Add the response headers Django does not set on its own.

    Django covers nosniff, referrer policy, HSTS and frame options through
    settings; Content-Security-Policy and Permissions-Policy are added here.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.csp = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        self.permissions_policy = getattr(settings, "PERMISSIONS_POLICY", "")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if self.csp and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self._policy_for(request)
        if self.permissions_policy and "Permissions-Policy" not in response:
            response["Permissions-Policy"] = self.permissions_policy
        return response

    def _policy_for(self, request: HttpRequest) -> str:
        # Swagger UI is bundled from a CDN by drf-spectacular's template and
        # needs a slightly wider policy. It is the only exception, it is scoped
        # to one path, and the route only exists where API_DOCS_ENABLED is on.
        if request.path.startswith("/api/docs"):
            return (
                "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                "object-src 'none'; img-src 'self' data: https:; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "connect-src 'self'"
            )
        return self.csp


def client_ip(request: HttpRequest) -> str | None:
    """Resolve the client IP, honouring only as many proxies as configured.

    ``NUM_PROXIES`` reflects the real deployment topology. Trusting the whole
    ``X-Forwarded-For`` chain would let a client spoof its own address and
    defeat both rate limiting and audit attribution.
    """
    num_proxies = settings.REST_FRAMEWORK.get("NUM_PROXIES", 0) or 0
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if num_proxies and forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(parts) >= num_proxies:
            return parts[-num_proxies]
        return parts[0] if parts else None
    return request.META.get("REMOTE_ADDR")


def current_request_id() -> str:
    return get_request_id()
