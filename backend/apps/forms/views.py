"""Form builder API (``/api/v1/forms/``, ERP Phase 8).

Reading (`form.view`) is superadmin/admin/manager/counsellor; building —
creating a definition, a draft version, replacing its fields, publishing or
unpublishing — is `form.manage` (superadmin/admin only,
`docs/erp/PERMISSION_CATALOG.md`). Every route here requires an
authenticated session (the capability check implies login), so none of them
are anonymous-reachable and none need `EnforceCSRFMixin`.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch
from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.common.caching import MINUTE, remember
from apps.common.exceptions import ApplicationError
from apps.common.permissions import HasCapability

from . import services
from .models import FormDefinition, FormVersion, FormVersionStatus
from .serializers import (
    FormDefinitionCreateSerializer,
    FormDefinitionDetailSerializer,
    FormDefinitionSerializer,
    FormFieldsWriteSerializer,
    FormPreviewSerializer,
    FormVersionCreateSerializer,
    FormVersionDetailSerializer,
)
from .validation import validate_payload

TAG = ["Forms"]

_PUBLISHED_CACHE_TTL = 60 * MINUTE  # 1 hour


def _versions_queryset():
    return FormVersion.objects.with_related().annotate(field_count=Count("fields"))


def _definitions_queryset():
    return FormDefinition.objects.with_related().prefetch_related(
        Prefetch("versions", queryset=_versions_queryset(), to_attr="_prefetched_versions")
    )


def _definition_or_404(slug: str) -> FormDefinition:
    return get_object_or_404(_definitions_queryset(), slug=slug)


def _version_or_404(definition: FormDefinition, number: int) -> FormVersion:
    return get_object_or_404(
        FormVersion.objects.with_related().prefetch_related("fields"),
        definition=definition,
        number=number,
    )


class FormDefinitionListCreateView(ListAPIView):
    permission_classes = (HasCapability,)
    capability_map = {"GET": Capability.FORM_VIEW, "POST": Capability.FORM_MANAGE}
    serializer_class = FormDefinitionSerializer
    pagination_class = None
    queryset = FormDefinition.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FormDefinition.objects.none()
        return _definitions_queryset()

    @extend_schema(summary="Every form definition", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a form definition",
        request=FormDefinitionCreateSerializer,
        responses={
            201: FormDefinitionDetailSerializer,
            409: OpenApiResponse(description="Slug taken"),
        },
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = FormDefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        definition = services.create_definition(actor=request.user, **serializer.validated_data)
        return Response(
            FormDefinitionDetailSerializer(_definition_or_404(definition.slug)).data,
            status=http_status.HTTP_201_CREATED,
        )


class FormDefinitionDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_VIEW
    serializer_class = FormDefinitionDetailSerializer

    @extend_schema(
        summary="One form definition with its versions",
        responses={200: FormDefinitionDetailSerializer},
        tags=TAG,
    )
    def get(self, request, slug):
        return Response(FormDefinitionDetailSerializer(_definition_or_404(slug)).data)


class FormVersionDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_VIEW
    serializer_class = FormVersionDetailSerializer

    @extend_schema(
        summary="One form version with its fields",
        responses={200: FormVersionDetailSerializer},
        tags=TAG,
    )
    def get(self, request, slug, number):
        definition = _definition_or_404(slug)
        version = _version_or_404(definition, number)
        return Response(FormVersionDetailSerializer(version).data)


class FormVersionCreateView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_MANAGE
    serializer_class = FormVersionCreateSerializer

    @extend_schema(
        summary="Start a new draft version",
        request=FormVersionCreateSerializer,
        responses={
            201: FormVersionDetailSerializer,
            409: OpenApiResponse(description="A draft already exists"),
        },
        tags=TAG,
    )
    def post(self, request, slug):
        definition = _definition_or_404(slug)
        serializer = FormVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cloned_from_number = serializer.validated_data.get(
            "cloned_from"
        ) or request.query_params.get("cloned_from")
        cloned_from = None
        if cloned_from_number:
            cloned_from = _version_or_404(definition, int(cloned_from_number))
        version = services.create_draft_version(
            actor=request.user, definition=definition, cloned_from=cloned_from
        )
        return Response(
            FormVersionDetailSerializer(_version_or_404(definition, version.number)).data,
            status=http_status.HTTP_201_CREATED,
        )


class FormVersionFieldsView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_MANAGE
    serializer_class = FormFieldsWriteSerializer

    @extend_schema(
        summary="Replace a draft version's fields",
        request=FormFieldsWriteSerializer,
        responses={
            200: FormVersionDetailSerializer,
            409: OpenApiResponse(description="The version is published and immutable"),
        },
        tags=TAG,
    )
    def put(self, request, slug, number):
        definition = _definition_or_404(slug)
        version = _version_or_404(definition, number)
        serializer = FormFieldsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_fields(
            actor=request.user, version=version, fields=serializer.validated_data["fields"]
        )
        return Response(FormVersionDetailSerializer(_version_or_404(definition, number)).data)


class FormVersionPublishView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_MANAGE
    serializer_class = FormVersionDetailSerializer

    @extend_schema(
        summary="Publish a draft version",
        responses={
            200: FormVersionDetailSerializer,
            409: OpenApiResponse(description="Already published, or nothing changed"),
        },
        tags=TAG,
    )
    def post(self, request, slug, number):
        definition = _definition_or_404(slug)
        version = _version_or_404(definition, number)
        services.publish_version(actor=request.user, version=version)
        return Response(FormVersionDetailSerializer(_version_or_404(definition, number)).data)


class FormVersionUnpublishView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_MANAGE
    serializer_class = FormVersionDetailSerializer

    @extend_schema(
        summary="Unpublish the currently-published version",
        responses={
            200: FormVersionDetailSerializer,
            409: OpenApiResponse(description="This version is not published"),
        },
        tags=TAG,
    )
    def post(self, request, slug, number):
        definition = _definition_or_404(slug)
        version = _version_or_404(definition, number)
        services.unpublish_version(actor=request.user, version=version)
        return Response(FormVersionDetailSerializer(_version_or_404(definition, number)).data)


class FormPreviewView(APIView):
    """Validate a sample response against the builder's current draft.

    A builder tool, not a public submit endpoint — gated on `form.manage`
    like the rest of the editing surface, and it never stores anything.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_MANAGE
    serializer_class = FormPreviewSerializer

    @extend_schema(
        summary="Preview-validate a sample response",
        request=FormPreviewSerializer,
        responses={200: OpenApiResponse(description="{valid, values | errors}")},
        tags=TAG,
    )
    def post(self, request, slug):
        definition = _definition_or_404(slug)
        version = (
            FormVersion.objects.prefetch_related("fields")
            .filter(definition=definition, status=FormVersionStatus.DRAFT)
            .first()
            or FormVersion.objects.prefetch_related("fields")
            .filter(definition=definition, status=FormVersionStatus.PUBLISHED)
            .first()
        )
        if version is None:
            raise ApplicationError(
                {"non_field_errors": ["This form has no draft or published version yet."]}
            )
        serializer = FormPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cleaned = validate_payload(
                version=version, values=serializer.validated_data["values"], actor=request.user
            )
        except ApplicationError as exc:
            return Response({"valid": False, "version": version.number, "errors": exc.detail})
        return Response({"valid": True, "version": version.number, "values": cleaned})


class PublishedFormView(APIView):
    """The published version of a form, for rendering.

    `form.view` is enough of a gate for Phase 8 — there is no consumer yet
    to check an entity-specific creation right against, and every role that
    can reach this endpoint already may see form configuration.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_VIEW
    serializer_class = FormVersionDetailSerializer

    @extend_schema(
        summary="The published version of a form, for rendering",
        responses={
            200: FormVersionDetailSerializer,
            404: OpenApiResponse(description="No published version"),
        },
        tags=TAG,
    )
    def get(self, request, slug):
        def _compute():
            definition = _definition_or_404(slug)
            version = (
                FormVersion.objects.annotate(field_count=Count("fields"))
                .prefetch_related("fields")
                .filter(definition=definition, status=FormVersionStatus.PUBLISHED)
                .first()
            )
            if version is None:
                return {}
            return FormVersionDetailSerializer(version).data

        # The cache prefix is exactly `form:published:{slug}` (`API_CONTRACTS.md`),
        # so `services._forget_published` — which bumps this same prefix's
        # version on publish/unpublish — invalidates precisely this form.
        cached = remember(f"form:published:{slug}", (), _PUBLISHED_CACHE_TTL, _compute)
        if not cached:
            raise Http404("This form has no published version.")
        return Response(cached)
