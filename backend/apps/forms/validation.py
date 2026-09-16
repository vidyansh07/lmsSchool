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
======================== ============================================

Upload resolution — a known gap, not an oversight
--------------------------------------------------
The phase prompt for this module assumes ``apps/common/uploads.py`` already
exposes a generic upload record with an id. It does not: every
``FileField``/``ImageField`` in this codebase (``apps.assignments``,
``apps.courses``, ``apps.exams``, ``apps.projects``, ``apps.reporting``)
belongs to its own owning entity, and ``apps.common.uploads`` is a bundle of
validators and ``upload_to`` functions, not a model with a queryable id.
Phase 8 itself has no owning entity for a form response yet (the prompt
says so explicitly), so there is nothing for a generic upload id to be
attached to in this phase either.

Rather than invent a generic upload store the phase did not ask for and no
consumer yet needs, ``file``/``image`` fields validate against an
injectable seam, :data:`UPLOAD_RESOLVER`. It resolves an upload id to
``{"content_type": str, "size_bytes": int, "filename": str}`` or ``None``
if the id does not resolve. The default implementation always returns
``None`` (nothing resolves, so nothing is silently trusted) until a later
phase's real upload endpoint registers a resolver here. Tests exercise both
branches by monkeypatching this attribute — the validation *logic* (accept
list, max size, image content-type) is fully implemented and tested; only
the existence check is stubbed pending that generic store.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from apps.common.exceptions import ApplicationError

from .models import FormField, FormFieldType, FormVersion

# ---------------------------------------------------------------------------
# Upload resolution seam (see module docstring)
# ---------------------------------------------------------------------------


def _default_upload_resolver(upload_id: str) -> dict[str, Any] | None:
    return None


#: Replaced by a real generic-upload lookup once one exists. Module-level so
#: tests (and a future phase) can monkeypatch it without changing call sites.
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


def _validate_upload(value: Any, rules: dict[str, Any], *, image: bool) -> tuple[Any, list[str]]:
    if not isinstance(value, str) or not value:
        return None, ["An uploaded file is required."]
    metadata = UPLOAD_RESOLVER(value)
    if metadata is None:
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
    FormFieldType.FILE: lambda v, f, a: _validate_upload(v, f.validation, image=False),
    FormFieldType.IMAGE: lambda v, f, a: _validate_upload(v, f.validation, image=True),
    FormFieldType.RELATION: lambda v, f, a: _validate_relation(v, f.options, actor=a),
}


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

    errors: dict[str, list[str]] = {}
    cleaned: dict[str, Any] = {}

    for key in values:
        if key not in by_key:
            errors[key] = ["This field is not part of the form."]

    for field in fields:
        present = field.key in values
        value = values.get(field.key)
        if not present or value is None or value == "":
            if field.required:
                errors.setdefault(field.key, []).append("This field is required.")
            continue
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


__all__ = ["UPLOAD_RESOLVER", "is_snake_case", "sanitise_richtext", "validate_payload"]
