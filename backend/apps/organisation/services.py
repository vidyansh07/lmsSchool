"""Writing organisational structure.

Opening a centre and closing one are governance events, not edits: everything a
branch-scoped manager can see is decided by which branch they are in, so the set
of branches is the shape of the whole institution's visibility. Every change
here is audited with what it was and what it became.

Closing rather than deleting
----------------------------
There is no ``delete_branch``. A centre with people in it cannot be removed —
every foreign key onto it is ``PROTECT``-ed — and one without people has still
run classes whose history should stay readable. :func:`set_branch_active` is
the whole of "this centre is no longer open".
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError

from .models import Branch

#: What a caller may set through ``**fields``. ``is_active`` is deliberately
#: absent: closing a centre changes what a whole set of accounts can see, so it
#: moves only through :func:`set_branch_active`, which asks for a reason.
WRITABLE_FIELDS = frozenset({"code", "name", "city"})


def _validate(branch: Branch) -> None:
    try:
        branch.full_clean()
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


@transaction.atomic
def create_branch(*, actor: User, **fields: Any) -> Branch:
    """Open a centre."""
    unknown = sorted(set(fields) - WRITABLE_FIELDS)
    if unknown:
        raise ApplicationError({field: ["This field cannot be set here."] for field in unknown})

    branch = Branch(**fields)
    _validate(branch)
    try:
        branch.save()
    except IntegrityError as exc:
        # Reachable only by administrators, so naming the conflict is safe.
        raise ConflictError("A branch with this code already exists.") from exc

    record(
        action=AuditAction.BRANCH_CREATED,
        actor=actor,
        resource_type="branch",
        resource_id=branch.pk,
        context={"code": branch.code, "name": branch.name},
        durable=False,
    )
    return branch


@transaction.atomic
def update_branch(*, branch: Branch, actor: User, **fields: Any) -> Branch:
    """Rename a centre, or correct its code or city."""
    unknown = sorted(set(fields) - WRITABLE_FIELDS)
    if unknown:
        raise ApplicationError({field: ["This field cannot be set here."] for field in unknown})

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(branch, field) != value:
            setattr(branch, field, value)
            changed.append(field)

    if not changed:
        return branch

    _validate(branch)
    branch.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.BRANCH_UPDATED,
        actor=actor,
        resource_type="branch",
        resource_id=branch.pk,
        context={"code": branch.code, "changed_fields": sorted(changed)},
        durable=False,
    )
    return branch


@transaction.atomic
def set_branch_active(*, branch: Branch, is_active: bool, actor: User, reason: str = "") -> Branch:
    """Open or close a centre.

    Closing does not hide anything: the batches, students and trainers stamped
    with it stay exactly as visible as they were to the people already in it.
    What it says is that nobody should be filed here any more.
    """
    if branch.is_active == is_active:
        return branch

    branch.is_active = is_active
    branch.save(update_fields=["is_active", "updated_at"])

    record(
        action=AuditAction.BRANCH_UPDATED,
        actor=actor,
        resource_type="branch",
        resource_id=branch.pk,
        context={"code": branch.code, "is_active": is_active, "reason": reason},
        durable=False,
    )
    return branch
