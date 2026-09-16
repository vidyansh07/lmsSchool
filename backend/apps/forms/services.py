"""Dynamic forms business rules (ERP Phase 8).

Every rule about building, versioning and answering a form lives here.
Views resolve *which* definition/version a URL names (`views.py`); this
module never re-derives that, it is handed the row.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.caching import forget
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError

from .models import (
    FormDefinition,
    FormField,
    FormFieldType,
    FormResponse,
    FormVersion,
    FormVersionStatus,
)
from .validation import is_snake_case, validate_payload


def _require_manage(actor: Any) -> None:
    if not has_capability(actor, Capability.FORM_MANAGE):
        raise AuthorityError("You do not have authority to manage forms.")


def _published_cache_key(slug: str) -> str:
    return f"form:published:{slug}"


def _forget_published(slug: str) -> None:
    forget(_published_cache_key(slug))


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


@transaction.atomic
def create_definition(*, actor, slug: str, name: str, entity: str) -> FormDefinition:
    """Create a definition and its first (empty, draft) version."""
    _require_manage(actor)
    if FormDefinition.objects.filter(slug=slug).exists():
        raise ConflictError({"slug": ["A form with this slug already exists."]})

    try:
        with transaction.atomic():
            definition = FormDefinition.objects.create(
                slug=slug,
                name=name,
                entity=entity,
                created_by=actor if getattr(actor, "pk", None) else None,
            )
    except IntegrityError:
        # A concurrent create won the slug-uniqueness race between the
        # `exists()` check above and this insert; the DB constraint (not
        # this service) is what actually prevented the duplicate, so
        # translate its IntegrityError into the same ConflictError the
        # pre-check raises instead of surfacing a 500. The nested atomic()
        # confines the failed insert to its own savepoint so the outer
        # transaction started by this function is still usable afterwards.
        raise ConflictError({"slug": ["A form with this slug already exists."]}) from None
    version = FormVersion.objects.create(
        definition=definition, number=1, status=FormVersionStatus.DRAFT
    )
    record(
        action=AuditAction.FORM_DEFINITION_CREATED,
        actor=actor,
        resource_type="form_definition",
        resource_id=definition.pk,
        context={"slug": slug, "name": name, "entity": entity},
        durable=False,
    )
    record(
        action=AuditAction.FORM_VERSION_CREATED,
        actor=actor,
        resource_type="form_version",
        resource_id=version.pk,
        context={"definition": str(definition.pk), "number": version.number},
        durable=False,
    )
    return definition


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@transaction.atomic
def create_draft_version(
    *, actor, definition: FormDefinition, cloned_from: FormVersion | None = None
) -> FormVersion:
    """A new draft version for `definition`. Refused if one already exists."""
    _require_manage(actor)
    if FormVersion.objects.filter(definition=definition, status=FormVersionStatus.DRAFT).exists():
        raise ConflictError({"non_field_errors": ["A draft version already exists for this form."]})

    next_number = (
        FormVersion.objects.filter(definition=definition)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
        or 0
    ) + 1
    try:
        with transaction.atomic():
            version = FormVersion.objects.create(
                definition=definition,
                number=next_number,
                status=FormVersionStatus.DRAFT,
                cloned_from=cloned_from,
            )
    except IntegrityError:
        # A concurrent caller raced this one between the draft-exists check
        # (or the next-number computation) and this insert and won the
        # `form_version_number_unique` constraint; translate that into the
        # same ConflictError the pre-check raises rather than a 500. The
        # nested atomic() keeps the failed insert on its own savepoint so
        # the outer transaction is still usable afterwards.
        raise ConflictError(
            {"non_field_errors": ["A draft version already exists for this form."]}
        ) from None
    if cloned_from is not None:
        FormField.objects.bulk_create(
            [
                FormField(
                    version=version,
                    key=field.key,
                    label=field.label,
                    help=field.help,
                    type=field.type,
                    required=field.required,
                    order=field.order,
                    group=field.group,
                    options=field.options,
                    validation=field.validation,
                    visible_to_student=field.visible_to_student,
                    performance_key=field.performance_key,
                )
                for field in cloned_from.fields.all()
            ]
        )
    record(
        action=AuditAction.FORM_VERSION_CREATED,
        actor=actor,
        resource_type="form_version",
        resource_id=version.pk,
        context={
            "definition": str(definition.pk),
            "number": version.number,
            "cloned_from": version.cloned_from_id and str(version.cloned_from_id),
        },
        durable=False,
    )
    return version


def _validate_field_payload(fields: list[dict[str, Any]]) -> None:
    seen_keys: set[str] = set()
    errors: dict[str, list[str]] = {}
    valid_types = set(FormFieldType.values)
    for index, field in enumerate(fields):
        key = field.get("key")
        prefix = key or f"#{index}"
        if not key or not is_snake_case(key):
            errors[prefix] = ["Field keys must be snake_case."]
            continue
        if key in seen_keys:
            errors[key] = ["Duplicate field key in this version."]
            continue
        seen_keys.add(key)
        if field.get("type") not in valid_types:
            errors[key] = [f"Unknown field type: {field.get('type')!r}."]
    if errors:
        raise ApplicationError(errors)


@transaction.atomic
def set_fields(*, actor, version: FormVersion, fields: list[dict[str, Any]]) -> FormVersion:
    """Full replace of `version`'s fields. Refused once the version is published."""
    _require_manage(actor)
    if version.status != FormVersionStatus.DRAFT:
        raise ConflictError(
            {
                "non_field_errors": [
                    "A published version's fields are immutable. Create a new draft."
                ]
            }
        )
    _validate_field_payload(fields)

    version.fields.all().delete()
    FormField.objects.bulk_create(
        [
            FormField(
                version=version,
                key=field["key"],
                label=field.get("label", ""),
                help=field.get("help", ""),
                type=field["type"],
                required=bool(field.get("required", False)),
                order=field.get("order", index),
                group=field.get("group", ""),
                options=field.get("options", []),
                validation=field.get("validation", {}),
                visible_to_student=bool(field.get("visible_to_student", False)),
                performance_key=field.get("performance_key") or "",
            )
            for index, field in enumerate(fields)
        ]
    )
    record(
        action=AuditAction.FORM_FIELDS_REPLACED,
        actor=actor,
        resource_type="form_version",
        resource_id=version.pk,
        context={
            "definition": str(version.definition_id),
            "number": version.number,
            "count": len(fields),
        },
        durable=False,
    )
    return version


def _schema_hash(version: FormVersion) -> str:
    """sha256 of the ordered field set: (key, type, required, options, validation)."""
    ordered = [
        (field.key, field.type, field.required, field.options, field.validation)
        for field in version.fields.order_by("order", "key")
    ]
    payload = json.dumps(ordered, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@transaction.atomic
def publish_version(*, actor, version: FormVersion) -> FormVersion:
    """Publish `version`, archiving whatever was published before it.

    Refused if the computed hash is identical to the currently-published
    version's — "nothing changed" is not worth a new published version.
    """
    _require_manage(actor)

    # Lock every version row of this definition before checking anything.
    # Two concurrent publish_version calls for different draft versions of
    # the same definition must not both pass the "what's currently
    # published" check before either writes — that is exactly the
    # check-then-act race that would leave two versions PUBLISHED at once,
    # the invariant the FormVersion docstring assigns to this module. Since
    # nothing about "the currently published version" is a static shape a
    # UniqueConstraint can express, the lock has to be taken here: a
    # SELECT ... FOR UPDATE across the definition's own version rows, so a
    # second concurrent call blocks until the first one's transaction
    # commits (or rolls back) and then re-reads fresh, correct statuses.
    locked_versions = {
        row.pk: row
        for row in FormVersion.objects.select_for_update().filter(definition=version.definition_id)
    }
    # Refresh the caller's own instance in place (never rebind `version` to
    # a different object) — callers hold onto and keep using the instance
    # they passed in.
    fresh = locked_versions.get(version.pk)
    if fresh is not None:
        version.status = fresh.status
        version.schema_hash = fresh.schema_hash
        version.published_at = fresh.published_at
        version.published_by_id = fresh.published_by_id

    if version.status == FormVersionStatus.PUBLISHED:
        raise ConflictError({"non_field_errors": ["This version is already published."]})

    new_hash = _schema_hash(version)
    current = next(
        (
            row
            for row in locked_versions.values()
            if row.pk != version.pk and row.status == FormVersionStatus.PUBLISHED
        ),
        None,
    )
    if current is not None and current.schema_hash == new_hash:
        raise ConflictError({"non_field_errors": ["Nothing changed since the published version."]})

    if current is not None:
        current.status = FormVersionStatus.ARCHIVED
        current.save(update_fields=["status", "updated_at"])

    version.status = FormVersionStatus.PUBLISHED
    version.schema_hash = new_hash
    version.published_at = timezone.now()
    version.published_by = actor if getattr(actor, "pk", None) else None
    version.save(
        update_fields=["status", "schema_hash", "published_at", "published_by", "updated_at"]
    )

    _forget_published(version.definition.slug)
    record(
        action=AuditAction.FORM_PUBLISHED,
        actor=actor,
        resource_type="form_version",
        resource_id=version.pk,
        context={
            "definition": str(version.definition_id),
            "slug": version.definition.slug,
            "number": version.number,
            "schema_hash": new_hash,
        },
        durable=False,
    )
    return version


@transaction.atomic
def unpublish_version(*, actor, version: FormVersion) -> FormVersion:
    """Return the currently-published version to draft so it can be edited."""
    _require_manage(actor)
    if version.status != FormVersionStatus.PUBLISHED:
        raise ConflictError({"non_field_errors": ["This version is not published."]})

    version.status = FormVersionStatus.DRAFT
    version.save(update_fields=["status", "updated_at"])
    _forget_published(version.definition.slug)
    record(
        action=AuditAction.FORM_UNPUBLISHED,
        actor=actor,
        resource_type="form_version",
        resource_id=version.pk,
        context={
            "definition": str(version.definition_id),
            "slug": version.definition.slug,
            "number": version.number,
        },
        durable=False,
    )
    return version


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def validate_response(*, actor, version: FormVersion, values: dict[str, Any]) -> dict[str, Any]:
    """Validate `values` against `version`'s fields. Does not persist.

    Relation fields are checked against `actor`'s own visibility, so a
    caller cannot reference a record they could not otherwise see.
    """
    return validate_payload(version=version, values=values, actor=actor)


@transaction.atomic
def submit_response(
    *, actor, version: FormVersion, values: dict[str, Any], content_object: Any
) -> FormResponse:
    """Validate and persist a response against `content_object`.

    Only a published version accepts responses — a draft is still being
    designed, and there is no "the" shape yet to answer against.
    """
    if version.status != FormVersionStatus.PUBLISHED:
        raise ApplicationError(
            {"non_field_errors": ["Only a published form version accepts responses."]}
        )
    cleaned = validate_response(actor=actor, version=version, values=values)
    response = FormResponse.objects.create(
        version=version,
        values=cleaned,
        content_type=ContentType.objects.get_for_model(content_object),
        object_id=content_object.pk,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    return response


__all__ = [
    "create_definition",
    "create_draft_version",
    "publish_version",
    "set_fields",
    "submit_response",
    "unpublish_version",
    "validate_response",
]
