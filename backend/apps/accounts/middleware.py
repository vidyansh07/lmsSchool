"""Session activity middleware (ERP Phase 6, ADR-06).

Placed after ``AuthenticationMiddleware`` in ``settings.MIDDLEWARE`` so
``request.user`` and ``request.session`` are already resolved by the time
this runs. Deliberately its own small middleware rather than folded into
``apps.common.middleware.RequestIDMiddleware``: that one runs *before*
sessions and authentication are resolved (it has to, to capture the request
id for the whole chain), so it cannot see ``request.user`` at the point where
it would need to.

Every authenticated request pays one guarded ``UPDATE`` here (see
``apps.accounts.sessions.touch_last_seen``) — a flat, uniform per-request
cost like the session and user reads ``AuthenticationMiddleware`` already
pays, which is why the flat-cost tests in ``tests/test_performance.py`` and
friends account for it as one more fixed query rather than something that
scales. What the guard actually bounds is the *write*: the statement matches
zero rows, and so changes nothing, on every call within five minutes of the
last one that did.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class TouchSessionActivityMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            session_key = getattr(request.session, "session_key", None)
            if session_key:
                from .sessions import touch_last_seen

                touch_last_seen(session_key)
        return response
