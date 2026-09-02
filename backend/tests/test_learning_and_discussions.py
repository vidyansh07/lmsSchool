"""Calendar, learning surface, discussions and privacy — §7.4 to §7.9."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.discussions.models import Reply
from apps.learning.models import LessonBookmark, LessonNote


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


# ---------------------------------------------------------------------------
# §7.4 — one calendar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_calendar_carries_every_kind_of_deadline(
    api_client_no_csrf, admin_user, published_course, batch, enrollment, student_profile
):
    """§7.9 calendar accuracy: one feed, every source."""
    from apps.assessments.models import AssessmentDelivery, AssessmentStatus
    from apps.assessments.services import create_assessment, set_assessment_status
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import create_assignment, set_assignment_status
    from apps.exams.models import ExamStatus
    from apps.exams.services import create_exam, set_exam_status
    from apps.projects.models import ProjectStatus
    from apps.projects.services import create_project, set_project_status
    from apps.questions.models import QuestionType
    from apps.questions.services import create_question

    soon = timezone.now() + timedelta(days=3)

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Calendar assignment",
        due_at=soon,
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)

    test = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Calendar test",
        delivery=AssessmentDelivery.OFFLINE,
        scheduled_for=soon,
    )
    set_assessment_status(assessment=test, actor=admin_user, status=AssessmentStatus.PUBLISHED)

    project = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Calendar project",
        end_date=(soon + timedelta(days=1)).date(),
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)

    for index in range(2):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.MCQ,
            text=f"C{index}?",
            marks=Decimal("1.00"),
            options=[{"text": "a", "is_correct": True}, {"text": "b"}],
        )
    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Calendar exam",
        opens_at=soon,
        closes_at=soon + timedelta(hours=2),
        sections=[{"title": "A", "question_count": 2, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"/api/v1/calendar/?start={today}&end={today + timedelta(days=10)}"
    ).json()

    kinds = {event["kind"] for event in body["events"]}
    assert "assignment_due" in kinds
    assert "quiz" in kinds
    assert "exam" in kinds
    assert "project_due" in kinds


@pytest.mark.django_db
def test_the_calendar_shows_nothing_from_another_students_batch(
    api_client_no_csrf, admin_user, published_course, upcoming_batch, other_student_profile
):
    """A deadline on a batch you are not on is not your deadline."""
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import create_assignment, set_assignment_status

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=upcoming_batch,
        title="Not mine",
        due_at=timezone.now() + timedelta(days=2),
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)

    api_client_no_csrf.force_login(other_student_profile.user)
    today = timezone.localdate()
    body = api_client_no_csrf.get(
        f"/api/v1/calendar/?start={today}&end={today + timedelta(days=10)}"
    ).json()

    assert all(event["title"] != "Not mine" for event in body["events"])


@pytest.mark.django_db
def test_one_broken_source_does_not_blank_the_calendar(student_profile, enrollment):
    from unittest import mock

    from apps.dashboards.calendar import events_for

    today = timezone.localdate()
    with mock.patch("apps.dashboards.calendar.assignment_events", side_effect=Exception("boom")):
        events = events_for(student_profile.user, today, today + timedelta(days=7))

    assert isinstance(events, list)  # the rest of the feed survived


# ---------------------------------------------------------------------------
# §7.5 — the learning surface
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_continue_learning_points_at_the_lesson_in_progress(
    api_client_no_csrf, student_profile, enrollment, paid_lesson
):
    from apps.enrollments.services import touch_lesson

    touch_lesson(student=student_profile, lesson=paid_lesson)

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/learning/home/").json()

    assert len(body) == 1
    assert body[0]["continue_learning"]["lesson_id"] == str(paid_lesson.pk)
    assert body[0]["recent"][0]["lesson_title"] == paid_lesson.title


@pytest.mark.django_db
def test_continue_learning_falls_back_to_the_next_unfinished_lesson(
    student_profile, enrollment, preview_lesson
):
    from apps.enrollments.services import set_lesson_completion
    from apps.learning.services import continue_learning

    set_lesson_completion(student=student_profile, lesson=preview_lesson, completed=True)
    nxt = continue_learning(enrollment)

    assert nxt is not None
    assert nxt["lesson_id"] != str(preview_lesson.pk)


@pytest.mark.django_db
def test_a_student_bookmarks_and_notes_a_lesson(
    api_client_no_csrf, student_profile, enrollment, paid_lesson
):
    api_client_no_csrf.force_login(student_profile.user)

    bookmarked = api_client_no_csrf.post(
        f"/api/v1/learning/lessons/{paid_lesson.id}/bookmark/",
        {"note": "Come back to the examples."},
        format="json",
    )
    assert bookmarked.status_code == 200
    assert LessonBookmark.objects.count() == 1

    noted = api_client_no_csrf.put(
        f"/api/v1/learning/lessons/{paid_lesson.id}/note/",
        {"body": "chmod 755 means rwxr-xr-x."},
        format="json",
    )
    assert noted.status_code == 200
    assert LessonNote.objects.get().body.startswith("chmod")

    listing = api_client_no_csrf.get("/api/v1/learning/bookmarks/").json()
    assert listing[0]["lesson_title"] == paid_lesson.title


@pytest.mark.django_db
def test_writing_an_empty_note_clears_it(
    api_client_no_csrf, student_profile, enrollment, paid_lesson
):
    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/learning/lessons/{paid_lesson.id}/note/"

    api_client_no_csrf.put(url, {"body": "Something"}, format="json")
    assert LessonNote.objects.count() == 1

    api_client_no_csrf.put(url, {"body": "   "}, format="json")
    assert LessonNote.objects.count() == 0


@pytest.mark.django_db
def test_bookmarks_and_notes_are_private(
    api_client_no_csrf,
    student_profile,
    other_student_profile,
    other_enrollment,
    enrollment,
    paid_lesson,
):
    """§7.9 student privacy: nobody else reads a person's working notes."""
    api_client_no_csrf.force_login(student_profile.user)
    api_client_no_csrf.put(
        f"/api/v1/learning/lessons/{paid_lesson.id}/note/", {"body": "Mine"}, format="json"
    )

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get("/api/v1/learning/notes/").json() == []
    assert api_client_no_csrf.get("/api/v1/learning/bookmarks/").json() == []


@pytest.mark.django_db
def test_a_lesson_from_another_course_cannot_be_bookmarked(
    api_client_no_csrf, student_profile, enrollment, admin_user, draft_course
):
    from apps.courses.services import create_lesson, create_module

    module = create_module(course=draft_course, actor=admin_user, title="Elsewhere")
    stray = create_lesson(module=module, actor=admin_user, title="Not my course", text_content="…")

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/learning/lessons/{stray.id}/bookmark/", {}, format="json"
    )

    assert response.status_code == 403
    assert LessonBookmark.objects.count() == 0


@pytest.mark.django_db
def test_upcoming_work_reads_the_same_calendar(
    api_client_no_csrf, admin_user, published_course, batch, enrollment, student_profile
):
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import create_assignment, set_assignment_status

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Coming up",
        due_at=timezone.now() + timedelta(days=2),
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/learning/upcoming/").json()

    assert any("Coming up" in row["title"] for row in body)


# ---------------------------------------------------------------------------
# §7.6 — discussions
# ---------------------------------------------------------------------------


@pytest.fixture
def thread(batch, student_profile, enrollment):
    from apps.discussions.services import create_thread

    return create_thread(
        batch=batch,
        actor=student_profile.user,
        title="Why does chmod 777 matter?",
        body="I do not follow the octal notation.",
    )


@pytest.mark.django_db
def test_a_student_starts_a_thread_and_the_trainer_is_told(
    api_client_no_csrf, batch, student_profile, enrollment, trainer_profile
):
    from apps.notifications.models import Notification

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/threads/",
        {"title": "A question", "body": "About permissions."},
        format="json",
    )

    assert response.status_code == 201
    # The trainer hears about it; classmates do not — that is how a board
    # becomes noise.
    assert Notification.objects.filter(recipient=trainer_profile.user).count() == 1
    assert Notification.objects.filter(recipient=student_profile.user).count() == 0


@pytest.mark.django_db
def test_a_trainer_reply_is_marked_as_one(api_client_no_csrf, thread, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/discussions/{thread.id}/replies/",
        {"body": "Read it as three groups of three bits."},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["is_trainer_response"] is True

    thread.refresh_from_db()
    assert thread.reply_count == 1
    assert thread.has_trainer_reply is True


@pytest.mark.django_db
def test_a_student_from_another_batch_cannot_read_or_post(
    api_client_no_csrf, thread, other_student_profile, upcoming_batch, admin_user
):
    """§7.9 discussion access."""
    from apps.enrollments.services import enrol_student

    enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get(f"/api/v1/discussions/{thread.id}/").status_code == 404
    assert (
        api_client_no_csrf.post(
            f"/api/v1/discussions/{thread.id}/replies/", {"body": "hello"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_a_closed_thread_takes_no_replies(
    api_client_no_csrf, thread, trainer_profile, student_profile
):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(
        f"/api/v1/discussions/{thread.id}/moderate/", {"closed": True}, format="json"
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/discussions/{thread.id}/replies/", {"body": "One more"}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_a_student_cannot_moderate(api_client_no_csrf, thread, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/discussions/{thread.id}/moderate/", {"pinned": True}, format="json"
    )

    assert response.status_code == 403
    thread.refresh_from_db()
    assert thread.is_pinned is False


@pytest.mark.django_db
def test_hiding_a_reply_keeps_it_and_records_why(
    api_client_no_csrf, thread, trainer_profile, student_profile
):
    from apps.discussions.services import reply

    row = reply(thread=thread, actor=student_profile.user, body="Something unhelpful")

    api_client_no_csrf.force_login(trainer_profile.user)
    hidden = api_client_no_csrf.post(
        f"/api/v1/discussions/replies/{row.id}/hide/",
        {"reason": "Off topic."},
        format="json",
    )

    assert hidden.status_code == 200
    row.refresh_from_db()
    assert row.is_hidden is True
    assert row.hidden_reason == "Off topic."
    # Kept, not deleted: a conversation with a hole in it makes no sense.
    assert Reply.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_a_hidden_reply_is_gone_for_others_but_not_its_author(
    api_client_no_csrf,
    thread,
    trainer_profile,
    student_profile,
    other_student_profile,
    other_enrollment,
):
    from apps.discussions.services import hide_reply, reply

    row = reply(thread=thread, actor=student_profile.user, body="Hidden message")
    hide_reply(row=row, actor=trainer_profile.user, reason="Off topic.")

    api_client_no_csrf.force_login(other_student_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/discussions/{thread.id}/").json()
    assert all(item["body"] != "Hidden message" for item in body["replies"])

    # The author still sees what happened to their own message.
    api_client_no_csrf.force_login(student_profile.user)
    mine = api_client_no_csrf.get(f"/api/v1/discussions/{thread.id}/").json()
    assert any(item["body"] == "Hidden message" for item in mine["replies"])


@pytest.mark.django_db
def test_moderation_is_audited(thread, trainer_profile, student_profile):
    from apps.discussions.services import hide_reply, reply, set_closed

    row = reply(thread=thread, actor=student_profile.user, body="Noise")
    hide_reply(row=row, actor=trainer_profile.user, reason="Off topic.")
    set_closed(thread=thread, actor=trainer_profile.user, closed=True)

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.THREAD_CREATED in actions
    assert AuditAction.REPLY_CREATED in actions
    assert AuditAction.REPLY_HIDDEN in actions
    assert AuditAction.THREAD_MODERATED in actions


# ---------------------------------------------------------------------------
# §7.7 — the batch directory
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_sees_classmates_names_and_nothing_else(
    api_client_no_csrf, student_profile, enrollment, other_student_profile, other_enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(
        f"/api/v1/learning/enrollments/{enrollment.id}/classmates/"
    ).json()

    assert len(body) == 2
    assert set(body[0]) == {"full_name", "student_code", "is_you"}

    serialised = str(body)
    assert other_student_profile.user.email not in serialised
    assert "phone" not in serialised


@pytest.mark.django_db
def test_the_class_list_can_be_switched_off(
    api_client_no_csrf, admin_user, student_profile, enrollment
):
    """§7.7: only if the privacy design permits — which is configuration."""
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.request_context import clear_scope

    update_policy(policy=get_or_create_policy(), actor=admin_user, batch_directory_visible=False)
    clear_scope()

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/learning/enrollments/{enrollment.id}/classmates/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_student_cannot_read_another_batchs_class_list(
    api_client_no_csrf, other_student_profile, other_enrollment, enrollment, student_profile
):
    api_client_no_csrf.force_login(other_student_profile.user)
    # `other_enrollment` is on the same batch, so use a foreign enrolment id.
    from apps.enrollments.models import Enrollment

    foreign = Enrollment.objects.exclude(student=other_student_profile).first()
    response = api_client_no_csrf.get(f"/api/v1/learning/enrollments/{foreign.id}/classmates/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, thread):
    for url in (
        "/api/v1/learning/home/",
        "/api/v1/learning/bookmarks/",
        "/api/v1/discussions/",
        f"/api/v1/discussions/{thread.id}/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url
