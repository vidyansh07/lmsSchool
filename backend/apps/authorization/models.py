"""Roles as rows (ERP Phase 1, ADR-01).

The permission *catalog* stays in code — `apps.accounts.roles.Capability` —
because a permission only means something when a view checks it. What lives
here is the mapping: which role holds which permission, at which scope, and
whether that grant is locked. The six system roles are seeded from
`ROLE_CAPABILITIES` so the day this table appears nothing changes; a custom
role is a system kind with a different set, never a kind of its own.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.roles import UserRole
from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class RoleStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    DISABLED = "disabled", _("Disabled")


class PermissionScope(models.TextChoices):
    """How far a grant reaches. Never wider than the role kind's floor (ADR-02)."""

    ALL = "all", _("Every centre")
    BRANCH = "branch", _("Own centre")
    ASSIGNED = "assigned", _("Assigned batches and courses")
    OWN = "own", _("Own records")


class PermissionCategory(models.TextChoices):
    PEOPLE = "people", _("People")
    ACADEMIC = "academic", _("Academic")
    OPERATIONS = "operations", _("Operations")
    CONFIGURATION = "configuration", _("Configuration")
    COMMUNICATION = "communication", _("Communication")
    SYSTEM = "system", _("System")


class Permission(BaseModel):
    """One row per `Capability` member, kept equal by `sync_catalog`."""

    code = models.CharField(_("code"), max_length=60, unique=True)
    resource = models.CharField(_("resource"), max_length=30)
    action = models.CharField(_("action"), max_length=30)
    category = models.CharField(_("category"), max_length=20, choices=PermissionCategory.choices)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_system = models.BooleanField(_("system"), default=True, editable=False)
    is_lockable = models.BooleanField(_("lockable"), default=False)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("False once the enum member is gone; rows are never deleted."),
    )

    class Meta:
        verbose_name = _("permission")
        verbose_name_plural = _("permissions")
        ordering = ("category", "code")

    def __str__(self) -> str:
        return self.code


class RoleQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("created_by", "updated_by").prefetch_related(
            "grants__permission"
        )

    def active(self):
        return self.filter(status=RoleStatus.ACTIVE)


class Role(SoftDeleteBaseModel):
    slug = models.SlugField(_("slug"), max_length=60)
    name = models.CharField(_("name"), max_length=80)
    description = models.CharField(_("description"), max_length=300, blank=True)
    kind = models.CharField(
        _("kind"),
        max_length=20,
        choices=UserRole.choices,
        help_text=_(
            "The system role this is built from. Fixes its place on the ladder "
            "and how far it sees; a custom role adjusts the set, never the kind."
        ),
    )
    status = models.CharField(
        _("status"), max_length=10, choices=RoleStatus.choices, default=RoleStatus.ACTIVE
    )
    is_system = models.BooleanField(_("system"), default=False, editable=False)
    is_locked = models.BooleanField(
        _("locked"),
        default=False,
        help_text=_("Only a superadmin with a step-up may edit a locked role."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(RoleQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ("-is_system", "kind", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                name="role_slug_unique",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(grant.permission.code for grant in self.grants.all())


class RolePermission(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="grants")
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT, related_name="grants")
    # Blank, not null: "the kind's floor" is a real answer, spelled as the
    # empty string so the column stays a plain CharField (DJ001).
    scope = models.CharField(
        _("scope"),
        max_length=10,
        choices=PermissionScope.choices,
        blank=True,
        default="",
        help_text=_("Empty means the role kind's floor."),
    )
    is_locked = models.BooleanField(_("locked"), default=False)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("role permission")
        verbose_name_plural = _("role permissions")
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.role_id}:{self.permission_id}"
