"""Creating and changing the institution's own short lists.

Academic years and banks here; payment categories and tax groups are the
same shape in `apps.fees.settings_lists`, next to the models they belong to.

Three rules hold across all four, and they are the reason this is a service
rather than four `ModelViewSet`s:

* **Exactly one year is current, and at most one of everything else is the
  default.** Setting one unsets the other in the same transaction, because
  two current years is a question no screen can answer and nobody would
  notice until an admission was filed under the wrong one.
* **Nothing is deleted.** A year, a bank or a category is referenced by
  records that outlive the institute's interest in it; `is_active` takes it
  out of the pickers and leaves history legible.
* **Every change is audited** with what it was and what it became. These are
  small lists that quietly change the meaning of money — which bank a cheque
  went through, which tax a payment was taken under — so "who changed this,
  and when" is not optional.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError

from .models import AcademicYear, Bank


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


# ---------------------------------------------------------------------------
# Academic years
# ---------------------------------------------------------------------------


@transaction.atomic
def create_academic_year(*, actor: User, **fields: Any) -> AcademicYear:
    _require(actor)
    name = (fields.get("name") or "").strip()
    if AcademicYear.objects.filter(name__iexact=name).exists():
        raise ConflictError({"name": ["There is already a year with this name."]})
    year = AcademicYear(**{**fields, "name": name})
    _check_dates(year)
    year.full_clean()
    year.save()
    if year.is_current:
        _make_only_current(year)
    _audit(actor, kind="academic_year", instance=year, changed=["created"])
    return year


@transaction.atomic
def update_academic_year(*, actor: User, year: AcademicYear, **fields: Any) -> AcademicYear:
    _require(actor)
    changed: list[str] = []
    for name, value in fields.items():
        if name == "name":
            value = (value or "").strip()
            if AcademicYear.objects.filter(name__iexact=value).exclude(pk=year.pk).exists():
                raise ConflictError({"name": ["There is already a year with this name."]})
        if getattr(year, name) != value:
            setattr(year, name, value)
            changed.append(name)
    if not changed:
        return year
    _check_dates(year)
    year.full_clean()
    year.save(update_fields=[*changed, "updated_at"])
    if year.is_current:
        _make_only_current(year)
    _audit(actor, kind="academic_year", instance=year, changed=changed)
    return year


def _check_dates(year: AcademicYear) -> None:
    if year.starts_on and year.ends_on and year.ends_on < year.starts_on:
        raise ApplicationError({"ends_on": ["A year cannot end before it starts."]})


def _make_only_current(year: AcademicYear) -> None:
    """One current year, always. The screen offers a switch per row, so the
    rule has to live here rather than in whichever screen was used."""
    AcademicYear.objects.filter(is_current=True).exclude(pk=year.pk).update(is_current=False)


# ---------------------------------------------------------------------------
# Banks
# ---------------------------------------------------------------------------


@transaction.atomic
def create_bank(*, actor: User, name: str, is_active: bool = True) -> Bank:
    _require(actor)
    name = (name or "").strip()
    if Bank.objects.filter(name__iexact=name).exists():
        raise ConflictError({"name": ["There is already a bank with this name."]})
    bank = Bank(name=name, is_active=is_active)
    bank.full_clean()
    bank.save()
    _audit(actor, kind="bank", instance=bank, changed=["created"])
    return bank


@transaction.atomic
def update_bank(*, actor: User, bank: Bank, **fields: Any) -> Bank:
    _require(actor)
    changed: list[str] = []
    for name, value in fields.items():
        if name == "name":
            value = (value or "").strip()
            if Bank.objects.filter(name__iexact=value).exclude(pk=bank.pk).exists():
                raise ConflictError({"name": ["There is already a bank with this name."]})
        if getattr(bank, name) != value:
            setattr(bank, name, value)
            changed.append(name)
    if not changed:
        return bank
    bank.full_clean()
    bank.save(update_fields=[*changed, "updated_at"])
    _audit(actor, kind="bank", instance=bank, changed=changed)
    return bank
