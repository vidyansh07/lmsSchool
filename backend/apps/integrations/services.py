"""Integrations: API keys and the lead endpoint (in), webhooks (out).

Everything that changes a key or a webhook needs `integration.manage` and is
audited. The lead endpoint itself is authenticated by the key alone — there
is no user behind a website's form post — so what a key may do is narrow on
purpose: create an enquiry, or update the open one with the same mobile (or
the same external id) at its own centre. It cannot read anything back.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError

from . import crypto
from .models import ApiKey, IntakeStatus, LeadIntake, Preset, Webhook, WebhookDelivery
from .presets import LEAD_FIELDS, MERITTO_LEAD_KEYS, WEBHOOK_HEADERS
from .security import check_url

logger = logging.getLogger("grras.integrations")

KEY_PREFIX = "grk_"
_PAYLOAD_KEEP_BYTES = 4000
_TIMEOUT_SECONDS = 10
_EXCERPT = 500


def _require(actor) -> None:
    if not has_capability(actor, Capability.INTEGRATION_MANAGE):
        raise AuthorityError("You do not have permission to manage integrations.")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


@transaction.atomic
def create_api_key(
    *,
    actor,
    name: str,
    preset: str = Preset.GENERIC,
    branch=None,
    default_source: str = "website",
    field_map: dict[str, str] | None = None,
) -> tuple[ApiKey, str]:
    """A new key, and the key itself — returned this once and never again."""
    _require(actor)
    if preset not in Preset.values:
        raise ApplicationError({"preset": [f"Unknown preset: {preset!r}."]})
    _check_field_map(field_map or {})
    prefix = secrets.token_hex(4)
    while ApiKey.objects.filter(prefix=prefix).exists():  # 1 in 4 billion, but cheap
        prefix = secrets.token_hex(4)
    plaintext = f"{KEY_PREFIX}{prefix}_{secrets.token_urlsafe(32)}"
    key = ApiKey.objects.create(
        name=name.strip(),
        preset=preset,
        prefix=prefix,
        key_hash=_hash(plaintext),
        branch=branch,
        default_source=default_source or "website",
        field_map=field_map or {},
        created_by=actor,
    )
    record(
        action=AuditAction.INTEGRATION_KEY_CREATED,
        actor=actor,
        resource_type="integrations.apikey",
        resource_id=key.pk,
        context={"name": key.name, "prefix": prefix, "preset": preset},
    )
    return key, plaintext


@transaction.atomic
def update_api_key(*, actor, key: ApiKey, **fields: Any) -> ApiKey:
    _require(actor)
    if "field_map" in fields:
        _check_field_map(fields["field_map"] or {})
    changed = []
    for name in ("name", "branch", "default_source", "field_map"):
        if name in fields and getattr(key, name) != fields[name]:
            setattr(key, name, fields[name])
            changed.append(name)
    if changed:
        key.save()
        record(
            action=AuditAction.INTEGRATION_KEY_UPDATED,
            actor=actor,
            resource_type="integrations.apikey",
            resource_id=key.pk,
            context={"fields": changed},
        )
    return key


@transaction.atomic
def revoke_api_key(*, actor, key: ApiKey) -> ApiKey:
    _require(actor)
    if key.revoked_at is None:
        key.revoked_at = timezone.now()
        key.revoked_by = actor
        key.save(update_fields=["revoked_at", "revoked_by", "updated_at"])
        record(
            action=AuditAction.INTEGRATION_KEY_REVOKED,
            actor=actor,
            resource_type="integrations.apikey",
            resource_id=key.pk,
            context={"name": key.name, "prefix": key.prefix},
        )
    return key


def _check_field_map(field_map: dict) -> None:
    from apps.enquiries.services import ANSWER_FIELDS

    if not isinstance(field_map, dict):
        raise ApplicationError({"field_map": ["Send an object of payload field to enquiry field."]})
    allowed = set(ANSWER_FIELDS) | {"external_id"}
    wrong = sorted(str(target) for target in field_map.values() if str(target) not in allowed)
    if wrong:
        raise ApplicationError({"field_map": [f"Not an enquiry field: {', '.join(wrong)}."]})


def authenticate(header_value: str) -> ApiKey | None:
    """The live key a request's `Authorization: Bearer grk_…` (or
    `X-Api-Key`) names, or None. Constant-time on the hash."""
    token = (header_value or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token.startswith(KEY_PREFIX):
        return None
    prefix = token[len(KEY_PREFIX) :].split("_", 1)[0]
    key = ApiKey.objects.select_related("branch").filter(prefix=prefix).first()
    if key is None or key.revoked_at is not None:
        return None
    if not hmac.compare_digest(key.key_hash, _hash(token)):
        return None
    return key


# ---------------------------------------------------------------------------
# Receiving a lead
# ---------------------------------------------------------------------------


def _trimmed(payload: dict) -> dict:
    from apps.common.logging import scrub

    cleaned = scrub(payload) if isinstance(payload, dict) else {}
    text = json.dumps(cleaned, default=str)
    if len(text) <= _PAYLOAD_KEEP_BYTES:
        return cleaned
    return {"_truncated": text[:_PAYLOAD_KEEP_BYTES]}


def map_lead(key: ApiKey, payload: dict) -> tuple[dict[str, Any], str]:
    """The enquiry answers a payload carries, and its external id."""
    from apps.enquiries.models import SOURCE_CHOICES, Enquiry

    mapping = {**LEAD_FIELDS.get(key.preset, LEAD_FIELDS[Preset.GENERIC]), **(key.field_map or {})}
    values: dict[str, Any] = {}
    external_id = ""
    for name, raw in payload.items():
        target = mapping.get(name)
        if target is None or raw in (None, "") or isinstance(raw, (dict, list)):
            continue
        text = str(raw).strip()
        if target == "external_id":
            external_id = text[:100]
            continue
        if target in values:
            continue
        model_field = "stage" if target == "lead_stage" else target
        try:
            limit = Enquiry._meta.get_field(model_field).max_length
        except Exception:
            limit = None
        values[target] = text[:limit] if limit else text

    known_sources = {value for value, _label in SOURCE_CHOICES}
    source = values.get("source", "")
    if source not in known_sources:
        if source:
            note = f"Source given: {source}"
            values["remarks"] = f"{values['remarks']}\n{note}" if values.get("remarks") else note
        values["source"] = key.default_source if key.default_source in known_sources else "other"
    # A lead from outside never sets its own stage or owner here.
    for name in ("stage", "lead_stage", "lost_reason", "next_follow_up"):
        values.pop(name, None)
    return values, external_id


def receive_lead(*, key: ApiKey, payload: Any) -> LeadIntake:
    """Create or update an enquiry from one posted lead. Never raises for a
    bad lead: the refusal is the `LeadIntake` row the caller turns into a 400."""
    from apps.enquiries import services as enquiries
    from apps.enquiries.models import CLOSED_STAGES, Enquiry

    ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
    if not isinstance(payload, dict):
        return LeadIntake.objects.create(
            api_key=key,
            status=IntakeStatus.REJECTED,
            errors={"non_field_errors": ["Send one lead as a JSON object."]},
        )
    values, external_id = map_lead(key, payload)
    kept = _trimmed(payload)
    system = key.preset if key.preset != Preset.GENERIC else f"key:{key.prefix}"
    try:
        with transaction.atomic():
            existing = None
            if external_id:
                existing = (
                    Enquiry.objects.select_for_update()
                    .filter(branch=key.branch, external_system=system, external_id=external_id)
                    .exclude(stage__in=list(CLOSED_STAGES))
                    .first()
                )
            if existing is not None:
                fields = {
                    name: value
                    for name, value in enquiries.answers_to_fields(values).items()
                    if name in enquiries.EDITABLE_FIELDS
                }
                enquiry, _changed, _previous = enquiries.update(
                    actor=None, enquiry=existing, fields=fields
                )
                created = False
            else:
                enquiry, created = enquiries.capture(actor=None, values=values, branch=key.branch)
            if external_id and not enquiry.external_id:
                Enquiry.objects.filter(pk=enquiry.pk).update(
                    external_system=system, external_id=external_id
                )
            return LeadIntake.objects.create(
                api_key=key,
                status=IntakeStatus.CREATED if created else IntakeStatus.UPDATED,
                enquiry=enquiry,
                external_id=external_id,
                payload=kept,
            )
    except ApplicationError as exc:
        return LeadIntake.objects.create(
            api_key=key,
            status=IntakeStatus.REJECTED,
            external_id=external_id,
            payload=kept,
            errors=exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": [str(exc)]},
        )


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


@transaction.atomic
def save_webhook(
    *,
    actor,
    webhook: Webhook | None = None,
    name: str | None = None,
    url: str | None = None,
    preset: str | None = None,
    headers: dict[str, str] | None = None,
    is_active: bool | None = None,
    rotate_secret: bool = False,
) -> tuple[Webhook, str]:
    """Create or change a webhook. Returns the webhook and its signing secret
    when one was just made (on creation, or `rotate_secret`), else ``""``."""
    _require(actor)
    creating = webhook is None
    webhook = webhook or Webhook(created_by=actor, preset=preset or Preset.GENERIC)
    if preset is not None:
        if preset not in Preset.values:
            raise ApplicationError({"preset": [f"Unknown preset: {preset!r}."]})
        webhook.preset = preset
    if name is not None:
        webhook.name = name.strip()
    if url is not None:
        check_url(url.strip())
        webhook.url = url.strip()
    if creating and (not webhook.name or not webhook.url):
        raise ApplicationError({"non_field_errors": ["A webhook needs a name and an address."]})
    if headers is not None:
        cleaned = {str(k).strip(): str(v) for k, v in headers.items() if str(k).strip()}
        bad = [name for name in cleaned if not _header_name_ok(name)]
        if bad:
            raise ApplicationError({"headers": [f"Not a header name: {', '.join(bad)}."]})
        webhook.headers_encrypted = crypto.encrypt_json(cleaned)
        webhook.header_names = sorted(cleaned)
    if is_active is not None:
        webhook.is_active = is_active
    secret = ""
    if creating or rotate_secret:
        secret = secrets.token_urlsafe(32)
        webhook.secret_encrypted = crypto.encrypt(secret)
    webhook.full_clean()
    webhook.save()
    record(
        action=AuditAction.INTEGRATION_WEBHOOK_SAVED,
        actor=actor,
        resource_type="integrations.webhook",
        resource_id=webhook.pk,
        context={
            "name": webhook.name,
            "created": creating,
            "rotated_secret": bool(secret) and not creating,
            "header_names": webhook.header_names,
        },
    )
    return webhook, secret


def _header_name_ok(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9-]{1,64}", name)) and name.lower() not in {
        "host",
        "content-length",
        "content-type",
        "x-grras-signature",
        "x-grras-event",
    }


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def webhook_body(webhook: Webhook, *, event: str, data: dict[str, Any], rule=None) -> dict:
    """What is posted. The generic preset sends the automation context as it
    is; the Meritto preset flattens an enquiry to Meritto's lead fields."""
    body: dict[str, Any] = {
        "event": event,
        "occurred_at": timezone.now().isoformat(),
        "rule": rule.name if rule is not None else None,
        "data": data,
    }
    if webhook.preset == Preset.MERITTO and isinstance(data.get("enquiry"), dict):
        enquiry = data["enquiry"]
        body = {
            meritto: enquiry.get(ours)
            for ours, meritto in MERITTO_LEAD_KEYS.items()
            if enquiry.get(ours) not in (None, "")
        }
        body["grras_enquiry_id"] = enquiry.get("id")
        body["grras_event"] = event
    return body


def deliver(*, webhook: Webhook, event: str, data: dict[str, Any], rule=None) -> WebhookDelivery:
    """Post one event to a webhook and log the outcome. Never raises."""
    from apps.common.logging import scrub

    started = time.monotonic()
    delivery = WebhookDelivery(webhook=webhook, event=event[:60], rule=rule)
    try:
        if not webhook.is_active:
            raise ApplicationError({"non_field_errors": ["This webhook is switched off."]})
        check_url(webhook.url)
        body = json.dumps(webhook_body(webhook, event=event, data=data, rule=rule), default=str)
        raw = body.encode("utf-8")
        headers = {
            **crypto.decrypt_json(webhook.headers_encrypted),
            "Content-Type": "application/json",
            "User-Agent": "Grras-LMS-Webhook/1",
            "X-Grras-Event": event,
            "X-Grras-Signature": signature(crypto.decrypt(webhook.secret_encrypted), raw),
        }
        request = urllib_request.Request(  # noqa: S310 -- https enforced by check_url
            webhook.url, data=raw, headers=headers, method="POST"
        )
        try:
            with urllib_request.urlopen(  # noqa: S310  # nosec B310 -- https enforced
                request, timeout=_TIMEOUT_SECONDS
            ) as response:
                delivery.status_code = response.status
                delivery.response_excerpt = response.read(_EXCERPT).decode("utf-8", "replace")
                delivery.ok = 200 <= response.status < 300
        except urllib_error.HTTPError as exc:
            delivery.status_code = exc.code
            delivery.response_excerpt = exc.read(_EXCERPT).decode("utf-8", "replace")
            delivery.error = f"The receiver answered {exc.code}."
    except ApplicationError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        messages = [message for values in detail.values() for message in values] or [str(exc)]
        delivery.error = "; ".join(str(m) for m in messages)[:_EXCERPT]
    except Exception as exc:
        delivery.error = str(scrub({"error": str(exc)}).get("error", ""))[:_EXCERPT]
    delivery.duration_ms = int((time.monotonic() - started) * 1000)
    delivery.response_excerpt = delivery.response_excerpt[:_EXCERPT]
    delivery.save()
    return delivery


def send_test(*, actor, webhook: Webhook) -> WebhookDelivery:
    _require(actor)
    return deliver(
        webhook=webhook,
        event="test",
        data={"message": "A test from Grras LMS.", "sent_by": getattr(actor, "email", "")},
    )


__all__ = [
    "WEBHOOK_HEADERS",
    "authenticate",
    "create_api_key",
    "deliver",
    "map_lead",
    "receive_lead",
    "revoke_api_key",
    "save_webhook",
    "send_test",
    "signature",
    "update_api_key",
]
