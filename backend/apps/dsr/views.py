"""Daily status report API.

Same authorization shape used throughout this codebase: every record is
fetched from a queryset the caller is already entitled to
(`access.visible_dsrs`), so an id from another trainer's batch produces 404
before any permission code even runs — there is no "load it, then check it"
path to race.

The one endpoint that cannot work that way is the session-scoped one. Before
a report exists there is nothing to fetch it from, so `SessionDSRView` decides
who may see the *prefilled shape* with `access.can_start_dsr`, which asks the
same question `visible_dsrs` would have answered had the row already existed.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.common.deletion import soft_delete
from apps.common.permissions import IsActiveUser
from apps.courses.models import Module
from apps.sessions import access as session_access

from . import access, services
from .models import DSR
from .serializers import DSRDeleteSerializer, DSRReviewSerializer, DSRSerializer, DSRWriteSerializer

DSR_TAG = ["dsr"]


def _forbidden(request, message: str) -> Response:
    return Response(
        {
            "error": {
                "code": "permission_denied",
                "message": message,
                "request_id": getattr(request, "request_id", "-"),
            }
        },
        status=http_status.HTTP_403_FORBIDDEN,
    )


def _resolve_module(batch, fields: dict) -> dict:
    """Turn a submitted module id into the object, scoped to the batch's course.

    A module id from a different course must not become a 400 that confirms
    the module exists — the same reasoning `apps.assignments.views` applies to
    its own module and lesson lookups.
    """
    if "module" not in fields:
        return fields
    value = fields.pop("module")
    if value is None:
        fields["module"] = None
    else:
        fields["module"] = get_object_or_404(Module.objects.filter(course=batch.course), pk=value)
    return fields


def _dsr_for(request, dsr_id) -> DSR:
    return get_object_or_404(access.visible_dsrs(request.user), pk=dsr_id)


def _owns_or_manages(user, dsr: DSR) -> bool:
    """Whose report this is, with no opinion on its status.

    Used for submitting rather than `access.can_write_dsr`, on purpose:
    submission is only legal from `DRAFT` or `REVISION_REQUIRED` already, so
    folding that same status check into the permission check here would turn
    "you already submitted this" into an opaque 403 instead of the 409
    `services.submit_dsr` is built to give.
    """
    if has_capability(user, Capability.DSR_MANAGE_ANY):
        return True
    trainer = batch_access.trainer_profile(user)
    return trainer is not None and trainer.pk == dsr.trainer_id


class DSRFilterSet(django_filters.FilterSet):
    batch = django_filters.UUIDFilter(field_name="batch_id")
    trainer = django_filters.UUIDFilter(field_name="trainer_id")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    date_after = django_filters.DateFilter(field_name="report_date", lookup_expr="gte")
    date_before = django_filters.DateFilter(field_name="report_date", lookup_expr="lte")

    class Meta:
        model = DSR
        fields = ("batch", "trainer", "status")


class DSRListView(ListAPIView):
    """Reports the caller may see, across every batch they may see them for."""

    permission_classes = (IsActiveUser,)
    serializer_class = DSRSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DSRFilterSet
    # Declared for schema generation, which builds a view without a request;
    # the real queryset is scoped per caller in `get_queryset`.
    queryset = DSR.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DSR.objects.none()
        return access.visible_dsrs(self.request.user)

    @extend_schema(summary="List daily status reports", tags=DSR_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DSRDetailView(APIView):
    """Read one report, or edit it while it is still the trainer's to change."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Daily status report detail", responses={200: DSRSerializer}, tags=DSR_TAG
    )
    def get(self, request, dsr_id):
        return Response(DSRSerializer(_dsr_for(request, dsr_id)).data)

    @extend_schema(
        summary="Edit a daily status report",
        request=DSRWriteSerializer,
        responses={200: DSRSerializer},
        tags=DSR_TAG,
    )
    def patch(self, request, dsr_id):
        dsr = _dsr_for(request, dsr_id)
        if not access.can_write_dsr(request.user, dsr):
            return _forbidden(request, "You cannot edit this report.")

        serializer = DSRWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        should_submit = validated.pop("submit", False)
        fields = _resolve_module(dsr.batch, validated)
        force = has_capability(request.user, Capability.DSR_MANAGE_ANY)
        dsr = services.update_dsr(dsr=dsr, actor=request.user, force=force, **fields)
        if should_submit:
            dsr = services.submit_dsr(dsr=dsr, actor=request.user)
        return Response(DSRSerializer(dsr).data)


class DSRSubmitView(APIView):
    """Hand a report to its reviewer."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Submit a daily status report",
        request=None,
        responses={200: DSRSerializer},
        tags=DSR_TAG,
    )
    def post(self, request, dsr_id):
        dsr = _dsr_for(request, dsr_id)
        if not _owns_or_manages(request.user, dsr):
            return _forbidden(request, "You cannot submit this report.")
        dsr = services.submit_dsr(dsr=dsr, actor=request.user)
        return Response(DSRSerializer(dsr).data)


class DSRReviewView(APIView):
    """Approve, reject, or send a report back."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Review a daily status report",
        request=DSRReviewSerializer,
        responses={200: DSRSerializer},
        tags=DSR_TAG,
    )
    def post(self, request, dsr_id):
        dsr = _dsr_for(request, dsr_id)
        if not access.can_review_dsr(request.user, dsr):
            return _forbidden(request, "You cannot review this report.")

        serializer = DSRReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dsr = services.review_dsr(
            dsr=dsr,
            actor=request.user,
            decision=serializer.validated_data["decision"],
            comments=serializer.validated_data.get("comments", ""),
        )
        return Response(DSRSerializer(dsr).data)


class DSRDeleteView(APIView):
    """Soft-delete a report. Reversible, and always with a reason."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Delete a daily status report",
        request=DSRDeleteSerializer,
        responses={204: None},
        tags=DSR_TAG,
    )
    def post(self, request, dsr_id):
        dsr = _dsr_for(request, dsr_id)
        if not access.can_write_dsr(request.user, dsr):
            return _forbidden(request, "You cannot delete this report.")

        serializer = DSRDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        soft_delete(instance=dsr, actor=request.user, reason=serializer.validated_data["reason"])
        return Response(status=http_status.HTTP_204_NO_CONTENT)


def _preview_dsr(session, actor) -> DSR:
    """An unsaved report, shaped exactly as :func:`services.start_dsr` would
    save it, so a client can render a "new report" screen from one request.

    ``id``, ``created_at`` and ``updated_at`` are cleared after construction:
    the base model classes assign a fresh id and Django leaves the timestamp
    fields unset until ``save()``, and a random-looking id on a row that does
    not exist would be worse than an absent one.
    """
    counts = services.prefill_counts(session)
    trainer = services.resolve_trainer(session, actor)
    preview = DSR(
        session=session,
        batch=session.batch,
        trainer=trainer,
        report_date=session.session_date,
        start_time=session.start_time,
        end_time=session.end_time,
        planned_topic=session.topic,
        actual_topic=session.topic,
        online_count=0,
        offline_count=0,
        **counts,
    )
    preview.id = None
    preview.created_at = None
    preview.updated_at = None
    return preview


class SessionDSRView(APIView):
    """The report for one class: read it if it exists, or start it."""

    permission_classes = (IsActiveUser,)

    def _session(self, request, session_id):
        return get_object_or_404(session_access.visible_sessions(request.user), pk=session_id)

    @extend_schema(
        summary="Get a class's daily status report",
        responses={200: DSRSerializer},
        tags=DSR_TAG,
    )
    def get(self, request, session_id):
        session = self._session(request, session_id)
        try:
            dsr = session.dsr
        except DSR.DoesNotExist:
            dsr = None

        if dsr is not None:
            if not access.visible_dsrs(request.user).filter(pk=dsr.pk).exists():
                return _forbidden(request, "You cannot see this report.")
            return Response(DSRSerializer(dsr).data)

        if not access.can_start_dsr(request.user, session):
            return _forbidden(request, "You cannot start a report for this class.")
        return Response(DSRSerializer(_preview_dsr(session, request.user)).data)

    @extend_schema(
        summary="Start a class's daily status report",
        description=(
            "Creates the draft, prefilled from the register. Pass `submit: true` "
            "to hand it straight to the reviewer in the same request — the "
            "common case, since this is written at the end of class rather "
            "than drafted later, and a trainer with nothing to correct on top "
            "of the prefilled numbers should not need a second request."
        ),
        request=DSRWriteSerializer,
        responses={201: DSRSerializer},
        tags=DSR_TAG,
    )
    def post(self, request, session_id):
        session = self._session(request, session_id)
        if not access.can_start_dsr(request.user, session):
            return _forbidden(request, "You cannot start a report for this class.")

        serializer = DSRWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        should_submit = validated.pop("submit", False)
        fields = _resolve_module(session.batch, validated)
        dsr = services.start_dsr(session=session, actor=request.user, **fields)
        if should_submit:
            dsr = services.submit_dsr(dsr=dsr, actor=request.user)
        return Response(DSRSerializer(dsr).data, status=http_status.HTTP_201_CREATED)


class BatchDSRListView(ListAPIView):
    """Every report on one batch."""

    permission_classes = (IsActiveUser,)
    serializer_class = DSRSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DSRFilterSet
    queryset = DSR.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DSR.objects.none()
        batch = get_object_or_404(
            batch_access.visible_batches(self.request.user), pk=self.kwargs["batch_id"]
        )
        return access.visible_dsrs(self.request.user).filter(batch=batch)

    @extend_schema(summary="Daily status reports for a batch", tags=DSR_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
