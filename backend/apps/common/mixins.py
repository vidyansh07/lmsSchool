"""Reusable view mixins."""

from __future__ import annotations

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied


class CSRFFailed(APIException):
    """CSRF rejection with a stable code and no server-state detail."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "CSRF verification failed. Fetch a CSRF token and retry the request."
    default_code = "csrf_failed"


class EnforceCSRFMixin:
    """Require a valid CSRF token on unsafe methods, even for anonymous callers.

    DRF marks API views ``csrf_exempt`` and defers the check to
    ``SessionAuthentication``, which only runs once a session user is present.
    Endpoints that accept unauthenticated POSTs — login above all — are
    therefore unprotected by default, which allows login CSRF (forcing a victim's
    browser into an attacker-controlled session). This mixin closes that gap.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            try:
                SessionAuthentication().enforce_csrf(request)
            except PermissionDenied as exc:
                raise CSRFFailed() from exc
