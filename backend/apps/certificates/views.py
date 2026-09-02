"""Certificate API — §6.7 and §6.8.

The public verification endpoint is the only unauthenticated write-adjacent
surface in the product, so it is worth being explicit about what protects it:

* it takes an unguessable code, never a certificate number or an id;
* it is throttled, so it cannot be used to confirm codes in bulk;
* it returns an allowlist built in the service, not a model serializer;
* a code that does not exist and a code that was revoked are both answered —
  a revoked certificate must be distinguishable from a forged one.
"""

from __future__ import annotations

import django_filters
from django.http import FileResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import AllowAnyPublic, IsActiveUser
from apps.progress import access as progress_access
from apps.progress.models import CourseCompletion

from . import services
from .models import Certificate, CertificateTemplate
from .rendering import render_certificate_pdf, verification_url
from .serializers import (
    CertificateSerializer,
    IssueSerializer,
    PublicCertificateSerializer,
    ReasonSerializer,
    ReissueSerializer,
    StudentCertificateSerializer,
    TemplateSerializer,
    TemplateWriteSerializer,
)

CERTIFICATES_TAG = ["certificates"]


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


def visible_certificates(user):
    """Staff see the certificates of students they can reach; a student sees theirs."""
    base = Certificate.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.filter(completion__enrollment__in=progress_access.visible_enrollments(user))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateListView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Certificate templates",
        responses={200: TemplateSerializer(many=True)},
        tags=CERTIFICATES_TAG,
    )
    def get(self, request):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot manage certificates.")
        return Response(TemplateSerializer(CertificateTemplate.objects.all(), many=True).data)

    @extend_schema(
        summary="Create a certificate template",
        request=TemplateWriteSerializer,
        responses={201: TemplateSerializer},
        tags=CERTIFICATES_TAG,
    )
    def post(self, request):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot manage certificates.")
        serializer = TemplateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = services.save_template(actor=request.user, **serializer.validated_data)
        return Response(TemplateSerializer(template).data, status=http_status.HTTP_201_CREATED)


class TemplateDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Edit a certificate template",
        request=TemplateWriteSerializer,
        responses={200: TemplateSerializer},
        tags=CERTIFICATES_TAG,
    )
    def patch(self, request, template_id):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot manage certificates.")
        template = get_object_or_404(CertificateTemplate.objects.all(), pk=template_id)
        serializer = TemplateWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        template = services.save_template(
            actor=request.user, template=template, **serializer.validated_data
        )
        return Response(TemplateSerializer(template).data)


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


class CertificateFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    course = django_filters.UUIDFilter(field_name="completion__enrollment__course_id")
    batch = django_filters.UUIDFilter(field_name="completion__enrollment__batch_id")

    class Meta:
        model = Certificate
        fields = ("status", "course", "batch")


class CertificateListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = CertificateSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = CertificateFilterSet
    search_fields = ("number", "student_name", "student_code", "course_title")
    ordering_fields = ("issued_at", "completion_date")
    ordering = ("-issued_at",)

    def get_queryset(self):
        return visible_certificates(self.request.user)

    @extend_schema(summary="List certificates", tags=CERTIFICATES_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MyCertificatesView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My certificates",
        responses={200: StudentCertificateSerializer(many=True)},
        tags=CERTIFICATES_TAG,
    )
    def get(self, request):
        student = batch_access.student_profile(request.user)
        if student is None:
            return Response([])
        rows = Certificate.objects.with_related().filter(completion__enrollment__student=student)
        return Response(StudentCertificateSerializer(rows, many=True).data)


class IssueCertificateView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Issue a certificate for an approved completion",
        request=IssueSerializer,
        responses={201: CertificateSerializer},
        tags=CERTIFICATES_TAG,
    )
    def post(self, request, enrollment_id):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot issue certificates.")

        enrollment = get_object_or_404(
            progress_access.visible_enrollments(request.user), pk=enrollment_id
        )
        completion = get_object_or_404(CourseCompletion.objects.all(), enrollment=enrollment)

        serializer = IssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template_id = serializer.validated_data.get("template")
        template = (
            get_object_or_404(CertificateTemplate.objects.all(), pk=template_id)
            if template_id
            else None
        )

        certificate = services.issue_certificate(
            completion=completion, actor=request.user, template=template
        )
        return Response(
            CertificateSerializer(certificate).data, status=http_status.HTTP_201_CREATED
        )


def _certificate_for(request, certificate_id) -> Certificate:
    return get_object_or_404(visible_certificates(request.user), pk=certificate_id)


class CertificateDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Certificate detail", responses={200: CertificateSerializer}, tags=CERTIFICATES_TAG
    )
    def get(self, request, certificate_id):
        certificate = _certificate_for(request, certificate_id)
        if progress_access.can_manage_certificates(request.user):
            return Response(CertificateSerializer(certificate).data)
        return Response(StudentCertificateSerializer(certificate).data)


class ReissueCertificateView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Reissue a certificate",
        request=ReissueSerializer,
        responses={201: CertificateSerializer},
        tags=CERTIFICATES_TAG,
    )
    def post(self, request, certificate_id):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot reissue certificates.")
        certificate = _certificate_for(request, certificate_id)

        serializer = ReissueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template_id = serializer.validated_data.get("template")
        template = (
            get_object_or_404(CertificateTemplate.objects.all(), pk=template_id)
            if template_id
            else None
        )

        replacement = services.reissue_certificate(
            certificate=certificate,
            actor=request.user,
            reason=serializer.validated_data["reason"],
            template=template,
        )
        return Response(
            CertificateSerializer(replacement).data, status=http_status.HTTP_201_CREATED
        )


class RevokeCertificateView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Revoke a certificate",
        request=ReasonSerializer,
        responses={200: CertificateSerializer},
        tags=CERTIFICATES_TAG,
    )
    def post(self, request, certificate_id):
        if not progress_access.can_manage_certificates(request.user):
            return _forbidden(request, "You cannot revoke certificates.")
        certificate = _certificate_for(request, certificate_id)

        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = services.revoke_certificate(
            certificate=certificate, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(CertificateSerializer(certificate).data)


class CertificatePdfView(APIView):
    """The certificate itself.

    Drawn on demand rather than stored: the PDF is a pure function of the
    snapshot on the row, so there is nothing to keep in sync and no stale file
    to serve after a reissue.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a certificate",
        responses={200: OpenApiResponse(description="The certificate, as a PDF.")},
        tags=CERTIFICATES_TAG,
    )
    def get(self, request, certificate_id):
        from io import BytesIO

        certificate = _certificate_for(request, certificate_id)
        template = certificate.template or services.default_template()
        if template is None:
            raise Http404

        record(
            action=AuditAction.CERTIFICATE_DOWNLOADED,
            actor=request.user,
            resource_type="certificate",
            resource_id=certificate.pk,
            context={"number": certificate.number},
            durable=False,
        )

        pdf = render_certificate_pdf(certificate=certificate, template=template)
        response = FileResponse(BytesIO(pdf), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{certificate.number}.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


# ---------------------------------------------------------------------------
# Public verification — §6.8
# ---------------------------------------------------------------------------


class VerificationThrottle(AnonRateThrottle):
    """Slow enough that the endpoint cannot be used to confirm codes in bulk.

    A 160-bit code is not brute-forceable regardless; this bounds the damage of
    a leaked list being checked wholesale, and keeps an anonymous endpoint from
    becoming a free database read.
    """

    scope = "certificate_verification"


class VerifyCertificateView(APIView):
    """Check a certificate. Anonymous, by design — that is what verification is."""

    permission_classes = (AllowAnyPublic,)
    authentication_classes = ()
    throttle_classes = (VerificationThrottle,)

    @extend_schema(
        summary="Verify a certificate",
        responses={
            200: PublicCertificateSerializer,
            404: OpenApiResponse(description="No certificate with that code."),
        },
        tags=CERTIFICATES_TAG,
    )
    def get(self, request, code):
        certificate = (
            Certificate.objects.select_related("template").filter(verification_code=code).first()
        )
        if certificate is None:
            # Deliberately the same answer for a typo and for a code that was
            # never issued: there is nothing to learn from the difference.
            raise Http404

        record(
            action=AuditAction.CERTIFICATE_VERIFIED,
            actor=None,
            resource_type="certificate",
            resource_id=certificate.pk,
            context={"number": certificate.number, "status": certificate.status},
            durable=False,
        )
        return Response(PublicCertificateSerializer(services.public_view(certificate)).data)


class VerificationLinkView(APIView):
    """The URL a certificate's QR code points at. Staff, for checking a print run."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="A certificate's verification URL",
        responses={200: OpenApiResponse(description="The public verification address.")},
        tags=CERTIFICATES_TAG,
    )
    def get(self, request, certificate_id):
        certificate = _certificate_for(request, certificate_id)
        return Response({"url": verification_url(certificate.verification_code)})
