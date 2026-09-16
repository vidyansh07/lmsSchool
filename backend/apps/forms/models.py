"""Dynamic forms (ERP Phase 8).

A `FormDefinition` names a form (`mock-interview`, `student-custom`); a
`FormVersion` is one shape of it, with `FormField` rows describing the
fields; a `FormResponse` is one filled-in submission, stamped against the
version it was answered on so a historical record still renders correctly
after the definition moves on (`DATA_MODEL.md` §4, `FORM_CATALOG.md`
"Versioning and visibility").

Only one version per definition may be `published` at a time — enforced in
`services.py`, not by a database constraint, because "the currently
published one" is a temporal fact (archiving the old one and publishing the
new one happen together in one transaction) rather than a static shape a
`UniqueConstraint` can express without also blocking the in-flight moment
where a version is being swapped in.

`FormResponse` is a plain, append-only `BaseModel`: a correction is a new
row, never an edit to an old one, so a form rendered against last month's
answer keeps showing what was actually submitted then.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    BaseModel,
    SoftDeleteBaseModel,
    SoftDeleteQuerySet,
    soft_delete_managers,
)


class FormEntity(models.TextChoices):
    ACTIVITY = "activity", _("Activity")
    STUDENT = "student", _("Student")
    REGISTRATION = "registration", _("Registration")
    REVIEW = "review", _("Review")


class FormDefinitionStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    ARCHIVED = "archived", _("Archived")


class FormVersionStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


#: The 17 field types the validator in `validation.py` knows about. Kept
#: here, not just there, so the model's `choices` and the validator's
#: dispatch table cannot drift silently — a type absent from one but not the
#: other is exactly the kind of gap a migration review should catch.
class FormFieldType(models.TextChoices):
    TEXT = "text", _("Text")
    TEXTAREA = "textarea", _("Textarea")
    NUMBER = "number", _("Number")
    DECIMAL = "decimal", _("Decimal")
    DATE = "date", _("Date")
    DATETIME = "datetime", _("Date and time")
    BOOLEAN = "boolean", _("Boolean")
    SELECT = "select", _("Select")
    MULTISELECT = "multiselect", _("Multi-select")
    RADIO = "radio", _("Radio")
    CHECKBOX = "checkbox", _("Checkbox")
    EMAIL = "email", _("Email")
    PHONE = "phone", _("Phone")
    URL = "url", _("URL")
    FILE = "file", _("File")
    IMAGE = "image", _("Image")
    RICHTEXT = "richtext", _("Rich text")
    RELATION = "relation", _("Relation")


class FormDefinitionQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("created_by")


class FormDefinition(SoftDeleteBaseModel):
    """One named form. The fields live on its versions, never here."""

    slug = models.CharField(_("slug"), max_length=60)
    name = models.CharField(_("name"), max_length=150)
    entity = models.CharField(_("entity"), max_length=20, choices=FormEntity.choices)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=FormDefinitionStatus.choices,
        default=FormDefinitionStatus.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(FormDefinitionQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("form definition")
        verbose_name_plural = _("form definitions")
        ordering = ("slug",)
        constraints = [
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="form_definition_slug_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.slug


class FormVersionQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("definition", "published_by", "cloned_from")


class FormVersion(BaseModel):
    """One shape of a definition. Immutable once `published` (`services.py`
    refuses field writes; a change goes through a new draft version)."""

    definition = models.ForeignKey(
        FormDefinition, on_delete=models.CASCADE, related_name="versions"
    )
    number = models.PositiveIntegerField(_("number"))
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=FormVersionStatus.choices,
        default=FormVersionStatus.DRAFT,
    )
    schema_hash = models.CharField(_("schema hash"), max_length=64, blank=True)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    cloned_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="clones"
    )

    objects = models.Manager.from_queryset(FormVersionQuerySet)()

    class Meta:
        verbose_name = _("form version")
        verbose_name_plural = _("form versions")
        ordering = ("definition_id", "-number")
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "number"], name="form_version_number_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.definition_id} v{self.number}"

    def performance_field(self) -> FormField | None:
        """The one field this version derives a numeric score from — the
        field flagged with a non-empty `performance_key` — or `None` if none
        is. `apps.work.services._extract_score` (deriving the score) and
        `apps.work.serializers.ActivityDetailSerializer` (deciding whether a
        student caller may see it) both call this, so "which field is the
        score field" has exactly one definition."""
        return self.fields.exclude(performance_key="").order_by("order").first()


class FormField(BaseModel):
    """One field on a version. Full-replaced by `services.set_fields`, never
    patched field-by-field — a version's field list is a single unit."""

    version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(_("key"), max_length=60)
    label = models.CharField(_("label"), max_length=150)
    help = models.CharField(_("help text"), max_length=500, blank=True)
    type = models.CharField(_("type"), max_length=20, choices=FormFieldType.choices)
    required = models.BooleanField(_("required"), default=False)
    order = models.PositiveIntegerField(_("order"), default=0)
    group = models.CharField(_("group"), max_length=60, blank=True)
    options = models.JSONField(_("options"), default=list, blank=True)
    validation = models.JSONField(_("validation"), default=dict, blank=True)
    visible_to_student = models.BooleanField(_("visible to student"), default=False)
    # Blank, not null: "no performance key" is a real answer, spelled as the
    # empty string so the column stays a plain CharField (DJ001, the same
    # choice `RolePermission.scope` makes).
    performance_key = models.CharField(_("performance key"), max_length=30, blank=True, default="")

    class Meta:
        verbose_name = _("form field")
        verbose_name_plural = _("form fields")
        ordering = ("version_id", "order")
        constraints = [
            models.UniqueConstraint(fields=["version", "key"], name="form_field_key_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.version_id}:{self.key}"


class FormResponseQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("version", "version__definition", "created_by", "content_type")


class FormResponse(BaseModel):
    """One submitted response. Append-only: a correction is a new row."""

    version = models.ForeignKey(FormVersion, on_delete=models.PROTECT, related_name="responses")
    values = models.JSONField(_("values"), default=dict)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="+")
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = models.Manager.from_queryset(FormResponseQuerySet)()

    class Meta:
        verbose_name = _("form response")
        verbose_name_plural = _("form responses")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="form_response_owner_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.version_id}:{self.pk}"
