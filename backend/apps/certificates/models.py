"""Certificates — §6.7 and §6.8.

A certificate is the one artefact of this system that leaves it. Somebody will
put it on a CV, an employer will type its code into a public page, and it has to
still be right and still be checkable years later. Three consequences shape the
model.

**It is a snapshot, not a view.** The student's name and the course title are
*copied onto the row* at the moment of issue. A course renamed in 2027 must not
retroactively change what a 2026 certificate says, and neither must a student
correcting the spelling of their name — that is a reissue, deliberately, with
the old one superseded and both kept.

**The verification code is not the identifier.** The primary key is a UUID and
the certificate number is sequential and human-readable; neither is what the
public endpoint takes. That takes ``verification_code``: 160 bits from
``secrets``, unguessable. Anyone who can read one certificate number therefore
cannot enumerate the rest (§6.8).

**Revocation is a state, not a delete.** A revoked certificate still verifies —
and says it was revoked. Deleting it would make a forgery unfalsifiable, because
the checker would see "not found" for both a fake and a withdrawal.
"""

from __future__ import annotations

import re
import secrets

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters

#: 160 bits, url-safe. Long enough that guessing is not a strategy, short enough
#: to print under a QR code.
VERIFICATION_CODE_BYTES = 20


def new_verification_code() -> str:
    return secrets.token_urlsafe(VERIFICATION_CODE_BYTES)


class CertificateStatus(models.TextChoices):
    ISSUED = "issued", _("Issued")
    REVOKED = "revoked", _("Revoked")
    SUPERSEDED = "superseded", _("Superseded by a reissue")


#: Statuses in which a certificate is a valid claim.
LIVE_STATUSES = frozenset({CertificateStatus.ISSUED})


class CertificateTemplate(BaseModel):
    """The wording and look of a certificate.

    Deliberately a small set of named fields rather than free HTML: a template
    is rendered into a PDF, and accepting markup would mean accepting a document
    format's worth of injection surface for the sake of letting somebody centre
    a heading.
    """

    #: Only these may appear in the body. An unknown placeholder is a typo the
    #: author should be told about, not a hole in a rendered certificate.
    ALLOWED_PLACEHOLDERS = (
        "student_name",
        "course_title",
        "completion_date",
        "certificate_number",
        "batch_code",
        "institution_name",
    )

    name = models.CharField(
        _("name"), max_length=120, unique=True, validators=[validate_no_control_characters]
    )
    is_default = models.BooleanField(_("default"), default=False)

    institution_name = models.CharField(_("institution"), max_length=160, default="Grras Solutions")
    title = models.CharField(_("heading"), max_length=120, default="Certificate of Completion")
    body = models.TextField(
        _("body"),
        default=(
            "This is to certify that {student_name} has successfully completed "
            "the course {course_title} on {completion_date}."
        ),
        help_text=_(
            "Placeholders: {student_name}, {course_title}, {completion_date}, "
            "{certificate_number}, {batch_code}, {institution_name}."
        ),
    )
    signatory_name = models.CharField(_("signatory"), max_length=120, blank=True)
    signatory_title = models.CharField(_("signatory title"), max_length=120, blank=True)
    footer = models.CharField(
        _("footer"),
        max_length=200,
        blank=True,
        default="Verify this certificate at the address in the QR code.",
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="certificate_templates",
    )

    class Meta:
        verbose_name = _("certificate template")
        verbose_name_plural = _("certificate templates")
        ordering = ("-is_default", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="certificate_single_default_template",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        used = set(re.findall(r"\{(\w+)\}", self.body or ""))
        unknown = sorted(used - set(self.ALLOWED_PLACEHOLDERS))
        if unknown:
            raise ValidationError(
                {
                    "body": (
                        "Unknown placeholder(s): "
                        + ", ".join(f"{{{name}}}" for name in unknown)
                        + "."
                    )
                }
            )


class CertificateQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "completion",
            "completion__enrollment",
            "completion__enrollment__student",
            "completion__enrollment__student__user",
            "completion__enrollment__course",
            "completion__enrollment__batch",
            "template",
            "issued_by",
        )

    def live(self):
        return self.filter(status__in=list(LIVE_STATUSES))


class Certificate(BaseModel):
    """One issued certificate, and everything a verifier needs to check it."""

    number = models.CharField(_("certificate number"), max_length=24, unique=True, editable=False)
    verification_code = models.CharField(
        _("verification code"),
        max_length=64,
        unique=True,
        editable=False,
        default=new_verification_code,
        help_text=_("What the public endpoint takes. Unguessable, and not the number."),
    )

    completion = models.ForeignKey(
        "progress.CourseCompletion", on_delete=models.PROTECT, related_name="certificates"
    )
    template = models.ForeignKey(
        CertificateTemplate, null=True, on_delete=models.PROTECT, related_name="certificates"
    )

    # --- The snapshot. Copied at issue, never read through a relation again.
    student_name = models.CharField(_("student name"), max_length=200)
    student_code = models.CharField(_("student id"), max_length=20)
    course_title = models.CharField(_("course"), max_length=200)
    batch_code = models.CharField(_("batch"), max_length=20)
    completion_date = models.DateField(_("completion date"))

    status = models.CharField(
        _("status"),
        max_length=12,
        choices=CertificateStatus.choices,
        default=CertificateStatus.ISSUED,
    )
    issued_at = models.DateTimeField(_("issued at"), default=timezone.now)
    issued_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="certificates_issued",
    )

    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)
    revocation_reason = models.CharField(_("reason"), max_length=300, blank=True)

    #: A reissue points at what it replaces, so the chain can be walked.
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="superseded_by"
    )
    reissue_reason = models.CharField(_("reissue reason"), max_length=300, blank=True)

    objects = CertificateQuerySet.as_manager()

    class Meta:
        verbose_name = _("certificate")
        verbose_name_plural = _("certificates")
        ordering = ("-issued_at",)
        indexes = [
            models.Index(fields=["status"], name="certificate_status_idx"),
            models.Index(fields=["student_code"], name="certificate_student_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=CertificateStatus.REVOKED) | models.Q(revoked_at__isnull=False)
                ),
                name="certificate_revoked_has_a_time",
            ),
            # At most one live certificate per completion. A reissue supersedes
            # the old one in the same transaction, so two valid claims to the
            # same course cannot exist.
            models.UniqueConstraint(
                fields=["completion"],
                condition=models.Q(status=CertificateStatus.ISSUED),
                name="certificate_one_live_per_completion",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def enrollment(self):
        return self.completion.enrollment
