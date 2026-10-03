"""Forms in automation: the Meritto-style field types, conditional fields,
uploads, sending a form to someone to fill, filling one in directly, the
`FORM_SUBMITTED` trigger and the `assign_form` action.

Fixtures come from `tests/conftest.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.automation import services as automation_services
from apps.automation.models import (
    AutomationRule,
    AutomationRun,
    AutomationRunStatus,
    AutomationTrigger,
)
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.forms import services
from apps.forms.models import (
    FormAssignment,
    FormAssignmentStatus,
    FormDefinition,
    FormVersionStatus,
)
from apps.forms.validation import validate_payload
from apps.notifications.models import Notification, NotificationKind

pytestmark = pytest.mark.django_db

ASSIGNMENTS = "/api/v1/forms/assignments/"


@pytest.fixture(autouse=True)
def _pause_seeded_rules(db):
    """Seeded rules must not run alongside the rule a test builds."""
    AutomationRule.objects.update(status="paused")


def _form(actor, slug, fields, *, entity="general"):
    definition = services.create_definition(
        actor=actor, slug=slug, name=slug.title(), entity=entity
    )
    version = definition.versions.get(status=FormVersionStatus.DRAFT)
    services.set_fields(actor=actor, version=version, fields=fields)
    services.publish_version(actor=actor, version=version)
    return definition


def _published(definition):
    return definition.versions.get(status=FormVersionStatus.PUBLISHED)


LOCATION_FIELDS = [
    {
        "key": "state",
        "label": "State",
        "type": "select",
        "required": True,
        "options": [
            {"value": "rajasthan", "label": "Rajasthan"},
            {"value": "maharashtra", "label": "Maharashtra"},
        ],
    },
    {
        "key": "city",
        "label": "City",
        "type": "dependent_select",
        "required": True,
        "options": {
            "parent": "state",
            "choices": {
                "rajasthan": [{"value": "jaipur", "label": "Jaipur"}],
                "maharashtra": [{"value": "pune", "label": "Pune"}],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------


def test_dependent_select_accepts_only_the_parents_choices(admin_user):
    version = _published(_form(admin_user, "location", LOCATION_FIELDS))
    cleaned = validate_payload(
        version=version, values={"state": "rajasthan", "city": "jaipur"}, actor=admin_user
    )
    assert cleaned == {"state": "rajasthan", "city": "jaipur"}

    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(
            version=version, values={"state": "rajasthan", "city": "pune"}, actor=admin_user
        )
    assert "city" in excinfo.value.detail


def test_new_field_types_validate(admin_user):
    version = _published(
        _form(
            admin_user,
            "types",
            [
                {"key": "intro", "label": "About you", "type": "heading"},
                {
                    "key": "call_at",
                    "label": "Call at",
                    "type": "time",
                    "validation": {"min": "09:00"},
                },
                {"key": "quality", "label": "Quality", "type": "rating", "validation": {"max": 5}},
                {"key": "agree", "label": "I agree", "type": "consent", "required": True},
                {
                    "key": "utm_source",
                    "label": "UTM",
                    "type": "hidden",
                    "validation": {"default": "walk-in"},
                },
            ],
        )
    )
    cleaned = validate_payload(
        version=version,
        values={"call_at": "10:30", "quality": 4, "agree": True},
        actor=admin_user,
    )
    assert cleaned == {"call_at": "10:30", "quality": 4, "agree": True, "utm_source": "walk-in"}

    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(
            version=version,
            values={"intro": "x", "call_at": "08:00", "quality": 9, "agree": False},
            actor=admin_user,
        )
    errors = excinfo.value.detail
    assert set(errors) == {"intro", "call_at", "quality", "agree"}


def test_a_hidden_conditional_field_is_not_required_and_its_value_is_dropped(admin_user):
    version = _published(
        _form(
            admin_user,
            "conditional",
            [
                {
                    "key": "stage",
                    "label": "Stage",
                    "type": "select",
                    "required": True,
                    "options": [
                        {"value": "interested", "label": "Interested"},
                        {"value": "lost", "label": "Lost"},
                    ],
                },
                {
                    "key": "reason",
                    "label": "Reason",
                    "type": "text",
                    "required": True,
                    "show_if": {"field": "stage", "op": "eq", "value": "lost"},
                },
                {
                    "key": "competitor",
                    "label": "Competitor",
                    "type": "text",
                    "required": True,
                    "show_if": {"field": "reason", "op": "eq", "value": "competitor"},
                },
            ],
        )
    )
    cleaned = validate_payload(
        version=version,
        values={"stage": "interested", "reason": "left over", "competitor": "left over"},
        actor=admin_user,
    )
    assert cleaned == {"stage": "interested"}

    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(version=version, values={"stage": "lost"}, actor=admin_user)
    assert set(excinfo.value.detail) == {"reason"}

    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(
            version=version, values={"stage": "lost", "reason": "competitor"}, actor=admin_user
        )
    assert set(excinfo.value.detail) == {"competitor"}


@pytest.mark.parametrize(
    ("fields", "bad_key"),
    [
        (
            [
                {
                    "key": "city",
                    "label": "City",
                    "type": "dependent_select",
                    "options": {"parent": "state", "choices": {}},
                },
                {"key": "state", "label": "State", "type": "select", "options": []},
            ],
            "city",
        ),
        (
            [
                {"key": "name", "label": "Name", "type": "text"},
                {
                    "key": "city",
                    "label": "City",
                    "type": "dependent_select",
                    "options": {"parent": "name", "choices": {}},
                },
            ],
            "city",
        ),
        (
            [
                {
                    "key": "a",
                    "label": "A",
                    "type": "text",
                    "show_if": {"field": "b", "op": "eq", "value": "x"},
                },
                {"key": "b", "label": "B", "type": "text"},
            ],
            "a",
        ),
        ([{"key": "h", "label": "H", "type": "heading", "required": True}], "h"),
    ],
)
def test_set_fields_refuses_broken_dependencies(admin_user, fields, bad_key):
    definition = services.create_definition(
        actor=admin_user, slug="broken", name="Broken", entity="general"
    )
    version = definition.versions.get(status=FormVersionStatus.DRAFT)
    with pytest.raises(ApplicationError) as excinfo:
        services.set_fields(actor=admin_user, version=version, fields=fields)
    assert bad_key in excinfo.value.detail


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def _pdf(pdf_bytes, name="resume.pdf"):
    return SimpleUploadedFile(name, pdf_bytes, content_type="application/pdf")


def test_an_upload_can_be_attached_only_by_its_uploader(admin_user, manager_user, pdf_bytes):
    version = _published(
        _form(
            admin_user,
            "with-file",
            [
                {
                    "key": "resume",
                    "label": "Resume",
                    "type": "file",
                    "required": True,
                    "validation": {"accept": [".pdf"], "max_mb": 5},
                }
            ],
        )
    )
    upload = services.create_upload(actor=manager_user, uploaded_file=_pdf(pdf_bytes))
    assert upload.content_type == "application/pdf"
    assert upload.original_name == "resume.pdf"

    cleaned = validate_payload(
        version=version, values={"resume": str(upload.pk)}, actor=manager_user
    )
    assert cleaned == {"resume": str(upload.pk)}

    with pytest.raises(ApplicationError):
        validate_payload(version=version, values={"resume": str(upload.pk)}, actor=admin_user)


def test_upload_endpoint_refuses_a_disguised_file(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.post(
        "/api/v1/forms/uploads/",
        {"file": SimpleUploadedFile("cv.pdf", b"not a pdf at all", content_type="application/pdf")},
        format="multipart",
    )
    assert response.status_code == 400


def test_upload_download_is_limited_to_uploader_and_form_readers(
    api_client_no_csrf, student, trainer, manager_user, pdf_bytes
):
    api_client_no_csrf.force_login(student)
    created = api_client_no_csrf.post(
        "/api/v1/forms/uploads/", {"file": _pdf(pdf_bytes)}, format="multipart"
    )
    assert created.status_code == 201
    url = f"/api/v1/forms/uploads/{created.json()['id']}/"

    assert api_client_no_csrf.get(url).status_code == 200
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(url).status_code == 404
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.get(url).status_code == 200


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


SIMPLE_FIELDS = [
    {"key": "answer", "label": "Answer", "type": "text", "required": True},
    {"key": "notes", "label": "Notes", "type": "textarea"},
]


def test_sending_a_form_notifies_the_assignee_and_only_they_can_submit(
    admin_user, counsellor_user, trainer
):
    definition = _form(admin_user, "check-in", SIMPLE_FIELDS)
    assignment = services.assign_form(
        actor=counsellor_user,
        definition=definition,
        assigned_to=trainer,
        due_at=timezone.now() + timedelta(days=1),
        message="Please fill this in.",
    )
    assert assignment.status == FormAssignmentStatus.PENDING
    assert Notification.objects.filter(
        recipient=trainer, kind=NotificationKind.FORM_ASSIGNED
    ).exists()

    with pytest.raises(AuthorityError):
        services.submit_assignment(
            actor=counsellor_user, assignment=assignment, values={"answer": "x"}
        )

    submitted = services.submit_assignment(
        actor=trainer, assignment=assignment, values={"answer": "Done"}
    )
    assert submitted.status == FormAssignmentStatus.SUBMITTED
    assert submitted.response.values == {"answer": "Done"}
    assert Notification.objects.filter(
        recipient=counsellor_user, kind=NotificationKind.FORM_SUBMITTED
    ).exists()

    with pytest.raises(ConflictError):
        services.submit_assignment(actor=trainer, assignment=assignment, values={"answer": "again"})


def test_a_trainer_cannot_send_forms(admin_user, trainer, student):
    definition = _form(admin_user, "no-send", SIMPLE_FIELDS)
    with pytest.raises(AuthorityError):
        services.assign_form(actor=trainer, definition=definition, assigned_to=student)


def test_a_centre_manager_cannot_send_to_another_centre(
    admin_user, manager_user, other_branch_manager
):
    definition = _form(admin_user, "cross-centre", SIMPLE_FIELDS)
    with pytest.raises(ApplicationError) as excinfo:
        services.assign_form(
            actor=manager_user, definition=definition, assigned_to=other_branch_manager
        )
    assert "assigned_to" in excinfo.value.detail


def test_an_assignment_is_answered_on_its_pinned_version_after_a_republish(
    admin_user, counsellor_user, trainer
):
    definition = _form(admin_user, "pinned", SIMPLE_FIELDS)
    assignment = services.assign_form(
        actor=counsellor_user, definition=definition, assigned_to=trainer
    )
    draft = services.create_draft_version(
        actor=admin_user, definition=definition, cloned_from=assignment.version
    )
    services.set_fields(
        actor=admin_user,
        version=draft,
        fields=[*SIMPLE_FIELDS, {"key": "extra", "label": "Extra", "type": "text"}],
    )
    services.publish_version(actor=admin_user, version=draft)
    assignment.version.refresh_from_db()
    assert assignment.version.status == FormVersionStatus.ARCHIVED

    submitted = services.submit_assignment(
        actor=trainer, assignment=assignment, values={"answer": "on v1"}
    )
    assert submitted.response.version_id == assignment.version_id


def test_unpublishing_a_version_someone_is_filling_is_refused(admin_user, counsellor_user, trainer):
    definition = _form(admin_user, "in-use", SIMPLE_FIELDS)
    services.assign_form(actor=counsellor_user, definition=definition, assigned_to=trainer)
    with pytest.raises(ConflictError):
        services.unpublish_version(actor=admin_user, version=_published(definition))


def test_cancel_by_the_sender(admin_user, counsellor_user, trainer):
    definition = _form(admin_user, "cancel-me", SIMPLE_FIELDS)
    assignment = services.assign_form(
        actor=counsellor_user, definition=definition, assigned_to=trainer
    )
    with pytest.raises(AuthorityError):
        services.cancel_assignment(actor=trainer, assignment=assignment)
    cancelled = services.cancel_assignment(actor=counsellor_user, assignment=assignment)
    assert cancelled.status == FormAssignmentStatus.CANCELLED
    with pytest.raises(ConflictError):
        services.submit_assignment(actor=trainer, assignment=assignment, values={"answer": "x"})


def test_assignment_api_inbox_sent_and_submit(
    api_client_no_csrf, admin_user, counsellor_user, trainer
):
    definition = _form(admin_user, "api-form", SIMPLE_FIELDS)

    api_client_no_csrf.force_login(counsellor_user)
    created = api_client_no_csrf.post(
        ASSIGNMENTS,
        {"form": definition.slug, "assigned_to": str(trainer.pk), "title": "Weekly check-in"},
        format="json",
    )
    assert created.status_code == 201, created.content
    assignment_id = created.json()["id"]
    sent = api_client_no_csrf.get(ASSIGNMENTS, {"box": "sent"}).json()
    assert [row["id"] for row in sent["results"]] == [assignment_id]

    api_client_no_csrf.force_login(trainer)
    inbox = api_client_no_csrf.get(ASSIGNMENTS).json()
    assert [row["id"] for row in inbox["results"]] == [assignment_id]
    assert inbox["results"][0]["can_submit"] is True
    detail = api_client_no_csrf.get(f"{ASSIGNMENTS}{assignment_id}/").json()
    assert [field["key"] for field in detail["fields"]] == ["answer", "notes"]
    assert api_client_no_csrf.get(ASSIGNMENTS, {"box": "all"}).status_code == 403

    bad = api_client_no_csrf.post(
        f"{ASSIGNMENTS}{assignment_id}/submit/", {"values": {}}, format="json"
    )
    assert bad.status_code == 400
    ok = api_client_no_csrf.post(
        f"{ASSIGNMENTS}{assignment_id}/submit/", {"values": {"answer": "Yes"}}, format="json"
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "submitted"
    assert ok.json()["values"] == {"answer": "Yes"}


def test_someone_else_cannot_read_an_assignment(
    api_client_no_csrf, admin_user, counsellor_user, trainer, student
):
    definition = _form(admin_user, "private", SIMPLE_FIELDS)
    assignment = services.assign_form(
        actor=counsellor_user, definition=definition, assigned_to=trainer
    )
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(f"{ASSIGNMENTS}{assignment.pk}/").status_code == 404


def test_fill_directly_and_list_fillable_forms(api_client_no_csrf, counsellor_user, trainer):
    api_client_no_csrf.force_login(counsellor_user)
    fillable = api_client_no_csrf.get("/api/v1/forms/fillable/").json()
    slugs = {row["slug"] for row in fillable}
    assert {"enquiry", "enquiry-follow-up"} <= slugs
    assert "mock-interview" not in slugs  # activity forms reach people through activities

    response = api_client_no_csrf.post(
        "/api/v1/forms/enquiry/fill/",
        {
            "values": {
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
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "submitted"
    assert body["assigned_to"]["id"] == str(counsellor_user.pk)

    api_client_no_csrf.force_login(trainer)
    assert (
        api_client_no_csrf.post(
            "/api/v1/forms/enquiry/fill/", {"values": {}}, format="json"
        ).status_code
        == 403
    )


def test_seeded_enquiry_follow_up_asks_only_what_the_answers_call_for(counsellor_user):
    definition = FormDefinition.objects.get(slug="enquiry-follow-up")
    version = _published(definition)
    cleaned = validate_payload(
        version=version,
        values={"call_status": "connected", "lead_stage": "not_interested", "lost_reason": "fees"},
        actor=counsellor_user,
    )
    assert cleaned == {
        "call_status": "connected",
        "lead_stage": "not_interested",
        "lost_reason": "fees",
    }
    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(version=version, values={"call_status": "busy"}, actor=counsellor_user)
    assert set(excinfo.value.detail) == {"next_follow_up"}


# ---------------------------------------------------------------------------
# Automation: FORM_SUBMITTED and assign_form
# ---------------------------------------------------------------------------


def _submitted(actor, definition, assignee, values, *, student=None):
    assignment = services.assign_form(
        actor=actor, definition=definition, assigned_to=assignee, student=student
    )
    return services.submit_assignment(actor=assignee, assignment=assignment, values=values)


def test_form_submitted_rule_reads_answers_and_sends_the_next_form(
    admin_user, counsellor_user, trainer
):
    first = _form(
        admin_user,
        "intake",
        [
            {
                "key": "stage",
                "label": "Stage",
                "type": "select",
                "options": [
                    {"value": "interested", "label": "Interested"},
                    {"value": "lost", "label": "Lost"},
                ],
            },
            {"key": "remarks", "label": "Remarks", "type": "textarea"},
        ],
    )
    follow_up = _form(admin_user, "intake-follow-up", SIMPLE_FIELDS)
    rule = automation_services.create_rule(
        actor=admin_user,
        name="Intake follow-up",
        trigger="FORM_SUBMITTED",
        conditions=[
            {"path": "submission.form", "op": "eq", "value": "intake"},
            {"path": "form.stage", "op": "eq", "value": "interested"},
            {"path": "form.remarks", "op": "is_empty"},
        ],
        actions=[
            {
                "type": "assign_form",
                "params": {
                    "form": "intake-follow-up",
                    "to": "submitter",
                    "due_in_days": 2,
                    "title": "Follow up ({{form.stage}})",
                },
            }
        ],
        status="active",
    )

    lost = _submitted(counsellor_user, first, trainer, {"stage": "lost"})
    automation_services.dispatch(AutomationTrigger.FORM_SUBMITTED, lost)
    assert not AutomationRun.objects.filter(rule=rule).exists()

    interested = _submitted(counsellor_user, first, trainer, {"stage": "interested"})
    automation_services.dispatch(AutomationTrigger.FORM_SUBMITTED, interested)
    run = AutomationRun.objects.get(rule=rule)
    assert run.status == AutomationRunStatus.RAN, run.result

    sent = FormAssignment.objects.get(definition=follow_up)
    assert sent.assigned_to == trainer
    assert sent.title == "Follow up (interested)"
    assert sent.automation_run_id == run.pk
    assert sent.due_at is not None

    # Idempotent: the same submission does not send a second form.
    automation_services.dispatch(AutomationTrigger.FORM_SUBMITTED, interested)
    assert FormAssignment.objects.filter(definition=follow_up).count() == 1


def test_submitting_enqueues_the_trigger_on_commit(
    admin_user, counsellor_user, trainer, django_capture_on_commit_callbacks
):
    definition = _form(admin_user, "on-commit", SIMPLE_FIELDS)
    rule = automation_services.create_rule(
        actor=admin_user,
        name="Any submission",
        trigger="FORM_SUBMITTED",
        conditions=[{"path": "submission.form", "op": "eq", "value": "on-commit"}],
        actions=[],
        status="active",
    )
    assignment = services.assign_form(
        actor=counsellor_user, definition=definition, assigned_to=trainer
    )
    with django_capture_on_commit_callbacks(execute=True):
        services.submit_assignment(actor=trainer, assignment=assignment, values={"answer": "x"})
    assert AutomationRun.objects.filter(rule=rule, status=AutomationRunStatus.RAN).exists()


def test_activity_completed_context_now_carries_text_answers(
    admin_user, trainer_profile, enrollment
):
    from apps.automation.evaluator import context_for_activity_completed
    from apps.work import services as work_services
    from apps.work.models import Activity, ActivityStatus, ActivityType

    definition = _form(
        admin_user,
        "text-activity",
        [
            {"key": "topic", "label": "Topic", "type": "text", "required": True},
            {"key": "resolved", "label": "Resolved", "type": "boolean"},
        ],
        entity="activity",
    )
    activity_type = ActivityType.objects.create(
        slug="text-activity",
        name="Text activity",
        category="mentoring",
        allowed_creator_roles=["admin", "trainer"],
        allowed_assignee_roles=["trainer"],
        form=definition,
    )
    trainer_user = trainer_profile.user
    activity = Activity.objects.create(
        student=enrollment.student,
        enrollment=enrollment,
        batch=enrollment.batch,
        branch=enrollment.batch.branch,
        activity_type=activity_type,
        title="Doubt",
        status=ActivityStatus.IN_PROGRESS,
        created_by=trainer_user,
        assigned_to=trainer_user,
        performed_by=trainer_user,
        form_version=_published(definition),
    )

    # Republish before completing: the activity still completes on its pin.
    draft = services.create_draft_version(
        actor=admin_user, definition=definition, cloned_from=_published(definition)
    )
    services.set_fields(
        actor=admin_user,
        version=draft,
        fields=[{"key": "topic", "label": "Topic (v2)", "type": "text", "required": True}],
    )
    services.publish_version(actor=admin_user, version=draft)

    activity = work_services.complete_activity(
        actor=trainer_user, activity=activity, form_values={"topic": "Loops", "resolved": True}
    )
    context = context_for_activity_completed(activity)
    assert context["form"] == {"topic": "Loops", "resolved": True}


def test_assign_form_is_checked_when_the_rule_is_saved(admin_user, manager_user):
    with pytest.raises(ApplicationError):
        automation_services.create_rule(
            actor=admin_user,
            name="Unknown form",
            trigger="FORM_SUBMITTED",
            actions=[{"type": "assign_form", "params": {"form": "nope", "to": "submitter"}}],
        )
    with pytest.raises(ApplicationError):
        automation_services.create_rule(
            actor=admin_user,
            name="Activity form",
            trigger="FORM_SUBMITTED",
            actions=[
                {"type": "assign_form", "params": {"form": "mock-interview", "to": "submitter"}}
            ],
        )
    assert automation_services.ACTION_PERMISSIONS["assign_form"] == "form.assign"


def test_seeded_enquiry_rules_are_well_formed():
    names = {
        "Call a new enquiry within 2 hours",
        "Book a demo class for an interested enquiry",
        "Follow up an unanswered call next day",
        "Tell the manager about a lost enquiry",
    }
    rules = AutomationRule.objects.filter(name__in=names)
    assert rules.count() == 4
    for rule in rules:
        automation_services._validate_rule_shape(rule.trigger, rule.conditions, rule.actions)
