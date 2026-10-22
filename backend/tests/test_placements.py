"""Placements — where a student ended up, and who may know about it.

Three things this suite exists to prove:

1. The numbers mean what the screen says: `placed_students` counts people
   (somebody with two accepted offers is one placed person), everything else
   counts offers, and an offer nobody has accepted is not a placement.
2. A placement is filed into the *student's* centre, never a centre named by
   the caller — and read only by people at that centre, the student
   themselves, and nobody else. A trainer who teaches the student's batch is
   explicitly nobody else: an offer and its package are not learning data.
3. `placement.manage` is a separate right from `placement.view_any`, and
   writing is refused in the service, not only in the view.

Fixtures come from `tests/conftest.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.roles import Capability, UserRole
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.placements import services
from apps.placements.models import Placement, PlacementStatus

pytestmark = pytest.mark.django_db

PLACEMENTS = "/api/v1/placements/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _record(actor, student, **overrides):
    fields = {
        "company": "Infosys",
        "role_title": "Associate Engineer",
        "offered_on": date(2026, 9, 1),
    }
    fields.update(overrides)
    return services.record_placement(actor=actor, student=student, **fields)


# ---------------------------------------------------------------------------
# Recording and reading
# ---------------------------------------------------------------------------


def test_an_offer_is_recorded_against_the_students_own_centre(
    api_client_no_csrf, counsellor_user, student_profile
):
    """The centre comes from the student, not the request. A caller who could
    name it could file an offer into a centre they cannot read, where the
    people who need it would never see it."""
    response = _client(counsellor_user).post(
        PLACEMENTS,
        {
            "student": str(student_profile.pk),
            "company": "  Infosys Ltd ",
            "role_title": "Associate Engineer",
            "offered_on": "2026-09-01",
            "annual_package": "450000.00",
            "location": "Bengaluru",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    # Trimmed on the way in, so "Infosys Ltd " and "Infosys Ltd" are one
    # employer rather than two rows nobody can group.
    assert body["company"] == "Infosys Ltd"
    assert body["status"] == PlacementStatus.OFFERED
    assert body["is_placed"] is False
    assert body["student_name"]

    placement = Placement.objects.get(pk=body["id"])
    assert placement.branch_id == student_profile.branch_id
    assert placement.company_key == "infosys ltd"
    assert placement.created_by_id == counsellor_user.pk


def test_an_offer_needs_a_company_and_a_role(counsellor_user, student_profile):
    for bad in ({"company": "   "}, {"role_title": ""}):
        with pytest.raises(ApplicationError):
            _record(counsellor_user, student_profile, **bad)
    assert Placement.objects.count() == 0


def test_a_joined_offer_must_say_when_and_a_declined_one_must_not(counsellor_user, student_profile):
    """`status` and `joined_on` have to agree, and the mismatch is a message
    rather than an IntegrityError the API would show as a 500."""
    with pytest.raises(ApplicationError):
        _record(counsellor_user, student_profile, status=PlacementStatus.JOINED)
    with pytest.raises(ApplicationError):
        _record(
            counsellor_user,
            student_profile,
            status=PlacementStatus.DECLINED,
            joined_on=date(2026, 10, 1),
        )

    joined = _record(
        counsellor_user,
        student_profile,
        status=PlacementStatus.JOINED,
        joined_on=date(2026, 10, 1),
    )
    assert joined.is_placed is True


def test_an_offer_can_be_moved_along_and_every_change_is_audited(
    api_client_no_csrf, counsellor_user, student_profile
):
    from apps.audit.models import AuditLog

    placement = _record(counsellor_user, student_profile)
    response = _client(counsellor_user).patch(
        f"{PLACEMENTS}{placement.pk}/",
        {"status": "joined", "joined_on": "2026-10-01", "annual_package": "500000.00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["is_placed"] is True

    actions = set(
        AuditLog.objects.filter(
            resource_type="placement", resource_id=str(placement.pk)
        ).values_list("action", flat=True)
    )
    assert actions == {"placement.recorded", "placement.updated"}


def test_a_change_to_nothing_is_a_bad_request_not_a_silent_success(
    api_client_no_csrf, counsellor_user, student_profile
):
    placement = _record(counsellor_user, student_profile)
    response = _client(counsellor_user).patch(f"{PLACEMENTS}{placement.pk}/", {}, format="json")
    assert response.status_code == 400


def test_the_student_cannot_be_moved_to_another_person(counsellor_user, student_profile):
    """An offer recorded against the wrong person is withdrawn and recorded
    again, so the first student's record keeps its history."""
    placement = _record(counsellor_user, student_profile)
    with pytest.raises(ApplicationError):
        services.update_placement(
            actor=counsellor_user, placement=placement, fields={"student": "whoever"}
        )


def test_an_enrolment_from_another_student_is_refused(
    counsellor_user, student_profile, other_student_profile, batch, admin_user
):
    from apps.enrollments.services import enrol_student

    theirs = enrol_student(student=other_student_profile, batch=batch, actor=admin_user)
    with pytest.raises(ApplicationError):
        _record(counsellor_user, student_profile, enrollment=theirs)


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------


def test_the_summary_counts_people_placed_and_offers_everything_else(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    """Somebody who accepted one offer and joined another is one placed
    person, not two — counting rows would overstate every report built on
    this number."""
    _record(counsellor_user, student_profile, company="Infosys", status=PlacementStatus.ACCEPTED)
    _record(
        counsellor_user,
        student_profile,
        company="TCS",
        status=PlacementStatus.JOINED,
        joined_on=date(2026, 10, 1),
    )
    _record(counsellor_user, other_student_profile, company="Wipro")
    _record(
        counsellor_user,
        other_student_profile,
        company="HCL",
        status=PlacementStatus.DECLINED,
        notes="Wanted Jaipur.",
    )

    body = _client(counsellor_user).get(f"{PLACEMENTS}summary/").json()
    assert body["offers"] == 4
    assert body["placed_students"] == 1
    assert body["open_offers"] == 1
    assert body["closed_offers"] == 1


def test_offers_can_be_narrowed_to_the_ones_that_became_jobs(
    api_client_no_csrf, counsellor_user, student_profile
):
    _record(counsellor_user, student_profile, company="Infosys", status=PlacementStatus.ACCEPTED)
    _record(counsellor_user, student_profile, company="Wipro")

    client = _client(counsellor_user)
    placed = client.get(PLACEMENTS, {"placed": "true"}).json()
    assert [row["company"] for row in placed["results"]] == ["Infosys"]
    not_placed = client.get(PLACEMENTS, {"placed": "false"}).json()
    assert [row["company"] for row in not_placed["results"]] == ["Wipro"]


def test_students_open_to_placement_can_be_listed(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    """Where the officer's own list starts — the students who said they want
    to be put forward, which is the student's own answer, not an assumption."""
    student_profile.open_to_placement = True
    student_profile.save(update_fields=["open_to_placement"])

    body = _client(counsellor_user).get("/api/v1/students/", {"open_to_placement": "true"}).json()
    assert [row["id"] for row in body["results"]] == [str(student_profile.pk)]


# ---------------------------------------------------------------------------
# Who may know — the leaks this module must not have
# ---------------------------------------------------------------------------


def test_a_student_reads_their_own_offers_and_nobody_elses(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    mine = _record(counsellor_user, student_profile, company="Infosys")
    theirs = _record(counsellor_user, other_student_profile, company="Wipro")

    client = _client(student_profile.user)
    listed = client.get(PLACEMENTS).json()
    assert [row["id"] for row in listed["results"]] == [str(mine.pk)]
    # A classmate's offer by id is a 404, not a 403: it is not theirs to know
    # exists, and its package is somebody else's salary.
    assert client.get(f"{PLACEMENTS}{theirs.pk}/").status_code == 404
    assert client.get(f"{PLACEMENTS}{mine.pk}/").status_code == 200


def test_a_student_cannot_record_or_change_an_offer(
    api_client_no_csrf, counsellor_user, student_profile
):
    mine = _record(counsellor_user, student_profile)
    client = _client(student_profile.user)

    created = client.post(
        PLACEMENTS,
        {
            "student": str(student_profile.pk),
            "company": "Self Declared Ltd",
            "role_title": "CEO",
            "offered_on": "2026-09-01",
        },
        format="json",
    )
    assert created.status_code == 403
    assert (
        client.patch(
            f"{PLACEMENTS}{mine.pk}/", {"annual_package": "9900000.00"}, format="json"
        ).status_code
        == 403
    )
    mine.refresh_from_db()
    assert mine.annual_package is None


def test_a_trainer_teaching_the_student_sees_no_offer_at_all(
    api_client_no_csrf, counsellor_user, student_profile, trainer_profile, enrollment
):
    """The one deliberate narrowing of this app against the rest of the
    system: a trainer reaches a student's *learning* through the batch they
    teach, and an offer and its package are not learning. A trainer who
    should see them is given `placement.view_any` through a custom role by
    somebody who decided they should have it."""
    placement = _record(counsellor_user, student_profile)
    client = _client(trainer_profile.user)

    assert client.get(PLACEMENTS).json()["count"] == 0
    assert client.get(f"{PLACEMENTS}{placement.pk}/").status_code == 404
    # Not even the aggregate: the desk's figures need `placement.view_any`.
    assert client.get(f"{PLACEMENTS}summary/").status_code == 403


def test_another_centres_manager_sees_nothing_of_this_centres_offers(
    api_client_no_csrf, counsellor_user, student_profile, other_branch_manager
):
    placement = _record(counsellor_user, student_profile)
    client = _client(other_branch_manager)

    assert client.get(PLACEMENTS).json()["count"] == 0
    assert client.get(f"{PLACEMENTS}{placement.pk}/").status_code == 404
    assert client.get(f"{PLACEMENTS}summary/").json()["placed_students"] == 0
    # And cannot write one either, even naming a student they cannot see.
    refused = client.post(
        PLACEMENTS,
        {
            "student": str(student_profile.pk),
            "company": "Elsewhere Ltd",
            "role_title": "Engineer",
            "offered_on": "2026-09-01",
        },
        format="json",
    )
    assert refused.status_code == 404
    assert Placement.objects.count() == 1


def test_naming_another_students_id_on_the_filter_returns_nothing_not_their_offers(
    api_client_no_csrf, counsellor_user, student_profile, other_student_profile
):
    """`?student=` narrows an already-scoped list and can never widen it."""
    _record(counsellor_user, student_profile, company="Infosys")
    theirs = _record(counsellor_user, other_student_profile, company="Wipro")

    body = (
        _client(student_profile.user)
        .get(PLACEMENTS, {"student": str(other_student_profile.pk)})
        .json()
    )
    assert body["count"] == 0
    assert str(theirs.pk) not in str(body)


def test_reading_every_offer_does_not_imply_recording_one(
    api_client_no_csrf, student_profile, counsellor_user, branch, admin_user
):
    """A placement officer may be trusted to see the picture and not to change
    it. Built the way an administrator would build it — a custom role (ADR-02)
    holding `placement.view_any` and not `placement.manage` — so this proves
    the real resolution path, not a stand-in object.

    The service refuses the write, so a view wired wrong cannot grant it.
    """
    from apps.accounts.models import User
    from apps.accounts.roles import BASE_CAPABILITIES
    from apps.authorization.models import Permission, Role, RolePermission

    role = Role.objects.create(
        slug="placement-reader",
        name="Placement reader",
        kind=UserRole.MANAGER,
        description="Sees the centre's placements; records none.",
    )
    for code in sorted(BASE_CAPABILITIES | {Capability.PLACEMENT_VIEW_ANY}):
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
    reader = User.objects.create_user(
        email="placement.reader@example.test",
        password="x" * 16,
        first_name="Read",
        last_name="Only",
        role=UserRole.MANAGER,
        branch=branch,
        custom_role=role,
    )
    assert Capability.PLACEMENT_VIEW_ANY in reader.capabilities
    assert Capability.PLACEMENT_MANAGE not in reader.capabilities

    placement = _record(counsellor_user, student_profile)
    client = _client(reader)

    # Reads the centre's offers, as the role says.
    assert [row["id"] for row in client.get(PLACEMENTS).json()["results"]] == [str(placement.pk)]
    assert client.get(f"{PLACEMENTS}{placement.pk}/").status_code == 200

    # Records none.
    assert (
        client.patch(
            f"{PLACEMENTS}{placement.pk}/", {"company": "Somewhere Else"}, format="json"
        ).status_code
        == 403
    )
    assert (
        client.post(
            PLACEMENTS,
            {
                "student": str(student_profile.pk),
                "company": "Somewhere Else",
                "role_title": "Engineer",
                "offered_on": "2026-09-01",
            },
            format="json",
        ).status_code
        == 403
    )
    with pytest.raises(AuthorityError):
        services.update_placement(
            actor=reader, placement=placement, fields={"company": "Somewhere Else"}
        )
    placement.refresh_from_db()
    assert placement.company == "Infosys"


def test_an_anonymous_caller_sees_nothing(api_client):
    assert api_client.get(PLACEMENTS).status_code in (401, 403)
    assert api_client.get(f"{PLACEMENTS}summary/").status_code in (401, 403)


def test_the_module_records_a_second_offer_for_the_same_student_rather_than_overwriting(
    counsellor_user, student_profile
):
    """Four interviews, three declined, one joined is the officer's real
    record — so this is one row per offer, not one per student."""
    _record(counsellor_user, student_profile, company="A", status=PlacementStatus.DECLINED)
    _record(counsellor_user, student_profile, company="B", status=PlacementStatus.WITHDRAWN)
    _record(
        counsellor_user,
        student_profile,
        company="C",
        status=PlacementStatus.JOINED,
        joined_on=date.today() - timedelta(days=1),
    )
    assert Placement.objects.filter(student=student_profile).count() == 3
    assert Placement.objects.placed().count() == 1
