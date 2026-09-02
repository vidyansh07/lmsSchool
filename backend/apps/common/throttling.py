"""Rate limiting.

Architecture, not a single rule: throttle *scopes* are declared here and
attached per view, with the rates configured through environment variables so
each environment can be tuned without a code change.

Counters live in the Django cache. Local development uses in-process memory;
staging and production require a shared cache (enforced in
``config.settings.hardened``) because per-worker counters would multiply the
effective limit by the number of workers.
"""

from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class AuthEndpointThrottle(ScopedRateThrottle):
    """Applied to credential-checking endpoints (scope: ``auth``).

    Keyed on the client IP for anonymous callers so credential stuffing is
    limited per source rather than per submitted username.
    """

    scope = "auth"

    def get_cache_key(self, request, view):
        self.scope = getattr(view, "throttle_scope", self.scope)
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class BurstThrottle(SimpleRateThrottle):
    """The expensive endpoints: exports, bulk imports, import confirmation.

    Keyed on the caller rather than the source address, because these all
    require authentication and the cost is attributable to an account.

    The limit exists because these are the endpoints where one request is worth
    hundreds: an export walks every visible row, and an import parses and then
    writes a spreadsheet. The ordinary user limit — hundreds a minute — is far
    too generous for work like that, and a signed-in account with a script is
    all it takes to find out.
    """

    scope = "burst"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
