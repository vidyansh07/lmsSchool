"""The class report after class: drafts when the class ends, the reminder
and the overdue notice; lessons covered, homework, student notes, files and
the institution's own questions; the class it syncs back to; attendance
locking; what students see; the batch summary and export; and the three
class-report automation triggers.

No manager approval: a submitted report is done (the owner's call, 3 October
2026).
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.automation import services as automation_services
from apps.automation.models import AutomationRule, AutomationRun, AutomationRunStatus
from apps.common.exceptions import ApplicationError, ConflictError
from apps.dsr import services
from apps.dsr.models import DSR, DSRStatus
from apps.notifications.models import Notification, NotificationKind
from apps.sessions.models import TopicStatus

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _pause_seeded_rules(db):
    AutomationRule.objects.update(status="paused")


@pytest.fixture
def ended_session(admin_user, batch, schedule):
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
def course_lessons(published_course):
    from apps.courses.models import Lesson

    return list(Lesson.objects.filter(module__course=published_course).order_by("position")[:2])


def _draft(session, actor):
    return services.start_dsr(session=session, actor=actor)


# ---------------------------------------------------------------------------
# After class
# ---------------------------------------------------------------------------


def test_the_sweep_drafts_reminds_and_reports_overdue_once(
    ended_session, trainer_profile, manager_user
):
    ends = ended_session.ends_at

    counts = services.sweep_after_class(now=ends + timedelta(minutes=5))
    assert counts["drafted"] == 1
    dsr = DSR.objects.get(session=ended_session)
    assert dsr.status == DSRStatus.DRAFT
    assert dsr.due_at == ends + timedelta(hours=4)
    assert Notification.objects.filter(
        recipient=trainer_profile.user, kind=NotificationKind.DSR_DUE
    ).exists()

    # Nothing new before the reminder is due; once after it is.
    assert services.sweep_after_class(now=ends + timedelta(hours=1))["reminded"] == 0
    assert services.sweep_after_class(now=ends + timedelta(hours=2, minutes=1))["reminded"] == 1
    assert services.sweep_after_class(now=ends + timedelta(hours=3))["reminded"] == 0

    # Overdue: the centre's manager is told once.
    assert services.sweep_after_class(now=ends + timedelta(hours=4, minutes=1))["overdue"] == 1
    assert services.sweep_after_class(now=ends + timedelta(hours=5))["overdue"] == 0
    assert (
        Notification.objects.filter(
            recipient=manager_user, kind=NotificationKind.DSR_OVERDUE
        ).count()
        == 1
    )


def test_the_sweep_leaves_old_and_upcoming_classes_alone(ended_session):
    # A day and more after the class: outside the look-back window.
    assert (
        services.sweep_after_class(now=ended_session.ends_at + timedelta(hours=30))["drafted"] == 0
    )
    # Before the class ends.
    assert (
        services.sweep_after_class(now=ended_session.ends_at - timedelta(minutes=5))["drafted"] == 0
    )
    assert not DSR.objects.filter(session=ended_session).exists()


def test_a_submitted_report_is_done_without_approval(ended_session, trainer_profile):
    dsr = services.submit_dsr(
        dsr=_draft(ended_session, trainer_profile.user), actor=trainer_profile.user
    )
    assert dsr.status == DSRStatus.SUBMITTED
    assert dsr.is_done is True
    # And it no longer counts as overdue or reminded.
    counts = services.sweep_after_class(now=ended_session.ends_at + timedelta(hours=5))
    assert counts == {"drafted": 0, "reminded": 0, "overdue": 0}


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def test_lessons_notes_and_homework_sync_back_to_the_class(
    ended_session, trainer_profile, enrollment, course_lessons
):
    dsr = _draft(ended_session, trainer_profile.user)
    actor = trainer_profile.user
    services.update_dsr(
        dsr=dsr,
        actor=actor,
        actual_topic="Permissions and ownership",
        topic_status="in_progress",
        homework="Practise chmod on the lab VM",
        homework_due_on=timezone.localdate() + timedelta(days=2),
    )
    services.set_details(
        dsr=dsr,
        actor=actor,
        lessons_covered=[lesson.pk for lesson in course_lessons],
        student_notes=[
            {"enrollment": str(enrollment.pk), "flag": "needs_attention", "note": "Lost in labs"}
        ],
    )
    services.submit_dsr(dsr=dsr, actor=actor)

    ended_session.refresh_from_db()
    assert ended_session.topic == "Permissions and ownership"
    assert ended_session.topic_status == TopicStatus.IN_PROGRESS
    assert ended_session.actual_lesson_id == course_lessons[0].pk
    assert dsr.student_notes.get().flag == "needs_attention"


def test_details_refuse_what_does_not_belong(ended_session, trainer_profile, admin_user):
    dsr = _draft(ended_session, trainer_profile.user)
    with pytest.raises(ApplicationError):
        services.set_details(
            dsr=dsr,
            actor=trainer_profile.user,
            lessons_covered=["00000000-0000-0000-0000-000000000000"],
        )
    with pytest.raises(ApplicationError):
        services.set_details(
            dsr=dsr,
            actor=trainer_profile.user,
            student_notes=[{"enrollment": "00000000-0000-0000-0000-000000000000", "flag": "doubt"}],
        )
    with pytest.raises(ApplicationError):
        services.update_dsr(dsr=dsr, actor=trainer_profile.user, topic_status="half")


def test_attachments_are_the_uploaders_own(ended_session, trainer_profile, admin_user, pdf_bytes):
    from apps.forms.services import create_upload

    dsr = _draft(ended_session, trainer_profile.user)
    mine = create_upload(
        actor=trainer_profile.user,
        uploaded_file=SimpleUploadedFile("notes.pdf", pdf_bytes, content_type="application/pdf"),
    )
    theirs = create_upload(
        actor=admin_user,
        uploaded_file=SimpleUploadedFile("other.pdf", pdf_bytes, content_type="application/pdf"),
    )
    services.set_details(
        dsr=dsr,
        actor=trainer_profile.user,
        attachments=[{"upload": str(mine.pk), "caption": "Notes"}],
    )
    assert dsr.attachments.get().caption == "Notes"
    with pytest.raises(ApplicationError):
        services.set_details(
            dsr=dsr, actor=trainer_profile.user, attachments=[{"upload": str(theirs.pk)}]
        )


def test_the_institutions_extra_questions_are_asked_and_checked(
    ended_session, trainer_profile, admin_user
):
    from apps.forms import services as form_services
    from apps.forms.models import FormDefinition, FormVersionStatus

    definition = FormDefinition.objects.get(slug="dsr-extra")
    draft = form_services.create_draft_version(
        actor=admin_user,
        definition=definition,
        cloned_from=definition.versions.get(status=FormVersionStatus.PUBLISHED),
    )
    form_services.set_fields(
        actor=admin_user,
        version=draft,
        fields=[
            {"key": "lab_ready", "label": "Lab ready on time", "type": "boolean", "required": True}
        ],
    )
    form_services.publish_version(actor=admin_user, version=draft)

    dsr = _draft(ended_session, trainer_profile.user)
    assert dsr.form_version_id == draft.pk
    with pytest.raises(ApplicationError):
        services.submit_dsr(dsr=dsr, actor=trainer_profile.user)
    services.update_dsr(dsr=dsr, actor=trainer_profile.user, extra_answers={"lab_ready": True})
    assert services.submit_dsr(dsr=dsr, actor=trainer_profile.user).extra_answers == {
        "lab_ready": True
    }


# ---------------------------------------------------------------------------
# Attendance lock
# ---------------------------------------------------------------------------


def test_attendance_locks_for_the_trainer_once_submitted(
    ended_session, trainer_profile, manager_user, enrollment
):
    from apps.attendance.services import mark_attendance

    entries = [{"enrollment_id": str(enrollment.pk), "status": "present"}]
    mark_attendance(session=ended_session, actor=trainer_profile.user, entries=entries)
    services.submit_dsr(dsr=_draft(ended_session, trainer_profile.user), actor=trainer_profile.user)

    with pytest.raises(ConflictError):
        mark_attendance(
            session=ended_session,
            actor=trainer_profile.user,
            entries=[{"enrollment_id": str(enrollment.pk), "status": "absent"}],
        )
    # A manager still can.
    mark_attendance(
        session=ended_session,
        actor=manager_user,
        entries=[{"enrollment_id": str(enrollment.pk), "status": "absent"}],
    )


def test_the_register_tells_the_trainer_it_is_locked(
    api_client_no_csrf, ended_session, trainer_profile, manager_user
):
    url = f"/api/v1/sessions/{ended_session.pk}/register/"
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(url).json()["can_mark"] is True

    services.submit_dsr(dsr=_draft(ended_session, trainer_profile.user), actor=trainer_profile.user)
    assert api_client_no_csrf.get(url).json()["can_mark"] is False

    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.get(url).json()["can_mark"] is True


def test_a_report_without_a_lesson_does_not_mark_the_class_finished(ended_session, trainer_profile):
    ended_session.topic_status = TopicStatus.SKIPPED
    ended_session.save(update_fields=["topic_status"])
    dsr = _draft(ended_session, trainer_profile.user)
    services.update_dsr(dsr=dsr, actor=trainer_profile.user, topic_status="completed")
    services.submit_dsr(dsr=dsr, actor=trainer_profile.user)
    ended_session.refresh_from_db()
    assert ended_session.topic_status == TopicStatus.SKIPPED
    assert ended_session.actual_lesson_id is None


def test_submitting_keeps_the_lesson_the_trainer_named(
    ended_session, trainer_profile, course_lessons
):
    first, second = course_lessons
    ended_session.actual_lesson = second
    ended_session.save(update_fields=["actual_lesson"])
    dsr = _draft(ended_session, trainer_profile.user)
    services.set_details(dsr=dsr, actor=trainer_profile.user, lessons_covered=[first.pk, second.pk])
    services.submit_dsr(dsr=dsr, actor=trainer_profile.user)
    ended_session.refresh_from_db()
    assert ended_session.actual_lesson_id == second.pk


# ---------------------------------------------------------------------------
# API: students, missing, summary, export
# ---------------------------------------------------------------------------


def test_a_student_sees_what_was_covered_and_the_homework_only(
    api_client_no_csrf, ended_session, trainer_profile, enrollment
):
    dsr = _draft(ended_session, trainer_profile.user)
    services.update_dsr(
        dsr=dsr,
        actor=trainer_profile.user,
        actual_topic="Permissions",
        homework="Read chapter 4",
        teaching_notes="Private: two students struggled",
    )
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get("/api/v1/dsr/mine/").json()["count"] == 0  # draft: not yet

    services.submit_dsr(dsr=dsr, actor=trainer_profile.user)
    body = api_client_no_csrf.get("/api/v1/dsr/mine/").json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["topic"] == "Permissions"
    assert row["homework"] == "Read chapter 4"
    assert "teaching_notes" not in row
    assert "issues" not in row


def test_missing_summary_and_export(
    api_client_no_csrf, ended_session, manager_user, batch, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    missing = api_client_no_csrf.get("/api/v1/dsr/missing/").json()
    assert [row["session"] for row in missing] == [str(ended_session.pk)]

    summary = api_client_no_csrf.get(f"/api/v1/batches/{batch.pk}/dsr-summary/").json()
    assert summary["counts"]["missing"] == 1
    assert summary["classes"][0]["state"] == "missing"

    dsr = _draft(ended_session, trainer_profile.user)
    services.update_dsr(dsr=dsr, actor=trainer_profile.user, issues='=HYPERLINK("x")')
    services.submit_dsr(dsr=dsr, actor=trainer_profile.user)
    summary = api_client_no_csrf.get(f"/api/v1/batches/{batch.pk}/dsr-summary/").json()
    assert summary["classes"][0]["state"] == "submitted"
    assert summary["counts"]["submitted"] == 1
    assert api_client_no_csrf.get("/api/v1/dsr/missing/").json() == []

    export = api_client_no_csrf.get(f"/api/v1/batches/{batch.pk}/dsr-export/")
    assert export.status_code == 200
    text = export.content.decode()
    assert "Filesystem basics" in text
    assert "'=HYPERLINK" in text  # neutralised, never a live formula


def test_students_are_refused_the_staff_lists(api_client_no_csrf, enrollment, batch):
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get("/api/v1/dsr/missing/").status_code == 403
    assert api_client_no_csrf.get(f"/api/v1/batches/{batch.pk}/dsr-summary/").status_code == 403


def test_saving_details_through_the_api(
    api_client_no_csrf, ended_session, trainer_profile, enrollment, course_lessons
):
    api_client_no_csrf.force_login(trainer_profile.user)
    created = api_client_no_csrf.post(
        f"/api/v1/sessions/{ended_session.pk}/dsr/",
        {
            "lessons_covered": [str(course_lessons[0].pk)],
            "student_notes": [
                {"enrollment": str(enrollment.pk), "flag": "did_well", "note": "Great"}
            ],
            "homework": "Lab 3",
            "topic_status": "completed",
            "submit": True,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["status"] == "submitted"
    assert body["is_done"] is True
    assert [lesson["id"] for lesson in body["lessons_covered"]] == [str(course_lessons[0].pk)]
    assert body["student_notes"][0]["flag"] == "did_well"


# ---------------------------------------------------------------------------
# Automation
# ---------------------------------------------------------------------------


def test_class_report_triggers(admin_user, ended_session, trainer_profile, enrollment):
    from apps.automation.models import AutomationTrigger
    from apps.dsr.models import DSRStudentNote
    from apps.work.models import Activity

    submitted_rule = automation_services.create_rule(
        actor=admin_user,
        name="Thank the trainer",
        trigger="DSR_SUBMITTED",
        conditions=[{"path": "dsr.homework_given", "op": "eq", "value": True}],
        actions=[
            {
                "type": "send_notification",
                "params": {
                    "to": "dsr_trainer",
                    "kind": "dsr.due",
                    "title": "Thanks for {{dsr.batch_code}}",
                },
            }
        ],
        status="active",
    )
    flagged_rule = automation_services.create_rule(
        actor=admin_user,
        name="Counsel flagged",
        trigger="DSR_STUDENT_FLAGGED",
        conditions=[{"path": "note.flag", "op": "eq", "value": "needs_attention"}],
        actions=[
            {
                "type": "create_activity",
                "params": {"type": "counselling", "assign_to": "creator", "due_in_days": 2},
            }
        ],
        status="active",
    )
    dsr = _draft(ended_session, trainer_profile.user)
    services.update_dsr(dsr=dsr, actor=trainer_profile.user, homework="Lab 3")
    services.set_details(
        dsr=dsr,
        actor=trainer_profile.user,
        student_notes=[
            {"enrollment": str(enrollment.pk), "flag": "needs_attention", "note": "Behind"}
        ],
    )
    services.submit_dsr(dsr=dsr, actor=trainer_profile.user)

    automation_services.dispatch(AutomationTrigger.DSR_SUBMITTED, dsr)
    assert AutomationRun.objects.get(rule=submitted_rule).status == AutomationRunStatus.RAN
    assert Notification.objects.filter(
        recipient=trainer_profile.user, title=f"Thanks for {ended_session.batch.code}"
    ).exists()

    note = DSRStudentNote.objects.get(dsr=dsr)
    automation_services.dispatch(AutomationTrigger.DSR_STUDENT_FLAGGED, note)
    run = AutomationRun.objects.get(rule=flagged_rule)
    assert run.status == AutomationRunStatus.RAN, run.result
    assert Activity.objects.filter(student=enrollment.student, automation_run=run).exists()


def test_seeded_class_report_rule_is_a_draft_and_well_formed():
    rule = AutomationRule.objects.get(name="Counselling for a student flagged in class")
    automation_services._validate_rule_shape(rule.trigger, rule.conditions, rule.actions)
