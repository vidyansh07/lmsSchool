"""Payment categories and tax groups: the institute's own two money lists.

The same three rules as `apps.organisation.settings_lists`, which this is
deliberately a mirror of: at most one default, nothing deleted, every change
audited. They live here rather than there because they belong to the fee
models, and a settings screen reading two apps is better than a fee list
living in the organisation app.

A tax group is recorded and never computed (owner's decision, 23 October
2026): naming one on a payment says which tax it was taken under, and the
amount is whatever was actually collected.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.exceptions import AuthorityError, ConflictError

from .models import PaymentCategory, TaxGroup


def _require(actor: User) -> None:
    if not has_capability(actor, Capability.SETTINGS_MANAGE):
        raise AuthorityError("You do not have authority to change the institution's settings.")


def _audit(actor: User, *, kind: str, instance, changed: list[str]) -> None:
    record(
        action=AuditAction.SETTINGS_LIST_CHANGED,
        actor=actor,
        resource_type=kind,
        resource_id=instance.pk,
        context={"name": instance.name, "changed": changed},
    )


def _only_default(model, instance) -> None:
    """At most one default. The payment dialog opens with it, and two of them
    is a dialog that cannot decide."""
    model.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)


def _create(model, kind: str, *, actor: User, name: str, **fields: Any):
    _require(actor)
    name = (name or "").strip()
    if model.objects.filter(name__iexact=name).exists():
        raise ConflictError(
            {"name": [f"There is already a {kind.replace('_', ' ')} with this name."]}
        )
    row = model(name=name, **fields)
    row.full_clean()
    row.save()
    if row.is_default:
        _only_default(model, row)
    _audit(actor, kind=kind, instance=row, changed=["created"])
    return row


def _update(model, kind: str, *, actor: User, row, **fields: Any):
    _require(actor)
    changed: list[str] = []
    for name, value in fields.items():
        if name == "name":
            value = (value or "").strip()
            if model.objects.filter(name__iexact=value).exclude(pk=row.pk).exists():
                raise ConflictError(
                    {"name": [f"There is already a {kind.replace('_', ' ')} with this name."]}
                )
        if getattr(row, name) != value:
            setattr(row, name, value)
            changed.append(name)
    if not changed:
        return row
    row.full_clean()
    row.save(update_fields=[*changed, "updated_at"])
    if row.is_default:
        _only_default(model, row)
    _audit(actor, kind=kind, instance=row, changed=changed)
    return row


@transaction.atomic
def create_payment_category(*, actor: User, **fields: Any) -> PaymentCategory:
    return _create(PaymentCategory, "payment_category", actor=actor, **fields)


@transaction.atomic
def update_payment_category(
    *, actor: User, category: PaymentCategory, **fields: Any
) -> PaymentCategory:
    return _update(PaymentCategory, "payment_category", actor=actor, row=category, **fields)


@transaction.atomic
def create_tax_group(*, actor: User, **fields: Any) -> TaxGroup:
    return _create(TaxGroup, "tax_group", actor=actor, **fields)


@transaction.atomic
def update_tax_group(*, actor: User, group: TaxGroup, **fields: Any) -> TaxGroup:
    return _update(TaxGroup, "tax_group", actor=actor, row=group, **fields)
