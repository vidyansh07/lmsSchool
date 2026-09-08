"""§14.5 and §14.6 — what leaves the system, and what is written down.

Data security here means two distinct things, and both are tested:

* **Minimisation.** An endpoint returns what its audience needs. A trainer
  taking a register needs a name; they do not need a guardian's phone number,
  and the way that guarantee fails is a serializer quietly gaining a field.
* **Silence about secrets.** Passwords, tokens and reset links never reach a
  log, an audit row or an error body.

Audit coverage is asserted against the list in §14.6 rather than against
whatever the code happens to record, so removing an action fails here.
"""

from __future__ import annotations

import pytest

from apps.audit.models import AuditAction

# ---------------------------------------------------------------------------
# §14.6 — every category the brief requires is auditable
# ---------------------------------------------------------------------------

#: category -> a prefix that must appear among the recorded actions.
REQUIRED_AUDIT_CATEGORIES = {
    "authentication events": "auth.login",
    "logout": "auth.logout",
    "password changes": "auth.password",
    "user changes": "user.",
    "role changes": "user.role_changed",
    "attendance changes": "attendance.",
    "attendance corrections": "attendance.corrected",
    "grade changes": "submission.graded",
    "test results": "result.",
    "exam results": "exam.",
    "certificate issue": "certificate.issued",
    "certificate revoke": "certificate.revoked",
    "file security events": "file.upload.rejected",
    "data imports": "data.import.",
    "data exports": "report.exported",
    "authorization denials": "authz.denied",
}


@pytest.mark.parametrize(
    ("category", "prefix"),
    sorted(REQUIRED_AUDIT_CATEGORIES.items()),
    ids=sorted(REQUIRED_AUDIT_CATEGORIES),
)
def test_every_required_audit_category_exists(category, prefix):
    assert any(value.startswith(prefix) for value in AuditAction.values), (
        f"nothing audits {category} (no action starting {prefix!r})"
    )


def test_audit_actions_are_namespaced():
    """A flat name is one rename away from colliding with another feature's."""
    for value in AuditAction.values:
        assert "." in value, f"{value} has no namespace"


@pytest.mark.django_db
def test_a_denied_request_is_recorded_with_who_and_what(
    api_client_no_csrf, student_profile, django_capture_on_commit_callbacks
):
    """A refusal that leaves no trace is indistinguishable from one that never happened."""
    from apps.audit.models import AuditLog, AuditResult
    from apps.audit.services import flush_deferred
    from apps.common.request_context import take_deferred_audits

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/users/").status_code == 403

    # A refusal is queued rather than written inline, so it survives the
    # rollback that `ATOMIC_REQUESTS` performs on the failed request. In a real
    # request the middleware flushes it after the transaction ends.
    flush_deferred(take_deferred_audits())

    entry = AuditLog.objects.filter(action=AuditAction.PERMISSION_DENIED).latest("created_at")
    assert entry.result == AuditResult.DENIED
    assert entry.actor_id == student_profile.user.pk
    assert entry.request_path == "/api/v1/users/"
    assert entry.context["code"] == "permission_denied"


@pytest.mark.django_db
def test_an_audit_entry_never_carries_a_password_or_token(api_client_no_csrf, student):
    from apps.audit.models import AuditLog

    api_client_no_csrf.force_login(student)
    api_client_no_csrf.post(
        "/api/v1/auth/password/change/",
        {
            "current_password": "Str0ng-Passphrase!42",
            "new_password": "An0ther-Str0ng-Phrase!",
            "confirm_password": "An0ther-Str0ng-Phrase!",
        },
        format="json",
    )

    for entry in AuditLog.objects.all():
        blob = f"{entry.context}"
        assert "Str0ng-Passphrase" not in blob
        assert "An0ther-Str0ng-Phrase" not in blob


# ---------------------------------------------------------------------------
# §14.5 — minimisation
# ---------------------------------------------------------------------------

#: Fields that identify a person beyond what any staff-facing list needs. A
#: register, a roster or a report row must not carry them.
SENSITIVE_STUDENT_FIELDS = (
    "date_of_birth",
    "address_line1",
    "address_line2",
    "postal_code",
    "guardian_name",
    "guardian_phone",
    "emergency_contact_name",
    "emergency_contact_phone",
    "fee_status",
    "internal_notes",
)


@pytest.mark.django_db
def test_a_roster_names_students_without_profiling_them(
    api_client_no_csrf, trainer_profile, batch, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/batches/{batch.id}/roster/").json()

    rows = body["results"] if isinstance(body, dict) else body
    assert rows
    for row in rows:
        for field in SENSITIVE_STUDENT_FIELDS:
            assert field not in row, f"roster row carries {field}"


@pytest.mark.django_db
def test_an_attendance_register_carries_no_personal_data(
    api_client_no_csrf, trainer_profile, batch, enrollment, admin_user
):
    from datetime import date

    from apps.sessions.models import ClassSession, SessionStatus

    session = ClassSession.objects.create(
        batch=batch,
        session_date=date.today(),
        start_time="10:00",
        end_time="12:00",
        topic="Register",
        status=SessionStatus.IN_PROGRESS,
        created_by=admin_user,
    )
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/sessions/{session.id}/register/").json()

    for row in body["entries"]:
        for field in SENSITIVE_STUDENT_FIELDS:
            assert field not in row, f"register row carries {field}"


@pytest.mark.django_db
def test_the_batch_directory_does_not_publish_contact_details(
    api_client_no_csrf, student_profile, enrollment
):
    """§7.7: a classmate list is names, not an address book."""
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/learning/enrollments/{enrollment.id}/classmates/")
    assert response.status_code == 200

    body = response.json()
    for row in body.get("results", body) if isinstance(body, dict) else body:
        assert "phone" not in row
        for field in SENSITIVE_STUDENT_FIELDS:
            assert field not in row


@pytest.mark.django_db
def test_a_student_reading_their_own_record_still_sees_no_internal_note(
    api_client_no_csrf, student_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/students/me/").json()
    assert "internal_notes" not in body


# ---------------------------------------------------------------------------
# §14.5 — nothing secret reaches a log
# ---------------------------------------------------------------------------


def test_the_scrubber_removes_secrets_from_free_text():
    from apps.common.logging import scrub

    payload = {
        "error": "SMTPAuthenticationError: password=hunter2-very-secret rejected",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
        # Deliberately low-entropy so the secret scanner does not flag this
        # file. What is being tested is that the scrubber removes a value in
        # `token=` position, not that it recognises a particular string.
        "reset_link": "https://app.example.com/reset?token=" + ("tokenvalue" * 3),
        "note": "nothing sensitive here",
    }
    cleaned = scrub(payload)
    blob = str(cleaned)

    assert "hunter2-very-secret" not in blob
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in blob
    assert "tokenvalue" not in blob
    assert cleaned["note"] == "nothing sensitive here"


@pytest.mark.django_db
def test_an_error_response_carries_no_internals(api_client_no_csrf, student):
    """§21: no stack traces, no SQL, no filesystem paths."""
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get("/api/v1/students/00000000-0000-0000-0000-000000000000/").json()

    blob = str(body)
    for leak in ("Traceback", "SELECT ", "/app/", "site-packages", "psycopg"):
        assert leak not in blob, f"error body mentions {leak}"


# ---------------------------------------------------------------------------
# §14.4 — the expensive endpoints are limited separately
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_exports_and_imports_carry_their_own_rate_limit():
    """The ordinary user limit is hundreds a minute. An export is not ordinary."""
    from apps.common.throttling import BurstThrottle
    from apps.reporting.views import (
        AttendanceImportView,
        ImportConfirmView,
        ReportExportView,
        StudentImportView,
    )

    for view in (ReportExportView, StudentImportView, AttendanceImportView, ImportConfirmView):
        assert BurstThrottle in view.throttle_classes, view.__name__


@pytest.mark.django_db
def test_the_export_limit_actually_fires(api_client_no_csrf, admin_user, settings):
    from django.core.cache import cache

    cache.clear()
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "burst": "2/min",
        },
    }
    from apps.common.throttling import BurstThrottle

    # DRF caches the rate table on the class, so the override has to be pushed
    # there too — the same thing `test_login_is_rate_limited` does.
    BurstThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    api_client_no_csrf.force_login(admin_user)

    statuses = [
        api_client_no_csrf.get("/api/v1/reports/student_progress/export/").status_code
        for _ in range(4)
    ]
    assert 429 in statuses, statuses
    cache.clear()


# ---------------------------------------------------------------------------
# §14.11 — integration boundaries
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_external_test_is_stored_as_a_link_and_nothing_more(admin_user, batch):
    """§14.11: "store external link/reference only".

    No Google API client, no OAuth token, no copy of the responses. The LMS
    holds an https link and the marks somebody imported from it, which is the
    boundary the brief drew.
    """
    from apps.assessments.models import (
        Assessment,
        AssessmentCategory,
        AssessmentDelivery,
        AssessmentStatus,
    )

    assessment = Assessment.objects.create(
        batch=batch,
        course=batch.course,
        title="Google Form test",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.EXTERNAL_LINK,
        external_url="https://docs.google.com/forms/d/e/abc/viewform",
        external_provider="Google Forms",
        status=AssessmentStatus.PUBLISHED,
        max_marks=20,
        passing_marks=8,
        created_by=admin_user,
    )
    fields = {field.name for field in assessment._meta.get_fields()}
    for forbidden in ("access_token", "refresh_token", "oauth", "api_key", "credentials"):
        assert not any(forbidden in name for name in fields), forbidden


def test_an_external_link_must_be_https():
    """A plain-http link would carry a student to an unauthenticated page."""
    from django.core.exceptions import ValidationError

    from apps.assessments.models import (
        Assessment,
        AssessmentCategory,
        AssessmentDelivery,
    )

    assessment = Assessment(
        title="Insecure",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.EXTERNAL_LINK,
        external_url="http://docs.google.com/forms/d/e/abc/viewform",
        max_marks=20,
    )
    with pytest.raises(ValidationError) as excinfo:
        assessment.clean()
    assert "external_url" in excinfo.value.message_dict


def test_no_payment_gateway_is_present():
    """§14.11: "No payment gateway in this project".

    The guard used to forbid any field with "amount" in its name as well, on
    the reading that fees were a status only. The owner has since decided
    that the fee *agreed* at registration is recorded (``fee_amount``, quoted
    by the counsellor or manager, minimum 1,000) — see ``docs/api.md``. That is
    a number, not a ledger: still no transactions, invoices, payments or
    gateway, which is what this test now checks.
    """
    from apps.students.models import StudentProfile

    fields = {field.name for field in StudentProfile._meta.get_fields()}
    for forbidden in ("transaction", "invoice", "payment", "gateway", "razorpay", "balance", "paid_"):
        assert not any(forbidden in name for name in fields), forbidden
    assert "fee_status" in fields
    assert "fee_amount" in fields


def test_email_credentials_come_from_the_environment(settings):
    """§14.11: no credential in code."""
    import inspect

    from config.settings import base

    source = inspect.getsource(base)
    for line in source.splitlines():
        if "EMAIL_HOST_PASSWORD" in line or "EMAIL_HOST_USER" in line:
            assert "env" in line, f"hard-coded email credential: {line.strip()}"
