"""Serializer base classes.

Serializers validate and shape data. Business rules live in ``services.py`` in
each app so that a rule holds no matter which entry point invokes it — API,
management command, admin action or a future background task.

The strictness here is the project's mass-assignment defence. A serializer
exposes an explicit field list, and anything outside it is *rejected*, not
ignored — so a request like ``{"role": "admin"}`` sent to a self-service
endpoint returns 400 naming the offending field instead of appearing to succeed.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .validators import validate_no_control_characters


class StrictFieldsMixin:
    """Reject unknown fields instead of silently ignoring them.

    Silent ignoring hides client bugs and, worse, hides an attacker probing for
    fields the server might accept. Read-only fields are rejected on write too:
    sending ``student_id`` should fail loudly rather than look accepted.
    """

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, dict):
            writable = {name for name, field in self.fields.items() if not field.read_only}
            unknown = set(data) - writable
            if unknown:
                raise serializers.ValidationError(
                    {field: ["This field is not accepted."] for field in sorted(unknown)}
                )
        return super().to_internal_value(data)


class StrictSerializer(StrictFieldsMixin, serializers.Serializer):
    """Plain serializer that rejects unknown fields."""


class StrictModelSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    """Model serializer that rejects unknown fields.

    Subclasses must declare ``Meta.fields`` explicitly. A wildcard would leak
    whatever field is added to the model next — ``password``, ``is_superuser``,
    internal notes — the moment someone adds it.
    """


class SafeCharField(serializers.CharField):
    """CharField that strips surrounding whitespace and rejects control chars."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("trim_whitespace", True)
        super().__init__(**kwargs)
        self.validators.append(validate_no_control_characters)
