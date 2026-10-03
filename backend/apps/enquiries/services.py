"""Enquiry business rules: capture, update, stage changes.

Form answers reach an enquiry through one mapping, `ANSWER_FIELDS`: an
enquiry-entity form whose questions use these keys writes them onto the
enquiry — the enquiry form captures a new lead, the follow-up form (or a
counselling call's form) updates one. A repeat enquiry from the same mobile
number at the same centre updates the open enquiry instead of creating a
second one, the way Meritto de-duplicates leads.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError

from .models import CLOSED_STAGES, Enquiry, EnquiryStage
from .signals import enquiry_changed

#: Form question key → enquiry field. Keys not listed are kept on the form
#: response only.
ANSWER_FIELDS: dict[str, str] = {
    "full_name": "full_name",
    "mobile": "mobile",
    "email": "email",
    "whatsapp_number": "whatsapp_number",
    "state": "state",
    "city": "city",
    "course": "course",
    "track": "track",
    "preferred_centre": "preferred_centre",
    "mode": "mode",
    "batch_timing": "batch_timing",
    "qualification": "qualification",
    "source": "source",
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "remarks": "remarks",
    "lead_stage": "stage",
    "stage": "stage",
    "lost_reason": "lost_reason",
    "lead_quality": "lead_quality",
    "next_follow_up": "next_follow_up_at",
}

#: Fields a person (or an automation rule) may change directly.
EDITABLE_FIELDS = frozenset(
    {
        "full_name",
        "mobile",
        "email",
        "whatsapp_number",
        "state",
        "city",
        "course",
        "track",
        "preferred_centre",
        "mode",
        "batch_timing",
        "qualification",
        "source",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "remarks",
        "stage",
        "lost_reason",
        "lead_quality",
        "next_follow_up_at",
        "owner",
    }
)

_LOST_STAGES = frozenset({EnquiryStage.NOT_INTERESTED, EnquiryStage.NOT_ELIGIBLE})


def mobile_key(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    return digits[-10:]


def _parse_datetime(value: Any):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _clean(field: str, value: Any) -> Any:
    if field == "stage":
        if value not in EnquiryStage.values:
            raise ApplicationError({"stage": [f"Unknown stage: {value!r}."]})
        return value
    if field == "lead_quality":
        if value in (None, ""):
            return None
        try:
            quality = int(value)
        except (TypeError, ValueError):
            raise ApplicationError({"lead_quality": ["Must be a number from 1 to 5."]}) from None
        if not 1 <= quality <= 5:
            raise ApplicationError({"lead_quality": ["Must be a number from 1 to 5."]})
        return quality
    if field == "next_follow_up_at":
        return _parse_datetime(value)
    if field == "owner":
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def answers_to_fields(values: dict[str, Any]) -> dict[str, Any]:
    """The enquiry fields a form's answers set, cleaned. An answer that is
    not a valid value for its enquiry field (a custom form offering a stage
    the pipeline does not have) is skipped, not allowed to fail the form."""
    fields: dict[str, Any] = {}
    for key, value in (values or {}).items():
        target = ANSWER_FIELDS.get(key)
        if target is None or value in (None, ""):
            continue
        try:
            fields[target] = _clean(target, value)
        except ApplicationError:
            continue
    return fields


def _emit(enquiry: Enquiry, *, event: str, changed: list[str], previous_stage: str, actor) -> None:
    enquiry_changed.send(
        sender=Enquiry,
        enquiry=enquiry,
        event=event,
        changed=changed,
        previous_stage=previous_stage,
        actor=actor,
    )


def _apply(enquiry: Enquiry, fields: dict[str, Any]) -> list[str]:
    """Set `fields` on `enquiry` (unsaved); return the names that changed."""
    changed: list[str] = []
    for name, value in fields.items():
        if name == "owner":
            if enquiry.owner_id != getattr(value, "pk", None):
                enquiry.owner = value
                changed.append("owner")
            continue
        if getattr(enquiry, name) != value:
            setattr(enquiry, name, value)
            changed.append(name)
    if "mobile" in changed:
        enquiry.mobile_key = mobile_key(enquiry.mobile)
    if "stage" in changed:
        enquiry.stage_changed_at = timezone.now()
        if enquiry.stage not in _LOST_STAGES and "lost_reason" not in fields:
            enquiry.lost_reason = ""
    return changed


@transaction.atomic
def capture(*, actor, values: dict[str, Any], branch=None) -> tuple[Enquiry, bool]:
    """Create an enquiry from a capture form's answers — or, when an open
    enquiry from the same mobile already exists at the centre, update that
    one. Returns ``(enquiry, created)``."""
    fields = answers_to_fields(values)
    if not fields.get("full_name") or not fields.get("mobile"):
        raise ApplicationError(
            {"non_field_errors": ["An enquiry needs a name and a mobile number."]}
        )
    key = mobile_key(fields["mobile"])
    branch = branch or (
        getattr(actor, "branch", None) if getattr(actor, "branch_id", None) else None
    )

    existing = (
        Enquiry.objects.select_for_update()
        .filter(mobile_key=key, branch=branch)
        .exclude(stage__in=list(CLOSED_STAGES))
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        fields.pop("stage", None)  # a repeat enquiry never moves the pipeline by itself
        previous_stage = existing.stage
        changed = _apply(existing, fields)
        if changed:
            existing.save()
        record(
            action=AuditAction.ENQUIRY_UPDATED,
            actor=actor,
            resource_type="enquiry",
            resource_id=existing.pk,
            context={"changed": changed, "repeat": True},
            durable=False,
        )
        if changed:
            _emit(
                existing,
                event="updated",
                changed=changed,
                previous_stage=previous_stage,
                actor=actor,
            )
        return existing, False

    staff = getattr(actor, "pk", None) and getattr(actor, "role", "") != "student"
    enquiry = Enquiry(
        mobile_key=key,
        branch=branch,
        created_by=actor if getattr(actor, "pk", None) else None,
        owner=actor if staff else None,
        stage=EnquiryStage.NEW,
        stage_changed_at=timezone.now(),
    )
    _apply(enquiry, fields)
    enquiry.mobile_key = key
    enquiry.save()
    record(
        action=AuditAction.ENQUIRY_CREATED,
        actor=actor,
        resource_type="enquiry",
        resource_id=enquiry.pk,
        context={"source": enquiry.source, "course": enquiry.course},
        durable=False,
    )
    _emit(enquiry, event="created", changed=[], previous_stage="", actor=actor)
    return enquiry, True


@transaction.atomic
def update(
    *,
    actor,
    enquiry: Enquiry,
    fields: dict[str, Any],
    emit: bool = True,
) -> tuple[Enquiry, list[str], str]:
    """Change an enquiry. Returns ``(enquiry, changed, previous_stage)``.

    ``emit=False`` is for the automation engine's `update_enquiry` action,
    which dispatches the follow-on event itself (see `signals.py`)."""
    unknown = sorted(set(fields) - EDITABLE_FIELDS)
    if unknown:
        raise ApplicationError({name: ["This field cannot be changed here."] for name in unknown})
    cleaned = {name: _clean(name, value) for name, value in fields.items()}
    if cleaned.get("full_name") == "" or cleaned.get("mobile") == "":
        raise ApplicationError(
            {"non_field_errors": ["An enquiry needs a name and a mobile number."]}
        )

    locked = Enquiry.objects.select_for_update().get(pk=enquiry.pk)
    previous_stage = locked.stage
    changed = _apply(locked, cleaned)
    if not changed:
        return locked, [], previous_stage
    locked.save()
    record(
        action=AuditAction.ENQUIRY_UPDATED,
        actor=actor,
        resource_type="enquiry",
        resource_id=locked.pk,
        context={
            "changed": changed,
            "stage": locked.stage if "stage" in changed else None,
            "previous_stage": previous_stage if "stage" in changed else None,
        },
        durable=False,
    )
    if emit:
        _emit(locked, event="updated", changed=changed, previous_stage=previous_stage, actor=actor)
    return locked, changed, previous_stage


def apply_answers(*, actor, enquiry: Enquiry, values: dict[str, Any]) -> list[str]:
    """A follow-up about `enquiry` was answered: write its mapped answers,
    and note the contact."""
    fields = answers_to_fields(values)
    # Identity comes from the capture form, not from a follow-up about it.
    for name in ("full_name", "mobile"):
        fields.pop(name, None)
    status = (values or {}).get("call_status")
    if status == "connected" or "stage" in fields:
        fields_with_contact = {**fields}
        if fields_with_contact.get("stage") is None and enquiry.stage == EnquiryStage.NEW:
            fields_with_contact["stage"] = EnquiryStage.CONTACTED
        fields = fields_with_contact
    _locked, changed, _previous = update(actor=actor, enquiry=enquiry, fields=fields)
    if status:
        Enquiry.objects.filter(pk=enquiry.pk).update(last_contacted_at=timezone.now())
    return changed


__all__ = [
    "ANSWER_FIELDS",
    "EDITABLE_FIELDS",
    "answers_to_fields",
    "apply_answers",
    "capture",
    "mobile_key",
    "update",
]
