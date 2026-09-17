"""The WhatsApp provider webhook (ERP Phase 19).

The one endpoint in this codebase that is deliberately **not**
session-authenticated: an external provider calls it, not a signed-in user.
Two things make that safe rather than a hole:

1. ``authentication_classes = ()`` — not merely `AllowAnyPublic` on top of
   the default `SessionAuthentication`. Leaving `SessionAuthentication` in
   place would mean a request that happens to carry a *valid* session
   cookie (a staff member's browser, an XHR replay, a misconfigured proxy
   forwarding cookies) gets treated as "signed in as that person" by
   `request.user` even though nothing about this endpoint should ever care
   who, if anyone, is signed in. Removing authentication entirely is what
   the phase's own instruction — "never treated as authenticated by session
   under any circumstance" — actually requires; `AllowAnyPublic` alone does
   not deliver it.
2. Every payload is refused before it touches a single `Delivery` row
   unless it carries a valid signature (`POST`) or verify token (`GET`),
   checked against ``WHATSAPP_APP_SECRET``/``WHATSAPP_WEBHOOK_VERIFY_TOKEN``.
   An unconfigured secret fails every verification closed — there is no
   "accept anything because nothing is configured yet" fallback, unlike the
   Null *provider* (which is a deliberate, harmless no-op for sending).
   Accepting unauthenticated writes because a secret was never set would be
   the opposite of harmless.

Also why this view carries no CSRF check (unlike every other anonymous-POST
endpoint this codebase has, per `AGENT_PLAYBOOK.md`'s `EnforceCSRFMixin`
rule): CSRF defends a browser-driven request that rides on a victim's
cookies. A server-to-server provider callback carries no browser session
and no CSRF cookie at all — enforcing CSRF here would only ever reject the
provider's own genuine calls, never a forged one. The signature check above
*is* this endpoint's real authentication.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import AllowAnyPublic

from . import services

logger = logging.getLogger("grras.communication")


def _verify_signature(raw_body: bytes, header_value: str) -> bool:
    secret = settings.WHATSAPP_APP_SECRET
    if not secret or not header_value.startswith("sha256="):
        return False
    provided = header_value.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


class WhatsAppWebhookView(APIView):
    """`GET` answers the provider's one-time subscription handshake; `POST`
    delivers status callbacks."""

    authentication_classes = ()
    permission_classes = (AllowAnyPublic,)
    serializer_class = None

    @extend_schema(exclude=True)
    def get(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")
        verify_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        if mode == "subscribe" and verify_token and hmac.compare_digest(token, verify_token):
            return HttpResponse(challenge, content_type="text/plain")
        return Response(status=403)

    @extend_schema(exclude=True)
    def post(self, request):
        raw_body = request._request.body
        # signature must be checked over the exact bytes that were signed,
        # never a value DRF has already parsed and could re-serialise
        # differently.
        signature = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        if not _verify_signature(raw_body, signature):
            logger.warning("Rejected an unsigned or invalid WhatsApp webhook call")
            return Response(status=403)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response(status=400)

        updated = 0
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for status_update in value.get("statuses") or []:
                    provider_message_id = status_update.get("id", "")
                    status = status_update.get("status", "")
                    errors = status_update.get("errors") or []
                    error_detail = errors[0].get("title", "") if errors else ""
                    if services.apply_whatsapp_status_update(
                        provider_message_id=provider_message_id,
                        status=status,
                        error=error_detail,
                    ):
                        updated += 1

        return Response({"updated": updated}, status=200)
