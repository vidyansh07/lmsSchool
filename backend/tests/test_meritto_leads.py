"""Meritto leads in the LMS (owner's decisions, 17 October 2026).

What is pinned:

- Meritto sends a lead when it is ready to admit; Meritto's stage and owner
  arrive in its own words (`external_stage`, `external_owner`) and never move
  the LMS pipeline;
- a Meritto lead is read-only to people in the LMS — the detail screen's
  PATCH, a bulk owner change, a follow-up form's answers and the walk-in desk
  all leave it as Meritto sent it;
- LMS lead automation does not run for it;
- "Register this lead" is the one thing the LMS does with it: it links the
  student and marks it registered on the LMS side, and it leaves the "ready
  to admit" queue;
- a walk-in entered in the LMS stays fully editable.
"""

from __future__ import annotations

import pytest

from apps.enquiries import services as enquiries
from apps.enquiries.models import Enquiry
from apps.integrations import services

LEADS = "/api/v1/integrations/leads/"


@pytest.fixture
def meritto_key(admin_user, branch):
    _key, plaintext = services.create_api_key(
        actor=admin_user, name="Meritto", preset="meritto", branch=branch
    )
    return plaintext


def _send(client, key, **body):
    payload = {
        "lead_id": "MER-1",
        "student_name": "Aman Verma",
        "mobile_number": "9876500001",
        "email_id": "aman@example.test",
        "course_name": "DevOps",
        "lead_stage": "Ready for admission",
        "lead_owner": "Pooja (Meritto)",
        **body,
    }
    return client.post(LEADS, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {key}")


@pytest.mark.django_db
def test_meritto_stage_and_owner_arrive_in_its_own_words(api_client, meritto_key):
    response = _send(api_client, meritto_key)
    assert response.status_code == 201, response.json()
    lead = Enquiry.objects.get()
    assert lead.is_managed_externally
    assert lead.external_stage == "Ready for admission"
    assert lead.external_owner == "Pooja (Meritto)"
    assert lead.stage == "new"
    assert lead.owner is None

    # Meritto moves it on: the LMS shows Meritto's new words.
    _send(api_client, meritto_key, lead_stage="Fee discussion", lead_owner="Ravi (Meritto)")
    lead.refresh_from_db()
    assert (lead.external_stage, lead.external_owner) == ("Fee discussion", "Ravi (Meritto)")
    assert Enquiry.objects.count() == 1


@pytest.mark.django_db
def test_a_meritto_lead_is_read_only_to_people(
    api_client, api_client_no_csrf, meritto_key, counsellor_user
):
    _send(api_client, meritto_key)
    lead = Enquiry.objects.get()
    api_client_no_csrf.force_login(counsellor_user)

    detail = api_client_no_csrf.get(f"/api/v1/enquiries/{lead.pk}/").json()
    assert detail["managed_externally"] is True
    assert detail["can_manage"] is False
    assert detail["can_register"] is True
    assert detail["external_stage"] == "Ready for admission"

    patched = api_client_no_csrf.patch(
        f"/api/v1/enquiries/{lead.pk}/", {"stage": "interested"}, format="json"
    )
    assert patched.status_code == 400
    assert "managed in Meritto" in str(patched.json())

    bulk = api_client_no_csrf.post(
        "/api/v1/enquiries/bulk/",
        {"action": "assign_owner", "ids": [str(lead.pk)], "owner_id": str(counsellor_user.pk)},
        format="json",
    )
    assert bulk.status_code == 200, bulk.json()
    assert bulk.json()["done"] == 0
    lead.refresh_from_db()
    assert lead.stage == "new" and lead.owner is None

    # Follow-up answers and the walk-in desk leave it alone too.
    assert (
        enquiries.apply_answers(actor=counsellor_user, enquiry=lead, values={"stage": "interested"})
        == []
    )
    same, created = enquiries.capture(
        actor=counsellor_user,
        values={"full_name": "Aman V", "mobile": "9876500001", "city": "Jaipur"},
        branch=lead.branch,
    )
    assert same.pk == lead.pk and created is False
    lead.refresh_from_db()
    assert lead.full_name == "Aman Verma" and lead.city == ""


@pytest.mark.django_db
def test_lms_lead_rules_do_not_run_for_a_meritto_lead(
    api_client, meritto_key, admin_user, branch, django_capture_on_commit_callbacks, monkeypatch
):
    from apps.automation import tasks

    seen: list = []
    monkeypatch.setattr(tasks.dispatch_enquiry_event, "delay", lambda *args: seen.append(args))
    with django_capture_on_commit_callbacks(execute=True):
        _send(api_client, meritto_key)
    assert seen == []

    with django_capture_on_commit_callbacks(execute=True):
        enquiries.capture(
            actor=admin_user, values={"full_name": "Walk In", "mobile": "9000011111"}, branch=branch
        )
    assert [args[1] for args in seen] == ["ENQUIRY_CREATED"]


@pytest.mark.django_db
def test_register_this_lead_links_the_student_and_clears_the_queue(
    api_client, api_client_no_csrf, meritto_key, counsellor_user, student_profile
):
    _send(api_client, meritto_key)
    lead = Enquiry.objects.get()
    api_client_no_csrf.force_login(counsellor_user)

    queue = api_client_no_csrf.get("/api/v1/enquiries/?ready_to_admit=true").json()
    assert [row["id"] for row in queue["results"]] == [str(lead.pk)]
    assert api_client_no_csrf.get("/api/v1/enquiries/summary/").json()["ready_to_admit"] == 1

    response = api_client_no_csrf.post(
        f"/api/v1/enquiries/{lead.pk}/register/",
        {"student": str(student_profile.pk)},
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["student"]["id"] == str(student_profile.pk)
    assert body["stage"] == "registered"
    assert body["external_stage"] == "Ready for admission"  # Meritto's own word, untouched
    assert body["can_register"] is False

    assert api_client_no_csrf.get("/api/v1/enquiries/?ready_to_admit=true").json()["results"] == []


@pytest.mark.django_db
def test_registering_needs_student_create(
    api_client, api_client_no_csrf, meritto_key, trainer, student_profile
):
    _send(api_client, meritto_key)
    lead = Enquiry.objects.get()
    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.post(
        f"/api/v1/enquiries/{lead.pk}/register/",
        {"student": str(student_profile.pk)},
        format="json",
    )
    assert response.status_code in (403, 404)
    lead.refresh_from_db()
    assert lead.student is None


@pytest.mark.django_db
def test_a_walk_in_stays_editable(api_client_no_csrf, counsellor_user, branch):
    walk_in, _ = enquiries.capture(
        actor=counsellor_user,
        values={"full_name": "Walk In", "mobile": "9000022222", "source": "walk_in"},
        branch=branch,
    )
    api_client_no_csrf.force_login(counsellor_user)
    detail = api_client_no_csrf.get(f"/api/v1/enquiries/{walk_in.pk}/").json()
    assert detail["managed_externally"] is False and detail["can_manage"] is True
    patched = api_client_no_csrf.patch(
        f"/api/v1/enquiries/{walk_in.pk}/", {"stage": "interested"}, format="json"
    )
    assert patched.status_code == 200
    assert Enquiry.objects.get(pk=walk_in.pk).stage == "interested"
