"""Planned-versus-actual course timeline tracking.

`ClassSession.planned_lesson` / `actual_lesson` are the link nothing else in
the schedule provides: a free-text `topic` cannot be compared against a
curriculum position, so before this there was no way to answer "is this batch
ahead of or behind its curriculum?". These tests cover the three pieces that
make that answerable — planning and recording a topic, the `autoplan_batch`
bulk action, and `timeline_progress`'s arithmetic — plus the authorization
rule that ties recording to whoever actually teaches the class.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.batches.services import create_batch
from apps.courses import services as course_services
from apps.courses.models import Lesson, LessonContentType, PublishStatus
from apps.progress.reports import timeline_progress
from apps.sessions.models import ClassSession, SessionStatus, TopicStatus
from apps.sessions.services import (
    autoplan_batch,
    create_session,
    plan_session_topic,
    record_session_topic,
    reschedule_session,
    set_session_status,
)

pytestmark = pytest.mark.django_db

SESSIONS_URL = "/api/v1/sessions/"


def _topic_url(session) -> str:
    return f"{SESSIONS_URL}{session.id}/topic/"


def _timeline_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/timeline/"


def _autoplan_url(batch) -> str:
    return f"/api/v1/batches/{batch.id}/timeline/autoplan/"


def _add_session(batch, actor, day, **kwargs):
    return create_session(
        batch=batch,
        actor=actor,
        session_date=day,
        start_time=kwargs.pop("start_time", time(9, 0)),
        end_time=kwargs.pop("end_time", time(11, 0)),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# A richer course than `published_course`, for curriculum-order tests: two
# published modules, two published lessons each, in a known order.
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_course(admin_user, category):
    course = course_services.create_course(
        actor=admin_user,
        title="Python Bootcamp",
        category=category,
        short_description="A course with real curriculum order.",
    )
    basics = course_services.create_module(
        course=course, actor=admin_user, title="Basics", status=PublishStatus.PUBLISHED
    )
    advanced = course_services.create_module(
        course=course, actor=admin_user, title="Advanced", status=PublishStatus.PUBLISHED
    )
    titles_by_module = [
        (basics, "Variables"),
        (basics, "Loops"),
        (advanced, "Decorators"),
        (advanced, "Generators"),
    ]
    for module, title in titles_by_module:
        course_services.create_lesson(
            module=module,
            actor=admin_user,
            title=title,
            content_type=LessonContentType.TEXT,
            text_content=f"Content for {title}.",
            status=PublishStatus.PUBLISHED,
        )
    course_services.set_course_status(
        course=course, target=PublishStatus.PUBLISHED, actor=admin_user, may_publish=True
    )
    course.refresh_from_db()
    return course


@pytest.fixture
def rich_lessons(rich_course) -> list[Lesson]:
    """The course's lessons, in curriculum order."""
    return list(
        Lesson.objects.filter(module__course=rich_course).order_by("module__position", "position")
    )


@pytest.fixture
def rich_batch(admin_user, rich_course, trainer_profile):
    """A batch on `rich_course`, running from a week ago to sixty days out."""
    today = timezone.localdate()
    return create_batch(
        actor=admin_user,
        name="Python Bootcamp — Batch 1",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=7),
        end_date=today + timedelta(days=63),
        capacity=5,
    )


# ---------------------------------------------------------------------------
# Planning and recording — the services
# ---------------------------------------------------------------------------


def test_plan_session_topic_sets_planned_lesson(admin_user, batch, preview_lesson):
    session = _add_session(batch, admin_user, batch.start_date)
    plan_session_topic(session=session, actor=admin_user, lesson=preview_lesson)

    session.refresh_from_db()
    assert session.planned_lesson_id == preview_lesson.pk


def test_plan_session_topic_is_audited(admin_user, batch, preview_lesson):
    session = _add_session(batch, admin_user, batch.start_date)
    plan_session_topic(session=session, actor=admin_user, lesson=preview_lesson)

    entry = AuditLog.objects.filter(action=AuditAction.SESSION_TOPIC_PLANNED).first()
    assert entry is not None
    assert entry.context["lesson_id"] == str(preview_lesson.pk)
    assert entry.context["batch_code"] == batch.code


def test_record_session_topic_sets_actual_lesson_and_status(admin_user, batch, paid_lesson):
    session = _add_session(batch, admin_user, batch.start_date)
    record_session_topic(
        session=session, actor=admin_user, lesson=paid_lesson, status=TopicStatus.COMPLETED
    )

    session.refresh_from_db()
    assert session.actual_lesson_id == paid_lesson.pk
    assert session.topic_status == TopicStatus.COMPLETED


def test_record_session_topic_is_audited(admin_user, batch, paid_lesson):
    session = _add_session(batch, admin_user, batch.start_date)
    record_session_topic(session=session, actor=admin_user, lesson=paid_lesson)

    entry = AuditLog.objects.filter(action=AuditAction.SESSION_TOPIC_RECORDED).first()
    assert entry is not None
    assert entry.context["lesson_id"] == str(paid_lesson.pk)
    assert entry.context["topic_status"] == TopicStatus.COMPLETED


def test_recording_a_skipped_topic_needs_no_lesson(admin_user, batch):
    """A skipped class covered nothing — forcing a lesson would misdescribe it."""
    session = _add_session(batch, admin_user, batch.start_date)
    record_session_topic(session=session, actor=admin_user, lesson=None, status=TopicStatus.SKIPPED)

    session.refresh_from_db()
    assert session.actual_lesson_id is None
    assert session.topic_status == TopicStatus.SKIPPED


def test_the_free_text_topic_field_is_unaffected(admin_user, batch, paid_lesson):
    """Planning and recording are additive — the trainer's own note still works."""
    session = _add_session(batch, admin_user, batch.start_date, topic="Covered permissions")
    record_session_topic(session=session, actor=admin_user, lesson=paid_lesson)

    session.refresh_from_db()
    assert session.topic == "Covered permissions"
    assert session.actual_lesson_id == paid_lesson.pk


# ---------------------------------------------------------------------------
# Recording a topic — the API and its authorization
# ---------------------------------------------------------------------------


def test_admin_can_record_a_topic_via_the_api(api_client_no_csrf, admin_user, batch, paid_lesson):
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _topic_url(session),
        {"lesson_id": str(paid_lesson.pk), "status": "completed"},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actual_lesson_id"] == str(paid_lesson.pk)
    assert body["actual_lesson_title"] == paid_lesson.title
    assert body["topic_status"] == "completed"


def test_trainer_can_record_a_topic_for_their_own_batch(
    api_client_no_csrf, admin_user, batch, trainer_profile, paid_lesson
):
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(trainer_profile.user)

    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(paid_lesson.pk)}, format="json"
    )
    assert response.status_code == 200


def test_trainer_cannot_record_a_topic_for_an_unrelated_batch(
    api_client_no_csrf,
    admin_user,
    upcoming_batch,
    trainer_profile,
    trainer_profile_two,
    published_course,
):
    """A trainer holding a session id for somebody else's class gets nothing."""
    session = _add_session(upcoming_batch, admin_user, upcoming_batch.start_date)
    api_client_no_csrf.force_login(trainer_profile.user)

    response = api_client_no_csrf.post(_topic_url(session), {}, format="json")
    assert response.status_code == 404


def test_session_manage_any_overrides_for_recording(
    api_client_no_csrf, manager_user, batch, paid_lesson
):
    """The override is a distinct capability, held by managers and admins."""
    session = _add_session(batch, manager_user, batch.start_date)
    api_client_no_csrf.force_login(manager_user)

    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(paid_lesson.pk)}, format="json"
    )
    assert response.status_code == 200


def test_a_student_is_refused_recording_a_topic(
    api_client_no_csrf, admin_user, batch, enrollment, paid_lesson
):
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(enrollment.student.user)

    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(paid_lesson.pk)}, format="json"
    )
    assert response.status_code == 403


def test_batch_manage_schedule_does_not_imply_topic_management(
    api_client_no_csrf, admin_user, counsellor_user, batch, paid_lesson
):
    """A counsellor may manage a batch's timetable but not its curriculum record.

    `SESSION_MANAGE_ANY` is deliberately a different capability from
    `BATCH_MANAGE_SCHEDULE` — see `apps.sessions.access.can_manage_topic`.
    A counsellor holds the latter and not the former.
    """
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(counsellor_user)

    # The counsellor can see the session (BATCH_VIEW_ANY)...
    assert api_client_no_csrf.get(f"{SESSIONS_URL}{session.id}/").status_code == 200
    # ...but not record its topic.
    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(paid_lesson.pk)}, format="json"
    )
    assert response.status_code == 403


def test_anonymous_callers_are_refused_recording_a_topic(api_client_no_csrf, admin_user, batch):
    session = _add_session(batch, admin_user, batch.start_date)
    response = api_client_no_csrf.post(_topic_url(session), {}, format="json")
    assert response.status_code in (401, 403)


def test_recording_a_lesson_from_another_course_is_refused(
    api_client_no_csrf, admin_user, batch, rich_lessons
):
    """A lesson has to belong to the batch's own course."""
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(rich_lessons[0].pk)}, format="json"
    )
    assert response.status_code == 404


def test_recording_an_invalid_status_is_rejected(
    api_client_no_csrf, admin_user, batch, paid_lesson
):
    session = _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        _topic_url(session), {"lesson_id": str(paid_lesson.pk), "status": "not-a-status"}
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Autoplan
# ---------------------------------------------------------------------------


def test_autoplan_assigns_lessons_in_curriculum_order(admin_user, rich_batch, rich_lessons):
    for offset in range(4):
        _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset * 2))

    autoplan_batch(batch=rich_batch, actor=admin_user)

    sessions = list(
        ClassSession.objects.filter(batch=rich_batch).order_by("session_date", "start_time")
    )
    assert [session.planned_lesson_id for session in sessions] == [
        lesson.pk for lesson in rich_lessons
    ]


def test_autoplan_is_idempotent(admin_user, rich_batch, rich_lessons):
    for offset in range(4):
        _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset * 2))

    first = autoplan_batch(batch=rich_batch, actor=admin_user)
    before = list(
        ClassSession.objects.filter(batch=rich_batch)
        .order_by("session_date")
        .values_list("planned_lesson_id", flat=True)
    )

    second = autoplan_batch(batch=rich_batch, actor=admin_user)
    after = list(
        ClassSession.objects.filter(batch=rich_batch)
        .order_by("session_date")
        .values_list("planned_lesson_id", flat=True)
    )

    assert first["planned"] == 4
    assert second["planned"] == 0
    assert before == after


def test_autoplan_skips_sessions_that_already_have_a_plan(admin_user, rich_batch, rich_lessons):
    sessions = [
        _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset * 2))
        for offset in range(3)
    ]
    # Hand-plan the first session with the *second* lesson, out of order.
    plan_session_topic(session=sessions[0], actor=admin_user, lesson=rich_lessons[1])

    autoplan_batch(batch=rich_batch, actor=admin_user)

    sessions[0].refresh_from_db()
    sessions[1].refresh_from_db()
    sessions[2].refresh_from_db()
    # The hand-made plan survives...
    assert sessions[0].planned_lesson_id == rich_lessons[1].pk
    # ...and the lesson it used is not handed to anybody else.
    remaining_plans = {sessions[1].planned_lesson_id, sessions[2].planned_lesson_id}
    assert rich_lessons[1].pk not in remaining_plans
    assert remaining_plans == {rich_lessons[0].pk, rich_lessons[2].pk}


def test_autoplan_never_assigns_draft_or_unpublished_lessons(admin_user, category, trainer_profile):
    course = course_services.create_course(
        actor=admin_user,
        title="Half-finished course",
        category=category,
        description="A course with one draft lesson still being written.",
    )
    module = course_services.create_module(
        course=course, actor=admin_user, title="Module one", status=PublishStatus.PUBLISHED
    )
    published_lesson = course_services.create_lesson(
        module=module,
        actor=admin_user,
        title="Ready",
        content_type=LessonContentType.TEXT,
        text_content="Ready to teach.",
        status=PublishStatus.PUBLISHED,
    )
    course_services.create_lesson(
        module=module,
        actor=admin_user,
        title="Still being written",
        content_type=LessonContentType.TEXT,
        text_content="Not ready.",
        status=PublishStatus.DRAFT,
    )
    course_services.set_course_status(
        course=course, target=PublishStatus.PUBLISHED, actor=admin_user, may_publish=True
    )

    today = timezone.localdate()
    draft_batch = create_batch(
        actor=admin_user,
        name="Half-finished — Batch",
        course=course,
        trainer=trainer_profile,
        start_date=today,
        end_date=today + timedelta(days=30),
        capacity=5,
    )
    sessions = [
        _add_session(draft_batch, admin_user, today + timedelta(days=offset)) for offset in range(2)
    ]

    result = autoplan_batch(batch=draft_batch, actor=admin_user)

    assert result["lessons_total"] == 1
    assert result["planned"] == 1
    sessions[0].refresh_from_db()
    sessions[1].refresh_from_db()
    planned = {sessions[0].planned_lesson_id, sessions[1].planned_lesson_id}
    assert planned == {published_lesson.pk, None}


def test_autoplan_does_not_consume_a_lesson_for_a_cancelled_class(
    admin_user, rich_batch, rich_lessons
):
    sessions = [
        _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset * 2))
        for offset in range(2)
    ]
    set_session_status(
        session=sessions[0], target=SessionStatus.CANCELLED, actor=admin_user, reason="Holiday"
    )

    autoplan_batch(batch=rich_batch, actor=admin_user)

    sessions[0].refresh_from_db()
    sessions[1].refresh_from_db()
    assert sessions[0].planned_lesson_id is None
    # The surviving class gets the first lesson, not the second.
    assert sessions[1].planned_lesson_id == rich_lessons[0].pk


def test_autoplan_does_not_plan_the_superseded_half_of_a_reschedule(
    admin_user, rich_batch, rich_lessons
):
    original = _add_session(rich_batch, admin_user, rich_batch.start_date)
    reschedule_session(
        session=original,
        actor=admin_user,
        new_date=rich_batch.start_date + timedelta(days=1),
        new_start=time(14, 0),
        new_end=time(16, 0),
    )

    autoplan_batch(batch=rich_batch, actor=admin_user)

    original.refresh_from_db()
    replacement = ClassSession.objects.get(rescheduled_from=original)
    assert original.planned_lesson_id is None
    assert replacement.planned_lesson_id == rich_lessons[0].pk


def test_autoplan_leaves_extra_sessions_unplanned_when_lessons_run_out(
    admin_user, batch, published_course
):
    """`published_course` has exactly two published lessons."""
    sessions = [
        _add_session(batch, admin_user, batch.start_date + timedelta(days=offset))
        for offset in range(3)
    ]

    result = autoplan_batch(batch=batch, actor=admin_user)

    assert result["lessons_total"] == 2
    assert result["planned"] == 2
    assert result["unplanned_remaining"] == 1
    planned_count = sum(
        1 for s in sessions if ClassSession.objects.get(pk=s.pk).planned_lesson_id is not None
    )
    assert planned_count == 2


def test_autoplan_via_the_api(api_client_no_csrf, admin_user, rich_batch, rich_lessons):
    for offset in range(2):
        _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset))
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(_autoplan_url(rich_batch))
    assert response.status_code == 200
    body = response.json()
    assert body["planned"] == 2
    assert body["lessons_total"] == 4


def test_trainer_can_autoplan_their_own_batch(
    api_client_no_csrf, admin_user, rich_batch, trainer_profile
):
    _add_session(rich_batch, admin_user, rich_batch.start_date)
    api_client_no_csrf.force_login(trainer_profile.user)

    response = api_client_no_csrf.post(_autoplan_url(rich_batch))
    assert response.status_code == 200


def test_a_student_cannot_autoplan_a_batch(api_client_no_csrf, admin_user, batch, enrollment):
    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.post(_autoplan_url(batch))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# timeline_progress — the arithmetic
# ---------------------------------------------------------------------------


def test_timeline_progress_with_no_sessions_returns_none_and_not_started(batch):
    result = timeline_progress(batch)

    assert result["sessions_total"] == 0
    assert result["percent_complete"] is None
    assert result["percent_expected"] is None
    assert result["variance_percent"] is None
    assert result["status"] == "not_started"


def test_timeline_progress_on_a_course_with_no_lessons_returns_none_and_not_started(
    admin_user, category, trainer_profile
):
    empty_course = course_services.create_course(
        actor=admin_user, title="Empty course", category=category
    )
    course_services.create_module(
        course=empty_course, actor=admin_user, title="Module", status=PublishStatus.DRAFT
    )
    # Kept in review, not published: a course with no published lessons cannot
    # be published, and the point of this fixture is to have no published
    # content at all. (A batch may run any course that is not archived.)
    course_services.set_course_status(
        course=empty_course, target=PublishStatus.IN_REVIEW, actor=admin_user, may_publish=False
    )
    today = timezone.localdate()
    empty_batch = create_batch(
        actor=admin_user,
        name="Empty course batch",
        course=empty_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=25),
        capacity=5,
    )
    _add_session(empty_batch, admin_user, today - timedelta(days=1))

    result = timeline_progress(empty_batch)

    assert result["course_lessons_total"] == 0
    assert result["percent_complete"] is None
    assert result["percent_expected"] is None
    assert result["variance_percent"] is None
    assert result["status"] == "not_started"


def test_timeline_progress_on_a_batch_that_has_not_started(admin_user, upcoming_batch):
    _add_session(upcoming_batch, admin_user, upcoming_batch.start_date)

    result = timeline_progress(upcoming_batch)

    assert result["percent_expected"] is None
    assert result["status"] == "not_started"


def test_timeline_progress_next_lesson_is_the_first_uncovered_one(
    admin_user, rich_batch, rich_lessons
):
    session = _add_session(rich_batch, admin_user, rich_batch.start_date)
    record_session_topic(session=session, actor=admin_user, lesson=rich_lessons[0])

    result = timeline_progress(rich_batch)

    assert result["next_lesson"]["id"] == str(rich_lessons[1].pk)
    assert result["next_lesson"]["title"] == rich_lessons[1].title


def test_timeline_progress_next_lesson_is_none_when_everything_is_covered(
    admin_user, rich_batch, rich_lessons
):
    for offset, lesson in enumerate(rich_lessons):
        session = _add_session(
            rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset)
        )
        record_session_topic(session=session, actor=admin_user, lesson=lesson)

    result = timeline_progress(rich_batch)
    assert result["next_lesson"] is None
    assert result["lessons_covered"] == 4
    assert result["percent_complete"] == 100


def test_timeline_progress_ignores_non_completed_recordings_as_coverage(
    admin_user, rich_batch, rich_lessons
):
    """Recording a lesson as `in_progress` is not the same as covering it."""
    session = _add_session(rich_batch, admin_user, rich_batch.start_date)
    record_session_topic(
        session=session, actor=admin_user, lesson=rich_lessons[0], status=TopicStatus.IN_PROGRESS
    )

    result = timeline_progress(rich_batch)
    assert result["lessons_covered"] == 0
    assert result["next_lesson"]["id"] == str(rich_lessons[0].pk)


def test_timeline_progress_ahead_status(admin_user, rich_course, rich_lessons, trainer_profile):
    today = timezone.localdate()
    # Only two days into a sixty-day batch...
    ahead_batch = create_batch(
        actor=admin_user,
        name="Ahead batch",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=58),
        capacity=5,
    )
    # ...but every lesson is already covered.
    for offset, lesson in enumerate(rich_lessons):
        session = _add_session(
            ahead_batch, admin_user, today - timedelta(days=2) + timedelta(days=offset)
        )
        record_session_topic(session=session, actor=admin_user, lesson=lesson)

    result = timeline_progress(ahead_batch)
    assert result["percent_complete"] == 100
    assert result["percent_expected"] <= 5
    assert result["variance_percent"] > 10
    assert result["status"] == "ahead"


def test_timeline_progress_behind_status(admin_user, rich_course, rich_lessons, trainer_profile):
    today = timezone.localdate()
    # Half-way through a sixty-day batch...
    behind_batch = create_batch(
        actor=admin_user,
        name="Behind batch",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        capacity=5,
    )
    # ...but nothing at all has been covered.
    _add_session(behind_batch, admin_user, today - timedelta(days=29))

    result = timeline_progress(behind_batch)
    assert result["percent_complete"] == 0
    assert 40 <= result["percent_expected"] <= 60
    assert result["variance_percent"] < -10
    assert result["status"] == "behind"


def test_timeline_progress_on_track_status(admin_user, rich_course, rich_lessons, trainer_profile):
    today = timezone.localdate()
    # Half-way through a sixty-day batch, having covered half the curriculum.
    on_track_batch = create_batch(
        actor=admin_user,
        name="On track batch",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        capacity=5,
    )
    for offset, lesson in enumerate(rich_lessons[:2]):
        session = _add_session(
            on_track_batch, admin_user, today - timedelta(days=29) + timedelta(days=offset)
        )
        record_session_topic(session=session, actor=admin_user, lesson=lesson)

    result = timeline_progress(on_track_batch)
    assert result["percent_complete"] == 50
    assert 40 <= result["percent_expected"] <= 60
    assert abs(result["variance_percent"]) <= 10
    assert result["status"] == "on_track"


def test_timeline_progress_variance_is_complete_minus_expected(
    admin_user, rich_course, rich_lessons, trainer_profile
):
    today = timezone.localdate()
    batch_ = create_batch(
        actor=admin_user,
        name="Variance batch",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=20),
        end_date=today + timedelta(days=20),
        capacity=5,
    )
    session = _add_session(batch_, admin_user, today - timedelta(days=19))
    record_session_topic(session=session, actor=admin_user, lesson=rich_lessons[0])

    result = timeline_progress(batch_)
    assert result["variance_percent"] == result["percent_complete"] - result["percent_expected"]


def test_timeline_progress_percent_expected_is_clamped_after_the_end_date(
    admin_user, rich_course, rich_lessons, trainer_profile
):
    today = timezone.localdate()
    overrun_batch = create_batch(
        actor=admin_user,
        name="Overrun batch",
        course=rich_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=90),
        end_date=today - timedelta(days=10),
        capacity=5,
    )
    _add_session(overrun_batch, admin_user, today - timedelta(days=89))

    result = timeline_progress(overrun_batch)
    assert result["percent_expected"] == 100


def test_timeline_progress_sessions_completed_counts_only_completed_status(admin_user, batch):
    scheduled = _add_session(batch, admin_user, batch.start_date)
    done = _add_session(batch, admin_user, batch.start_date + timedelta(days=1))
    set_session_status(session=done, target=SessionStatus.COMPLETED, actor=admin_user)

    result = timeline_progress(batch)
    assert result["sessions_total"] == 2
    assert result["sessions_completed"] == 1
    assert scheduled.status == SessionStatus.SCHEDULED


def test_timeline_progress_excludes_cancelled_sessions_from_totals(admin_user, batch):
    kept = _add_session(batch, admin_user, batch.start_date)
    cancelled = _add_session(batch, admin_user, batch.start_date + timedelta(days=1))
    set_session_status(
        session=cancelled, target=SessionStatus.CANCELLED, actor=admin_user, reason="Holiday"
    )

    result = timeline_progress(batch)
    assert result["sessions_total"] == 1
    assert kept.status == SessionStatus.SCHEDULED


def test_timeline_progress_lessons_planned_counts_distinct_planned_lessons(
    admin_user, rich_batch, rich_lessons
):
    first = _add_session(rich_batch, admin_user, rich_batch.start_date)
    second = _add_session(rich_batch, admin_user, rich_batch.start_date + timedelta(days=1))
    plan_session_topic(session=first, actor=admin_user, lesson=rich_lessons[0])
    plan_session_topic(session=second, actor=admin_user, lesson=rich_lessons[1])

    result = timeline_progress(rich_batch)
    assert result["lessons_planned"] == 2


def test_timeline_progress_survives_a_deleted_lesson(admin_user, batch, paid_lesson):
    """`SET_NULL` must leave the session readable, not raise."""
    session = _add_session(batch, admin_user, batch.start_date)
    plan_session_topic(session=session, actor=admin_user, lesson=paid_lesson)
    record_session_topic(session=session, actor=admin_user, lesson=paid_lesson)

    paid_lesson.delete()

    session.refresh_from_db()
    assert session.planned_lesson_id is None
    assert session.actual_lesson_id is None
    # The batch's timeline still computes without error.
    result = timeline_progress(batch)
    assert result["lessons_covered"] == 0


def test_timeline_progress_query_count_does_not_grow_with_lessons_or_sessions(
    admin_user, rich_batch, rich_lessons, django_assert_num_queries
):
    for offset, lesson in enumerate(rich_lessons):
        session = _add_session(
            rich_batch, admin_user, rich_batch.start_date + timedelta(days=offset)
        )
        record_session_topic(session=session, actor=admin_user, lesson=lesson)

    with django_assert_num_queries(2):
        timeline_progress(rich_batch)


def test_timeline_progress_via_the_api(api_client_no_csrf, admin_user, batch):
    _add_session(batch, admin_user, batch.start_date)
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.get(_timeline_url(batch))
    assert response.status_code == 200
    body = response.json()
    assert "percent_complete" in body
    assert "status" in body
    assert body["as_of"] == timezone.localdate().isoformat()


def test_a_trainer_can_view_their_own_batchs_timeline(
    api_client_no_csrf, admin_user, batch, trainer_profile
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(_timeline_url(batch))
    assert response.status_code == 200


def test_an_enrolled_student_can_view_their_batchs_timeline(
    api_client_no_csrf, admin_user, batch, enrollment
):
    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.get(_timeline_url(batch))
    assert response.status_code == 200


def test_a_trainer_cannot_view_an_unrelated_batchs_timeline(
    api_client_no_csrf, trainer_profile_two, batch
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.get(_timeline_url(batch))
    assert response.status_code == 404
