"""Duplicate detection at registration (ERP Phase 17), `USER_JOURNEYS.md`
§4.2 — treated as the disclosure-sensitive read it is, the same risk class
Phase 11's global search review scrutinized: a match outside the caller's
own reach must come back as nothing, never a redacted stub.

Also covers the override-with-reason audit trail written by
`apps.students.services.create_student` when registration proceeds past a
matched duplicate.
"""

from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.students.services import create_student

DUPLICATES_URL = "/api/v1/students/duplicates/"
STUDENTS_URL = "/api/v1/students/"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def matching_student(admin_user):
    """An existing, in-branch student the duplicate check should be able to
    find — by exact email in one test, by exact phone in another."""
    return create_student(
        email="rahul.verma@example.test",
        first_name="Rahul",
        last_name="Verma",
        phone="9876500000",
        actor=admin_user,
        password=PASSWORD,
        send_invitation=False,
    )


# ---------------------------------------------------------------------------
# GET /students/duplicates/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_exact_email_match_is_found(api_client_no_csrf, counsellor_user, matching_student):
    api_client_no_csrf.force_login(counsellor_user)

    body = api_client_no_csrf.get(f"{DUPLICATES_URL}?email=rahul.verma@example.test").json()

    assert [row["id"] for row in body["results"]] == [str(matching_student.pk)]
    row = body["results"][0]
    assert row["name"] == "Rahul Verma"
    assert row["student_id"] == matching_student.student_id
    assert row["batch_code"] == ""  # not yet enrolled on anything
    assert row["created_at"]


@pytest.mark.django_db
def test_an_exact_phone_match_is_found(api_client_no_csrf, counsellor_user, matching_student):
    api_client_no_csrf.force_login(counsellor_user)

    body = api_client_no_csrf.get(f"{DUPLICATES_URL}?phone=9876500000").json()

    assert [row["id"] for row in body["results"]] == [str(matching_student.pk)]


@pytest.mark.django_db
def test_an_email_that_matches_nobody_returns_an_empty_list(
    api_client_no_csrf, counsellor_user, matching_student
):
    api_client_no_csrf.force_login(counsellor_user)

    body = api_client_no_csrf.get(f"{DUPLICATES_URL}?email=nobody.here@example.test").json()

    assert body["results"] == []


@pytest.mark.django_db
def test_no_query_at_all_returns_an_empty_list(
    api_client_no_csrf, counsellor_user, matching_student
):
    """Neither field complete yet — the wizard has not asked the question."""
    api_client_no_csrf.force_login(counsellor_user)

    assert api_client_no_csrf.get(DUPLICATES_URL).json()["results"] == []


@pytest.mark.django_db
def test_a_match_outside_the_callers_branch_is_not_returned(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, other_branch
):
    """The safe failure mode: a real match at another centre comes back as
    nothing, not as a redacted stub. A false negative here is correct; a
    disclosure is not."""
    outside = create_student(
        email="pooja.pune@example.test",
        first_name="Pooja",
        last_name="Pune",
        phone="9998887777",
        actor=unbounded_superadmin,
        branch=other_branch,
        password=PASSWORD,
        send_invitation=False,
    )
    assert outside.branch_id == other_branch.pk  # the fixture set up what it claims to

    api_client_no_csrf.force_login(counsellor_user)
    by_email = api_client_no_csrf.get(f"{DUPLICATES_URL}?email=pooja.pune@example.test").json()
    by_phone = api_client_no_csrf.get(f"{DUPLICATES_URL}?phone=9998887777").json()

    assert by_email["results"] == []
    assert by_phone["results"] == []


@pytest.mark.django_db
def test_a_student_cannot_reach_the_duplicate_check(
    api_client_no_csrf, enrollment, matching_student
):
    """Gated on `student.create` — the same capability the registration
    wizard itself requires, not a laxer, separate gate."""
    api_client_no_csrf.force_login(enrollment.student.user)

    response = api_client_no_csrf.get(f"{DUPLICATES_URL}?email=rahul.verma@example.test")

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Override with reason, at the point registration actually proceeds
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_registering_past_a_shown_duplicate_without_a_reason_is_refused(
    api_client_no_csrf, counsellor_user, matching_student
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "second.rahul@example.test",
            "first_name": "Second",
            "last_name": "Rahul",
            "phone": "9876500000",  # matches `matching_student`
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "override_reason" in response.data["error"]["details"]
    from apps.accounts.models import User

    assert not User.objects.filter(email="second.rahul@example.test").exists()


@pytest.mark.django_db
def test_registering_past_a_shown_duplicate_with_a_reason_is_recorded(
    api_client_no_csrf, counsellor_user, matching_student
):
    reason = "Confirmed by phone — a shared family number, different person."

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "second.rahul@example.test",
            "first_name": "Second",
            "last_name": "Rahul",
            "phone": "9876500000",
            "override_reason": reason,
        },
        format="json",
    )

    assert response.status_code == 201, response.data

    entry = AuditLog.objects.get(
        action=AuditAction.STUDENT_DUPLICATE_OVERRIDDEN, resource_id=response.data["id"]
    )
    assert entry.context["reason"] == reason
    assert str(matching_student.pk) in entry.context["matched_student_ids"]


@pytest.mark.django_db
def test_registering_with_no_duplicate_needs_no_reason_and_audits_nothing(
    api_client_no_csrf, counsellor_user
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {"email": "nobody.else@example.test", "first_name": "Nobody", "last_name": "Else"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert not AuditLog.objects.filter(
        action=AuditAction.STUDENT_DUPLICATE_OVERRIDDEN, resource_id=response.data["id"]
    ).exists()


@pytest.mark.django_db
def test_a_duplicate_outside_the_actors_reach_needs_no_override(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, other_branch
):
    """The same safe-failure-mode reasoning applies at creation time: a
    phone shared with a student the counsellor cannot see must not force
    them through a reason prompt they have no way to make sense of."""
    create_student(
        email="pooja.pune@example.test",
        first_name="Pooja",
        last_name="Pune",
        phone="9998887777",
        actor=unbounded_superadmin,
        branch=other_branch,
        password=PASSWORD,
        send_invitation=False,
    )

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "another.newcomer@example.test",
            "first_name": "Another",
            "last_name": "Newcomer",
            "phone": "9998887777",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
