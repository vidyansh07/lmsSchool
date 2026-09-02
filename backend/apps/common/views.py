"""Project-wide error views.

Django's default error pages return HTML. This API is JSON-only, so the
handlers are overridden to emit the same envelope the DRF handler produces.
They never include exception text or configuration details.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from .exceptions import GENERIC_SERVER_ERROR, error_payload


def bad_request(request: HttpRequest, exception=None) -> JsonResponse:
    return JsonResponse(error_payload("bad_request", "Malformed request."), status=400)


def permission_denied(request: HttpRequest, exception=None) -> JsonResponse:
    return JsonResponse(
        error_payload("permission_denied", "You do not have permission to perform this action."),
        status=403,
    )


def not_found(request: HttpRequest, exception=None) -> JsonResponse:
    return JsonResponse(
        error_payload("not_found", "The requested resource was not found."), status=404
    )


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_payload("internal_error", GENERIC_SERVER_ERROR), status=500)


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    """CSRF rejection as JSON.

    ``reason`` is deliberately dropped: it describes server-side token state.
    """
    return JsonResponse(
        error_payload(
            "csrf_failed",
            "CSRF verification failed. Fetch a CSRF token and retry the request.",
        ),
        status=403,
    )
