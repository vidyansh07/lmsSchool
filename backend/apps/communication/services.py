"""Communication centre business rules (ERP Phase 19, ADR-12).

Every state change here is audited (rule 5); authorization is checked in
`views.py` (capabilities) before a service is ever called, except for the
one thing a queryset cannot express — the WhatsApp step-up requirement on
`approve_version` — which `views.py` also checks before calling in, per
`AGENT_PLAYBOOK.md`'s pattern for `policies`/`authorization`'s own
critical-setting step-up gates.

Why an OTP send can never appear in `GET /deliveries/`
-------------------------------------------------------
The contract (API_CONTRACTS.md, Phase 19) requires that the delivery log
never expose an OTP send's body or variables. This module took the "exclude
by construction" branch of that either/or, not a serializer-level scrub,
because it is structurally true rather than merely enforced:

A `Delivery` row is created from exactly three places in this codebase —
`create_deliveries` (manual send and the automation `send_email`/
`send_whatsapp` actions both call it) and `test_send`. Every one-time code
this codebase sends — sign-in codes, step-up codes — goes through
`apps.accounts.otp.send_email_code`, which calls
`apps.accounts.emails.send_otp_code_email` directly: a bare `send_mail()`
call with no `EmailMessage` row, no `Notification` row, and certainly no
`Delivery` row (see that module's own docstring for *why* it bypasses the
outbox entirely — the code itself is the credential). There is no code path
by which an OTP send could reach `create_deliveries`, so a `Delivery` whose
`variables` field holds a one-time code cannot exist to begin with, and
`DeliverySerializer` needs no OTP-specific redaction. `test_send.py`'s
`test_deliveries_list_never_carries_an_otp_send` asserts the *structural*
half of this (nothing in `apps.accounts` ever imports this module), since
there is no OTP `Delivery` row to assert the serializer hides.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.caching import MINUTE, forget, remember
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.common.logging import scrub
from apps.notifications.models import NotificationKind

from .models import (
    Delivery,
    DeliveryState,
    MessageChannel,
    MessageTemplate,
    TemplateStatus,
    TemplateVersion,
)
from .providers import get_provider
from .rendering import render_template

logger = logging.getLogger("grras.communication")

#: How many times a failed `Delivery` may be retried through the manual
#: retry endpoint before the UI should stop offering it. Not enforced here
#: (the endpoint's own capability + "failed only" gate is the real limit);
#: kept for `dispatch_delivery`'s attempts bookkeeping, mirroring
#: `apps.notifications.channels.MAX_ATTEMPTS`.
MAX_ATTEMPTS = 4
ERROR_MAX = 500

#: `resolve_published_template`'s cache (PERFORMANCE_PLAN.md: 1 h, scope key
#: `(key, channel)`). The `key`/`channel` pair lives in the *prefix* itself —
#: the same per-key-prefix trick `apps.forms.services._forget_published`
#: uses for `form:published:{slug}` — so `_forget_published` below bumps
#: exactly this one template, never every template's cache.
_PUBLISHED_CACHE_TTL = 60 * MINUTE  # 1 hour


def _published_cache_key(key: str, channel: str) -> str:
    return f"template:published:{key}:{channel}"


def _forget_published(key: str, channel: str) -> None:
    """Invalidate now *and* again on commit — the same double bump
    `apps.authorization.services._forget` uses, for the same reason.
    `publish_version`/`create_draft_version` call this from inside their own
    `@transaction.atomic` block, before the write is durable. Bumping only
    now would leave a window open between this call and the transaction's
    COMMIT in which a concurrent `resolve_published_template()` could
    recompute from the pre-write row and cache that stale answer under the
    *new* version for the full TTL — with no second write left to correct
    it, since the transaction that would fire another `forget()` already
    ran its only one. Registering the same call again via `on_commit`
    closes that window: whatever got cached during it is bumped again the
    moment the write actually lands."""
    published_key = _published_cache_key(key, channel)
    forget(published_key)
    transaction.on_commit(lambda: forget(published_key))


def _require(actor: Any, capability: str) -> None:
    if not has_capability(actor, capability):
        raise AuthorityError("You do not have authority to do that.")


def _store_error(exc: Exception) -> str:
    return str(scrub({"error": str(exc)}).get("error", ""))[:ERROR_MAX]


# ---------------------------------------------------------------------------
# Template CRUD, versioning, approval, publishing
# ---------------------------------------------------------------------------


def create_template(
    *, actor, key: str, name: str, channel: str, kind: str, language: str = "en"
) -> MessageTemplate:
    _require(actor, Capability.TEMPLATE_MANAGE)
    if channel not in MessageChannel.values:
        raise ApplicationError({"channel": [f"Unknown channel: {channel!r}."]})
    if channel == MessageChannel.IN_APP and kind not in NotificationKind.values:
        raise ApplicationError(
            {"kind": ["An in-app template's kind must be a real notification kind."]}
        )
    if not kind:
        raise ApplicationError({"kind": ["A template needs a kind."]})
    if MessageTemplate.objects.filter(key=key).exists():
        raise ConflictError({"key": ["A template with this key already exists."]})

    with transaction.atomic():
        template = MessageTemplate.objects.create(
            key=key,
            name=name,
            channel=channel,
            kind=kind,
            language=language or "en",
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        version = TemplateVersion.objects.create(template=template, number=1)
    record(
        action=AuditAction.TEMPLATE_CREATED,
        actor=actor,
        resource_type="message_template",
        resource_id=template.pk,
        context={"key": key, "channel": channel, "kind": kind},
        durable=False,
    )
    record(
        action=AuditAction.TEMPLATE_VERSION_CREATED,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={"template": str(template.pk), "number": version.number},
        durable=False,
    )
    return template


@transaction.atomic
def create_draft_version(*, actor, template: MessageTemplate) -> TemplateVersion:
    """A new draft on top of whatever is currently published. Refused if an
    unpublished (draft) version already exists — mirrors
    `apps.forms.services.create_draft_version` exactly."""
    _require(actor, Capability.TEMPLATE_MANAGE)
    if TemplateVersion.objects.filter(template=template, published_at__isnull=True).exists():
        raise ConflictError(
            {"non_field_errors": ["A draft version already exists for this template."]}
        )

    next_number = (
        TemplateVersion.objects.filter(template=template)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
        or 0
    ) + 1
    current = template.current_version
    version = TemplateVersion.objects.create(
        template=template,
        number=next_number,
        subject=current.subject if current else "",
        body_html=current.body_html if current else "",
        body_text=current.body_text if current else "",
        variables=list(current.variables) if current else [],
        provider_template_id=current.provider_template_id if current else "",
    )
    if template.status != TemplateStatus.DRAFT:
        # This is the "unpublish" transition for caching purposes: a new
        # draft on top of a published template means `resolve_published_template`
        # must stop answering with the old version from its next call on.
        template.status = TemplateStatus.DRAFT
        template.save(update_fields=["status", "updated_at"])
        _forget_published(template.key, template.channel)
    record(
        action=AuditAction.TEMPLATE_VERSION_CREATED,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={"template": str(template.pk), "number": version.number},
        durable=False,
    )
    return version


@transaction.atomic
def update_draft_version(*, actor, version: TemplateVersion, **fields: Any) -> TemplateVersion:
    """Edit a draft's content. 409 once published — the version's own
    immutability, not a separate lock."""
    _require(actor, Capability.TEMPLATE_MANAGE)
    if version.is_published:
        raise ConflictError({"non_field_errors": ["A published version's content is immutable."]})

    allowed = {"subject", "body_html", "body_text", "variables", "provider_template_id"}
    changed: list[str] = []
    for field, value in fields.items():
        if field not in allowed:
            continue
        if getattr(version, field) != value:
            setattr(version, field, value)
            changed.append(field)

    if not changed:
        return version

    # Editing a version's content invalidates whatever approval it already
    # had — the reviewer signed off on the *previous* text, not this one.
    if version.approved_at is not None:
        version.approved_by = None
        version.approved_at = None
        changed += ["approved_by", "approved_at"]
        if version.template.status != TemplateStatus.DRAFT:
            version.template.status = TemplateStatus.DRAFT
            version.template.save(update_fields=["status", "updated_at"])

    version.save(update_fields=[*dict.fromkeys(changed), "updated_at"])
    record(
        action=AuditAction.TEMPLATE_VERSION_UPDATED,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={
            "template": str(version.template_id),
            "number": version.number,
            "fields": sorted(set(changed)),
        },
        durable=False,
    )
    return version


@transaction.atomic
def approve_version(*, actor, version: TemplateVersion) -> TemplateVersion:
    """Sign off on a draft's content. Capability + (for WhatsApp) a fresh
    step-up are checked in `views.py` before this is called."""
    _require(actor, Capability.TEMPLATE_APPROVE)
    if version.is_published:
        raise ConflictError({"non_field_errors": ["A published version needs no approval."]})

    version.approved_by = actor if getattr(actor, "pk", None) else None
    version.approved_at = timezone.now()
    version.save(update_fields=["approved_by", "approved_at", "updated_at"])

    template = version.template
    if template.status != TemplateStatus.APPROVED:
        template.status = TemplateStatus.APPROVED
        template.save(update_fields=["status", "updated_at"])

    record(
        action=AuditAction.TEMPLATE_APPROVED,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={
            "template": str(template.pk),
            "number": version.number,
            "channel": template.channel,
        },
        durable=False,
    )
    return version


def _content_matches(a: TemplateVersion, b: TemplateVersion) -> bool:
    return (
        a.subject == b.subject
        and a.body_html == b.body_html
        and a.body_text == b.body_text
        and list(a.variables or []) == list(b.variables or [])
        and a.provider_template_id == b.provider_template_id
    )


@transaction.atomic
def publish_version(*, actor, version: TemplateVersion) -> TemplateVersion:
    """Publish a version, making it the template's `current_version`.

    Refused if already published (409), if it has not been approved (400 —
    the review gate `approve_version` exists for), or if nothing actually
    changed since the version currently published (409) — the same
    "nothing changed" refusal `apps.forms.services.publish_version` gives a
    `FormVersion`, adapted from a schema hash to a direct field comparison
    since a template version carries no `schema_hash`-shaped column of its
    own worth adding for this alone.
    """
    _require(actor, Capability.TEMPLATE_MANAGE)
    if version.is_published:
        raise ConflictError({"non_field_errors": ["This version is already published."]})
    if version.approved_at is None:
        raise ApplicationError(
            {"non_field_errors": ["A version must be approved before it can be published."]}
        )

    template = MessageTemplate.objects.select_for_update().get(pk=version.template_id)
    current = template.current_version
    if current is not None and current.pk != version.pk and _content_matches(current, version):
        raise ConflictError({"non_field_errors": ["Nothing changed since the published version."]})

    version.published_at = timezone.now()
    version.save(update_fields=["published_at", "updated_at"])

    template.current_version = version
    template.status = TemplateStatus.PUBLISHED
    template.save(update_fields=["current_version", "status", "updated_at"])
    _forget_published(template.key, template.channel)

    record(
        action=AuditAction.TEMPLATE_PUBLISHED,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={"template": str(template.pk), "key": template.key, "number": version.number},
        durable=False,
    )
    return version


def preview_version(*, version: TemplateVersion, variables: dict[str, Any]) -> dict[str, Any]:
    """Render only — never sends, never creates a `Delivery` row."""
    return render_template(version, variables or {})


@transaction.atomic
def test_send(*, actor, version: TemplateVersion) -> Delivery:
    """Send this version to the caller's own address only — the safety rail
    the contract names explicitly. Works on a draft, approved or published
    version alike; testing before approval is the point."""
    _require(actor, Capability.TEMPLATE_MANAGE)
    template = version.template
    if template.channel == MessageChannel.WHATSAPP and not (actor.whatsapp_opt_in and actor.phone):
        raise ApplicationError(
            {
                "channel": [
                    "Opt in to WhatsApp and set a phone number on your own account "
                    "before test-sending a WhatsApp template."
                ]
            }
        )

    deliveries = create_deliveries(
        channel=template.channel,
        template_version=version,
        recipients=[actor],
        requested_by=actor,
    )
    if not deliveries:
        raise ApplicationError(
            {"channel": ["Could not resolve your own address for this channel."]}
        )

    record(
        action=AuditAction.TEMPLATE_TEST_SENT,
        actor=actor,
        resource_type="template_version",
        resource_id=version.pk,
        context={"template": template.key, "channel": template.channel},
        durable=False,
    )
    return deliveries[0]


def resolve_published_template(*, key: str, channel: str) -> TemplateVersion | None:
    """The published version for `key`/`channel`, or `None`. The one place
    both the manual-send endpoint and automation's `send_email`/
    `send_whatsapp` actions resolve "which template" from — see
    `apps.automation.actions`.

    Cached an hour (`template:published:{key}:{channel}`), the same shape
    `apps.forms.views`' `form:published` uses — called on every send, and a
    template is published rarely. `_forget_published` (called from
    `publish_version` and `create_draft_version`, the two places a
    template's published state actually changes) invalidates precisely this
    key/channel pair, never any other template's."""
    if not key:
        return None

    def _compute():
        template = (
            MessageTemplate.objects.filter(
                key=key, channel=channel, status=TemplateStatus.PUBLISHED, deleted_at__isnull=True
            )
            .select_related("current_version")
            .first()
        )
        if template is None or template.current_version_id is None:
            return None
        return template.current_version

    return remember(_published_cache_key(key, channel), (), _PUBLISHED_CACHE_TTL, _compute)


# ---------------------------------------------------------------------------
# Recipient resolution and Delivery creation
# ---------------------------------------------------------------------------


def _address_for(channel: str, user) -> str | None:
    if channel == MessageChannel.EMAIL:
        return user.email or None
    if channel == MessageChannel.WHATSAPP:
        return user.phone if user.whatsapp_opt_in and user.phone else None
    if channel == MessageChannel.IN_APP:
        return ""
    return None


def _recipient_variables(user) -> dict[str, Any]:
    return {
        "recipient": {
            "id": str(user.pk),
            "name": user.get_full_name(),
            "first_name": user.first_name,
            "email": user.email,
            "phone": user.phone,
        }
    }


def resolve_recipients(*, actor, channel: str, spec: dict[str, Any]) -> list:
    """The real recipient set for a manual send, resolved entirely
    server-side and always through the caller's own `visible_*` scope —
    never an unscoped `User.objects` lookup (ADR-15).

    `spec` names exactly one of `students` (a list of `StudentProfile` ids),
    `batch` (a batch id) or `role` (a `UserRole` value). The returned list is
    already filtered to whoever is actually eligible for `channel` (has an
    email; has opted in to WhatsApp and carries a phone number) — that
    filtered list *is* "the real recipient set" `manual_send`'s
    `confirm_count` check compares against, per the contract.
    """
    from apps.accounts.models import User
    from apps.accounts.roles import UserRole
    from apps.batches import access as batch_access
    from apps.organisation.scoping import actor_branch_id, is_unbounded
    from apps.students.access import visible_students

    named = [key for key in ("students", "batch", "role") if spec.get(key)]
    if len(named) != 1:
        raise ApplicationError(
            {"recipients": ["Name exactly one of 'students', 'batch' or 'role'."]}
        )

    users: list[User]
    if spec.get("students"):
        student_ids = spec["students"]
        profiles = visible_students(actor).filter(pk__in=student_ids, user__isnull=False)
        found = {str(profile.pk) for profile in profiles}
        missing = {str(sid) for sid in student_ids} - found
        if missing:
            raise ApplicationError(
                {"recipients": [f"Unknown or unreachable student id(s): {sorted(missing)}."]}
            )
        users = [profile.user for profile in profiles]
    elif spec.get("batch"):
        from apps.notifications.services import students_of_batch

        batch = batch_access.visible_batches(actor).filter(pk=spec["batch"]).first()
        if batch is None:
            raise ApplicationError({"recipients": ["Unknown or unreachable batch."]})
        users = students_of_batch(batch)
    else:
        role = spec["role"]
        if role not in UserRole.values:
            raise ApplicationError({"recipients": [f"Unknown role: {role!r}."]})
        qs = User.objects.filter(role=role, is_active=True)
        if not is_unbounded(actor):
            branch_id = actor_branch_id(actor)
            qs = qs.filter(branch_id=branch_id) if branch_id is not None else qs.none()
        users = list(qs)

    eligible = [
        user for user in users if user.is_active and _address_for(channel, user) is not None
    ]
    return eligible


def create_deliveries(
    *,
    channel: str,
    template_version: TemplateVersion,
    recipients: list = (),
    literal_addresses: list[str] = (),
    base_variables: dict[str, Any] | None = None,
    related_object: Any = None,
    requested_by=None,
) -> list[Delivery]:
    """Create one `Delivery` row per eligible recipient/address, and hand
    each one to its own dispatch task on commit.

    The one function every caller that ever creates a `Delivery` goes
    through — the manual-send service, automation's `send_email`/
    `send_whatsapp` actions, and `test_send` above — so "how is a Delivery's
    address resolved and its dispatch scheduled" has exactly one answer.
    """
    related_type = None
    related_id = None
    if related_object is not None and getattr(related_object, "pk", None):
        related_type = ContentType.objects.get_for_model(related_object)
        related_id = related_object.pk

    rows: list[Delivery] = []
    for user in recipients:
        address = _address_for(channel, user)
        if address is None:
            continue
        variables = {**_recipient_variables(user), **(base_variables or {})}
        rows.append(
            Delivery(
                channel=channel,
                recipient=user,
                address=address,
                template_version=template_version,
                variables=variables,
                related_type=related_type,
                related_id=related_id,
                requested_by=requested_by,
            )
        )
    if channel == MessageChannel.EMAIL:
        for address in literal_addresses:
            if not address:
                continue
            rows.append(
                Delivery(
                    channel=channel,
                    address=address,
                    template_version=template_version,
                    variables={**{"recipient": {"email": address}}, **(base_variables or {})},
                    related_type=related_type,
                    related_id=related_id,
                    requested_by=requested_by,
                )
            )

    if not rows:
        return []

    created = Delivery.objects.bulk_create(rows)
    for delivery in created:
        transaction.on_commit(lambda delivery_id=delivery.pk: _enqueue_dispatch(delivery_id))
    return created


def _enqueue_dispatch(delivery_id) -> None:
    from .tasks import dispatch_delivery

    try:
        dispatch_delivery.delay(str(delivery_id))
    except Exception:
        # The row stays QUEUED; a broker outage leaves evidence rather than
        # losing the send. There is no scheduled sweep for a stuck Delivery
        # in this phase (unlike the email outbox's own retry sweep) — the
        # manual retry endpoint only accepts a FAILED one, so a row stuck at
        # QUEUED because the broker was briefly down is the one gap the
        # phase accepts rather than adding a second sweep task for; see the
        # phase's final report for this as a named, deliberate limitation.
        logger.warning(
            "Could not queue a Delivery dispatch",
            extra={"context": {"delivery": str(delivery_id)}},
        )


@transaction.atomic
def manual_send(
    *,
    actor,
    channel: str,
    template_key: str,
    recipients_spec: dict[str, Any],
    variables: dict[str, Any] | None,
    confirm_count: int,
) -> dict[str, Any]:
    """`POST /communication/send/`'s own service. Recomputes the recipient
    count from scratch and refuses (409) if the caller's `confirm_count`
    does not match — the same "recompute server-side, never trust the
    client" discipline this codebase's other confirm-gated writes use."""
    _require(actor, Capability.COMMUNICATION_SEND)
    if channel not in MessageChannel.values:
        raise ApplicationError({"channel": [f"Unknown channel: {channel!r}."]})

    template_version = resolve_published_template(key=template_key, channel=channel)
    if template_version is None:
        raise ApplicationError(
            {"template": [f"No published {channel} template with key {template_key!r}."]}
        )

    recipients = resolve_recipients(actor=actor, channel=channel, spec=recipients_spec or {})
    actual_count = len(recipients)
    if confirm_count != actual_count:
        raise ConflictError(
            {
                "confirm_count": [
                    f"The recipient count has changed; there are now {actual_count} "
                    "eligible recipient(s). Review and confirm again."
                ]
            }
        )

    deliveries = create_deliveries(
        channel=channel,
        template_version=template_version,
        recipients=recipients,
        base_variables=variables or {},
        requested_by=actor,
    )
    record(
        action=AuditAction.COMMUNICATION_SENT,
        actor=actor,
        resource_type="message_template",
        resource_id=template_version.template_id,
        # Counts only — never the resolved recipients themselves (ADR-15 /
        # the same reasoning `search.performed`'s audit context documents).
        context={"channel": channel, "template": template_key, "count": len(deliveries)},
        durable=False,
    )
    return {"count": len(deliveries), "delivery_ids": [str(row.pk) for row in deliveries]}


@transaction.atomic
def retry_delivery(*, actor, delivery: Delivery) -> Delivery:
    _require(actor, Capability.COMMUNICATION_SEND)
    if delivery.state != DeliveryState.FAILED:
        raise ConflictError({"delivery": ["Only a failed delivery can be retried."]})
    delivery.state = DeliveryState.QUEUED
    delivery.next_attempt_at = None
    delivery.save(update_fields=["state", "next_attempt_at", "updated_at"])
    transaction.on_commit(lambda delivery_id=delivery.pk: _enqueue_dispatch(delivery_id))
    record(
        action=AuditAction.DELIVERY_RETRIED,
        actor=actor,
        resource_type="delivery",
        resource_id=delivery.pk,
        context={"channel": delivery.channel},
        durable=False,
    )
    return delivery


@transaction.atomic
def cancel_delivery(*, actor, delivery: Delivery) -> Delivery:
    _require(actor, Capability.COMMUNICATION_SEND)
    if delivery.state != DeliveryState.QUEUED:
        raise ConflictError({"delivery": ["Only a queued delivery can be cancelled."]})
    delivery.state = DeliveryState.CANCELLED
    delivery.save(update_fields=["state", "updated_at"])
    record(
        action=AuditAction.DELIVERY_CANCELLED,
        actor=actor,
        resource_type="delivery",
        resource_id=delivery.pk,
        context={"channel": delivery.channel},
        durable=False,
    )
    return delivery


# ---------------------------------------------------------------------------
# Dispatch — the actual per-channel send. Called only from
# `apps.communication.tasks.dispatch_delivery`, never inline in a request.
# ---------------------------------------------------------------------------


def dispatch_delivery(delivery: Delivery) -> None:
    delivery.state = DeliveryState.PROCESSING
    delivery.attempts += 1
    delivery.save(update_fields=["state", "attempts", "updated_at"])

    rendered = None
    if delivery.template_version_id:
        rendered = render_template(delivery.template_version, delivery.variables or {})

    try:
        if delivery.channel == MessageChannel.EMAIL:
            _dispatch_email(delivery, rendered)
        elif delivery.channel == MessageChannel.WHATSAPP:
            _dispatch_whatsapp(delivery, rendered)
        elif delivery.channel == MessageChannel.IN_APP:
            _dispatch_in_app(delivery, rendered)
        else:
            delivery.state = DeliveryState.FAILED
            delivery.error = f"Unknown channel: {delivery.channel!r}"
            delivery.save(update_fields=["state", "error", "updated_at"])
    except Exception as exc:  # a provider/channel bug must not crash the worker
        logger.exception(
            "Delivery dispatch raised", extra={"context": {"delivery": str(delivery.pk)}}
        )
        delivery.state = DeliveryState.FAILED
        delivery.error = _store_error(exc)
        delivery.save(update_fields=["state", "error", "updated_at"])


def _dispatch_email(delivery: Delivery, rendered: dict[str, Any] | None) -> None:
    from apps.notifications.channels import send_email_message
    from apps.notifications.models import EmailMessage

    if not delivery.address:
        delivery.state = DeliveryState.FAILED
        delivery.error = "No email address to send to."
        delivery.save(update_fields=["state", "error", "updated_at"])
        return

    subject = (rendered or {}).get("subject") or ""
    body = (rendered or {}).get("text") or (rendered or {}).get("html") or ""
    template_key = delivery.template_version.template.key if delivery.template_version_id else ""
    message = EmailMessage.objects.create(
        to_email=delivery.address, subject=subject[:255], body=body, template=template_key[:60]
    )
    delivery.email_message = message
    delivery.save(update_fields=["email_message", "updated_at"])

    ok = send_email_message(message)
    message.refresh_from_db(fields=["last_error"])
    delivery.state = DeliveryState.SENT if ok else DeliveryState.FAILED
    delivery.error = "" if ok else message.last_error
    delivery.save(update_fields=["state", "error", "updated_at"])


def _dispatch_whatsapp(delivery: Delivery, rendered: dict[str, Any] | None) -> None:
    # Defence in depth: opt-in is already required to resolve a Delivery for
    # this channel in the first place (`_address_for`), but consent can be
    # withdrawn between queue time and send time.
    if delivery.recipient_id and not delivery.recipient.whatsapp_opt_in:
        delivery.state = DeliveryState.FAILED
        delivery.error = "Recipient has not opted in to WhatsApp."
        delivery.save(update_fields=["state", "error", "updated_at"])
        return
    if not delivery.address:
        delivery.state = DeliveryState.FAILED
        delivery.error = "No WhatsApp number to send to."
        delivery.save(update_fields=["state", "error", "updated_at"])
        return

    result = get_provider().send(
        to=delivery.address,
        template_version=delivery.template_version,
        variables=delivery.variables or {},
        rendered=rendered or {},
    )
    delivery.state = DeliveryState.SENT if result.ok else DeliveryState.FAILED
    delivery.provider_message_id = result.provider_message_id
    delivery.error = result.error[:ERROR_MAX] if not result.ok else ""
    delivery.save(update_fields=["state", "provider_message_id", "error", "updated_at"])


def _dispatch_in_app(delivery: Delivery, rendered: dict[str, Any] | None) -> None:
    from apps.notifications.services import notify

    if not delivery.recipient_id:
        delivery.state = DeliveryState.FAILED
        delivery.error = "No recipient to notify."
        delivery.save(update_fields=["state", "error", "updated_at"])
        return

    kind = (
        delivery.template_version.template.kind
        if delivery.template_version_id
        else NotificationKind.ANNOUNCEMENT
    )
    title = (rendered or {}).get("subject") or (
        delivery.template_version.template.name if delivery.template_version_id else ""
    )
    body = (rendered or {}).get("text") or ""
    # `send_email=False`: the in-app channel is this Delivery's whole job.
    # Sending mail too would double-send against whatever
    # `NotificationPreference` already governs for plain `notify()` calls.
    notify(recipient=delivery.recipient, kind=kind, title=title[:200], body=body, send_email=False)
    delivery.state = DeliveryState.SENT
    delivery.error = ""
    delivery.save(update_fields=["state", "error", "updated_at"])


# ---------------------------------------------------------------------------
# WhatsApp webhook callbacks
# ---------------------------------------------------------------------------

_WEBHOOK_STATE_MAP = {
    "sent": DeliveryState.SENT,
    "delivered": DeliveryState.DELIVERED,
    "read": DeliveryState.DELIVERED,
    "failed": DeliveryState.FAILED,
}


def apply_whatsapp_status_update(
    *, provider_message_id: str, status: str, error: str = ""
) -> Delivery | None:
    """Update the `Delivery` a provider callback names, once the webhook
    view has already verified the request's signature. Returns `None` for
    an unknown message id or status — there is nothing to refuse; the
    caller (an external provider) gets a 200 either way so it stops
    retrying, per the webhook's own contract."""
    new_state = _WEBHOOK_STATE_MAP.get(status)
    if new_state is None or not provider_message_id:
        return None

    delivery = Delivery.objects.filter(
        provider_message_id=provider_message_id, channel=MessageChannel.WHATSAPP
    ).first()
    if delivery is None or delivery.state == DeliveryState.CANCELLED:
        # A cancelled delivery never gets resurrected by a stray callback.
        return None

    delivery.state = new_state
    if error:
        delivery.error = str(scrub({"error": error}).get("error", ""))[:ERROR_MAX]
    delivery.save(update_fields=["state", "error", "updated_at"])
    record(
        action=AuditAction.DELIVERY_WEBHOOK_UPDATED,
        actor=None,
        resource_type="delivery",
        resource_id=delivery.pk,
        context={"provider_message_id": provider_message_id, "state": new_state},
        durable=False,
    )
    return delivery
