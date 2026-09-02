"""Certificate services — issue, reissue, revoke.

Approval comes first, always: §6.7 requires that an administrator has approved
the completion before anything is issued, and there is no path here that skips
it. Everything else follows from the model's three rules — a certificate is a
snapshot, its verification code is not its number, and revocation is a state.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_certificate_number
from apps.progress.models import CompletionStatus, CourseCompletion

from .models import Certificate, CertificateStatus, CertificateTemplate


def default_template() -> CertificateTemplate | None:
    return CertificateTemplate.objects.filter(is_default=True).first()


@transaction.atomic
def save_template(
    *, actor: User, template: CertificateTemplate | None = None, **fields
) -> CertificateTemplate:
    """Create or edit a template.

    Marking one default clears the previous one in the same transaction — the
    partial unique index would otherwise refuse the write, which is the right
    outcome for the database and a confusing one for the person clicking.
    """
    template = template or CertificateTemplate(created_by=actor)
    for key, value in fields.items():
        setattr(template, key, value)

    if template.is_default:
        # Cleared *before* validating: the partial unique index is real, and
        # `full_clean` would otherwise refuse a state we are in the middle of
        # changing. The surrounding transaction undoes this if validation fails.
        CertificateTemplate.objects.exclude(pk=template.pk).filter(is_default=True).update(
            is_default=False
        )

    try:
        template.full_clean(exclude=["created_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    template.save()

    record(
        action=AuditAction.CERTIFICATE_TEMPLATE_SAVED,
        actor=actor,
        resource_type="certificate_template",
        resource_id=template.pk,
        context={"name": template.name, "default": template.is_default},
        durable=False,
    )
    return template


def _snapshot(completion: CourseCompletion) -> dict:
    """The values copied onto the certificate at the moment of issue."""
    enrollment = completion.enrollment
    student = enrollment.student
    return {
        "student_name": student.user.get_full_name(),
        "student_code": student.student_id,
        "course_title": enrollment.course.title,
        "batch_code": enrollment.batch.code,
        "completion_date": completion.completed_on,
    }


@transaction.atomic
def issue_certificate(
    *, completion: CourseCompletion, actor: User, template: CertificateTemplate | None = None
) -> Certificate:
    """Issue the certificate for an approved completion."""
    if completion.status != CompletionStatus.APPROVED:
        raise ApplicationError(
            {"completion": ["The completion must be approved before a certificate is issued."]}
        )
    if completion.certificates.live().exists():
        raise ConflictError(
            {"certificate": ["A certificate has already been issued. Reissue it instead."]}
        )

    chosen = template or default_template()
    if chosen is None:
        raise ApplicationError(
            {"template": ["Create a certificate template before issuing certificates."]}
        )

    certificate = Certificate.objects.create(
        number=next_certificate_number(),
        completion=completion,
        template=chosen,
        issued_by=actor if getattr(actor, "pk", None) else None,
        status=CertificateStatus.ISSUED,
        **_snapshot(completion),
    )

    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=completion.enrollment.student.user,
        kind=NotificationKind.CERTIFICATE_ISSUED,
        title=certificate.course_title,
        body=f"Certificate {certificate.number} has been issued.",
        link_path="/my-progress",
        resource_type="certificate",
        resource_id=certificate.pk,
    )

    record(
        action=AuditAction.CERTIFICATE_ISSUED,
        actor=actor,
        resource_type="certificate",
        resource_id=certificate.pk,
        context={
            "number": certificate.number,
            "student": certificate.student_code,
            "course": certificate.course_title,
        },
        durable=False,
    )
    return certificate


@transaction.atomic
def reissue_certificate(
    *,
    certificate: Certificate,
    actor: User,
    reason: str,
    template: CertificateTemplate | None = None,
) -> Certificate:
    """Replace a certificate with a fresh one, keeping both.

    Used when the snapshot needs to change — a corrected name, a re-typed course
    title. The old row is marked superseded rather than edited, so a copy
    already in circulation still verifies and says what happened to it.
    """
    if not reason.strip():
        raise ApplicationError({"reason": ["Say why the certificate is being reissued."]})
    if certificate.status == CertificateStatus.REVOKED:
        raise ConflictError(
            {"certificate": ["A revoked certificate cannot be reissued. Issue a new one."]}
        )

    completion = certificate.completion
    certificate.status = CertificateStatus.SUPERSEDED
    certificate.save(update_fields=["status", "updated_at"])

    replacement = Certificate.objects.create(
        number=next_certificate_number(),
        completion=completion,
        template=template or certificate.template or default_template(),
        issued_by=actor if getattr(actor, "pk", None) else None,
        status=CertificateStatus.ISSUED,
        supersedes=certificate,
        reissue_reason=reason[:300],
        **_snapshot(completion),
    )

    record(
        action=AuditAction.CERTIFICATE_REISSUED,
        actor=actor,
        resource_type="certificate",
        resource_id=replacement.pk,
        context={
            "number": replacement.number,
            "replaces": certificate.number,
            "reason": replacement.reissue_reason,
        },
        durable=False,
    )
    return replacement


@transaction.atomic
def revoke_certificate(*, certificate: Certificate, actor: User, reason: str) -> Certificate:
    """Withdraw a certificate. It still verifies, and says it was revoked."""
    if not reason.strip():
        raise ApplicationError({"reason": ["Say why the certificate is being revoked."]})
    if certificate.status == CertificateStatus.REVOKED:
        raise ConflictError({"certificate": ["This certificate is already revoked."]})

    certificate.status = CertificateStatus.REVOKED
    certificate.revoked_at = timezone.now()
    certificate.revocation_reason = reason[:300]
    certificate.save(update_fields=["status", "revoked_at", "revocation_reason", "updated_at"])

    record(
        action=AuditAction.CERTIFICATE_REVOKED,
        actor=actor,
        resource_type="certificate",
        resource_id=certificate.pk,
        context={"number": certificate.number, "reason": certificate.revocation_reason},
        durable=False,
    )
    return certificate


def public_view(certificate: Certificate) -> dict:
    """What an anonymous verifier is allowed to see — §6.8.

    An allowlist, written out field by field, because the risk here is
    *addition*: a future serializer that grew a field would leak it to the
    internet. Deliberately absent: email, phone, marks, attendance, the
    enrolment, the student's internal id, and anything about the batch beyond
    its code.
    """
    return {
        "certificate_number": certificate.number,
        "student_name": certificate.student_name,
        "course_title": certificate.course_title,
        "completion_date": certificate.completion_date,
        "issued_on": certificate.issued_at.date(),
        "status": certificate.status,
        "is_valid": certificate.is_live,
        "revoked_on": certificate.revoked_at.date() if certificate.revoked_at else None,
        "institution": certificate.template.institution_name if certificate.template else "",
    }
