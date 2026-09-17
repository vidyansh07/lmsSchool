"""The WhatsApp provider abstraction (ERP Phase 19, ADR-12).

`NullWhatsAppProvider` is the default and the deliberate scope boundary the
plan names for this phase: it never calls out to anything and always
returns a "not configured" result, so a `Delivery` created on a system with
no WhatsApp integration fails cleanly and legibly rather than hanging or
pretending to succeed.

`MetaCloudWhatsAppProvider` is the real integration, active only once both
`WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` are configured —
`get_provider` gates on their presence the same way
`config.settings.hardened.configure_error_reporting` gates on `SENTRY_DSN`,
so an unconfigured deployment never fails at import time or at request time.

Only the standard library talks HTTP here (`urllib.request`) rather than a
new third-party dependency, matching the "reuse, don't add a dependency"
discipline the rendering module's sanitiser reuse already follows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger("grras.communication")

_TIMEOUT_SECONDS = 10
_ERROR_MAX = 500


@dataclass(frozen=True)
class WhatsAppSendResult:
    ok: bool
    provider_message_id: str = ""
    error: str = ""


class WhatsAppProvider:
    """One method: attempt to send one message, return the outcome.

    Never raises — a provider outage is a failed `Delivery`, never a failed
    Celery task (ADR-17: "a failed action is a failed run, never a failed
    request", the same discipline this phase's own send path follows).
    """

    def send(
        self, *, to: str, template_version: Any, variables: dict[str, Any], rendered: dict[str, Any]
    ) -> WhatsAppSendResult:
        raise NotImplementedError


class NullWhatsAppProvider(WhatsAppProvider):
    """The default. Always skips, cleanly, with a reason a `Delivery`'s
    `error` column can show as-is."""

    def send(self, *, to, template_version, variables, rendered) -> WhatsAppSendResult:
        return WhatsAppSendResult(
            ok=False, error="WhatsApp is not configured for this environment."
        )


class MetaCloudWhatsAppProvider(WhatsAppProvider):
    """The real integration: the Meta Cloud API's `/messages` endpoint.

    A WhatsApp Business template message can only use the provider's own
    pre-approved template (`provider_template_id`) with positional
    parameters — never free text — so this sends the template by name and
    language rather than the rendered HTML/text; `rendered` is accepted for
    a consistent call shape with the Null provider but unused here.
    """

    def __init__(self, *, access_token: str, phone_number_id: str, api_base_url: str) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._api_base_url = api_base_url.rstrip("/")

    def send(self, *, to, template_version, variables, rendered) -> WhatsAppSendResult:
        from apps.common.logging import scrub

        template_name = (
            getattr(template_version, "provider_template_id", "") or template_version.template.key
        )
        language = template_version.template.language or "en"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language}},
        }
        url = f"{self._api_base_url}/{self._phone_number_id}/messages"
        if not url.startswith("https://"):
            # `WHATSAPP_API_BASE_URL` is an administrator-configured setting,
            # not caller input, but this is the real mitigation bandit's
            # S310 (below) exists to ask for — refusing any non-`https`
            # scheme before ever calling `urlopen` — so the two `noqa`s
            # after this point are a checked, not a blanket, suppression.
            return WhatsAppSendResult(ok=False, error="WHATSAPP_API_BASE_URL is misconfigured.")
        request = urllib_request.Request(  # noqa: S310
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(  # noqa: S310  # nosec B310 -- https:// enforced above
                request, timeout=_TIMEOUT_SECONDS
            ) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except urllib_error.HTTPError as exc:
            detail = str(scrub({"error": exc.read().decode("utf-8", "replace")}).get("error", ""))
            return WhatsAppSendResult(ok=False, error=detail[:_ERROR_MAX])
        except Exception as exc:  # network error, timeout, malformed response
            detail = str(scrub({"error": str(exc)}).get("error", ""))
            return WhatsAppSendResult(ok=False, error=detail[:_ERROR_MAX])

        message_id = ((body.get("messages") or [{}])[0]).get("id", "")
        return WhatsAppSendResult(ok=True, provider_message_id=message_id)


def get_provider() -> WhatsAppProvider:
    """The configured provider, or the Null one. Never crashes for a missing
    setting — see the module docstring."""
    from django.conf import settings

    access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    if access_token and phone_number_id:
        return MetaCloudWhatsAppProvider(
            access_token=access_token,
            phone_number_id=phone_number_id,
            api_base_url=getattr(
                settings, "WHATSAPP_API_BASE_URL", "https://graph.facebook.com/v19.0"
            ),
        )
    return NullWhatsAppProvider()
