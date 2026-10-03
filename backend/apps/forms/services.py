"""Dynamic forms business rules (ERP Phase 8).

Every rule about building, versioning and answering a form lives here.
Views resolve *which* definition/version a URL names (`views.py`); this
module never re-derives that, it is handed the row.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.common.caching import forget
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError

from .models import (
    DISPLAY_ONLY_FIELD_TYPES,
    FormAssignment,
    FormAssignmentStatus,
    FormDefinition,
    FormDefinitionStatus,
    FormField,
    FormFieldType,
    FormResponse,
    FormUpload,
    FormVersion,
    FormVersionStatus,
)
from .validation import SHOW_IF_OPERATORS, is_snake_case, validate_payload


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
                    show_if=field.show_if,
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


_CHOICE_PARENT_TYPES = frozenset(
    {FormFieldType.SELECT, FormFieldType.RADIO, FormFieldType.DEPENDENT_SELECT}
)


def _validate_field_payload(fields: list[dict[str, Any]]) -> None:
    seen_keys: set[str] = set()
    types_by_key: dict[str, str] = {}
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
        field_type = field.get("type")
        if field_type not in valid_types:
            errors[key] = [f"Unknown field type: {field_type!r}."]
            seen_keys.add(key)
            continue

        problems: list[str] = []
        if field_type == FormFieldType.DEPENDENT_SELECT:
            options = field.get("options")
            parent = options.get("parent") if isinstance(options, dict) else None
            if not parent or parent not in seen_keys:
                problems.append("A dependent select must name a field above it as its parent.")
            elif types_by_key.get(parent) not in _CHOICE_PARENT_TYPES:
                problems.append(
                    "A dependent select's parent must be a select, radio or dependent select."
                )
            if not isinstance(options, dict) or not isinstance(options.get("choices"), dict):
                problems.append("A dependent select needs a choices list for each parent answer.")

        show_if = field.get("show_if") or {}
        if show_if:
            if not isinstance(show_if, dict):
                problems.append("show_if must be an object.")
            else:
                target = show_if.get("field")
                if not target or target not in seen_keys:
                    problems.append("show_if must name a field above this one.")
                if show_if.get("op", "eq") not in SHOW_IF_OPERATORS:
                    problems.append(f"Unknown show_if operator: {show_if.get('op')!r}.")

        if field_type in DISPLAY_ONLY_FIELD_TYPES and field.get("required"):
            problems.append("A heading cannot be required.")

        if problems:
            errors[key] = problems
        seen_keys.add(key)
        types_by_key[key] = field_type
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
                show_if=field.get("show_if") or {},
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
    """sha256 of the ordered field set: (key, type, required, options, validation),
    plus ``show_if`` for a field that has one — appended only then, so a
    version published before conditional fields existed keeps its hash."""
    ordered = [
        (field.key, field.type, field.required, field.options, field.validation)
        + ((field.show_if,) if field.show_if else ())
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


def _version_in_use(version: FormVersion) -> bool:
    """Whether anything still waiting to be filled pinned this version."""
    from apps.work.models import OPEN_STATUSES, Activity

    if FormAssignment.objects.filter(version=version, status=FormAssignmentStatus.PENDING).exists():
        return True
    return Activity.objects.filter(form_version=version, status__in=OPEN_STATUSES).exists()


@transaction.atomic
def unpublish_version(*, actor, version: FormVersion) -> FormVersion:
    """Return the currently-published version to draft so it can be edited."""
    _require_manage(actor)
    if version.status != FormVersionStatus.PUBLISHED:
        raise ConflictError({"non_field_errors": ["This version is not published."]})
    if _version_in_use(version):
        raise ConflictError(
            {
                "non_field_errors": [
                    "Open activities or forms waiting to be filled use this version. "
                    "Create a new draft instead, so their fields do not change under them."
                ]
            }
        )

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
    *,
    actor,
    version: FormVersion,
    values: dict[str, Any],
    content_object: Any,
    pinned: bool = False,
) -> FormResponse:
    """Validate and persist a response against `content_object`.

    Only a published version accepts responses — a draft is still being
    designed, and there is no "the" shape yet to answer against. ``pinned``
    is for a record that fixed its version when it was created (an activity,
    a form assignment): it may still be answered on that version after a
    newer one was published and archived it, because that is the shape the
    person was asked to fill. A draft is refused either way.
    """
    accepted = {FormVersionStatus.PUBLISHED}
    if pinned:
        accepted.add(FormVersionStatus.ARCHIVED)
    if version.status not in accepted:
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


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def create_upload(*, actor, uploaded_file) -> FormUpload:
    """Store one file for a later `file`/`image` field answer.

    Checked with the same allowlist, signature sniffing and malware scan as a
    course resource (`apps.common.uploads.validate_resource_upload`), against
    the institution's `file_upload.max_mb` ceiling. The client's filename is
    kept only for display; the stored path is generated.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.common.uploads import validate_resource_upload
    from apps.policies.resolver import policy

    if uploaded_file is None:
        raise ApplicationError({"file": ["Choose a file to upload."]})
    limit_mb = int(policy("file_upload", "max_mb"))
    try:
        extension, content_type = validate_resource_upload(
            uploaded_file, limit_bytes=limit_mb * 1024 * 1024
        )
    except DjangoValidationError as exc:
        raise ApplicationError({"file": exc.messages}) from None

    original = PurePosixPath(getattr(uploaded_file, "name", "") or "").name
    upload = FormUpload(
        original_name=original[:255],
        extension=extension,
        content_type=content_type,
        size_bytes=uploaded_file.size or 0,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
    )
    upload.file = uploaded_file
    upload.save()
    return upload


# ---------------------------------------------------------------------------
# Assignments — sending a form to someone to fill
# ---------------------------------------------------------------------------


def _require_assign(actor: Any) -> None:
    if not has_capability(actor, Capability.FORM_ASSIGN):
        raise AuthorityError("You do not have authority to send or fill in forms.")


def published_version_of(definition: FormDefinition) -> FormVersion:
    version = (
        FormVersion.objects.filter(definition=definition, status=FormVersionStatus.PUBLISHED)
        .order_by("-number")
        .first()
    )
    if version is None:
        raise ApplicationError({"form": ["This form has no published version yet."]})
    return version


def _check_reach(actor, *, assigned_to, student) -> None:
    """A centre-bounded sender reaches only their own centre: the student
    the form is about must be one they can see, and the person it goes to
    must work (or study) at their centre."""
    from apps.organisation.scoping import actor_branch_id, is_unbounded
    from apps.students.access import visible_students

    if student is not None and not visible_students(actor).filter(pk=student.pk).exists():
        raise ApplicationError({"student": ["Was not found, or is not visible to you."]})
    if is_unbounded(actor):
        return
    branch_id = actor_branch_id(actor)
    if assigned_to.branch_id and assigned_to.branch_id != branch_id:
        raise ApplicationError(
            {"assigned_to": ["You can only send forms to people at your own centre."]}
        )


def _branch_for(*, actor, assigned_to, student, enquiry=None):
    if enquiry is not None and enquiry.branch_id:
        return enquiry.branch
    if student is not None and student.branch_id:
        return student.branch
    if getattr(assigned_to, "branch_id", None):
        return assigned_to.branch
    return getattr(actor, "branch", None) if getattr(actor, "branch_id", None) else None


@transaction.atomic
def assign_form(
    *,
    actor,
    definition: FormDefinition,
    assigned_to,
    student=None,
    enquiry=None,
    due_at=None,
    title: str = "",
    message: str = "",
    automation_run=None,
    enforce_authority: bool = True,
    notify_assignee: bool = True,
) -> FormAssignment:
    """Send ``definition`` to ``assigned_to`` to fill, pinned to its published
    version. ``enforce_authority=False`` is for the automation engine, whose
    rule author's `form.assign` was already checked when the rule was saved
    (ADR-13: a run executes as the system)."""
    if enforce_authority:
        _require_assign(actor)
        _check_reach(actor, assigned_to=assigned_to, student=student)
        if enquiry is not None:
            from apps.enquiries.access import visible_enquiries

            if not visible_enquiries(actor).filter(pk=enquiry.pk).exists():
                raise ApplicationError({"enquiry": ["Was not found, or is not visible to you."]})
    if definition.status != FormDefinitionStatus.ACTIVE:
        raise ApplicationError({"form": ["This form is archived."]})
    if not assigned_to.is_active:
        raise ApplicationError({"assigned_to": ["This person's account is not active."]})
    version = published_version_of(definition)

    assignment = FormAssignment.objects.create(
        definition=definition,
        version=version,
        assigned_to=assigned_to,
        requested_by=actor if getattr(actor, "pk", None) else None,
        student=student,
        enquiry=enquiry,
        branch=_branch_for(actor=actor, assigned_to=assigned_to, student=student, enquiry=enquiry),
        due_at=due_at,
        title=(title or definition.name)[:200],
        message=message or "",
        automation_run=automation_run,
    )
    record(
        action=AuditAction.FORM_ASSIGNED,
        actor=actor,
        resource_type="form_assignment",
        resource_id=assignment.pk,
        context={
            "form": definition.slug,
            "version": version.number,
            "assigned_to": str(assigned_to.pk),
            "student": str(student.pk) if student is not None else None,
            "enquiry": str(enquiry.pk) if enquiry is not None else None,
            "automation_run": str(automation_run.pk) if automation_run is not None else None,
        },
        durable=False,
    )
    if notify_assignee and getattr(actor, "pk", None) != assigned_to.pk:
        from apps.notifications.models import NotificationKind
        from apps.notifications.services import notify

        notify(
            recipient=assigned_to,
            kind=NotificationKind.FORM_ASSIGNED,
            title=f"Form to fill: {assignment.title}",
            body=assignment.message,
            link_path=f"/forms/{assignment.pk}",
            resource_type="form_assignment",
            resource_id=assignment.pk,
        )
    return assignment


@transaction.atomic
def submit_assignment(
    *, actor, assignment: FormAssignment, values: dict[str, Any]
) -> FormAssignment:
    """The assignee answers the form. The row is locked first, so two
    submissions racing each other cannot both land — the second one sees
    `submitted` and is refused."""
    locked = FormAssignment.objects.select_for_update().get(pk=assignment.pk)
    if locked.assigned_to_id != getattr(actor, "pk", None):
        raise AuthorityError("Only the person this form was sent to can submit it.")
    if locked.status == FormAssignmentStatus.SUBMITTED:
        raise ConflictError({"non_field_errors": ["This form was already submitted."]})
    if locked.status == FormAssignmentStatus.CANCELLED:
        raise ConflictError({"non_field_errors": ["This form was cancelled."]})

    response = submit_response(
        actor=actor, version=locked.version, values=values, content_object=locked, pinned=True
    )
    locked.status = FormAssignmentStatus.SUBMITTED
    locked.submitted_at = timezone.now()
    locked.response = response
    locked.save(update_fields=["status", "submitted_at", "response", "updated_at"])

    record(
        action=AuditAction.FORM_ASSIGNMENT_SUBMITTED,
        actor=actor,
        resource_type="form_assignment",
        resource_id=locked.pk,
        context={"form": locked.definition.slug, "response": str(response.pk)},
        durable=False,
    )
    if locked.requested_by_id and locked.requested_by_id != actor.pk:
        from apps.notifications.models import NotificationKind
        from apps.notifications.services import notify

        notify(
            recipient=locked.requested_by,
            kind=NotificationKind.FORM_SUBMITTED,
            title=f"Form submitted: {locked.title}",
            body=f"{actor.get_full_name() or actor.email} filled in {locked.definition.name}.",
            link_path=f"/forms/{locked.pk}",
            resource_type="form_assignment",
            resource_id=locked.pk,
        )

    from .signals import form_submitted

    form_submitted.send(sender=FormAssignment, assignment=locked, actor=actor)
    return locked


@transaction.atomic
def fill_form(
    *,
    actor,
    definition: FormDefinition,
    values: dict[str, Any],
    student=None,
    enquiry=None,
) -> FormAssignment:
    """Fill in a form directly — a counsellor entering a walk-in enquiry, say.
    Recorded as an assignment to oneself that is submitted at once, so a
    direct entry and a requested one look the same to everything downstream,
    the `FORM_SUBMITTED` automation trigger included."""
    assignment = assign_form(
        actor=actor,
        definition=definition,
        assigned_to=actor,
        student=student,
        enquiry=enquiry,
        notify_assignee=False,
    )
    return submit_assignment(actor=actor, assignment=assignment, values=values)


@transaction.atomic
def cancel_assignment(*, actor, assignment: FormAssignment, reason: str = "") -> FormAssignment:
    from .access import can_cancel_assignment

    locked = FormAssignment.objects.select_for_update().get(pk=assignment.pk)
    if not can_cancel_assignment(actor, locked):
        raise AuthorityError("You cannot cancel this form request.")
    if locked.status != FormAssignmentStatus.PENDING:
        raise ConflictError(
            {"non_field_errors": ["Only a form still waiting to be filled can be cancelled."]}
        )
    locked.status = FormAssignmentStatus.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=["status", "cancelled_at", "updated_at"])
    record(
        action=AuditAction.FORM_ASSIGNMENT_CANCELLED,
        actor=actor,
        resource_type="form_assignment",
        resource_id=locked.pk,
        context={"form": locked.definition.slug, "reason": reason[:500]},
        durable=False,
    )
    return locked


__all__ = [
    "assign_form",
    "cancel_assignment",
    "create_definition",
    "create_draft_version",
    "create_upload",
    "fill_form",
    "publish_version",
    "published_version_of",
    "set_fields",
    "submit_assignment",
    "submit_response",
    "unpublish_version",
    "validate_response",
]
