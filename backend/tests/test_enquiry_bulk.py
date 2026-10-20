"""`POST /enquiries/bulk/`: hand many enquiries to one person at once.

Each enquiry needs the same right as changing it alone (its owner, or
`enquiry.manage` at its centre) and the same owner rule (active staff at the
enquiry's centre); one that fails is skipped with the reason.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.accounts.roles import UserRole
from apps.automation.models import AutomationRule
from apps.enquiries.models import Enquiry
from apps.forms import services as forms_services
from apps.forms.models import FormDefinition

pytestmark = pytest.mark.django_db

URL = "/api/v1/enquiries/bulk/"

ANSWERS = {
    "full_name": "Ravi Sharma",
    "whatsapp_same": True,
    "state": "rajasthan",
    "city": "jaipur",
    "course": "devops",
    "track": "devops_aws",
    "preferred_centre": "jaipur",
    "source": "walk_in",
    "consent": True,
}


@pytest.fixture(autouse=True)
def _pause_seeded_rules(db):
    AutomationRule.objects.update(status="paused")


def _enquiry(actor, mobile: str, name: str) -> Enquiry:
    definition = FormDefinition.objects.get(slug="enquiry")
    assignment = forms_services.fill_form(
        actor=actor,
        definition=definition,
        values={**ANSWERS, "mobile": mobile, "full_name": name},
    )
    assignment.refresh_from_db()
    return assignment.enquiry


@pytest.fixture
def colleague(branch):
    return User.objects.create_user(
        email="colleague@example.test",
        password=None,
        first_name="Neha",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )


def test_a_manager_hands_ticked_enquiries_to_a_colleague(
    api_client_no_csrf, manager_user, counsellor_user, colleague
):
    first = _enquiry(counsellor_user, "9876500001", "Asha")
    second = _enquiry(counsellor_user, "9876500002", "Bala")
    untouched = _enquiry(counsellor_user, "9876500003", "Chitra")

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        URL,
        {
            "action": "assign_owner",
            "owner_id": str(colleague.pk),
            "ids": [str(first.pk), str(second.pk)],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["done"] == 2
    for enquiry in (first, second, untouched):
        enquiry.refresh_from_db()
    assert first.owner == colleague and second.owner == colleague
    assert untouched.owner == counsellor_user


def test_every_enquiry_the_filter_matches(
    api_client_no_csrf, manager_user, counsellor_user, colleague
):
    _enquiry(counsellor_user, "9876500011", "Deepa")
    _enquiry(counsellor_user, "9876500012", "Esha")
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        URL,
        {
            "action": "assign_owner",
            "owner_id": str(colleague.pk),
            "filters": {"owner": str(counsellor_user.pk), "q": "Deepa"},
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["done"] == 1
    assert Enquiry.objects.get(full_name="Deepa").owner == colleague
    assert Enquiry.objects.get(full_name="Esha").owner == counsellor_user


def test_the_mine_filter_reads_the_caller(api_client_no_csrf, counsellor_user, colleague):
    """`owner=me` needs the request; a bulk run must resolve it the same way."""
    _enquiry(counsellor_user, "9876500021", "Farah")
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        URL,
        {"action": "assign_owner", "owner_id": str(colleague.pk), "filters": {"owner": "me"}},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["done"] == 1


def test_an_owner_at_another_centre_or_a_student_is_refused(
    api_client_no_csrf, manager_user, counsellor_user, other_branch_manager, student_profile
):
    enquiry = _enquiry(counsellor_user, "9876500031", "Gita")
    api_client_no_csrf.force_login(manager_user)

    far = api_client_no_csrf.post(
        URL,
        {
            "action": "assign_owner",
            "owner_id": str(other_branch_manager.pk),
            "ids": [str(enquiry.pk)],
        },
        format="json",
    )
    assert far.status_code == 200
    assert far.json()["done"] == 0
    assert "centre" in far.json()["skipped"][0]["reason"]

    pupil = api_client_no_csrf.post(
        URL,
        {
            "action": "assign_owner",
            "owner_id": str(student_profile.user.pk),
            "ids": [str(enquiry.pk)],
        },
        format="json",
    )
    assert pupil.status_code == 400
    enquiry.refresh_from_db()
    assert enquiry.owner == counsellor_user


def test_the_single_change_refuses_a_student_owner_too(
    api_client_no_csrf, manager_user, counsellor_user, student_profile
):
    enquiry = _enquiry(counsellor_user, "9876500041", "Hema")
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/enquiries/{enquiry.pk}/", {"owner": str(student_profile.user.pk)}, format="json"
    )
    assert response.status_code == 400
    enquiry.refresh_from_db()
    assert enquiry.owner == counsellor_user


def test_unassigning_and_already_theirs(api_client_no_csrf, manager_user, counsellor_user):
    enquiry = _enquiry(counsellor_user, "9876500051", "Indu")
    api_client_no_csrf.force_login(manager_user)
    same = api_client_no_csrf.post(
        URL,
        {"action": "assign_owner", "owner_id": str(counsellor_user.pk), "ids": [str(enquiry.pk)]},
        format="json",
    )
    assert same.json()["skipped"][0]["reason"] == "Already theirs."

    off = api_client_no_csrf.post(
        URL, {"action": "assign_owner", "owner_id": None, "ids": [str(enquiry.pk)]}, format="json"
    )
    assert off.json()["done"] == 1
    enquiry.refresh_from_db()
    assert enquiry.owner is None


def test_a_student_is_refused(api_client_no_csrf, student_profile, counsellor_user):
    enquiry = _enquiry(counsellor_user, "9876500061", "Jaya")
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        URL,
        {"action": "assign_owner", "owner_id": str(counsellor_user.pk), "ids": [str(enquiry.pk)]},
        format="json",
    )
    assert response.status_code == 403
