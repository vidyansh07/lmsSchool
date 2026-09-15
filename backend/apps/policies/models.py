"""Policy management (ERP Phase 3, ADR-04).

`AcademicPolicy` (academic rules) and `SystemSetting` (institution settings)
already have their own named-column shape, chosen on purpose (D-024, D-032):
the resolver, the admin form and the API cannot drift. That still holds, and
neither table moves here.

Everything else the ERP configures — authentication, password, session,
risk, performance weights, communication, export, deletion, approval, file
upload, notification — is read by code that did not exist before this phase,
so a generic `Policy(category, key, value JSON)` with a code-defined schema
registry (`apps.policies.schemas.POLICY_SCHEMAS`) gives named, validated
settings without a table per category.

Two layers, like `AcademicPolicy`
----------------------------------
A row is either institution-wide (`scope=global`, `branch=NULL`) or one
centre's override (`scope=branch`, `branch` set). Resolution — branch
override, then global, then the schema default — lives in exactly one place:
`apps.policies.resolver.policy()`.

Why two partial unique constraints, not one
--------------------------------------------
"One row per (category, key, branch)" cannot be a single `UniqueConstraint`
on those three columns: PostgreSQL does not treat two `NULL`s as equal, so
two global rows for the same key (`branch IS NULL` on both) would not
collide and the "one" in "one row" would not be a fact about the database.
`ScopeGrant` met the identical shape (exactly one of two nullable relations)
and solved it the same way — one partial constraint for the global case,
one for the branch case — which is followed here rather than invented anew.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class PolicyScope(models.TextChoices):
    GLOBAL = "global", _("Institution-wide")
    BRANCH = "branch", _("Branch override")


class PolicyQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("branch", "updated_by")


class Policy(SoftDeleteBaseModel):
    """One configured value: a schema key, at global or one centre's scope."""

    category = models.CharField(_("category"), max_length=30)
    key = models.CharField(_("key"), max_length=60)
    scope = models.CharField(
        _("scope"), max_length=10, choices=PolicyScope.choices, default=PolicyScope.GLOBAL
    )
    branch = models.ForeignKey(
        "organisation.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="policies",
        help_text=_("Set only when scope is 'branch'."),
    )
    value = models.JSONField(_("value"), help_text=_("Validated against POLICY_SCHEMAS on write."))
    version = models.PositiveIntegerField(_("version"), default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(PolicyQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("policy")
        verbose_name_plural = _("policies")
        ordering = ("category", "key", "branch_id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope=PolicyScope.GLOBAL, branch__isnull=True)
                    | models.Q(scope=PolicyScope.BRANCH, branch__isnull=False)
                ),
                name="policy_scope_matches_branch",
            ),
            models.UniqueConstraint(
                fields=["category", "key"],
                condition=models.Q(branch__isnull=True, deleted_at__isnull=True),
                name="policy_global_unique",
            ),
            models.UniqueConstraint(
                fields=["category", "key", "branch"],
                condition=models.Q(branch__isnull=False, deleted_at__isnull=True),
                name="policy_branch_unique",
            ),
        ]

    def __str__(self) -> str:
        where = f"@{self.branch_id}" if self.branch_id else ""
        return f"{self.category}.{self.key}{where}"


class PolicyVersion(BaseModel):
    """One prior value of a `Policy`, kept forever (D-019 extended to
    configuration history). Survives its policy being reset: a reset soft-
    deletes the `Policy` row, never a `PolicyVersion`, so the history stays
    readable across a reset-and-reconfigure."""

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField(_("version"))
    value = models.JSONField(_("value"))
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reason = models.CharField(_("reason"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("policy version")
        verbose_name_plural = _("policy versions")
        ordering = ("-version",)

    def __str__(self) -> str:
        return f"{self.policy_id} v{self.version}"
