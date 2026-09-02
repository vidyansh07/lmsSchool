"""Reusable input validation.

Validation is layered on purpose: serializers reject malformed input at the
edge, model validators and database constraints act as the backstop for code
paths that bypass the API (management commands, admin, data migrations).
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Conservative name policy: letters, spaces and a few joining characters.
#: Rejects control characters and markup rather than trying to sanitise them.
NAME_RE = re.compile(r"^[^\W\d_][\w .'\-]{0,99}$", re.UNICODE)

#: Digits with optional leading '+', 8-15 digits (E.164 sized).
PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_person_name(value: str) -> None:
    if not NAME_RE.match(value or ""):
        raise ValidationError(
            _("Enter a valid name using letters, spaces, apostrophes or hyphens."),
            code="invalid_name",
        )


def validate_phone_number(value: str) -> None:
    if value and not PHONE_RE.match(value):
        raise ValidationError(
            _("Enter a valid phone number in international format."), code="invalid_phone"
        )


def validate_no_control_characters(value: str) -> None:
    if value and CONTROL_CHARS_RE.search(value):
        raise ValidationError(
            _("This value contains characters that are not allowed."), code="invalid_characters"
        )


#: Only these keys are accepted, and only over HTTPS. An open map would let a
#: profile become a redirect surface (javascript:, data:, http:// downgrade).
ALLOWED_PROFESSIONAL_LINKS = ("linkedin", "github", "website")
MAX_LINK_LENGTH = 200


def validate_professional_links(value: object) -> None:
    """Validate the trainer's optional professional links map."""
    if not value:
        return
    if not isinstance(value, dict):
        raise ValidationError(_("Professional links must be an object."), code="invalid_links")
    unknown = set(value) - set(ALLOWED_PROFESSIONAL_LINKS)
    if unknown:
        raise ValidationError(
            _("Unsupported link keys: %(keys)s.") % {"keys": ", ".join(sorted(unknown))},
            code="unknown_link_key",
        )
    for key, url in value.items():
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValidationError(
                _("%(key)s must be an https:// URL.") % {"key": key}, code="insecure_link"
            )
        if len(url) > MAX_LINK_LENGTH:
            raise ValidationError(
                _("%(key)s URL is too long.") % {"key": key}, code="link_too_long"
            )
        validate_no_control_characters(url)


#: Slugs appear in URLs. Django's SlugField already restricts the character set;
#: this adds the rules that make a slug safe to route on and pleasant to read.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_SLUGS = frozenset({"new", "edit", "admin", "api", "me", "create", "delete"})


def validate_slug_value(value: str) -> None:
    """Lower-case, hyphen-separated, no leading/trailing/double hyphens."""
    if not value:
        return
    if not SLUG_RE.match(value):
        raise ValidationError(
            _(
                "Use lower-case letters, numbers and single hyphens, "
                "with no hyphen at the start or end."
            ),
            code="invalid_slug",
        )
    if value in RESERVED_SLUGS:
        # Otherwise /courses/new would be ambiguous between a route and a record.
        raise ValidationError(
            _("'%(value)s' is reserved and cannot be used as a slug.") % {"value": value},
            code="reserved_slug",
        )
