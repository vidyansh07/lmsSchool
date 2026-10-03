"""The one place that knows all of the form builder's field types.

``validate_payload`` takes a :class:`~apps.forms.models.FormVersion` and a
raw ``values`` dict, and returns a cleaned dict or raises
:class:`~apps.common.exceptions.ApplicationError` with every field's errors
at once (``details: {field: [...]}]``) — never just the first one, so a
caller fixing a submission does not have to resubmit N times to discover N
mistakes.

Rules are exactly ``FORM_CATALOG.md``'s "Validation rules" table:

======================== ============================================
type                     rule
======================== ============================================
text/textarea/richtext   string; min_length/max_length/pattern; richtext
                         additionally sanitised (allowlist tags)
number/decimal           numeric; min/max/step; decimal kept as a string
date/datetime            ISO 8601 string; not_past/not_future, min/max
boolean                  bool
select/radio             value in options
multiselect/checkbox     list, subset of options, min_items/max_items
email/phone/url          format (E.164-ish phone, https-only url)
file/image               an existing upload id; accept/max_mb checked
                         against the upload's stored metadata
relation                 uuid resolving through the caller's own
                         ``visible_*`` for that model
time                     ``HH:MM`` (or ``HH:MM:SS``); min/max
rating                   whole number from 1 to ``validation.max``
                         (default 5)
consent                  bool; a required consent must be ``true``
hidden                   string up to 500 characters; ``validation.
                         default`` fills it when nothing is sent
heading                  never takes a value (display only)
dependent_select         a value from ``options.choices[<parent
                         answer>]``, where ``options.parent`` names
                         the field it depends on
======================== ============================================

Conditional fields
------------------
A field with ``show_if`` (``{"field": key, "op": op, "value": v}``, ``op``
one of eq, ne, in, not_in, filled, empty) is shown only while that other
field's answer matches. A field that is not shown is never required, and any
value sent for it is dropped rather than stored — the person filling the
form could not see it, so whatever the client left in it is not an answer.
A field depending on a hidden field is itself hidden.

Upload resolution
-----------------
A ``file``/``image`` value is the id of a :class:`~apps.forms.models.
FormUpload` row, created by ``POST /api/v1/forms/uploads/`` before the form
is submitted. :data:`UPLOAD_RESOLVER` turns that id into
``{"content_type", "size_bytes", "filename", "uploaded_by"}`` (or ``None``
when it does not resolve), and the field's ``accept``/``max_mb`` rules are
checked against that stored metadata, never against anything the client
claims. An upload can only be attached by the person who uploaded it, so
one person cannot submit another person's file by guessing its id. The
resolver stays a module-level seam so tests can substitute it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from apps.common.exceptions import ApplicationError

from .models import DISPLAY_ONLY_FIELD_TYPES, FormField, FormFieldType, FormVersion

# ---------------------------------------------------------------------------
# Upload resolution seam (see module docstring)
# ---------------------------------------------------------------------------


def _default_upload_resolver(upload_id: str) -> dict[str, Any] | None:
    from .models import FormUpload

    try:
        upload = FormUpload.objects.filter(pk=UUID(str(upload_id))).first()
    except (ValueError, TypeError, AttributeError):
        return None
    if upload is None:
        return None
    return {
        "content_type": upload.content_type,
        "size_bytes": upload.size_bytes,
        "filename": upload.original_name or f"upload{upload.extension}",
        "uploaded_by": str(upload.uploaded_by_id) if upload.uploaded_by_id else None,
    }


#: Module-level so tests can monkeypatch it without changing call sites.
UPLOAD_RESOLVER = _default_upload_resolver


# ---------------------------------------------------------------------------
# Relation resolution
# ---------------------------------------------------------------------------


def _visible_queryset(model_name: str, actor: Any):
    if model_name == "student":
        from apps.students.access import visible_students

        return visible_students(actor)
    if model_name == "trainer":
        from apps.trainers.access import visible_trainers

        return visible_trainers(actor)
    if model_name == "batch":
        from apps.batches.access import visible_batches

        return visible_batches(actor)
    return None


# ---------------------------------------------------------------------------
# Richtext sanitisation — allowlist tag strip, regex-based, no dependency
# ---------------------------------------------------------------------------

_RICHTEXT_ALLOWED_TAGS = frozenset(
    {"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "blockquote", "code", "pre", "a"}
)
_RICHTEXT_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>")
_RICHTEXT_HREF_RE = re.compile(r'href\s*=\s*"(https://[^"<>]*)"', re.IGNORECASE)
_RICHTEXT_SCRIPT_RE = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")


def sanitise_richtext(value: str) -> str:
    """Strip everything but a small allowlist of formatting tags.

    Script/style blocks are removed with their content; every other
    disallowed tag is unwrapped (its content kept, the tag dropped); an
    ``<a>`` keeps only an ``https://`` ``href``, dropping every other
    attribute (in particular any ``on*`` event handler).
    """
    value = _RICHTEXT_SCRIPT_RE.sub("", value)

    def _replace(match: re.Match[str]) -> str:
        closing, tag, attrs = match.group(1), match.group(2).lower(), match.group(3)
        if tag not in _RICHTEXT_ALLOWED_TAGS:
            return ""
        if closing:
            return f"</{tag}>"
        if tag == "a":
            href_match = _RICHTEXT_HREF_RE.search(attrs)
            return f'<a href="{href_match.group(1)}">' if href_match else "<a>"
        return f"<{tag}>"

    return _RICHTEXT_TAG_RE.sub(_replace, value)


# ---------------------------------------------------------------------------
# Format checks
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
#: E.164-ish: optional '+', 8-15 digits, no leading zero.
_PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def is_snake_case(key: str) -> bool:
    return bool(_SNAKE_CASE_RE.match(key or ""))


def _parse_iso(value: str) -> datetime | None:
    try:
        text = value.replace("Z", "+00:00") if isinstance(value, str) else value
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Per-type validation. Each returns (cleaned_value, errors).
# ---------------------------------------------------------------------------


def _validate_text(value: Any, rules: dict[str, Any], *, richtext: bool) -> tuple[Any, list[str]]:
    errors: list[str] = []
    if not isinstance(value, str):
        return None, ["Must be text."]
    cleaned = sanitise_richtext(value) if richtext else value
    min_length = rules.get("min_length")
    max_length = rules.get("max_length")
    pattern = rules.get("pattern")
    if min_length is not None and len(cleaned) < min_length:
        errors.append(f"Must be at least {min_length} characters.")
    if max_length is not None and len(cleaned) > max_length:
        errors.append(f"Must be at most {max_length} characters.")
    if pattern and not re.search(pattern, cleaned):
        errors.append("Does not match the required format.")
    return cleaned, errors


def _validate_number(value: Any, rules: dict[str, Any]) -> tuple[Any, list[str]]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, ["Must be a number."]
    return _apply_numeric_rules(value, rules)


def _validate_decimal(value: Any, rules: dict[str, Any]) -> tuple[Any, list[str]]:
    if isinstance(value, bool):
        return None, ["Must be a decimal number."]
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, ["Must be a decimal number."]
    cleaned, errors = _apply_numeric_rules(decimal_value, rules)
    return (str(cleaned) if not errors else None), errors


def _apply_numeric_rules(value: Any, rules: dict[str, Any]) -> tuple[Any, list[str]]:
    is_decimal = isinstance(value, Decimal)
    errors: list[str] = []
    minimum = rules.get("min")
    maximum = rules.get("max")
    step = rules.get("step")
    minimum_bound = Decimal(str(minimum)) if is_decimal and minimum is not None else minimum
    maximum_bound = Decimal(str(maximum)) if is_decimal and maximum is not None else maximum
    if minimum_bound is not None and value < minimum_bound:
        errors.append(f"Must be at least {minimum}.")
    if maximum_bound is not None and value > maximum_bound:
        errors.append(f"Must be at most {maximum}.")
    if step:
        step_value = Decimal(str(step)) if is_decimal else step
        base = minimum_bound if minimum_bound is not None else (Decimal(0) if is_decimal else 0)
        remainder = (value - base) % step_value
        if remainder != 0:
            errors.append(f"Must be a multiple of {step} from {base}.")
    return value, errors


def _validate_date(value: Any, rules: dict[str, Any], *, with_time: bool) -> tuple[Any, list[str]]:
    if not isinstance(value, str):
        return None, ["Must be an ISO 8601 date string."]
    parsed = _parse_iso(value)
    if parsed is None:
        return None, ["Must be a valid ISO 8601 date."]
    if not with_time and "T" in value:
        return None, ["Must be a date without a time component."]
    errors: list[str] = []
    now = _now()
    compare = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if rules.get("not_past") and compare < now:
        errors.append("Cannot be in the past.")
    if rules.get("not_future") and compare > now:
        errors.append("Cannot be in the future.")
    minimum = rules.get("min")
    maximum = rules.get("max")
    if minimum is not None:
        min_parsed = _parse_iso(minimum)
        if min_parsed is not None and compare < (
            min_parsed if min_parsed.tzinfo is not None else min_parsed.replace(tzinfo=UTC)
        ):
            errors.append(f"Must be on or after {minimum}.")
    if maximum is not None:
        max_parsed = _parse_iso(maximum)
        if max_parsed is not None and compare > (
            max_parsed if max_parsed.tzinfo is not None else max_parsed.replace(tzinfo=UTC)
        ):
            errors.append(f"Must be on or before {maximum}.")
    return value, errors


def _validate_boolean(value: Any) -> tuple[Any, list[str]]:
    if not isinstance(value, bool):
        return None, ["Must be true or false."]
    return value, []


def _option_values(options: Any) -> set[str]:
    if not isinstance(options, list):
        return set()
    return {
        str(item.get("value")) for item in options if isinstance(item, dict) and "value" in item
    }


def _validate_choice(value: Any, options: Any) -> tuple[Any, list[str]]:
    allowed = _option_values(options)
    if not isinstance(value, str) or value not in allowed:
        return None, ["Must be one of the allowed options."]
    return value, []


def _validate_multi_relation(
    value: Any, options: dict[str, Any], rules: dict[str, Any], *, actor: Any
) -> tuple[Any, list[str]]:
    """`multiselect`/`checkbox` whose options are relation-shaped
    (``{"model": "module"}``), e.g. ``technical-interview.topics_covered``.

    Each item is a uuid checked against the same `visible_*` queryset a
    single `relation` field uses — a list of options-that-are-rows rather
    than a fixed list of ``{value, label}`` choices.
    """
    model_name = options.get("model")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, ["Must be a list of option values."]
    queryset = _visible_queryset(model_name, actor)
    if queryset is None:
        return None, [f"Unsupported relation model: {model_name}."]

    errors: list[str] = []
    uuid_values: list[str] = []
    for item in value:
        try:
            uuid_values.append(str(UUID(item)))
        except (ValueError, AttributeError, TypeError):
            errors.append("Contains options that are not allowed.")
            break
    else:
        visible_ids = {
            str(pk) for pk in queryset.filter(pk__in=uuid_values).values_list("pk", flat=True)
        }
        if any(uuid_value not in visible_ids for uuid_value in uuid_values):
            errors.append("Contains options that are not allowed.")

    min_items = rules.get("min_items")
    max_items = rules.get("max_items")
    if min_items is not None and len(value) < min_items:
        errors.append(f"Choose at least {min_items}.")
    if max_items is not None and len(value) > max_items:
        errors.append(f"Choose at most {max_items}.")
    return (uuid_values if not errors else None), errors


def _validate_multi_choice(
    value: Any, options: Any, rules: dict[str, Any], *, actor: Any
) -> tuple[Any, list[str]]:
    if isinstance(options, dict) and options.get("model"):
        return _validate_multi_relation(value, options, rules, actor=actor)
    allowed = _option_values(options)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, ["Must be a list of option values."]
    invalid = [item for item in value if item not in allowed]
    errors: list[str] = []
    if invalid:
        errors.append("Contains options that are not allowed.")
    min_items = rules.get("min_items")
    max_items = rules.get("max_items")
    if min_items is not None and len(value) < min_items:
        errors.append(f"Choose at least {min_items}.")
    if max_items is not None and len(value) > max_items:
        errors.append(f"Choose at most {max_items}.")
    return value, errors


def _validate_email(value: Any) -> tuple[Any, list[str]]:
    if not isinstance(value, str) or not _EMAIL_RE.match(value):
        return None, ["Enter a valid email address."]
    return value, []


def _validate_phone(value: Any) -> tuple[Any, list[str]]:
    if not isinstance(value, str) or not _PHONE_RE.match(value.replace(" ", "")):
        return None, ["Enter a valid phone number, e.g. +919876543210."]
    return value, []


def _validate_url(value: Any) -> tuple[Any, list[str]]:
    if not isinstance(value, str):
        return None, ["Enter a valid URL."]
    # Reject whitespace/control characters up front: urlparse tolerates them
    # inside components it does not itself scrutinise (e.g. a query or
    # fragment), which would otherwise let extra unvalidated text ride along
    # after a plausible https://netloc.
    if any(ord(char) < 0x21 or ord(char) == 0x7F for char in value):
        return None, ["Enter a valid https:// URL."]
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return None, ["Enter a valid https:// URL."]
    # The parse must round-trip back to exactly the submitted string, so
    # nothing in `value` fell outside what urlparse actually modelled.
    if urlunparse(parsed) != value:
        return None, ["Enter a valid https:// URL."]
    return value, []


def _validate_upload(
    value: Any, rules: dict[str, Any], *, image: bool, actor: Any
) -> tuple[Any, list[str]]:
    if not isinstance(value, str) or not value:
        return None, ["An uploaded file is required."]
    metadata = UPLOAD_RESOLVER(value)
    if metadata is None:
        return None, ["The uploaded file could not be found."]
    owner = metadata.get("uploaded_by")
    actor_id = getattr(actor, "pk", None)
    if owner and actor_id is not None and str(actor_id) != str(owner):
        # Same message as "not found": whether somebody else's upload with
        # this id exists is not something to confirm.
        return None, ["The uploaded file could not be found."]
    errors: list[str] = []
    content_type = str(metadata.get("content_type", ""))
    if image and not content_type.startswith("image/"):
        errors.append("The uploaded file is not an image.")
    accept = rules.get("accept")
    if accept:
        filename = str(metadata.get("filename", ""))
        extension = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
        if content_type not in accept and extension not in accept:
            errors.append(f"File type must be one of: {', '.join(accept)}.")
    max_mb = rules.get("max_mb")
    if max_mb is not None:
        size_bytes = metadata.get("size_bytes") or 0
        if size_bytes > max_mb * 1024 * 1024:
            errors.append(f"File must be {max_mb} MB or smaller.")
    return (value if not errors else None), errors


def _validate_relation(value: Any, options: Any, *, actor: Any) -> tuple[Any, list[str]]:
    model_name = (options or {}).get("model") if isinstance(options, dict) else None
    if not model_name:
        return None, ["This field is misconfigured (no relation model)."]
    try:
        uuid_value = str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None, ["Must be a valid id."]
    queryset = _visible_queryset(model_name, actor)
    if queryset is None:
        return None, [f"Unsupported relation model: {model_name}."]
    if not queryset.filter(pk=uuid_value).exists():
        return None, ["Was not found, or is not visible to you."]
    return uuid_value, []


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")


def _validate_time(value: Any, rules: dict[str, Any]) -> tuple[Any, list[str]]:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        return None, ["Enter a time as HH:MM."]
    errors: list[str] = []
    # Zero-padded HH:MM[:SS] strings order the same way the times do.
    minimum = rules.get("min")
    maximum = rules.get("max")
    if minimum and value < str(minimum):
        errors.append(f"Must be {minimum} or later.")
    if maximum and value > str(maximum):
        errors.append(f"Must be {maximum} or earlier.")
    return value, errors


def _validate_rating(value: Any, rules: dict[str, Any]) -> tuple[Any, list[str]]:
    maximum = rules.get("max") or 5
    if isinstance(value, bool) or not isinstance(value, int):
        return None, ["Choose a rating."]
    if value < 1 or value > maximum:
        return None, [f"Rating must be between 1 and {maximum}."]
    return value, []


def _validate_consent(value: Any, field: FormField) -> tuple[Any, list[str]]:
    if not isinstance(value, bool):
        return None, ["Must be true or false."]
    if field.required and value is not True:
        return None, ["You must agree to continue."]
    return value, []


def _validate_hidden(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None, ["Must be text."]
    text = str(value)
    if len(text) > 500:
        return None, ["Must be at most 500 characters."]
    return text, []


def dependent_choices(options: Any, parent_value: Any) -> list[dict[str, Any]]:
    """The options a `dependent_select` offers for one answer of its parent
    field — an empty list when the parent is unanswered or has no mapping."""
    if not isinstance(options, dict) or parent_value in (None, ""):
        return []
    choices = options.get("choices")
    if not isinstance(choices, dict):
        return []
    found = choices.get(str(parent_value))
    return found if isinstance(found, list) else []


def _validate_dependent_choice(
    value: Any, options: Any, parent_value: Any
) -> tuple[Any, list[str]]:
    if parent_value in (None, ""):
        return None, ["Answer the field this one depends on first."]
    allowed = _option_values(dependent_choices(options, parent_value))
    if not isinstance(value, str) or value not in allowed:
        return None, ["Must be one of the allowed options."]
    return value, []


_DISPATCH: dict[str, Any] = {
    FormFieldType.TEXT: lambda v, f, a: _validate_text(v, f.validation, richtext=False),
    FormFieldType.TEXTAREA: lambda v, f, a: _validate_text(v, f.validation, richtext=False),
    FormFieldType.RICHTEXT: lambda v, f, a: _validate_text(v, f.validation, richtext=True),
    FormFieldType.NUMBER: lambda v, f, a: _validate_number(v, f.validation),
    FormFieldType.DECIMAL: lambda v, f, a: _validate_decimal(v, f.validation),
    FormFieldType.DATE: lambda v, f, a: _validate_date(v, f.validation, with_time=False),
    FormFieldType.DATETIME: lambda v, f, a: _validate_date(v, f.validation, with_time=True),
    FormFieldType.BOOLEAN: lambda v, f, a: _validate_boolean(v),
    FormFieldType.SELECT: lambda v, f, a: _validate_choice(v, f.options),
    FormFieldType.RADIO: lambda v, f, a: _validate_choice(v, f.options),
    FormFieldType.MULTISELECT: lambda v, f, a: _validate_multi_choice(
        v, f.options, f.validation, actor=a
    ),
    FormFieldType.CHECKBOX: lambda v, f, a: _validate_multi_choice(
        v, f.options, f.validation, actor=a
    ),
    FormFieldType.EMAIL: lambda v, f, a: _validate_email(v),
    FormFieldType.PHONE: lambda v, f, a: _validate_phone(v),
    FormFieldType.URL: lambda v, f, a: _validate_url(v),
    FormFieldType.FILE: lambda v, f, a: _validate_upload(v, f.validation, image=False, actor=a),
    FormFieldType.IMAGE: lambda v, f, a: _validate_upload(v, f.validation, image=True, actor=a),
    FormFieldType.RELATION: lambda v, f, a: _validate_relation(v, f.options, actor=a),
    FormFieldType.TIME: lambda v, f, a: _validate_time(v, f.validation),
    FormFieldType.RATING: lambda v, f, a: _validate_rating(v, f.validation),
    FormFieldType.CONSENT: lambda v, f, a: _validate_consent(v, f),
    FormFieldType.HIDDEN: lambda v, f, a: _validate_hidden(v),
    # `dependent_select` is dispatched in `validate_payload` itself: it needs
    # the parent field's cleaned answer, which no single-value handler sees.
}


# ---------------------------------------------------------------------------
# Conditional visibility
# ---------------------------------------------------------------------------

SHOW_IF_OPERATORS = frozenset({"eq", "ne", "in", "not_in", "filled", "empty"})


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value is False


def _show_if_matches(rule: dict[str, Any], parent_value: Any) -> bool:
    op = rule.get("op", "eq")
    target = rule.get("value")
    if op == "filled":
        return not _is_blank(parent_value)
    if op == "empty":
        return _is_blank(parent_value)
    if isinstance(parent_value, list):
        # A multi-choice parent matches when any of its picks matches.
        if op == "eq":
            return target in parent_value
        if op == "ne":
            return target not in parent_value
        if op == "in":
            return isinstance(target, list) and any(item in target for item in parent_value)
        if op == "not_in":
            return isinstance(target, list) and not any(item in target for item in parent_value)
        return False
    if op == "eq":
        return parent_value == target
    if op == "ne":
        return parent_value != target
    if op == "in":
        return isinstance(target, list) and parent_value in target
    if op == "not_in":
        return isinstance(target, list) and parent_value not in target
    return False


def visible_field_keys(fields: list[FormField], values: dict[str, Any]) -> set[str]:
    """The keys of every field shown for these answers.

    A field is shown when it has no ``show_if``, or when the field it names
    is itself shown and that field's answer matches. Resolved by walking the
    chain with a memo, so field order does not matter and a cycle (refused
    at save time anyway) resolves to hidden instead of recursing for ever.
    """
    by_key = {field.key: field for field in fields}
    memo: dict[str, bool] = {}

    def _visible(key: str, trail: frozenset[str]) -> bool:
        if key in memo:
            return memo[key]
        field = by_key.get(key)
        if field is None or key in trail:
            return False
        rule = field.show_if or {}
        parent_key = rule.get("field") if isinstance(rule, dict) else None
        if not parent_key:
            result = True
        else:
            result = _visible(parent_key, trail | {key}) and _show_if_matches(
                rule, values.get(parent_key)
            )
        memo[key] = result
        return result

    return {field.key for field in fields if _visible(field.key, frozenset())}


def validate_payload(*, version: FormVersion, values: dict[str, Any], actor: Any) -> dict[str, Any]:
    """Validate the whole ``values`` payload against ``version``'s fields.

    Every field's errors are collected before raising — a caller sees every
    problem in one round trip, never just the first. Unknown keys (not
    declared on the version) are refused the same way a
    ``StrictSerializer`` would refuse them.
    """
    if not isinstance(values, dict):
        raise ApplicationError({"non_field_errors": ["Submit an object of field values."]})

    fields: list[FormField] = list(version.fields.all())
    by_key = {field.key: field for field in fields}
    shown = visible_field_keys(fields, values)

    errors: dict[str, list[str]] = {}
    cleaned: dict[str, Any] = {}

    for key in values:
        if key not in by_key:
            errors[key] = ["This field is not part of the form."]
        elif by_key[key].type in DISPLAY_ONLY_FIELD_TYPES and values[key] not in (None, ""):
            errors[key] = ["This field does not take a value."]

    for field in fields:
        if field.type in DISPLAY_ONLY_FIELD_TYPES or field.key not in shown:
            continue
        present = field.key in values
        value = values.get(field.key)
        if field.type == FormFieldType.HIDDEN and (not present or value in (None, "")):
            default = (field.validation or {}).get("default")
            if default not in (None, ""):
                value, present = default, True
        if not present or value is None or value == "":
            if field.required:
                errors.setdefault(field.key, []).append("This field is required.")
            continue
        if field.type == FormFieldType.DEPENDENT_SELECT:
            options = field.options if isinstance(field.options, dict) else {}
            parent_key = options.get("parent")
            # The parent's *cleaned* answer: fields are validated in order and
            # a parent always comes first (enforced when fields are saved), so
            # an invalid or hidden parent leaves nothing to depend on.
            field_cleaned, field_errors = _validate_dependent_choice(
                value, field.options, cleaned.get(parent_key) if parent_key else None
            )
        else:
            handler = _DISPATCH.get(field.type)
            if handler is None:  # pragma: no cover - defensive, every type is dispatched
                errors.setdefault(field.key, []).append("Unsupported field type.")
                continue
            field_cleaned, field_errors = handler(value, field, actor)
        if field_errors:
            errors.setdefault(field.key, []).extend(field_errors)
        else:
            cleaned[field.key] = field_cleaned

    if errors:
        raise ApplicationError(errors)
    return cleaned


__all__ = [
    "SHOW_IF_OPERATORS",
    "UPLOAD_RESOLVER",
    "dependent_choices",
    "is_snake_case",
    "sanitise_richtext",
    "validate_payload",
    "visible_field_keys",
]
