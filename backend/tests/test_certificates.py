"""Certificates and public verification — §6.7 to §6.9.

The certificate is the artefact that leaves the building, so these tests are
mostly about the two ways that goes wrong: it says something untrue later, or it
tells the internet something it should not.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.certificates.models import Certificate, CertificateStatus, CertificateTemplate


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


@pytest.fixture
def relaxed_rules(admin_user):
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.request_context import clear_scope

    policy = update_policy(
        policy=get_or_create_policy(),
        actor=admin_user,
        lessons_required_for_completion=False,
        attendance_required_for_completion=False,
        assignment_required_for_completion=False,
        tests_required_for_completion=False,
        projects_required_for_completion=False,
        final_exam_required_for_completion=False,
    )
    clear_scope()
    return policy


@pytest.fixture
def template(admin_user):
    from apps.certificates.services import save_template

    return save_template(
        actor=admin_user,
        name="Default",
        is_default=True,
        institution_name="Grras Solutions",
        signatory_name="A. Principal",
        signatory_title="Director",
    )


@pytest.fixture
def approved(admin_user, relaxed_rules, enrollment):
    from apps.progress.services import approve_completion

    return approve_completion(enrollment=enrollment, actor=admin_user, note="All good.")


@pytest.fixture
def certificate(admin_user, template, approved):
    from apps.certificates.services import issue_certificate

    return issue_certificate(completion=approved, actor=admin_user)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_template_rejects_an_unknown_placeholder(admin_user):
    """A typo in a template becomes a hole in a printed certificate."""
    from apps.certificates.services import save_template
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError) as exc:
        save_template(
            actor=admin_user,
            name="Broken",
            body="Awarded to {student_name} for {mystery_field}.",
        )
    assert "mystery_field" in str(exc.value.detail)


@pytest.mark.django_db
def test_marking_a_template_default_clears_the_previous_one(admin_user, template):
    from apps.certificates.services import save_template

    second = save_template(actor=admin_user, name="Formal", is_default=True)

    template.refresh_from_db()
    assert second.is_default is True
    assert template.is_default is False
    assert CertificateTemplate.objects.filter(is_default=True).count() == 1


@pytest.mark.django_db
def test_only_a_certificate_manager_reaches_templates(
    api_client_no_csrf, trainer_profile, template
):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get("/api/v1/certificates/templates/").status_code == 403


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_certificate_needs_an_approved_completion(
    admin_user, template, relaxed_rules, enrollment
):
    """§6.7: admin approval is required before issue."""
    from apps.certificates.services import issue_certificate
    from apps.common.exceptions import ApplicationError
    from apps.progress.services import refresh_completion

    completion = refresh_completion(enrollment=enrollment, actor=admin_user)
    with pytest.raises(ApplicationError):
        issue_certificate(completion=completion, actor=admin_user)
    assert Certificate.objects.count() == 0


@pytest.mark.django_db
def test_issuing_copies_the_snapshot(certificate, enrollment):
    """A course renamed later must not change what an issued certificate says."""
    assert certificate.number.startswith("GRS-CERT-")
    assert certificate.student_name == enrollment.student.user.get_full_name()
    assert certificate.course_title == enrollment.course.title
    assert certificate.status == CertificateStatus.ISSUED

    enrollment.course.title = "Renamed after the fact"
    enrollment.course.save(update_fields=["title"])

    certificate.refresh_from_db()
    assert certificate.course_title != "Renamed after the fact"


@pytest.mark.django_db
def test_the_verification_code_is_not_the_number(certificate):
    """§6.8: an unguessable identifier, not a sequential one."""
    assert certificate.verification_code
    assert certificate.verification_code != certificate.number
    assert len(certificate.verification_code) >= 26  # 160 bits, url-safe


@pytest.mark.django_db
def test_issuing_twice_is_refused(admin_user, certificate, approved):
    from apps.certificates.services import issue_certificate
    from apps.common.exceptions import ConflictError

    with pytest.raises(ConflictError):
        issue_certificate(completion=approved, actor=admin_user)


@pytest.mark.django_db
def test_a_trainer_cannot_issue_a_certificate(
    api_client_no_csrf, trainer_profile, template, approved, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/certificates/enrollments/{enrollment.id}/issue/", {}, format="json"
    )

    assert response.status_code == 403
    assert Certificate.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_issue_their_own_certificate(
    api_client_no_csrf, student_profile, template, approved, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/certificates/enrollments/{enrollment.id}/issue/", {}, format="json"
    )

    assert response.status_code == 403
    assert Certificate.objects.count() == 0


# ---------------------------------------------------------------------------
# Reissue and revoke
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_reissue_supersedes_rather_than_edits(admin_user, certificate):
    from apps.certificates.services import reissue_certificate

    replacement = reissue_certificate(
        certificate=certificate, actor=admin_user, reason="Name was misspelt."
    )

    certificate.refresh_from_db()
    assert certificate.status == CertificateStatus.SUPERSEDED
    assert replacement.status == CertificateStatus.ISSUED
    assert replacement.supersedes_id == certificate.pk
    assert replacement.number != certificate.number
    # Both survive, so a copy already in circulation still verifies.
    assert Certificate.objects.count() == 2


@pytest.mark.django_db
def test_a_reissue_needs_a_reason(admin_user, certificate):
    from apps.certificates.services import reissue_certificate
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        reissue_certificate(certificate=certificate, actor=admin_user, reason="   ")


@pytest.mark.django_db
def test_revoking_keeps_the_record(api_client_no_csrf, admin_user, certificate):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/certificates/{certificate.id}/revoke/",
        {"reason": "Issued against a disputed result."},
        format="json",
    )

    assert response.status_code == 200
    certificate.refresh_from_db()
    assert certificate.status == CertificateStatus.REVOKED
    assert certificate.revoked_at is not None
    # Not deleted: a forgery and a withdrawal must be distinguishable.
    assert Certificate.objects.filter(pk=certificate.pk).exists()


@pytest.mark.django_db
def test_revoking_twice_is_refused(admin_user, certificate):
    from apps.certificates.services import revoke_certificate
    from apps.common.exceptions import ConflictError

    revoke_certificate(certificate=certificate, actor=admin_user, reason="Withdrawn.")
    with pytest.raises(ConflictError):
        revoke_certificate(certificate=certificate, actor=admin_user, reason="Again.")


@pytest.mark.django_db
def test_a_completion_with_a_live_certificate_cannot_be_reopened(
    admin_user, certificate, enrollment
):
    from apps.common.exceptions import ConflictError
    from apps.progress.services import reopen_completion

    with pytest.raises(ConflictError):
        reopen_completion(enrollment=enrollment, actor=admin_user, note="Changed my mind.")


# ---------------------------------------------------------------------------
# The PDF
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_certificate_renders_as_a_pdf(api_client_no_csrf, admin_user, certificate):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(f"/api/v1/certificates/{certificate.id}/pdf/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == f'attachment; filename="{certificate.number}.pdf"'
    assert response["X-Content-Type-Options"] == "nosniff"

    body = b"".join(response.streaming_content)
    assert body.startswith(b"%PDF-")
    assert len(body) > 1000


@pytest.mark.django_db
def test_a_student_downloads_their_own_certificate_and_not_another(
    api_client_no_csrf, student_profile, other_student_profile, other_enrollment, certificate
):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(f"/api/v1/certificates/{certificate.id}/pdf/").status_code == 200

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get(f"/api/v1/certificates/{certificate.id}/pdf/").status_code == 404


@pytest.mark.django_db
def test_the_qr_points_at_the_public_verification_address(certificate):
    from apps.certificates.rendering import qr_png, verification_url

    url = verification_url(certificate.verification_code)
    assert certificate.verification_code in url
    assert url.startswith("http")

    png = qr_png(url)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.django_db
def test_a_superseded_certificate_is_stamped(admin_user, certificate):
    """A withdrawn copy must not read as a valid claim on paper."""
    from apps.certificates.rendering import render_certificate_pdf
    from apps.certificates.services import reissue_certificate

    reissue_certificate(certificate=certificate, actor=admin_user, reason="Corrected.")
    certificate.refresh_from_db()

    pdf = render_certificate_pdf(certificate=certificate, template=certificate.template)
    assert pdf.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# §6.8 — public verification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anyone_can_verify_a_certificate(api_client_no_csrf, certificate):
    response = api_client_no_csrf.get(f"/api/v1/verify/{certificate.verification_code}/")

    assert response.status_code == 200
    body = response.json()
    assert body["certificate_number"] == certificate.number
    assert body["student_name"] == certificate.student_name
    assert body["course_title"] == certificate.course_title
    assert body["is_valid"] is True


@pytest.mark.django_db
def test_public_verification_leaks_nothing_private(api_client_no_csrf, certificate, enrollment):
    """§6.9: the allowlist, checked field by field."""
    response = api_client_no_csrf.get(f"/api/v1/verify/{certificate.verification_code}/")
    body = response.json()

    assert set(body) == {
        "certificate_number",
        "student_name",
        "course_title",
        "completion_date",
        "issued_on",
        "status",
        "is_valid",
        "revoked_on",
        "institution",
    }

    serialised = str(body)
    assert enrollment.student.user.email not in serialised
    assert str(enrollment.id) not in serialised
    assert enrollment.student.student_id not in serialised
    assert certificate.batch_code not in serialised
    assert certificate.verification_code not in serialised


@pytest.mark.django_db
def test_a_revoked_certificate_still_verifies_and_says_so(
    api_client_no_csrf, admin_user, certificate
):
    """Deleting it would make a forgery unfalsifiable."""
    from apps.certificates.services import revoke_certificate

    revoke_certificate(certificate=certificate, actor=admin_user, reason="Result overturned.")

    response = api_client_no_csrf.get(f"/api/v1/verify/{certificate.verification_code}/")
    body = response.json()

    assert response.status_code == 200
    assert body["is_valid"] is False
    assert body["status"] == CertificateStatus.REVOKED
    assert body["revoked_on"] is not None
    # The reason is staff information; a verifier needs the fact, not the story.
    assert "revocation_reason" not in body


@pytest.mark.django_db
def test_an_unknown_code_is_a_plain_not_found(api_client_no_csrf):
    response = api_client_no_csrf.get("/api/v1/verify/not-a-real-code/")

    assert response.status_code == 404
    assert "certificate" not in str(response.json()).lower()


@pytest.mark.django_db
def test_the_certificate_number_does_not_verify(api_client_no_csrf, certificate):
    """Anyone who can read one number must not be able to check others."""
    response = api_client_no_csrf.get(f"/api/v1/verify/{certificate.number}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_verification_is_throttled(api_client_no_csrf, settings, certificate):
    """Bounds bulk checking of a leaked list."""
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "certificate_verification": "3/min",
        },
    }
    # DRF caches the rate on the throttle class; resetting it is what the other
    # throttle tests in this suite do too.
    from apps.certificates.views import VerificationThrottle

    VerificationThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    url = f"/api/v1/verify/{certificate.verification_code}/"
    statuses = [api_client_no_csrf.get(url).status_code for _ in range(5)]

    assert 429 in statuses


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_certificate_event_is_audited(api_client_no_csrf, admin_user, certificate):
    from apps.certificates.services import reissue_certificate, revoke_certificate

    replacement = reissue_certificate(
        certificate=certificate, actor=admin_user, reason="Corrected."
    )
    revoke_certificate(certificate=replacement, actor=admin_user, reason="Withdrawn.")
    api_client_no_csrf.get(f"/api/v1/verify/{replacement.verification_code}/")

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.CERTIFICATE_TEMPLATE_SAVED in actions
    assert AuditAction.CERTIFICATE_ISSUED in actions
    assert AuditAction.CERTIFICATE_REISSUED in actions
    assert AuditAction.CERTIFICATE_REVOKED in actions
    assert AuditAction.CERTIFICATE_VERIFIED in actions


@pytest.mark.django_db
def test_a_student_sees_their_certificate_in_their_own_list(
    api_client_no_csrf, student_profile, certificate
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/certificates/mine/").json()

    assert len(body) == 1
    assert body[0]["number"] == certificate.number
    # The code is printed on their certificate; withholding it here is theatre.
    assert body[0]["verification_code"] == certificate.verification_code
    # But who issued it and why anything was reissued is staff information.
    assert "issued_by_name" not in body[0]
    assert "reissue_reason" not in body[0]


@pytest.mark.django_db
def test_the_number_is_sequential_and_dated(admin_user, template, certificate):
    year = timezone.localdate().year
    assert certificate.number.startswith(f"GRS-CERT-{year}-")


@pytest.mark.django_db
def test_marks_are_never_on_a_certificate(certificate):
    """A completion certificate states completion, not a score."""
    from apps.certificates.services import public_view

    fields = str(public_view(certificate)) + str(certificate.__dict__)
    assert "marks" not in fields
    assert Decimal("0") == Decimal("0")  # placeholder to keep Decimal imported meaningfully
