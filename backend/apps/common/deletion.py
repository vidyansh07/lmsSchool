"""Removing a record, and bringing it back.

One service for every soft-deletable model, rather than a `delete` method per
app, because the three things that must happen on every removal are the three
things a per-app implementation forgets: the reason, the audit entry, and the
children.

Three verbs, deliberately different words
-----------------------------------------
* :func:`soft_delete` — the record leaves every normal query and can be brought
  back. This is what a `DELETE` endpoint does.
* :func:`restore` — it comes back.
* :func:`purge` — it is destroyed, and this cannot be undone. Guarded by its own
  capability that only a superadmin holds.

"Delete" is not overloaded to mean two things. A queryset whose ``delete()``
secretly soft-deletes reads as destruction at every call site, and a reviewer
would have to know which model they were looking at to know what it did.

Cascading
---------
A soft delete does not cascade through the database, because nothing was
actually deleted — so a batch removed without its enrolments would leave its
students visible on a batch that no longer exists. Each caller declares what
travels with the record through ``cascade``, and the same list runs in reverse
on restore, restoring only the children that this deletion took with it.

That last part is the subtle one. A child deleted *before* its parent, for its
own reasons, must not be resurrected by the parent's restore — it was not part
of this. Children are matched on the parent's ``deleted_at`` timestamp, which is
stamped identically across the cascade for exactly this purpose.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Model, QuerySet
from django.utils import timezone

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError


def _label(instance: Model) -> str:
    """The model's app-qualified name, used as the audit resource type."""
    return instance._meta.label_lower.replace(".", ".")


def _describe(instance: Model) -> str:
    """A short human name for the record, for the recovery screen and the audit.

    Never the whole object: an audit context is read by people and stored
    forever, and dumping every field of a student into it would put personal
    data somewhere it does not need to be.
    """
    for attribute in ("code", "student_id", "trainer_id", "title", "name", "slug"):
        value = getattr(instance, attribute, None)
        if value:
            return str(value)[:120]
    return str(instance.pk)


def _is_soft_deletable(instance: Any) -> bool:
    return hasattr(instance, "deleted_at") and hasattr(instance, "mark_deleted")


@transaction.atomic
def soft_delete(
    *,
    instance: Model,
    actor,
    reason: str = "",
    cascade: tuple[QuerySet, ...] = (),
) -> Model:
    """Remove a record from every normal query, reversibly.

    ``reason`` is required in practice even though the column allows blank: an
    empty reason on a recovery screen looks like an answer when it is not. The
    services that call this pass one; the API serializers make it required.
    """
    if not _is_soft_deletable(instance):
        raise TypeError(f"{instance._meta.label} is not soft-deletable")

    if instance.deleted_at is not None:
        # Idempotent rather than an error: two clicks on a delete button is a
        # normal thing for a person to do, and the second must not be a 500.
        return instance

    stamp = timezone.now()
    instance.deleted_at = stamp
    instance.deleted_by = actor if getattr(actor, "pk", None) else None
    instance.delete_reason = reason
    instance.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])

    cascaded: dict[str, int] = {}
    for related in cascade:
        # The identical timestamp is what lets `restore` tell "deleted with this
        # parent" apart from "deleted earlier, for its own reasons".
        count = related.filter(deleted_at__isnull=True).update(
            deleted_at=stamp,
            deleted_by=actor if getattr(actor, "pk", None) else None,
            delete_reason=reason,
        )
        if count:
            cascaded[related.model._meta.label_lower] = count

    record(
        action=AuditAction.RECORD_DELETED,
        actor=actor,
        resource_type=_label(instance),
        resource_id=instance.pk,
        context={"reason": reason, "describes": _describe(instance), "cascaded": cascaded},
    )
    return instance


@transaction.atomic
def restore(*, instance: Model, actor, cascade: tuple[QuerySet, ...] = ()) -> Model:
    """Bring a record back, along with whatever went down with it."""
    if not _is_soft_deletable(instance):
        raise TypeError(f"{instance._meta.label} is not soft-deletable")

    if instance.deleted_at is None:
        raise ConflictError("That record is not deleted.")

    stamp = instance.deleted_at
    restored: dict[str, int] = {}
    for related in cascade:
        # Only the children this deletion took. One deleted a week earlier, for
        # its own reasons, stays deleted — restoring it would be inventing a
        # decision nobody made.
        count = related.filter(deleted_at=stamp).update(
            deleted_at=None, deleted_by=None, delete_reason=""
        )
        if count:
            restored[related.model._meta.label_lower] = count

    instance.deleted_at = None
    instance.deleted_by = None
    instance.delete_reason = ""
    instance.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])

    record(
        action=AuditAction.RECORD_RESTORED,
        actor=actor,
        resource_type=_label(instance),
        resource_id=instance.pk,
        context={"describes": _describe(instance), "restored_with_it": restored},
    )
    return instance


@transaction.atomic
def purge(*, instance: Model, actor, reason: str = "") -> None:
    """Destroy a record permanently. There is no undo.

    Separated from :func:`soft_delete` by a different verb *and* a different
    capability, because the two are not degrees of the same act. One is a
    reversible administrative tidy-up; the other is the end of the evidence.

    Only a record that is already soft-deleted may be purged. That is not
    ceremony: it means nothing can be destroyed without first having been
    removed, reviewed in the recycle bin, and destroyed as a second, deliberate
    decision — with an audit entry from each step.

    The audit entry is written *before* the delete and describes the record,
    because afterwards there is nothing left to describe.
    """
    if not _is_soft_deletable(instance):
        raise TypeError(f"{instance._meta.label} is not soft-deletable")

    if instance.deleted_at is None:
        raise ApplicationError(
            {
                "detail": [
                    "Only a deleted record can be destroyed. Delete it first, "
                    "so the decision is made twice."
                ]
            }
        )

    record(
        action=AuditAction.RECORD_PURGED,
        actor=actor,
        resource_type=_label(instance),
        resource_id=instance.pk,
        context={
            "reason": reason,
            "describes": _describe(instance),
            "deleted_at": instance.deleted_at.isoformat(),
        },
        durable=False,
    )
    instance.delete()


__all__ = ["purge", "restore", "soft_delete"]
