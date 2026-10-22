"""Enquiries — the Meritto-style lead pipeline — and the flows built on it:
capture from the enquiry form, repeat enquiries, follow-up answers moving
the stage, activities about an enquiry with their content filled in, the
three `ENQUIRY_*` triggers, the `update_enquiry` action, and who may see and
change an enquiry.

Fixtures come from `tests/conftest.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import UserRole
from apps.automation import services as automation_services
from apps.automation.models import (
    AutomationRule,
    AutomationRun,
    AutomationRunStatus,
    AutomationTrigger,
)
from apps.common.exceptions import ApplicationError
from apps.enquiries import services
from apps.enquiries.models import Enquiry, EnquiryStage
from apps.forms import services as forms_services
from apps.forms.models import FormDefinition
from apps.work import services as work_services
from apps.work.models import Activity, ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db

ENQUIRY_ANSWERS = {
    "full_name": "Ravi Sharma",
    "mobile": "9876543210",
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


def _fill_enquiry(actor, **overrides):
    definition = FormDefinition.objects.get(slug="enquiry")
    assignment = forms_services.fill_form(
        actor=actor, definition=definition, values={**ENQUIRY_ANSWERS, **overrides}
    )
    assignment.refresh_from_db()
    return assignment


# ---------------------------------------------------------------------------
# Capture and follow-up
# ---------------------------------------------------------------------------


def test_filling_the_enquiry_form_creates_an_enquiry(counsellor_user):
    assignment = _fill_enquiry(counsellor_user)
    enquiry = assignment.enquiry
    assert enquiry is not None
    assert enquiry.full_name == "Ravi Sharma"
    assert enquiry.course == "devops"
    assert enquiry.source == "walk_in"
    assert enquiry.stage == EnquiryStage.NEW
    assert enquiry.owner == counsellor_user
    assert enquiry.branch == counsellor_user.branch
    assert enquiry.mobile_key == "9876543210"


def test_a_repeat_enquiry_updates_the_open_one(counsellor_user):
    first = _fill_enquiry(counsellor_user).enquiry
    second = _fill_enquiry(
        counsellor_user, mobile="+91 98765 43210", course="aws", track="solutions_architect"
    ).enquiry
    assert second.pk == first.pk
    assert Enquiry.objects.count() == 1
    first.refresh_from_db()
    assert first.course == "aws"


def test_a_follow_up_about_an_enquiry_moves_its_stage(counsellor_user):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    follow_up = FormDefinition.objects.get(slug="enquiry-follow-up")
    assignment = forms_services.assign_form(
        actor=counsellor_user, definition=follow_up, assigned_to=counsellor_user, enquiry=enquiry
    )
    forms_services.submit_assignment(
        actor=counsellor_user,
        assignment=assignment,
        values={"call_status": "connected", "lead_stage": "not_interested", "lost_reason": "fees"},
    )
    enquiry.refresh_from_db()
    assert enquiry.stage == EnquiryStage.NOT_INTERESTED
    assert enquiry.lost_reason == "fees"
    assert enquiry.last_contacted_at is not None


def test_an_unknown_stage_on_a_custom_form_is_skipped_not_fatal(counsellor_user):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    assert services.answers_to_fields({"lead_stage": "maybe", "course": "aws"}) == {"course": "aws"}
    services.apply_answers(actor=counsellor_user, enquiry=enquiry, values={"lead_stage": "maybe"})
    enquiry.refresh_from_db()
    assert enquiry.stage == EnquiryStage.NEW


# ---------------------------------------------------------------------------
# Activities about an enquiry
# ---------------------------------------------------------------------------


def test_a_counselling_call_about_an_enquiry_carries_its_content(counsellor_user):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    call = ActivityType.objects.get(slug="enquiry-call")
    activity = work_services.create_activity(
        actor=counsellor_user,
        activity_type=call,
        enquiry=enquiry,
        assigned_to=counsellor_user,
        title="Call Ravi",
        summary="Asked about DevOps fees.",
        form_prefill={"call_status": "connected", "not_a_question": "x"},
        due_at=timezone.now() + timedelta(hours=2),
    )
    assert activity.student is None
    assert activity.enquiry == enquiry
    assert activity.summary == "Asked about DevOps fees."
    # Only questions the call's form asks are kept.
    assert activity.form_prefill == {"call_status": "connected"}

    # Completing the call with its form moves the enquiry along.
    activity.status = ActivityStatus.IN_PROGRESS
    activity.save(update_fields=["status"])
    work_services.complete_activity(
        actor=counsellor_user,
        activity=activity,
        form_values={"call_status": "connected", "lead_stage": "interested", "lead_quality": 4},
    )
    enquiry.refresh_from_db()
    assert enquiry.stage == EnquiryStage.INTERESTED
    assert enquiry.lead_quality == 4


def test_an_enquiry_activity_needs_an_enquiry_and_a_student_one_a_student(
    counsellor_user, student_profile
):
    with pytest.raises(ApplicationError):
        work_services.create_activity(
            actor=counsellor_user,
            activity_type=ActivityType.objects.get(slug="enquiry-call"),
            student=student_profile,
        )
    with pytest.raises(ApplicationError):
        work_services.create_activity(
            actor=counsellor_user,
            activity_type=ActivityType.objects.get(slug="counselling"),
            enquiry=_fill_enquiry(counsellor_user).enquiry,
        )


# ---------------------------------------------------------------------------
# Automation: enquiry events, update_enquiry, create_activity content
# ---------------------------------------------------------------------------


def _second_counsellor(branch):
    return User.objects.create_user(
        email="counsellor2@example.test",
        password="x" * 16,
        first_name="Second",
        last_name="Counsellor",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )


def test_a_new_enquiry_flow_assigns_and_creates_a_call_with_content(
    admin_user, counsellor_user, branch
):
    other = _second_counsellor(branch)
    rule = automation_services.create_rule(
        actor=admin_user,
        name="New enquiry flow",
        trigger="ENQUIRY_CREATED",
        conditions=[{"path": "enquiry.course", "op": "eq", "value": "devops"}],
        actions=[
            {"type": "update_enquiry", "params": {"owner": "least_busy_counsellor"}},
            {
                "type": "create_activity",
                "params": {
                    "type": "enquiry-call",
                    "assign_to": "enquiry_owner",
                    "due_in_hours": 2,
                    "title": "Call {{enquiry.full_name}}",
                    "summary": "Wants {{enquiry.course}} via {{enquiry.source}}",
                    "form_prefill": {"call_status": "connected"},
                },
            },
        ],
        status="active",
    )
    # The first counsellor already has open work; the second has none.
    work_services.create_activity(
        actor=counsellor_user,
        activity_type=ActivityType.objects.get(slug="enquiry-call"),
        enquiry=_fill_enquiry(
            counsellor_user, mobile="9000000001", course="aws", track="solutions_architect"
        ).enquiry,
        assigned_to=counsellor_user,
    )

    enquiry = _fill_enquiry(counsellor_user).enquiry
    automation_services.dispatch(AutomationTrigger.ENQUIRY_CREATED, enquiry)

    run = AutomationRun.objects.get(rule=rule)
    assert run.status == AutomationRunStatus.RAN, run.result
    enquiry.refresh_from_db()
    assert enquiry.owner == other

    call = Activity.objects.get(enquiry=enquiry, automation_run=run)
    assert call.assigned_to == other
    assert call.title == "Call Ravi Sharma"
    assert call.summary == "Wants devops via walk_in"
    assert call.form_prefill == {"call_status": "connected"}
    assert timedelta(hours=1, minutes=59) < call.due_at - timezone.now() <= timedelta(hours=2)


def test_update_enquiry_stage_chains_a_stage_changed_rule_one_level_deeper(
    admin_user, counsellor_user
):
    automation_services.create_rule(
        actor=admin_user,
        name="Promote",
        trigger="ENQUIRY_CREATED",
        actions=[{"type": "update_enquiry", "params": {"stage": "interested"}}],
        status="active",
    )
    demo = automation_services.create_rule(
        actor=admin_user,
        name="Demo",
        trigger="ENQUIRY_STAGE_CHANGED",
        conditions=[
            {"path": "enquiry.stage", "op": "eq", "value": "interested"},
            {"path": "enquiry.previous_stage", "op": "eq", "value": "new"},
        ],
        actions=[
            {
                "type": "create_activity",
                "params": {
                    "type": "demo-class",
                    "assign_to": "enquiry_owner",
                    "planned_in_hours": 24,
                },
            }
        ],
        status="active",
    )
    enquiry = _fill_enquiry(counsellor_user).enquiry
    automation_services.dispatch(AutomationTrigger.ENQUIRY_CREATED, enquiry)

    run = AutomationRun.objects.get(rule=demo)
    assert run.depth == 1
    assert run.status == AutomationRunStatus.RAN, run.result
    demo_class = Activity.objects.get(enquiry=enquiry, activity_type__slug="demo-class")
    assert demo_class.planned_at is not None


def test_enquiry_events_reach_automation_on_commit(
    admin_user, counsellor_user, django_capture_on_commit_callbacks
):
    rule = automation_services.create_rule(
        actor=admin_user,
        name="Any new enquiry",
        trigger="ENQUIRY_CREATED",
        actions=[],
        status="active",
    )
    with django_capture_on_commit_callbacks(execute=True):
        _fill_enquiry(counsellor_user)
    assert AutomationRun.objects.filter(rule=rule, status=AutomationRunStatus.RAN).exists()


def test_a_form_submitted_rule_sees_the_enquiry_it_created(admin_user, counsellor_user):
    rule = automation_services.create_rule(
        actor=admin_user,
        name="Enquiry form",
        trigger="FORM_SUBMITTED",
        conditions=[
            {"path": "submission.form", "op": "eq", "value": "enquiry"},
            {"path": "enquiry.stage", "op": "eq", "value": "new"},
        ],
        actions=[],
        status="active",
    )
    assignment = _fill_enquiry(counsellor_user)
    automation_services.dispatch(AutomationTrigger.FORM_SUBMITTED, assignment)
    assert AutomationRun.objects.filter(rule=rule).exists()


def test_update_enquiry_params_are_checked_when_saved(admin_user):
    with pytest.raises(ApplicationError):
        automation_services.create_rule(
            actor=admin_user,
            name="Bad stage",
            trigger="ENQUIRY_CREATED",
            actions=[{"type": "update_enquiry", "params": {"stage": "won"}}],
        )
    with pytest.raises(ApplicationError):
        automation_services.create_rule(
            actor=admin_user,
            name="Nothing to change",
            trigger="ENQUIRY_CREATED",
            actions=[{"type": "update_enquiry", "params": {}}],
        )
    with pytest.raises(ApplicationError):
        automation_services.create_rule(
            actor=admin_user,
            name="No type",
            trigger="ENQUIRY_CREATED",
            actions=[{"type": "create_activity", "params": {"type": "nope", "assign_to": "x"}}],
        )


# ---------------------------------------------------------------------------
# API and access
# ---------------------------------------------------------------------------


ENQUIRIES = "/api/v1/enquiries/"


def test_enquiry_list_is_scoped_to_the_centre(
    api_client_no_csrf, counsellor_user, other_branch_manager, trainer
):
    enquiry = _fill_enquiry(counsellor_user).enquiry

    api_client_no_csrf.force_login(counsellor_user)
    body = api_client_no_csrf.get(ENQUIRIES).json()
    assert [row["id"] for row in body["results"]] == [str(enquiry.pk)]
    summary = api_client_no_csrf.get(f"{ENQUIRIES}summary/").json()
    assert summary["stages"]["new"] == 1
    assert summary["total"] == 1

    api_client_no_csrf.force_login(other_branch_manager)
    assert api_client_no_csrf.get(ENQUIRIES).json()["count"] == 0
    assert api_client_no_csrf.get(f"{ENQUIRIES}{enquiry.pk}/").status_code == 404

    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(ENQUIRIES).json()["count"] == 0


def test_enquiry_detail_and_patch(api_client_no_csrf, counsellor_user, trainer):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    url = f"{ENQUIRIES}{enquiry.pk}/"

    api_client_no_csrf.force_login(counsellor_user)
    detail = api_client_no_csrf.get(url).json()
    assert detail["can_manage"] is True
    assert detail["history"][0]["action"] == "enquiry.created"

    changed = api_client_no_csrf.patch(
        url, {"stage": "interested", "lead_quality": 5}, format="json"
    )
    assert changed.status_code == 200, changed.content
    assert changed.json()["stage"] == "interested"
    assert changed.json()["lead_quality"] == 5

    bad = api_client_no_csrf.patch(url, {"stage": "won"}, format="json")
    assert bad.status_code == 400


def test_activities_can_be_listed_and_created_for_an_enquiry(api_client_no_csrf, counsellor_user):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    api_client_no_csrf.force_login(counsellor_user)
    created = api_client_no_csrf.post(
        "/api/v1/activities/",
        {
            "enquiry": str(enquiry.pk),
            "activity_type": "enquiry-call",
            "assigned_to": str(counsellor_user.pk),
            "summary": "Call back after 6 pm.",
            "form_prefill": {"call_status": "busy"},
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["student"] is None
    assert body["enquiry"]["id"] == str(enquiry.pk)
    assert body["summary"] == "Call back after 6 pm."
    assert body["form_prefill"] == {"call_status": "busy"}

    listed = api_client_no_csrf.get("/api/v1/activities/", {"enquiry": str(enquiry.pk)}).json()
    assert [row["id"] for row in listed["results"]] == [body["id"]]


def test_only_if_unowned_keeps_a_walk_in_with_its_counsellor(admin_user, counsellor_user, branch):
    _second_counsellor(branch)
    automation_services.create_rule(
        actor=admin_user,
        name="Allocate unowned",
        trigger="ENQUIRY_CREATED",
        actions=[
            {
                "type": "update_enquiry",
                "params": {"owner": "least_busy_counsellor", "only_if_unowned": True},
            }
        ],
        status="active",
    )
    enquiry = _fill_enquiry(counsellor_user).enquiry
    assert enquiry.owner == counsellor_user
    automation_services.dispatch(AutomationTrigger.ENQUIRY_CREATED, enquiry)
    enquiry.refresh_from_db()
    assert enquiry.owner == counsellor_user


# ---------------------------------------------------------------------------
# Online and offline leads
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_enquiry_is_online_or_offline_by_its_source_and_the_summary_counts_each(
    api_client_no_csrf, counsellor_user
):
    from apps.enquiries import services
    from apps.enquiries.models import Enquiry

    web, _ = services.capture(
        actor=counsellor_user,
        values={"full_name": "Web Lead", "mobile": "9876500001", "source": "website"},
    )
    walk, _ = services.capture(
        actor=counsellor_user,
        values={"full_name": "Walk Lead", "mobile": "9876500002", "source": "walk_in"},
    )
    assert (web.channel, walk.channel) == ("online", "offline")

    api_client_no_csrf.force_login(counsellor_user)
    summary = api_client_no_csrf.get("/api/v1/enquiries/summary/").json()
    assert summary["channels"] == {"online": 1, "offline": 1}
    assert summary["total"] == 2
    assert {row["value"] for row in summary["sources"]} >= {"website", "walk_in", "referral"}

    online = api_client_no_csrf.get("/api/v1/enquiries/?channel=online").json()
    assert [row["full_name"] for row in online["results"]] == ["Web Lead"]

    # The source can be changed from the list, and the channel follows it...
    response = api_client_no_csrf.patch(
        f"/api/v1/enquiries/{walk.pk}/", {"source": "google"}, format="json"
    )
    assert response.status_code == 200, response.json()
    assert response.json()["channel"] == "online"
    # ...unless the channel is set by hand in the same change.
    response = api_client_no_csrf.patch(
        f"/api/v1/enquiries/{walk.pk}/",
        {"source": "referral", "channel": "online"},
        format="json",
    )
    assert response.json()["channel"] == "online"
    assert Enquiry.objects.get(pk=walk.pk).channel == "online"


@pytest.mark.django_db
def test_enquiries_can_be_filtered_by_follow_up_and_date(api_client_no_csrf, counsellor_user):
    from datetime import timedelta

    from django.utils import timezone

    from apps.enquiries import services

    late, _ = services.capture(
        actor=counsellor_user, values={"full_name": "Late", "mobile": "9876500003"}
    )
    services.update(
        actor=counsellor_user,
        enquiry=late,
        fields={"next_follow_up_at": timezone.now() - timedelta(hours=2)},
    )
    services.capture(actor=counsellor_user, values={"full_name": "Fresh", "mobile": "9876500004"})

    api_client_no_csrf.force_login(counsellor_user)
    overdue = api_client_no_csrf.get("/api/v1/enquiries/?follow_up=overdue").json()
    assert [row["full_name"] for row in overdue["results"]] == ["Late"]
    none_planned = api_client_no_csrf.get("/api/v1/enquiries/?follow_up=none").json()
    assert [row["full_name"] for row in none_planned["results"]] == ["Fresh"]
    today = timezone.localdate()
    assert api_client_no_csrf.get(f"/api/v1/enquiries/?created_after={today}").json()["count"] == 2
    assert (
        api_client_no_csrf.get(
            f"/api/v1/enquiries/?created_before={today - timedelta(days=1)}"
        ).json()["count"]
        == 0
    )


# ---------------------------------------------------------------------------
# The follow-up thread
# ---------------------------------------------------------------------------


def test_a_follow_up_note_is_written_read_back_and_dated(api_client_no_csrf, counsellor_user):
    """A note goes in, comes back with its author and time, and — when it
    says when the next call is — moves the enquiry's own follow-up date and
    stamps the contact in the same act."""
    enquiry = _fill_enquiry(counsellor_user).enquiry
    url = f"{ENQUIRIES}{enquiry.pk}/notes/"
    when = (timezone.now() + timedelta(days=2)).replace(microsecond=0)

    api_client_no_csrf.force_login(counsellor_user)
    created = api_client_no_csrf.post(
        url,
        {"body": "Rang at 11. Wants the evening batch.", "next_follow_up_at": when.isoformat()},
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["body"] == "Rang at 11. Wants the evening batch."
    assert body["author"]["name"] == counsellor_user.get_full_name()

    enquiry.refresh_from_db()
    assert enquiry.next_follow_up_at == when
    assert enquiry.last_contacted_at is not None

    listed = api_client_no_csrf.get(url).json()
    assert [row["body"] for row in listed] == ["Rang at 11. Wants the evening batch."]


def test_the_thread_reads_downwards_and_rides_along_on_the_detail_response(
    api_client_no_csrf, counsellor_user
):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    for text in ("First call, no answer.", "Second call, spoke to father.", "Visiting Friday."):
        services.add_note(actor=counsellor_user, enquiry=enquiry, body=text)

    api_client_no_csrf.force_login(counsellor_user)
    detail = api_client_no_csrf.get(f"{ENQUIRIES}{enquiry.pk}/").json()

    # Oldest first: a conversation reads downwards, unlike this app's lists.
    assert [row["body"] for row in detail["notes"]] == [
        "First call, no answer.",
        "Second call, spoke to father.",
        "Visiting Friday.",
    ]


def test_a_note_without_a_next_date_leaves_the_follow_up_alone_rather_than_clearing_it(
    counsellor_user,
):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    when = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
    services.update(actor=counsellor_user, enquiry=enquiry, fields={"next_follow_up_at": when})

    services.add_note(actor=counsellor_user, enquiry=enquiry, body="Left a WhatsApp message.")

    enquiry.refresh_from_db()
    assert enquiry.next_follow_up_at == when


def test_an_empty_or_oversized_note_is_refused(api_client_no_csrf, counsellor_user):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    url = f"{ENQUIRIES}{enquiry.pk}/notes/"
    api_client_no_csrf.force_login(counsellor_user)

    for payload in ({"body": ""}, {"body": "   "}, {"body": "x" * (services.NOTE_MAX_LENGTH + 1)}):
        response = api_client_no_csrf.post(url, payload, format="json")
        assert response.status_code == 400, payload

    from apps.enquiries.models import EnquiryNote

    assert EnquiryNote.objects.count() == 0


def test_a_students_own_account_cannot_reach_an_enquirys_thread(
    api_client_no_csrf, counsellor_user, student_profile
):
    """Enquiries are the admissions desk's records. A student is told so on
    the thread exactly as they are on every other enquiry endpoint — never
    handed somebody's lead notes."""
    enquiry = _fill_enquiry(counsellor_user).enquiry
    url = f"{ENQUIRIES}{enquiry.pk}/notes/"

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(url).status_code == 403
    assert api_client_no_csrf.post(url, {"body": "Let me in."}, format="json").status_code == 403


def test_another_centres_staff_cannot_read_or_write_the_thread(
    api_client_no_csrf, counsellor_user, other_branch_manager
):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    services.add_note(actor=counsellor_user, enquiry=enquiry, body="Jaipur's own note.")
    url = f"{ENQUIRIES}{enquiry.pk}/notes/"

    api_client_no_csrf.force_login(other_branch_manager)
    # 404, not 403: an enquiry outside the caller's centre is not theirs to
    # know about at all — the same answer the detail endpoint gives.
    assert api_client_no_csrf.get(url).status_code == 404
    assert api_client_no_csrf.post(url, {"body": "Mine now."}, format="json").status_code == 404


def test_a_trainer_who_can_see_nothing_in_the_pipeline_gets_nothing_here(
    api_client_no_csrf, counsellor_user, trainer
):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(f"{ENQUIRIES}{enquiry.pk}/notes/").status_code == 404


def test_a_meritto_lead_takes_no_note_because_its_follow_ups_live_in_meritto(
    api_client_no_csrf, counsellor_user
):
    enquiry = _fill_enquiry(counsellor_user).enquiry
    Enquiry.objects.filter(pk=enquiry.pk).update(external_system="meritto", external_id="MER-9")
    enquiry.refresh_from_db()

    api_client_no_csrf.force_login(counsellor_user)
    refused = api_client_no_csrf.post(
        f"{ENQUIRIES}{enquiry.pk}/notes/", {"body": "Rang them."}, format="json"
    )
    assert refused.status_code == 400, refused.content
    assert "Meritto" in str(refused.json())

    from apps.enquiries.models import EnquiryNote

    assert EnquiryNote.objects.count() == 0


def test_a_colleague_at_the_same_centre_without_the_capability_cannot_post(
    api_client_no_csrf, counsellor_user, trainer_profile
):
    """Reading an enquiry and writing on it are different rights. A trainer
    who somehow reaches the enquiry (by owning it) is the only trainer who
    may write on it; one who merely shares the centre may not."""
    enquiry = _fill_enquiry(counsellor_user).enquiry
    api_client_no_csrf.force_login(trainer_profile.user)
    assert (
        api_client_no_csrf.post(
            f"{ENQUIRIES}{enquiry.pk}/notes/", {"body": "Hello."}, format="json"
        ).status_code
        == 404
    )
