"""Certificate serializers.

Two audiences, and the gap between them is the point of §6.8: staff see the
record, the public sees an allowlist.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import Certificate, CertificateTemplate


class TemplateSerializer(StrictModelSerializer):
    class Meta:
        model = CertificateTemplate
        fields = (
            "id",
            "name",
            "is_default",
            "institution_name",
            "title",
            "body",
            "signatory_name",
            "signatory_title",
            "footer",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TemplateWriteSerializer(StrictSerializer):
    name = SafeCharField(max_length=120)
    is_default = serializers.BooleanField(required=False)
    institution_name = SafeCharField(max_length=160, required=False)
    title = SafeCharField(max_length=120, required=False)
    body = serializers.CharField(max_length=4000, required=False)
    signatory_name = SafeCharField(max_length=120, required=False, allow_blank=True)
    signatory_title = SafeCharField(max_length=120, required=False, allow_blank=True)
    footer = SafeCharField(max_length=200, required=False, allow_blank=True)


class CertificateSerializer(StrictModelSerializer):
    """The staff record."""

    template_name = serializers.CharField(source="template.name", read_only=True, default=None)
    issued_by_name = serializers.CharField(
        source="issued_by.get_full_name", read_only=True, default=None
    )
    supersedes_number = serializers.CharField(
        source="supersedes.number", read_only=True, default=None
    )
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certificate
        fields = (
            "id",
            "number",
            "verification_code",
            "completion",
            "template",
            "template_name",
            "student_name",
            "student_code",
            "course_title",
            "batch_code",
            "completion_date",
            "status",
            "is_live",
            "issued_at",
            "issued_by_name",
            "revoked_at",
            "revocation_reason",
            "supersedes_number",
            "reissue_reason",
        )
        read_only_fields = fields


class StudentCertificateSerializer(StrictModelSerializer):
    """A student's own certificate.

    Carries the verification code — it is printed on their certificate, so
    withholding it here would be theatre — but not who issued it or why anything
    was reissued, which is staff information.
    """

    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certificate
        fields = (
            "id",
            "number",
            "verification_code",
            "course_title",
            "batch_code",
            "completion_date",
            "status",
            "is_live",
            "issued_at",
        )
        read_only_fields = fields


class IssueSerializer(StrictSerializer):
    template = serializers.UUIDField(required=False, allow_null=True)


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=300)


class ReissueSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=300)
    template = serializers.UUIDField(required=False, allow_null=True)


class PublicCertificateSerializer(StrictSerializer):
    """§6.8 — everything an anonymous verifier may see, and nothing else.

    Written as an explicit list rather than a model serializer with exclusions:
    the risk here is a field being *added* to the model later and silently
    appearing on a public endpoint.
    """

    certificate_number = serializers.CharField()
    student_name = serializers.CharField()
    course_title = serializers.CharField()
    completion_date = serializers.DateField()
    issued_on = serializers.DateField()
    status = serializers.CharField()
    is_valid = serializers.BooleanField()
    revoked_on = serializers.DateField(allow_null=True)
    institution = serializers.CharField(allow_blank=True)
