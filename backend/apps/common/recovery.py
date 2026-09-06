"""The recycle bin.

Soft deletion is only half a promise. A record that leaves every query and has
no screen showing it has not been *recovered* from — it has been lost politely.
This is the other half: one place that lists what has been removed, restores it,
and (for one role only) destroys it.

One generic surface, not a bin per app
--------------------------------------
Every soft-deletable model gets the same three operations, so writing them per
app would be twenty copies of the same view drifting apart, and — worse — a new
model adopting `SoftDeleteModel` would silently have no recovery screen at all.
Here it appears automatically the moment it inherits the base class.

The obvious risk of a generic endpoint, and what closes it
----------------------------------------------------------
An endpoint that takes a model name from the URL and looks it up is an
arbitrary-model-read vulnerability wearing a helpful shape. `django_apps.get_model`
on caller-supplied text would happily return `accounts.User`, `AuditLog`, or the
session table.

So the label is never used to *find* a model. It is matched against a registry
built at request time from the models that actually inherit
:class:`~apps.common.models.SoftDeleteModel` — a closed set the caller cannot
influence. Anything else is a 404, not an error message naming what exists.

Authorization is three separate rights
--------------------------------------
Seeing the bin, restoring from it, and emptying it are different acts:
`record.view_deleted`, `record.restore` and `record.purge`. Only the last is
withheld from administrators, because everything else on this ladder can be
undone and that one cannot.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps as django_apps
from django.db.models import Model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.deletion import purge, restore
from apps.common.models import SoftDeleteModel
from apps.common.pagination import DefaultPagination
from apps.common.permissions import Capability, HasCapability
from apps.common.serializers import SafeCharField, StrictSerializer

RECOVERY_TAG = ["recovery"]


def recoverable_models() -> dict[str, type[Model]]:
    """Every concrete soft-deletable model, keyed by its app-qualified label.

    Built fresh from the app registry rather than kept as a hand-maintained
    list, so a model that adopts `SoftDeleteModel` in a later phase appears in
    the bin without anybody remembering to add it. The alternative — a registry
    somebody has to update — fails silently in the one direction that matters:
    a record is deleted, nothing lists it, and it looks like it never existed.
    """
    return {
        model._meta.label_lower: model
        for model in django_apps.get_models()
        if issubclass(model, SoftDeleteModel) and not model._meta.abstract
    }


def _model_or_404(label: str) -> type[Model]:
    """Resolve a caller-supplied label against the closed set, or 404.

    Never `get_model(label)`. That would take text from the URL and use it to
    reach any table in the project, which is the whole vulnerability this
    function exists to not have.
    """
    from django.http import Http404

    model = recoverable_models().get((label or "").lower())
    if model is None:
        # A bare 404: naming which labels are valid would enumerate the schema
        # for somebody who is guessing.
        raise Http404
    return model


def _describe(instance: Model) -> str:
    """A short human name for the record, for the bin's list.

    Deliberately narrow. The bin is a list of things to restore, not a viewer
    for their contents — rendering every field of a deleted student would put
    personal data on a screen that exists to answer "was this the one?".
    """
    for attribute in ("code", "student_id", "trainer_id", "title", "name", "slug"):
        value = getattr(instance, attribute, None)
        if value:
            return str(value)[:120]
    return str(instance.pk)


class DeletedRecordSerializer(serializers.Serializer):
    """One row of the bin.

    Every field is always present, including the nullable ones. A screen reading
    this should never have to ask whether a key exists — `deleted_by` is `null`
    when the account that removed it has since been removed, and that is a fact
    worth rendering ("Unknown"), not a missing key to branch on.
    """

    id = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    describes = serializers.CharField(read_only=True)
    deleted_at = serializers.DateTimeField(read_only=True)
    deleted_by = serializers.CharField(read_only=True, allow_null=True)
    delete_reason = serializers.CharField(read_only=True, allow_blank=True)


class BinSummarySerializer(serializers.Serializer):
    label = serializers.CharField(read_only=True)
    verbose_name = serializers.CharField(read_only=True)
    deleted_count = serializers.IntegerField(read_only=True)


class PurgeSerializer(StrictSerializer):
    """Destroying a record asks for a reason, and does not accept a blank one.

    The reason is the only thing that will still exist afterwards.
    """

    reason = SafeCharField(max_length=255, allow_blank=False)


def _row(instance: Model) -> dict[str, Any]:
    actor = getattr(instance, "deleted_by", None)
    return {
        "id": str(instance.pk),
        "label": instance._meta.label_lower,
        "describes": _describe(instance),
        "deleted_at": instance.deleted_at,
        "deleted_by": getattr(actor, "email", None),
        "delete_reason": instance.delete_reason or "",
    }


class RecycleBinView(APIView):
    """What has been deleted, grouped by kind.

    The landing screen: counts per model, so somebody looking for a batch does
    not have to page through four thousand deleted attendance rows to find it.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.RECORD_VIEW_DELETED

    @extend_schema(
        summary="Deleted records, by kind",
        responses={200: BinSummarySerializer(many=True)},
        tags=RECOVERY_TAG,
    )
    def get(self, request):
        rows = []
        for label, model in sorted(recoverable_models().items()):
            count = model.all_objects.dead().count()
            if not count:
                # An empty bin for a model nobody has deleted from is noise on a
                # screen whose job is to show what needs attention.
                continue
            rows.append(
                {
                    "label": label,
                    "verbose_name": str(model._meta.verbose_name_plural),
                    "deleted_count": count,
                }
            )
        return Response(BinSummarySerializer(rows, many=True).data)


class DeletedRecordListView(APIView):
    """The deleted records of one kind, most recently removed first."""

    permission_classes = (HasCapability,)
    required_capability = Capability.RECORD_VIEW_DELETED

    @extend_schema(
        summary="Deleted records of one kind",
        responses={200: DeletedRecordSerializer(many=True)},
        tags=RECOVERY_TAG,
    )
    def get(self, request, label):
        model = _model_or_404(label)
        queryset = (
            model.all_objects.dead().select_related("deleted_by").order_by("-deleted_at", "pk")
        )

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            DeletedRecordSerializer([_row(instance) for instance in page], many=True).data
        )


class RestoreRecordView(APIView):
    """Bring one record back."""

    permission_classes = (HasCapability,)
    required_capability = Capability.RECORD_RESTORE

    @extend_schema(
        summary="Restore a deleted record",
        request=None,
        responses={
            200: DeletedRecordSerializer,
            404: OpenApiResponse(description="No such deleted record."),
            409: OpenApiResponse(description="That record is not deleted."),
        },
        tags=RECOVERY_TAG,
    )
    def post(self, request, label, record_id):
        model = _model_or_404(label)
        # Looked up through `dead()`, so restoring a live record is a 404 rather
        # than a confusing 409 — the id genuinely is not in the bin.
        instance = model.all_objects.dead().filter(pk=record_id).first()
        if instance is None:
            from django.http import Http404

            raise Http404

        restore(instance=instance, actor=request.user)
        instance.refresh_from_db()
        return Response(DeletedRecordSerializer(_row(instance)).data)


class PurgeRecordView(APIView):
    """Destroy one record permanently.

    A separate capability that only a superadmin holds, and it is the only
    endpoint in the project whose effect cannot be undone. The service refuses
    anything that is not already deleted, so nothing can be destroyed without
    having first been removed and seen in the bin — two decisions, two audit
    entries, two people if you want it that way.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.RECORD_PURGE

    @extend_schema(
        summary="Destroy a deleted record permanently",
        request=PurgeSerializer,
        responses={
            204: OpenApiResponse(description="Destroyed."),
            404: OpenApiResponse(description="No such deleted record."),
        },
        tags=RECOVERY_TAG,
    )
    def post(self, request, label, record_id):
        model = _model_or_404(label)
        instance = model.all_objects.dead().filter(pk=record_id).first()
        if instance is None:
            from django.http import Http404

            raise Http404

        serializer = PurgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        purge(instance=instance, actor=request.user, reason=serializer.validated_data["reason"])
        return Response(status=status.HTTP_204_NO_CONTENT)
