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

from apps.common.pagination import DefaultPagination

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


class PaginatedQuerySerializer(StrictSerializer):
    """Strict query serializer for a view that paginates in its own body.

    ``StrictSerializer`` refuses any field it does not declare, which is what
    turns a mistyped filter into a 400 rather than a parameter silently doing
    nothing. A view that paginates by hand validates ``request.query_params``
    with one of these *and* hands the same dict to
    :class:`~apps.common.pagination.DefaultPagination`, which reads ``page``
    and ``page_size`` out of it — so a serializer that does not declare those
    two rejects the very request its own ``@extend_schema`` advertises, and
    the screen behind it can never load a second page. That is exactly how
    the activity feed was broken: the endpoint answered every unpaginated
    request and 400'd every paginated one.

    Declared here rather than on each serializer so the paginator's parameter
    names and the validator's field names cannot drift apart. The view does
    not read these values — the paginator takes them from the request — so
    they exist to be *accepted*; the bounds are the paginator's own, which
    makes a nonsense page a clear 400 instead of an empty list.
    """

    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(
        required=False, min_value=1, max_value=DefaultPagination.max_page_size
    )


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
