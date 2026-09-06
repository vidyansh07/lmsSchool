"""Abstract model bases shared by every domain app.

Three decisions worth stating once, because every future LMS table inherits them:

* **UUID primary keys.** LMS identifiers appear in URLs, certificates and
  exports. Sequential integers leak enrolment counts and invite enumeration of
  other people's records; UUIDv4 does not.
* **Created/updated timestamps on everything.** Required for audit
  reconstruction and for incremental reporting later.
* **Deletion is reversible.** See :class:`SoftDeleteModel`.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """The default base for domain models."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)


# ---------------------------------------------------------------------------
# Soft deletion
# ---------------------------------------------------------------------------


class SoftDeleteQuerySet(models.QuerySet):
    """Queryset for records that can be deleted without being destroyed.

    ``delete()`` is deliberately *not* overridden to soft-delete. A queryset
    whose ``delete`` quietly means something else is a trap: the call reads as
    destruction at every call site, and a reviewer has to know which model they
    are looking at to know what it does. Removal goes through
    :func:`apps.common.deletion.soft_delete`, which is a different verb and
    takes the actor and the reason it needs.
    """

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        """The recycle bin: deleted, still recoverable."""
        return self.filter(deleted_at__isnull=False)

    def with_deleted(self):
        """Explicit opt-in to seeing everything.

        Reads as a decision at the call site, which is the point — the default
        manager already excludes deleted rows, so anything that needs them
        should have to say so.
        """
        return self


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """The default manager: live records only.

    Every ordinary query — a list endpoint, a reverse relation, a report — goes
    through here and cannot see a deleted row. That is the whole point: making
    each call site remember to filter is how a deleted student reappears on one
    screen out of forty.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


def soft_delete_managers(queryset_class: type[models.QuerySet]) -> tuple[models.Manager, ...]:
    """Build the `(objects, all_objects)` pair for a model with its own queryset.

    Most models here define a domain queryset — ``BatchQuerySet``,
    ``EnrollmentQuerySet`` — and assign it as ``objects``. That assignment
    *overrides* the inherited manager, so a model can adopt
    :class:`SoftDeleteModel`, gain all three columns, pass a migration, and go on
    returning deleted rows from every query. Nothing about it looks wrong.

    So the pair is built here instead::

        objects, all_objects = soft_delete_managers(BatchQuerySet)

    ``objects`` filters and keeps the domain queryset's own methods;
    ``all_objects`` keeps them and sees everything.

    The domain queryset should also inherit :class:`SoftDeleteQuerySet` so
    ``alive()``, ``dead()`` and ``with_deleted()`` are available on it.
    ``tests/test_soft_delete.py`` asserts the filtering actually happens, per
    model, rather than trusting that this was called.
    """
    return (
        SoftDeleteManager.from_queryset(queryset_class)(),
        models.Manager.from_queryset(queryset_class)(),
    )


class SoftDeleteModel(models.Model):
    """A record whose deletion is reversible.

    Why three fields rather than a flag
    -----------------------------------
    ``deleted_at`` alone would answer "is it gone?". The question actually asked
    when somebody notices a missing batch is "who removed it, when, and why?",
    and a boolean cannot answer any of it. The reason is required by the
    service, not by the column, because a blank reason is worse than no field —
    it looks like an answer.

    Two managers, and why the base one matters
    ------------------------------------------
    ``objects`` excludes deleted rows, so normal code cannot leak them.
    ``all_objects`` sees everything and is what the recovery screens use.

    ``Meta.base_manager_name`` is set to ``all_objects`` on purpose. Django uses
    the *base* manager to follow a forward foreign key, so without this, reading
    ``enrollment.batch`` after the batch was deleted would raise
    ``DoesNotExist`` — history would become unreadable exactly when somebody is
    trying to work out what happened. A child pointing at a deleted parent must
    still be able to name it.

    **Subclasses must inherit this Meta** (``class Meta(SoftDeleteModel.Meta):``)
    or they silently lose that, and Django's default would make the filtering
    manager the base manager too. ``tests/test_soft_delete.py`` walks every
    soft-deletable model and fails if one forgot, because "silently" is the
    problem with it.
    """

    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Set when the record was removed. Null means live."),
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Who removed it. Null if the account has since been removed."),
    )
    delete_reason = models.CharField(
        _("reason for deletion"),
        max_length=255,
        blank=True,
        help_text=_("Why it was removed. Shown on the recovery screen."),
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_deleted(self, *, actor=None, reason: str = "") -> None:
        """Set the fields. Callers use the service, which also audits."""
        self.deleted_at = timezone.now()
        self.deleted_by = actor if getattr(actor, "pk", None) else None
        self.delete_reason = reason
        self.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])

    def mark_restored(self) -> None:
        self.deleted_at = None
        self.deleted_by = None
        self.delete_reason = ""
        self.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])


class SoftDeleteBaseModel(SoftDeleteModel, BaseModel):
    """The base for domain models that can be removed and brought back.

    Ordering puts `SoftDeleteModel` first so its managers win: `objects` must be
    the filtering one, and it must be declared before `all_objects` so Django
    resolves it as the default.
    """

    class Meta(SoftDeleteModel.Meta, BaseModel.Meta):
        abstract = True
