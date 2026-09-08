"""The fee agreed at registration, and where a student studies or works.

Two fields, added together because they arrive together: the counsellor
registering somebody writes down what was agreed and where the person is
coming from. What is pinned here is less the happy path than the edges that
would make either field a liability:

- a fee below the floor is refused, not stored;
- a student can see their fee and cannot touch it, whatever they send;
- quoting a fee is a *permission*, checked in the service rather than only at
  the endpoint, so no other route into ``create_student`` can skip it;
- every change is audited with both the old and the new value.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.students import services
from apps.students.models import MIN_FEE_AMOUNT, InstitutionKind, StudentProfile

STUDENTS_URL = "/api/v1/students/"
ME_URL = "/api/v1/students/me/"


def fee_amount_url(profile: StudentProfile) -> str:
    return f"{STUDENTS_URL}{profile.pk}/fee-amount/"


# ---------------------------------------------------------------------------
# At registration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["counsellor_user", "manager_user", "admin_user"])
def test_a_counsellor_or_manager_quotes_the_fee_at_registration(
    api_client_no_csrf, request, fixture
):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {
            "email": "fee.student@example.test",
            "first_name": "Fee",
            "fee_amount": "12500.00",
            "profile": {"institution": "Tata Consultancy", "institution_kind": "employer"},
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    body = response.json()
    assert body["fee_amount"] == "12500.00"
    assert body["institution"] == "Tata Consultancy"
    assert body["institution_kind"] == "employer"
    assert body["fee_amount_updated_by"] is not None


@pytest.mark.django_db
def test_the_fee_is_optional_at_registration(api_client_no_csrf, counsellor_user):
    """Not every registration has a fee decided on the spot."""
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL, {"email": "nofee@example.test", "first_name": "No"}, format="json"
    )

    assert response.status_code == 201
    assert response.json()["fee_amount"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["999.99", "0", "-1", "500"])
def test_a_fee_below_the_floor_is_refused_not_stored(api_client_no_csrf, counsellor_user, amount):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {"email": "cheap@example.test", "first_name": "Cheap", "fee_amount": amount},
        format="json",
    )

    assert response.status_code == 400
    assert "fee_amount" in response.json()["error"]["details"]
    assert not StudentProfile.objects.filter(user__email="cheap@example.test").exists()


@pytest.mark.django_db
def test_exactly_the_floor_is_accepted(api_client_no_csrf, counsellor_user):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {"email": "floor@example.test", "first_name": "Floor", "fee_amount": str(MIN_FEE_AMOUNT)},
        format="json",
    )

    assert response.status_code == 201
    assert Decimal(response.json()["fee_amount"]) == MIN_FEE_AMOUNT


@pytest.mark.django_db
def test_the_fee_cannot_be_smuggled_in_through_the_profile(api_client_no_csrf, counsellor_user):
    """``profile`` is the self-editable set. A fee there would become a fee a
    student can edit the day the update serializer reads the same list."""
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        STUDENTS_URL,
        {"email": "smuggle@example.test", "first_name": "S", "profile": {"fee_amount": "5000"}},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_the_service_checks_the_permission_itself(trainer):
    """A trainer never reaches the endpoint, but the service is the rule."""
    with pytest.raises(AuthorityError):
        services.create_student(
            email="svc@example.test", first_name="Svc", actor=trainer, fee_amount=Decimal("2000")
        )
    assert not StudentProfile.objects.filter(user__email="svc@example.test").exists()


@pytest.mark.django_db
def test_the_service_enforces_the_floor_itself(counsellor_user):
    with pytest.raises(ApplicationError):
        services.create_student(
            email="svc2@example.test", first_name="Svc", actor=counsellor_user, fee_amount=Decimal("999")
        )


@pytest.mark.django_db
def test_registration_with_a_fee_is_audited(counsellor_user):
    profile = services.create_student(
        email="audited@example.test", first_name="A", actor=counsellor_user, fee_amount=Decimal("3000")
    )

    entry = AuditLog.objects.filter(
        action=AuditAction.STUDENT_CREATED, resource_id=str(profile.pk)
    ).first()
    assert entry is not None
    assert entry.context["fee_amount"] == "3000"


# ---------------------------------------------------------------------------
# Changing it later
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["counsellor_user", "manager_user", "admin_user"])
def test_the_fee_can_be_changed_by_those_who_may_quote_it(
    api_client_no_csrf, request, fixture, student_profile
):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))

    response = api_client_no_csrf.post(
        fee_amount_url(student_profile),
        {"fee_amount": "15000", "note": "Upgraded to the full course."},
        format="json",
    )

    assert response.status_code == 200, response.data
    student_profile.refresh_from_db()
    assert student_profile.fee_amount == Decimal("15000")
    assert student_profile.fee_amount_updated_by is not None


@pytest.mark.django_db
def test_a_change_is_audited_with_both_values(counsellor_user, student_profile):
    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("2000"), actor=counsellor_user)
    services.set_fee_amount(
        profile=student_profile, fee_amount=Decimal("2500"), actor=counsellor_user, note="Lab add-on"
    )

    entry = (
        AuditLog.objects.filter(action=AuditAction.STUDENT_FEE_AMOUNT_CHANGED)
        .order_by("-created_at")
        .first()
    )
    assert entry is not None
    assert entry.context["from"] == "2000"
    assert entry.context["to"] == "2500"
    assert entry.context["note"] == "Lab add-on"
    assert entry.actor == counsellor_user


@pytest.mark.django_db
def test_setting_the_same_fee_records_nothing(counsellor_user, student_profile):
    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("2000"), actor=counsellor_user)
    before = AuditLog.objects.filter(action=AuditAction.STUDENT_FEE_AMOUNT_CHANGED).count()

    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("2000"), actor=counsellor_user)

    assert AuditLog.objects.filter(action=AuditAction.STUDENT_FEE_AMOUNT_CHANGED).count() == before


@pytest.mark.django_db
def test_the_fee_can_be_cleared_back_to_undecided(api_client_no_csrf, manager_user, student_profile):
    """``null`` is the way back. Zero is not a fee."""
    api_client_no_csrf.force_login(manager_user)
    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("2000"), actor=manager_user)

    response = api_client_no_csrf.post(
        fee_amount_url(student_profile), {"fee_amount": None}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["fee_amount"] is None

    zero = api_client_no_csrf.post(fee_amount_url(student_profile), {"fee_amount": "0"}, format="json")
    assert zero.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["trainer", "student_profile"])
def test_nobody_else_may_change_it(api_client_no_csrf, request, fixture, student_profile):
    who = request.getfixturevalue(fixture)
    api_client_no_csrf.force_login(getattr(who, "user", who))

    response = api_client_no_csrf.post(
        fee_amount_url(student_profile), {"fee_amount": "1000"}, format="json"
    )

    assert response.status_code == 403
    student_profile.refresh_from_db()
    assert student_profile.fee_amount is None


# ---------------------------------------------------------------------------
# The student's side
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_sees_the_fee_and_cannot_change_it(
    api_client_no_csrf, counsellor_user, student_profile
):
    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("8000"), actor=counsellor_user)
    api_client_no_csrf.force_login(student_profile.user)

    assert api_client_no_csrf.get(ME_URL).json()["fee_amount"] == "8000.00"

    # A strict serializer names the field it refuses rather than ignoring it,
    # so a client that tries learns it tried.
    response = api_client_no_csrf.patch(ME_URL, {"fee_amount": "1"}, format="json")
    assert response.status_code == 400
    student_profile.refresh_from_db()
    assert student_profile.fee_amount == Decimal("8000")


@pytest.mark.django_db
def test_a_student_may_say_where_they_study_or_work(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    response = api_client_no_csrf.patch(
        ME_URL, {"institution": "IIT Jodhpur", "institution_kind": "college"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.json()["institution_kind"] == InstitutionKind.COLLEGE


@pytest.mark.django_db
def test_an_unknown_institution_kind_is_refused(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    response = api_client_no_csrf.patch(ME_URL, {"institution_kind": "school"}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_the_list_carries_the_fee_for_the_table(api_client_no_csrf, counsellor_user, student_profile):
    services.set_fee_amount(profile=student_profile, fee_amount=Decimal("4500"), actor=counsellor_user)
    api_client_no_csrf.force_login(counsellor_user)

    rows = api_client_no_csrf.get(f"{STUDENTS_URL}?search={student_profile.student_id}").json()["results"]

    assert rows[0]["fee_amount"] == "4500.00"
