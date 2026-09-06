"""Daily status reports: prefilling from attendance, the review workflow,
and the access boundaries around both.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.dsr.models import DSR, DSRStatus
from apps.dsr.services import review_dsr, start_dsr, submit_dsr, update_dsr

TEST_PASSWORD = "correct-horse-battery-staple"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def past_session(admin_user, batch, schedule):
    """A class that has already finished, so there is something to report on."""
    from apps.sessions.services import create_session

    return create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Filesystem basics",
    )


@pytest.fixture
def other_session(admin_user, upcoming_batch):
    """A class on a different batch, taught by a different trainer."""
    from apps.sessions.services import create_session

    return create_session(
        batch=upcoming_batch,
        actor=admin_user,
        session_date=upcoming_batch.start_date,
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Orientation",
    )


@pytest.fixture
def marked_session(admin_user, trainer_profile, past_session, enrollment, other_enrollment):
    """The register for `past_session` has been taken: one present, one absent."""
    from apps.attendance.services import mark_attendance

    mark_attendance(
        session=past_session,
        actor=trainer_profile.user,
        entries=[
            {"enrollment_id": str(enrollment.id), "status": "present"},
            {"enrollment_id": str(other_enrollment.id), "status": "absent"},
        ],
    )
    return past_session


@pytest.fixture
def draft_dsr(admin_user, past_session):
    """A draft report, created directly through the service."""
    return start_dsr(session=past_session, actor=admin_user)


@pytest.fixture
def submitted_dsr(draft_dsr, trainer_profile):
    return submit_dsr(dsr=draft_dsr, actor=trainer_profile.user)


def _session_dsr_url(session) -> str:
    return f"/api/v1/sessions/{session.id}/dsr/"


def _batch_dsr_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/dsr/"


def _list_url() -> str:
    return "/api/v1/dsr/"


def _detail_url(dsr) -> str:
    return f"/api/v1/dsr/{dsr.id}/"


def _submit_url(dsr) -> str:
    return f"/api/v1/dsr/{dsr.id}/submit/"


def _review_url(dsr) -> str:
    return f"/api/v1/dsr/{dsr.id}/review/"


def _delete_url(dsr) -> str:
    return f"/api/v1/dsr/{dsr.id}/delete/"


def _last_audit(action) -> AuditLog:
    return AuditLog.objects.filter(action=action).latest("created_at")


# ---------------------------------------------------------------------------
# Starting a report: the prefilled shape and creation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_prefilled_shape_has_no_id_and_defaults_from_the_session(
    api_client_no_csrf, trainer_profile, past_session, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(_session_dsr_url(past_session)).json()

    assert body["id"] is None
    assert body["report_date"] == past_session.session_date.isoformat()
    assert body["start_time"] == "09:00:00"
    assert body["end_time"] == "11:00:00"
    assert body["status"] == DSRStatus.DRAFT
    assert body["student_count"] == 2
    assert body["present_count"] == 0
    assert body["absent_count"] == 0
    assert body["online_count"] == 0
    assert body["offline_count"] == 0
    # The topic comes from the session record the trainer already filled in —
    # nothing here should ever ask them to retype it.
    assert body["planned_topic"] == "Filesystem basics"
    assert body["actual_topic"] == "Filesystem basics"


@pytest.mark.django_db
def test_a_session_with_no_attendance_still_gets_sensible_zero_counts(
    api_client_no_csrf, trainer_profile, past_session, enrollment
):
    """Zero present and absent, not an error and not null."""
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(_session_dsr_url(past_session)).json()

    assert body["student_count"] == 1
    assert body["present_count"] == 0
    assert body["absent_count"] == 0


@pytest.mark.django_db
def test_starting_a_report_prefills_counts_from_the_register(
    api_client_no_csrf, trainer_profile, marked_session
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_session_dsr_url(marked_session), {}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["id"] is not None
    assert body["status"] == DSRStatus.DRAFT
    assert body["student_count"] == 2
    assert body["present_count"] == 1
    assert body["absent_count"] == 1
    assert body["planned_topic"] == "Filesystem basics"
    assert body["actual_topic"] == "Filesystem basics"
    assert DSR.objects.filter(session=marked_session).exists()


@pytest.mark.django_db
def test_starting_a_report_and_submitting_it_is_one_request(
    api_client_no_csrf, trainer_profile, marked_session
):
    """The common case: nothing to correct, so the trainer creates and hands
    it over in the same request rather than confirming twice."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _session_dsr_url(marked_session), {"submit": True}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == DSRStatus.SUBMITTED
    assert body["submitted_at"] is not None

    assert _last_audit(AuditAction.DSR_CREATED).resource_id == body["id"]
    assert _last_audit(AuditAction.DSR_SUBMITTED).resource_id == body["id"]


@pytest.mark.django_db
def test_submit_false_leaves_it_a_draft(api_client_no_csrf, trainer_profile, past_session):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _session_dsr_url(past_session), {"submit": False}, format="json"
    )
    assert response.json()["status"] == DSRStatus.DRAFT


@pytest.mark.django_db
def test_starting_a_report_writes_the_created_audit_action(
    api_client_no_csrf, trainer_profile, past_session
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json")
    dsr_id = response.json()["id"]

    entry = _last_audit(AuditAction.DSR_CREATED)
    assert entry.resource_id == dsr_id
    assert entry.actor_id == trainer_profile.user_id


@pytest.mark.django_db
def test_starting_a_report_accepts_explicit_overrides(
    api_client_no_csrf, trainer_profile, past_session
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _session_dsr_url(past_session),
        {
            "planned_topic": "Shell scripting",
            "actual_topic": "Shell scripting basics",
            "online_count": 1,
            "offline_count": 1,
            "assignment_given": True,
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["planned_topic"] == "Shell scripting"
    assert body["actual_topic"] == "Shell scripting basics"
    assert body["online_count"] == 1
    assert body["offline_count"] == 1
    assert body["assignment_given"] is True


@pytest.mark.django_db
def test_a_second_report_on_the_same_class_is_refused(
    api_client_no_csrf, trainer_profile, past_session
):
    api_client_no_csrf.force_login(trainer_profile.user)
    first = api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json")
    assert first.status_code == 201

    second = api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json")
    assert second.status_code == 409


@pytest.mark.django_db
def test_end_before_start_is_refused_when_starting(
    api_client_no_csrf, trainer_profile, past_session
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _session_dsr_url(past_session),
        {"start_time": "11:00:00", "end_time": "09:00:00"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_manager_can_start_a_report_on_a_trainers_behalf(
    api_client_no_csrf, manager_user, trainer_profile, past_session
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json")

    assert response.status_code == 201
    dsr = DSR.objects.get(pk=response.json()["id"])
    assert dsr.trainer_id == trainer_profile.pk


# ---------------------------------------------------------------------------
# Who may reach the session-scoped endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_from_another_batch_cannot_see_the_prefilled_shape(
    api_client_no_csrf, trainer_profile_two, past_session
):
    """The class itself is on a batch this trainer does not teach, so the
    session lookup fails before any DSR-specific check runs."""
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.get(_session_dsr_url(past_session))
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_trainer_from_another_batch_cannot_start_a_report(
    api_client_no_csrf, trainer_profile_two, past_session
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json")
    assert response.status_code == 404
    assert not DSR.objects.filter(session=past_session).exists()


@pytest.mark.django_db
def test_a_student_cannot_reach_the_session_dsr_endpoint(
    api_client_no_csrf, student_profile, enrollment, past_session
):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(_session_dsr_url(past_session)).status_code == 403
    assert (
        api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json").status_code
        == 403
    )


@pytest.mark.django_db
def test_a_counsellor_cannot_reach_the_session_dsr_endpoint(
    api_client_no_csrf, counsellor_user, past_session
):
    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(_session_dsr_url(past_session)).status_code == 403
    assert (
        api_client_no_csrf.post(_session_dsr_url(past_session), {}, format="json").status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Reading and listing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_batch_endpoint_lists_its_own_reports(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(_batch_dsr_url(draft_dsr.batch)).json()
    assert body["count"] == 1
    assert body["results"][0]["id"] == str(draft_dsr.id)


@pytest.mark.django_db
def test_a_trainer_from_another_batch_cannot_open_the_batch_list_at_all(
    api_client_no_csrf, trainer_profile_two, draft_dsr
):
    """The batch itself is invisible to them, so the endpoint 404s."""
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.get(_batch_dsr_url(draft_dsr.batch))
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_student_is_refused_the_list_endpoint(
    api_client_no_csrf, student_profile, enrollment, draft_dsr
):
    """Refused, not answered with an empty page.

    `visible_dsrs` scopes a student to nothing, so the endpoint could safely
    return `{"count": 0}`. It should not. A daily status report is internal
    reporting about a class, written by staff for staff — a student is not
    somebody whose view of it happens to be empty, they have no view of it, and
    the status code should say which.

    It also keeps the authorization sweep meaningful: an allowlist that grows
    every route that "returns nothing anyway" stops testing anything.
    """
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(_list_url()).status_code == 403


@pytest.mark.django_db
def test_a_counsellor_is_refused_the_list_endpoint(api_client_no_csrf, counsellor_user, draft_dsr):
    """Admissions ends where teaching begins, and this is on the far side."""
    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(_list_url()).status_code == 403


@pytest.mark.django_db
def test_a_manager_sees_every_report_in_the_list(
    api_client_no_csrf, manager_user, draft_dsr, admin_user, other_session
):
    from apps.dsr.services import start_dsr as start

    start(session=other_session, actor=admin_user)

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_list_url()).json()
    assert body["count"] == 2


@pytest.mark.django_db
def test_the_list_can_be_filtered_by_status(
    api_client_no_csrf, manager_user, draft_dsr, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_list_url(), {"status": DSRStatus.SUBMITTED}).json()
    ids = {row["id"] for row in body["results"]}
    assert ids == {str(submitted_dsr.id)}


@pytest.mark.django_db
def test_the_list_can_be_filtered_by_batch(api_client_no_csrf, manager_user, draft_dsr):
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_list_url(), {"batch": str(draft_dsr.batch_id)}).json()
    assert body["count"] == 1


@pytest.mark.django_db
def test_the_list_can_be_filtered_by_trainer(api_client_no_csrf, manager_user, draft_dsr):
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get(_list_url(), {"trainer": str(draft_dsr.trainer_id)}).json()
    assert body["count"] == 1


@pytest.mark.django_db
def test_the_list_can_be_filtered_by_date_range(api_client_no_csrf, manager_user, draft_dsr):
    api_client_no_csrf.force_login(manager_user)
    future = (draft_dsr.report_date + timedelta(days=1)).isoformat()
    body = api_client_no_csrf.get(_list_url(), {"date_after": future}).json()
    assert body["count"] == 0


@pytest.mark.django_db
def test_the_list_endpoint_costs_a_bounded_number_of_queries(
    api_client_no_csrf, manager_user, admin_user, batch, django_assert_max_num_queries
):
    from apps.sessions.services import create_session

    for offset in range(5):
        session = create_session(
            batch=batch,
            actor=admin_user,
            session_date=timezone.localdate() - timedelta(days=offset + 2),
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        start_dsr(session=session, actor=admin_user)

    api_client_no_csrf.force_login(manager_user)
    with django_assert_max_num_queries(12):
        response = api_client_no_csrf.get(_list_url())
    assert response.json()["count"] == 5


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_trainer_can_edit_their_own_draft(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(draft_dsr), {"teaching_notes": "Covered permissions."}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["teaching_notes"] == "Covered permissions."


@pytest.mark.django_db
def test_editing_writes_the_updated_audit_action(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.patch(_detail_url(draft_dsr), {"issues": "Projector broken."}, format="json")

    entry = _last_audit(AuditAction.DSR_UPDATED)
    assert entry.resource_id == str(draft_dsr.id)


@pytest.mark.django_db
def test_another_trainer_cannot_edit_this_report(
    api_client_no_csrf, trainer_profile_two, draft_dsr
):
    """A report on a batch this trainer does not teach is not merely
    unwritable to them — `visible_dsrs` never surfaces it at all."""
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.patch(
        _detail_url(draft_dsr), {"teaching_notes": "Not mine."}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_the_trainer_cannot_edit_after_submitting(
    api_client_no_csrf, trainer_profile, submitted_dsr
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(submitted_dsr), {"teaching_notes": "Too late."}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_the_trainer_can_edit_again_once_revision_is_required(
    api_client_no_csrf, trainer_profile, manager_user, submitted_dsr
):
    review_dsr(
        dsr=submitted_dsr,
        actor=manager_user,
        decision=DSRStatus.REVISION_REQUIRED,
        comments="More detail please.",
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(submitted_dsr), {"teaching_notes": "More detail added."}, format="json"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_manage_any_can_correct_a_report_after_it_is_approved(
    api_client_no_csrf, admin_user, manager_user, submitted_dsr
):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.APPROVED)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _detail_url(submitted_dsr), {"teaching_notes": "Typo fixed."}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.APPROVED


@pytest.mark.django_db
def test_end_before_start_is_refused_on_edit(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(draft_dsr), {"start_time": "11:00:00", "end_time": "09:00:00"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_module_can_be_assigned_from_the_reports_own_course(
    api_client_no_csrf, trainer_profile, draft_dsr, published_module
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(draft_dsr), {"module": str(published_module.id)}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["module"] == str(published_module.id)


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_trainer_can_submit_their_draft(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_submit_url(draft_dsr), {}, format="json")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == DSRStatus.SUBMITTED
    assert body["submitted_at"] is not None


@pytest.mark.django_db
def test_submitting_writes_the_submitted_audit_action(
    api_client_no_csrf, trainer_profile, draft_dsr
):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(_submit_url(draft_dsr), {}, format="json")

    entry = _last_audit(AuditAction.DSR_SUBMITTED)
    assert entry.resource_id == str(draft_dsr.id)


@pytest.mark.django_db
def test_a_report_cannot_be_submitted_twice(api_client_no_csrf, trainer_profile, submitted_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_submit_url(submitted_dsr), {}, format="json")
    assert response.status_code == 409


@pytest.mark.django_db
def test_another_trainer_cannot_submit_this_report(
    api_client_no_csrf, trainer_profile_two, draft_dsr
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.post(_submit_url(draft_dsr), {}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_trainer_can_resubmit_after_revision_is_required(
    api_client_no_csrf, trainer_profile, manager_user, submitted_dsr
):
    review_dsr(
        dsr=submitted_dsr,
        actor=manager_user,
        decision=DSRStatus.REVISION_REQUIRED,
        comments="Say more.",
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_submit_url(submitted_dsr), {}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.SUBMITTED


@pytest.mark.django_db
def test_editing_and_resubmitting_after_revision_is_one_request(
    api_client_no_csrf, trainer_profile, manager_user, submitted_dsr
):
    review_dsr(
        dsr=submitted_dsr,
        actor=manager_user,
        decision=DSRStatus.REVISION_REQUIRED,
        comments="Say more.",
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        _detail_url(submitted_dsr),
        {"teaching_notes": "Added the missing detail.", "submit": True},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == DSRStatus.SUBMITTED
    assert body["teaching_notes"] == "Added the missing detail."


# ---------------------------------------------------------------------------
# Reviewing: legal transitions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_manager_can_take_a_submitted_report_under_review(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.UNDER_REVIEW}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == DSRStatus.UNDER_REVIEW
    assert body["reviewed_at"] is not None


@pytest.mark.django_db
def test_review_started_writes_its_own_audit_action(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.UNDER_REVIEW}, format="json"
    )

    entry = _last_audit(AuditAction.DSR_REVIEW_STARTED)
    assert entry.resource_id == str(submitted_dsr.id)


@pytest.mark.django_db
def test_a_manager_can_approve_a_submitted_report_directly(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.APPROVED

    entry = _last_audit(AuditAction.DSR_APPROVED)
    assert entry.resource_id == str(submitted_dsr.id)


@pytest.mark.django_db
def test_a_manager_can_reject_a_submitted_report_with_comments(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr),
        {"decision": DSRStatus.REJECTED, "comments": "Does not match the register."},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.REJECTED
    assert response.json()["manager_comments"] == "Does not match the register."

    entry = _last_audit(AuditAction.DSR_REJECTED)
    assert entry.resource_id == str(submitted_dsr.id)


@pytest.mark.django_db
def test_a_manager_can_send_a_submitted_report_back_for_revision(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr),
        {"decision": DSRStatus.REVISION_REQUIRED, "comments": "Add the assessment details."},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.REVISION_REQUIRED

    entry = _last_audit(AuditAction.DSR_REVISION_REQUESTED)
    assert entry.resource_id == str(submitted_dsr.id)


@pytest.mark.django_db
def test_an_under_review_report_can_be_approved(api_client_no_csrf, manager_user, submitted_dsr):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.UNDER_REVIEW)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.APPROVED


@pytest.mark.django_db
def test_an_under_review_report_can_be_rejected(api_client_no_csrf, manager_user, submitted_dsr):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.UNDER_REVIEW)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr),
        {"decision": DSRStatus.REJECTED, "comments": "No."},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.REJECTED


@pytest.mark.django_db
def test_an_under_review_report_can_require_revision(
    api_client_no_csrf, manager_user, submitted_dsr
):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.UNDER_REVIEW)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr),
        {"decision": DSRStatus.REVISION_REQUIRED, "comments": "Missing notes."},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == DSRStatus.REVISION_REQUIRED


# ---------------------------------------------------------------------------
# Reviewing: illegal transitions and refusals
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_draft_cannot_be_reviewed(api_client_no_csrf, manager_user, draft_dsr):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(draft_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_an_approved_report_cannot_be_reviewed_again(
    api_client_no_csrf, manager_user, submitted_dsr
):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.APPROVED)

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr),
        {"decision": DSRStatus.REJECTED, "comments": "Changed my mind."},
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_a_rejected_report_cannot_be_reviewed_again(
    api_client_no_csrf, manager_user, submitted_dsr
):
    review_dsr(dsr=submitted_dsr, actor=manager_user, decision=DSRStatus.REJECTED, comments="No.")

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_rejecting_without_comments_is_refused(api_client_no_csrf, manager_user, submitted_dsr):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.REJECTED}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_requiring_revision_without_comments_is_refused(
    api_client_no_csrf, manager_user, submitted_dsr
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.REVISION_REQUIRED}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_manager_who_is_also_the_trainer_cannot_review_their_own_report(
    api_client_no_csrf, admin_user, manager_user, batch
):
    """A manager holding `dsr.review` who happens to be the assigned trainer
    on this exact class must still be refused."""
    from apps.sessions.services import create_session
    from apps.trainers.services import create_trainer

    manager_as_trainer = create_trainer(
        email="manager.trainer@example.test",
        first_name="Mira",
        last_name="Manager",
        actor=admin_user,
        password=TEST_PASSWORD,
        send_invitation=False,
        profile_fields={"professional_title": "Also a manager", "skills": []},
    )
    # Swap the batch's trainer for one whose *user account* is the manager,
    # so the same login is both the batch's trainer and a review-capable role.
    from apps.batches.services import update_batch

    update_batch(batch=batch, actor=admin_user, trainer=manager_as_trainer)

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
    )
    dsr = start_dsr(session=session, actor=manager_as_trainer.user)
    dsr = submit_dsr(dsr=dsr, actor=manager_as_trainer.user)

    api_client_no_csrf.force_login(manager_as_trainer.user)
    response = api_client_no_csrf.post(
        _review_url(dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_trainer_cannot_review_reports_at_all(api_client_no_csrf, trainer_profile, submitted_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_counsellor_cannot_review_reports(api_client_no_csrf, counsellor_user, submitted_dsr):
    """A counsellor holds no DSR capability at all, so `visible_dsrs` returns
    nothing for them — the report is not merely unreviewable, it does not
    exist as far as this login is concerned."""
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        _review_url(submitted_dsr), {"decision": DSRStatus.APPROVED}, format="json"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Soft deletion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_deleting_requires_a_reason(api_client_no_csrf, trainer_profile, draft_dsr):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(_delete_url(draft_dsr), {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_deleting_removes_it_from_the_list_but_all_objects_still_has_it(
    api_client_no_csrf, trainer_profile, draft_dsr
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        _delete_url(draft_dsr), {"reason": "Started for the wrong class."}, format="json"
    )
    assert response.status_code == 204

    assert not DSR.objects.filter(pk=draft_dsr.id).exists()
    assert DSR.all_objects.filter(pk=draft_dsr.id).exists()

    body = api_client_no_csrf.get(_list_url()).json()
    assert body["count"] == 0


@pytest.mark.django_db
def test_deleting_writes_a_record_deleted_audit_entry(
    api_client_no_csrf, trainer_profile, draft_dsr
):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(_delete_url(draft_dsr), {"reason": "Duplicate."}, format="json")

    entry = _last_audit(AuditAction.RECORD_DELETED)
    assert entry.resource_id == str(draft_dsr.id)


@pytest.mark.django_db
def test_restoring_a_deleted_report_brings_it_back(admin_user, draft_dsr):
    from apps.common.deletion import restore, soft_delete

    soft_delete(instance=draft_dsr, actor=admin_user, reason="Oops.")
    assert not DSR.objects.filter(pk=draft_dsr.id).exists()

    restore(instance=draft_dsr, actor=admin_user)
    assert DSR.objects.filter(pk=draft_dsr.id).exists()


@pytest.mark.django_db
def test_another_trainer_cannot_delete_this_report(
    api_client_no_csrf, trainer_profile_two, draft_dsr
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.post(
        _delete_url(draft_dsr), {"reason": "Not mine."}, format="json"
    )
    assert response.status_code == 404
    assert DSR.objects.filter(pk=draft_dsr.id).exists()


# ---------------------------------------------------------------------------
# Direct service-layer checks: transitions, validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_end_before_start_is_refused_at_the_service_layer(admin_user, past_session):
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        start_dsr(
            session=past_session,
            actor=admin_user,
            start_time=time(11, 0),
            end_time=time(9, 0),
        )


@pytest.mark.django_db
def test_review_rejects_an_unknown_decision(manager_user, submitted_dsr):
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        review_dsr(dsr=submitted_dsr, actor=manager_user, decision="withdrawn")


@pytest.mark.django_db
def test_update_ignores_fields_outside_the_writable_set(admin_user, draft_dsr):
    """`status` cannot be smuggled through the generic update path."""
    updated = update_dsr(
        dsr=draft_dsr, actor=admin_user, status=DSRStatus.APPROVED, teaching_notes="x"
    )
    assert updated.status == DSRStatus.DRAFT


@pytest.mark.django_db
def test_update_with_no_real_change_does_not_write_an_audit_entry(admin_user, draft_dsr):
    before = AuditLog.objects.filter(action=AuditAction.DSR_UPDATED).count()
    update_dsr(dsr=draft_dsr, actor=admin_user, teaching_notes=draft_dsr.teaching_notes)
    after = AuditLog.objects.filter(action=AuditAction.DSR_UPDATED).count()
    assert after == before


@pytest.mark.django_db
def test_a_trainerless_session_cannot_start_a_report(admin_user, batch):
    from apps.batches.services import update_batch
    from apps.sessions.services import create_session

    update_batch(batch=batch, actor=admin_user, trainer=None)
    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        trainer=None,
    )

    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        start_dsr(session=session, actor=admin_user)
