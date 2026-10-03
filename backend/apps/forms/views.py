"""Form builder API (``/api/v1/forms/``, ERP Phase 8).

Reading (`form.view`) is superadmin/admin/manager/counsellor; building —
creating a definition, a draft version, replacing its fields, publishing or
unpublishing — is `form.manage` (superadmin/admin only,
`docs/erp/PERMISSION_CATALOG.md`). Sending a form to someone, or filling one
in directly, is `form.assign`; answering a form sent to you needs nothing but
being its assignee. Every route here requires an authenticated session, so
none of them are anonymous-reachable and none need `EnforceCSRFMixin`.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import django_filters
from django.db.models import Count, Prefetch
from django.http import FileResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.roles import Capability, has_capability
from apps.common.caching import MINUTE, remember
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import HasCapability, IsActiveUser
from apps.common.uploads import safe_download_name

from . import access, services
from .models import (
    FormAssignment,
    FormAssignmentStatus,
    FormDefinition,
    FormDefinitionStatus,
    FormEntity,
    FormUpload,
    FormVersion,
    FormVersionStatus,
)
from .serializers import (
    FormAssignmentCancelSerializer,
    FormAssignmentCreateSerializer,
    FormAssignmentDetailSerializer,
    FormAssignmentSerializer,
    FormDefinitionCreateSerializer,
    FormDefinitionDetailSerializer,
    FormDefinitionSerializer,
    FormFieldsWriteSerializer,
    FormFillSerializer,
    FormPreviewSerializer,
    FormUploadSerializer,
    FormValuesSerializer,
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


# ---------------------------------------------------------------------------
# Uploads, assignments and direct filling
# ---------------------------------------------------------------------------


class FormUploadView(APIView):
    """Upload one file for a `file`/`image` field; answer with its id.

    Any signed-in person may upload — whoever is filling a form needs to,
    and the id is only usable by its uploader (`validation._validate_upload`).
    """

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser,)
    serializer_class = FormUploadSerializer

    @extend_schema(
        summary="Upload a file for a form field",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
        responses={201: FormUploadSerializer},
        tags=TAG,
    )
    def post(self, request):
        upload = services.create_upload(actor=request.user, uploaded_file=request.FILES.get("file"))
        return Response(FormUploadSerializer(upload).data, status=http_status.HTTP_201_CREATED)


class FormUploadDownloadView(APIView):
    """Download an uploaded file: its uploader, or anyone holding `form.view`
    (the staff who read submitted forms)."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a form upload",
        responses={200: OpenApiResponse(description="The file, as an attachment")},
        tags=TAG,
    )
    def get(self, request, upload_id):
        upload = get_object_or_404(FormUpload, pk=upload_id)
        if upload.uploaded_by_id != request.user.pk and not has_capability(
            request.user, Capability.FORM_VIEW
        ):
            raise Http404
        if not upload.file:
            raise Http404
        response = FileResponse(upload.file.open("rb"), content_type=upload.content_type)
        base = PurePosixPath(upload.original_name or "upload").stem
        response["Content-Disposition"] = (
            f'attachment; filename="{safe_download_name(base, "")}{upload.extension}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-store"
        return response


class FormAssignmentFilterSet(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=FormAssignmentStatus.choices)
    form = django_filters.CharFilter(field_name="definition__slug")
    student = django_filters.UUIDFilter(field_name="student_id")
    enquiry = django_filters.UUIDFilter(field_name="enquiry_id")

    class Meta:
        model = FormAssignment
        fields = ("status", "form", "student", "enquiry")


class FormAssignmentListCreateView(ListAPIView):
    """``GET`` — forms sent to me (``?box=inbox``, the default), forms I
    sent (``?box=sent``), or every assignment I can see (``?box=all``,
    `form.view` holders). ``POST`` — send a form to someone (`form.assign`)."""

    permission_classes = (IsActiveUser,)
    serializer_class = FormAssignmentSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = FormAssignmentFilterSet
    queryset = FormAssignment.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FormAssignment.objects.none()
        user = self.request.user
        box = self.request.query_params.get("box", "inbox")
        visible = access.visible_assignments(user)
        if box == "sent":
            visible = visible.filter(requested_by=user).exclude(assigned_to=user)
        elif box == "all":
            if not has_capability(user, Capability.FORM_VIEW):
                raise AuthorityError("You cannot see other people's forms.")
        else:
            visible = visible.filter(assigned_to=user)
        return visible.order_by("status", "due_at", "-created_at")

    @extend_schema(summary="List form assignments", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Send a form to someone to fill",
        request=FormAssignmentCreateSerializer,
        responses={201: FormAssignmentDetailSerializer},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        if not has_capability(request.user, Capability.FORM_ASSIGN):
            raise AuthorityError("You do not have authority to send forms.")
        serializer = FormAssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        definition = _definition_or_404(data["form"])
        assigned_to = User.objects.filter(pk=data["assigned_to"]).first()
        if assigned_to is None:
            raise ApplicationError({"assigned_to": ["No such person."]})
        student = _student_or_error(request.user, data.get("student"))
        enquiry = _enquiry_or_error(request.user, data.get("enquiry"))
        assignment = services.assign_form(
            actor=request.user,
            definition=definition,
            assigned_to=assigned_to,
            student=student,
            enquiry=enquiry,
            due_at=data.get("due_at"),
            title=data.get("title", ""),
            message=data.get("message", ""),
        )
        return Response(
            FormAssignmentDetailSerializer(
                _assignment_or_404(request.user, assignment.pk), context={"request": request}
            ).data,
            status=http_status.HTTP_201_CREATED,
        )


def _student_or_error(user, student_id):
    if not student_id:
        return None
    from apps.students.access import visible_students

    student = visible_students(user).filter(pk=student_id).first()
    if student is None:
        raise ApplicationError({"student": ["Was not found, or is not visible to you."]})
    return student


def _enquiry_or_error(user, enquiry_id):
    if not enquiry_id:
        return None
    from apps.enquiries.access import visible_enquiries

    enquiry = visible_enquiries(user).filter(pk=enquiry_id).first()
    if enquiry is None:
        raise ApplicationError({"enquiry": ["Was not found, or is not visible to you."]})
    return enquiry


def _assignment_or_404(user, assignment_id) -> FormAssignment:
    assignment = (
        access.visible_assignments(user)
        .prefetch_related("version__fields")
        .filter(pk=assignment_id)
        .first()
    )
    if assignment is None:
        raise Http404
    return assignment


class FormAssignmentDetailView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = FormAssignmentDetailSerializer

    @extend_schema(
        summary="One form assignment, with its fields and any answers",
        responses={200: FormAssignmentDetailSerializer},
        tags=TAG,
    )
    def get(self, request, assignment_id):
        assignment = _assignment_or_404(request.user, assignment_id)
        return Response(
            FormAssignmentDetailSerializer(assignment, context={"request": request}).data
        )


class FormAssignmentSubmitView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = FormValuesSerializer

    @extend_schema(
        summary="Submit the answers to a form sent to me",
        request=FormValuesSerializer,
        responses={200: FormAssignmentDetailSerializer},
        tags=TAG,
    )
    def post(self, request, assignment_id):
        assignment = _assignment_or_404(request.user, assignment_id)
        serializer = FormValuesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.submit_assignment(
            actor=request.user, assignment=assignment, values=serializer.validated_data["values"]
        )
        return Response(
            FormAssignmentDetailSerializer(
                _assignment_or_404(request.user, assignment_id), context={"request": request}
            ).data
        )


class FormAssignmentCancelView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = FormAssignmentCancelSerializer

    @extend_schema(
        summary="Cancel a form request that has not been filled",
        request=FormAssignmentCancelSerializer,
        responses={200: FormAssignmentDetailSerializer},
        tags=TAG,
    )
    def post(self, request, assignment_id):
        assignment = _assignment_or_404(request.user, assignment_id)
        serializer = FormAssignmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_assignment(
            actor=request.user, assignment=assignment, reason=serializer.validated_data["reason"]
        )
        return Response(
            FormAssignmentDetailSerializer(
                _assignment_or_404(request.user, assignment_id), context={"request": request}
            ).data
        )


class FormFillView(APIView):
    """Fill in a published form directly (`form.assign`). Recorded as a
    submitted assignment to oneself — see `services.fill_form`."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_ASSIGN
    serializer_class = FormFillSerializer

    @extend_schema(
        summary="Fill in a form directly",
        request=FormFillSerializer,
        responses={201: FormAssignmentDetailSerializer},
        tags=TAG,
    )
    def post(self, request, slug):
        definition = _definition_or_404(slug)
        serializer = FormFillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = _student_or_error(request.user, serializer.validated_data.get("student"))
        assignment = services.fill_form(
            actor=request.user,
            definition=definition,
            values=serializer.validated_data["values"],
            student=student,
        )
        return Response(
            FormAssignmentDetailSerializer(
                _assignment_or_404(request.user, assignment.pk), context={"request": request}
            ).data,
            status=http_status.HTTP_201_CREATED,
        )


class FillableFormsView(APIView):
    """Published, active forms a `form.assign` holder may send or fill —
    everything except the activity forms, which reach people only through
    an activity."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FORM_ASSIGN

    @extend_schema(
        summary="Forms that can be sent or filled directly",
        responses={200: OpenApiResponse(description="[{slug, name, entity, version}]")},
        tags=TAG,
    )
    def get(self, request):
        rows = (
            FormVersion.objects.filter(
                status=FormVersionStatus.PUBLISHED,
                definition__status=FormDefinitionStatus.ACTIVE,
                definition__deleted_at__isnull=True,
            )
            .exclude(definition__entity=FormEntity.ACTIVITY)
            .select_related("definition")
            .order_by("definition__name")
        )
        return Response(
            [
                {
                    "slug": row.definition.slug,
                    "name": row.definition.name,
                    "entity": row.definition.entity,
                    "version": row.number,
                }
                for row in rows
            ]
        )
