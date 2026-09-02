"""Uniform API error handling.

Every failure the API returns — validation, auth, throttling, 404, unexpected
crash — uses one envelope so clients need a single parser:

.. code-block:: json

    {
      "error": {
        "code": "validation_error",
        "message": "The submitted data is invalid.",
        "details": {"email": ["Enter a valid email address."]},
        "request_id": "0f3c..."
      }
    }

Internal exception text is never forwarded to the client: unexpected errors
are logged with their traceback and answered with a generic message plus the
request id, so support can find the incident without leaking internals.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .request_context import get_request_id

logger = logging.getLogger("grras.api")

#: Machine-readable codes clients may branch on. Keep this list stable.
ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "authentication_required",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_406_NOT_ACCEPTABLE: "not_acceptable",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}

GENERIC_SERVER_ERROR = "An unexpected error occurred. Quote the request id when reporting it."


class ApplicationError(exceptions.APIException):
    """Base class for domain errors raised by the service layer.

    Service functions raise these; views do not translate them. The message is
    written for the end user, so subclasses must never embed internals.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The request could not be completed."
    default_code = "application_error"


class ConflictError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


def error_payload(
    code: str, message: str, details: Any = None, *, request_id: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id or get_request_id(),
    }
    if details is not None:
        body["details"] = details
    return {"error": body}


def _normalise_detail(detail: Any) -> tuple[str, Any]:
    """Split a DRF detail structure into (message, field details)."""
    if isinstance(detail, dict):
        # DRF wraps single-message errors as {"detail": "..."}. Treating that
        # as field errors would report every 403 as a validation failure.
        if set(detail) == {"detail"}:
            return str(detail["detail"]), None
        return "The submitted data is invalid.", detail
    if isinstance(detail, list):
        first = str(detail[0]) if detail else "Invalid input."
        return first, {"non_field_errors": [str(item) for item in detail]}
    return str(detail), None


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler producing the shared error envelope."""
    # Map framework-level exceptions onto their DRF equivalents first.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception: log with traceback, answer without internals.
        logger.exception(
            "Unhandled API exception",
            extra={"context": {"view": str(context.get("view")), "path": _path(context)}},
        )
        return Response(
            error_payload("internal_error", GENERIC_SERVER_ERROR),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = getattr(exc, "default_code", None) or ERROR_CODES.get(response.status_code, "error")
    message, details = _normalise_detail(response.data)

    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = "The submitted data is invalid."
        details = response.data
    elif isinstance(exc, exceptions.Throttled):
        code = "rate_limited"
        message = "Too many requests. Try again later."
        details = {"retry_after_seconds": exc.wait}
    elif isinstance(exc, exceptions.NotAuthenticated):
        code = "authentication_required"
        message = "Authentication is required."
        details = None
    elif isinstance(exc, exceptions.PermissionDenied):
        code = "permission_denied"
        # DRF's SessionAuthentication runs its own CSRF check before any view
        # code, and reports it as a generic PermissionDenied carrying the
        # server-side reason ("CSRF token missing", "Referer checking failed").
        # Normalise it so one condition always has one code, and so the reason
        # — which describes server state — never reaches the client.
        if str(_first_detail(response.data)).startswith("CSRF Failed"):
            code = "csrf_failed"
            message = "CSRF verification failed. Fetch a CSRF token and retry the request."
            details = None
    elif isinstance(exc, exceptions.AuthenticationFailed):
        # Never distinguish "no such account" from "wrong password".
        code = "authentication_failed"
        message = "Invalid credentials."
        details = None

    if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        message = GENERIC_SERVER_ERROR
        details = None

    logger.warning(
        "API error response",
        extra={
            "context": {
                "status_code": response.status_code,
                "code": code,
                "path": _path(context),
            }
        },
    )
    if response.status_code == status.HTTP_403_FORBIDDEN and code != "csrf_failed":
        _audit_refusal(context, code)
    response.data = error_payload(code, message, details)
    return response


def _audit_refusal(context: dict[str, Any], code: str) -> None:
    """Record an authorization refusal that no view recorded for itself.

    §14.6 asks for auditable authorization events, and before this the only
    refusals on record were the ones views wrote by hand. A refusal produced by
    the permission class — the most common kind, and the one that fires when
    somebody probes an endpoint they have no business calling — left no trace at
    all. Someone reading the audit log to answer "did anyone try?" would have
    seen nothing and concluded nobody did.

    CSRF failures are excluded: they are a browser-integration fault, not an
    attempt to exceed authority, and they would drown the signal.

    Never raises. An audit failure must not turn a 403 into a 500.
    """
    from apps.common.request_context import denial_already_recorded

    if denial_already_recorded():
        return
    try:
        from apps.audit.models import AuditAction, AuditResult
        from apps.audit.services import record

        request = context.get("request")
        view = context.get("view")
        record(
            action=AuditAction.PERMISSION_DENIED,
            actor=getattr(request, "user", None),
            result=AuditResult.DENIED,
            resource_type=type(view).__name__ if view is not None else "",
            context={"code": code, "method": getattr(request, "method", "")},
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not record an authorization refusal")


def _first_detail(data: Any) -> Any:
    """Best-effort extraction of the primary message from a DRF error body."""
    if isinstance(data, dict):
        return data.get("detail", "")
    if isinstance(data, list) and data:
        return data[0]
    return data


def _path(context: dict[str, Any]) -> str:
    request = context.get("request")
    return getattr(request, "path", "") if request is not None else ""
