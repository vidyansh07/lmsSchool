"""The student activity timeline (ERP Phase 10, ADR-09).

A read-model composition test suite: the interesting bugs here are not "does
a row exist" but "is it interleaved correctly across sources", "does the
cursor resume without a gap or a duplicate when two sources tie to the
second", "is a query never issued for a source nobody asked for", and "does
a caller who can see the student's *profile* still only see what their own
per-source scope allows" — the same class of bug Phase 9's review caught for
the activity list itself.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.work.models import ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _code_file(name: str = "solution.py", body: bytes = b"print('hi')\n"):
    return SimpleUploadedFile(name, body, content_type="text/x-python")


def _url(student, **params) -> str:
    from urllib.parse import urlencode

    base = f"/api/v1/students/{student.pk}/timeline/"
    return f"{base}?{urlencode(params)}" if params else base


def _make_type(**overrides):
    defaults = {
        "slug": f"tl-{ActivityType.objects.count()}",
        "name": "Timeline Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer", "counsellor"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _completed_activity(*, actor, student, enrollment=None, assigned_to=None, **overrides):
    """A `COMPLETED` activity with `completed_at` set, since a plain
    `create_activity` call only produces a `draft`/`planned` row and the
    timeline's activity source only surfaces the handful of statuses that
    represent a moment (see `apps.work.timeline._ACTIVITY_STATUS_TIMESTAMP`).
    """
    from apps.work import services

    activity_type = overrides.pop("activity_type", None) or _make_type(**overrides)
    activity = services.create_activity(
        actor=actor,
        student=student,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=assigned_to,
    )
    when = overrides.get("completed_at", timezone.now())
    type(activity).objects.filter(pk=activity.pk).update(
        status=ActivityStatus.COMPLETED, completed_at=when, updated_at=when
    )
    activity.refresh_from_db()
    return activity


# ---------------------------------------------------------------------------
# Composition: sources are merged and sorted, not grouped
# ---------------------------------------------------------------------------


def test_the_timeline_interleaves_sources_by_time_not_by_source(
    admin_user, student_profile, enrollment
):
    """Registration order in `TIMELINE_SOURCES` is
    enrolment/attendance/.../assignment/.../certificate — chronologically
    reversed here, so a naive "concatenate sources in registry order" bug
    would list the assignment entry before the certificate one."""
    from apps.assignments.models import AssignmentStatus, AssignmentSubmission
    from apps.assignments.services import (
        create_assignment,
        set_assignment_status,
        submit_assignment,
    )
    from apps.certificates.models import Certificate
    from apps.certificates.services import issue_certificate, save_template
    from apps.progress.services import approve_completion

    now = timezone.now()

    assignment = set_assignment_status(
        assignment=create_assignment(
            actor=admin_user,
            course=enrollment.course,
            title="Oldest event",
            instructions="Do the thing.",
            max_marks=Decimal("10.00"),
            passing_marks=Decimal("5.00"),
        ),
        actor=admin_user,
        status=AssignmentStatus.PUBLISHED,
    )
    submission = submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[_code_file()],
    )
    AssignmentSubmission.objects.filter(pk=submission.pk).update(
        submitted_at=now - timedelta(days=10)
    )

    from apps.academics.services import get_or_create_policy, update_policy

    update_policy(
        policy=get_or_create_policy(),
        actor=admin_user,
        lessons_required_for_completion=False,
        attendance_required_for_completion=False,
        assignment_required_for_completion=False,
        tests_required_for_completion=False,
        projects_required_for_completion=False,
        final_exam_required_for_completion=False,
    )
    completion = approve_completion(enrollment=enrollment, actor=admin_user, note="ok")
    save_template(actor=admin_user, name="Default", is_default=True)
    certificate = issue_certificate(completion=completion, actor=admin_user)
    Certificate.objects.filter(pk=certificate.pk).update(issued_at=now - timedelta(days=5))

    response = _client(admin_user).get(
        _url(
            student_profile,
            since=(now - timedelta(days=30)).isoformat(),
            until=now.isoformat(),
        )
    )
    assert response.status_code == 200
    kinds = [row["kind"] for row in response.json()["results"]]
    # Newest first: the enrolment (created "now", by the fixture), then the
    # certificate (now - 5d), then the assignment submission (now - 10d) —
    # exactly reversed from registry order.
    assert kinds.index("certificate_issued") < kinds.index("assignment_submitted")
    assert kinds.index("enrollment_created") < kinds.index("certificate_issued")


# ---------------------------------------------------------------------------
# Cursor pagination, including a same-second tie across two sources
# ---------------------------------------------------------------------------


def test_cursor_pagination_resumes_across_pages_with_a_same_second_tie(
    admin_user, trainer_profile, student_profile, enrollment
):
    from apps.assignments.models import AssignmentStatus, AssignmentSubmission
    from apps.assignments.services import (
        create_assignment,
        set_assignment_status,
        submit_assignment,
    )
    from apps.dsr.models import DSR
    from apps.dsr.services import start_dsr, submit_dsr
    from apps.sessions.services import create_session

    # Inside `enrollment.batch`'s date window (start_date - 7d .. +60d from
    # today, per the `batch` fixture), but far enough from "now" that the
    # narrow +/-1-minute window below excludes everything else the fixtures
    # created at setup time (the enrolment itself, in particular).
    moment = timezone.now() - timedelta(days=3)

    session = create_session(
        batch=enrollment.batch,
        actor=admin_user,
        session_date=moment.date(),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Tie-break class",
    )
    dsr = submit_dsr(
        dsr=start_dsr(session=session, actor=trainer_profile.user), actor=trainer_profile.user
    )
    DSR.objects.filter(pk=dsr.pk).update(submitted_at=moment)

    assignment = set_assignment_status(
        assignment=create_assignment(
            actor=admin_user,
            course=enrollment.course,
            title="Tie-break assignment",
            instructions="Do the thing.",
            max_marks=Decimal("10.00"),
            passing_marks=Decimal("5.00"),
        ),
        actor=admin_user,
        status=AssignmentStatus.PUBLISHED,
    )
    submission = submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[_code_file()],
    )
    AssignmentSubmission.objects.filter(pk=submission.pk).update(submitted_at=moment)

    window = {
        "since": (moment - timedelta(minutes=1)).isoformat(),
        "until": (moment + timedelta(minutes=1)).isoformat(),
        "page_size": 1,
    }
    client = _client(admin_user)

    first = client.get(_url(student_profile, **window)).json()
    assert len(first["results"]) == 1
    assert first["next_cursor"] is not None

    second = client.get(_url(student_profile, **window, cursor=first["next_cursor"])).json()
    assert len(second["results"]) == 1

    first_id = first["results"][0]["id"]
    second_id = second["results"][0]["id"]
    assert first_id != second_id
    assert {first_id, second_id} == {f"dsr:{dsr.pk}", f"assignment_submission:{submission.pk}"}

    # The tie is exhausted: a third page (if asked for) is empty and closed.
    if second["next_cursor"] is not None:
        third = client.get(_url(student_profile, **window, cursor=second["next_cursor"])).json()
        assert third["results"] == []
        assert third["next_cursor"] is None


# ---------------------------------------------------------------------------
# A tampered or stale cursor degrades gracefully rather than crashing
# ---------------------------------------------------------------------------


def test_a_naive_datetime_in_a_hand_crafted_cursor_is_rejected_not_500d(
    admin_user, student_profile
):
    """`decode_cursor` must reject an ISO timestamp with no UTC offset.

    `datetime.fromisoformat` happily parses a naive string, and every real
    entry's `occurred_at` is timezone-aware, so letting a naive value through
    would blow up later as `TypeError: can't compare offset-naive and
    offset-aware datetimes` when `timeline_for` sorts against it — a 500,
    not the 400 a bad cursor should produce.
    """
    import base64

    from apps.work.timeline import timeline_for

    naive_cursor = base64.urlsafe_b64encode(b"2026-01-01T00:00:00|activity:5").decode("ascii")

    response = _client(admin_user).get(_url(student_profile, cursor=naive_cursor))
    assert response.status_code == 400

    with pytest.raises(Exception) as excinfo:
        timeline_for(
            admin_user,
            student_profile,
            since=timezone.now() - timedelta(days=1),
            until=timezone.now(),
            cursor=naive_cursor,
        )
    from apps.common.exceptions import ApplicationError

    assert isinstance(excinfo.value, ApplicationError)


# ---------------------------------------------------------------------------
# Query budget
# ---------------------------------------------------------------------------


def test_the_timeline_costs_at_most_one_query_per_source(
    admin_user, trainer_profile, student_profile, enrollment
):
    """One query per source for its own data, once each source's capability
    and scope lookups are warm — the same reasoning `test_reporting.py`'s own
    cache-dependent query-count test gives for warming before measuring: a
    cold cache pays for `effective_scope`'s per-capability lookup once per
    capability, which every other endpoint in a real session already would
    have paid before a caller ever opens a student's timeline.

    Every source needs at least one matching row here, not just `enrolment`
    (via the `enrollment` fixture) — a source with zero rows never runs its
    per-row `select_related`/actor-lookup code, so a missing
    `select_related` there would pass this test by never being exercised.
    """
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.assessments.services import create_assessment, record_result
    from apps.assignments.models import AssignmentStatus, AssignmentSubmission
    from apps.assignments.services import (
        create_assignment,
        set_assignment_status,
        submit_assignment,
    )
    from apps.attendance.models import AttendanceRecord, AttendanceStatus
    from apps.certificates.services import issue_certificate, save_template
    from apps.dsr.services import start_dsr, submit_dsr
    from apps.progress.services import approve_completion
    from apps.projects.models import ProjectStatus, StudentProject, WorkStatus
    from apps.projects.services import create_project, set_project_status
    from apps.sessions.services import create_session
    from apps.work.timeline import TIMELINE_SOURCES, timeline_for

    now = timezone.now()

    # attendance
    session = create_session(
        batch=enrollment.batch,
        actor=admin_user,
        session_date=now.date(),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Query budget class",
    )
    AttendanceRecord.objects.create(
        session=session,
        enrollment=enrollment,
        status=AttendanceStatus.PRESENT,
        marked_by=admin_user,
    )

    # dsr
    submit_dsr(
        dsr=start_dsr(session=session, actor=trainer_profile.user), actor=trainer_profile.user
    )

    # assessment
    assessment = create_assessment(
        actor=admin_user,
        batch=enrollment.batch,
        title="Query budget test",
        external_url="https://forms.example.test/query-budget",
    )
    record_result(
        assessment=assessment, enrollment=enrollment, actor=admin_user, marks=Decimal("8.00")
    )

    # assignment
    assignment = set_assignment_status(
        assignment=create_assignment(
            actor=admin_user,
            course=enrollment.course,
            title="Query budget assignment",
            instructions="Do the thing.",
            max_marks=Decimal("10.00"),
            passing_marks=Decimal("5.00"),
        ),
        actor=admin_user,
        status=AssignmentStatus.PUBLISHED,
    )
    submission = submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[_code_file()],
    )
    AssignmentSubmission.objects.filter(pk=submission.pk).update(marks_awarded=Decimal("9.00"))

    # project, reviewed and approved so the reviewer's own actor lookup runs
    project = set_project_status(
        project=create_project(
            actor=admin_user,
            course=enrollment.course,
            title="Query budget project",
            instructions="Build the thing.",
        ),
        actor=admin_user,
        status=ProjectStatus.PUBLISHED,
    )
    StudentProject.objects.create(
        project=project,
        enrollment=enrollment,
        status=WorkStatus.APPROVED,
        reviewer=trainer_profile,
        submitted_at=now,
        reviewed_at=now,
        marks_awarded=Decimal("50.00"),
    )

    # activity
    _completed_activity(actor=admin_user, student=student_profile, enrollment=enrollment)

    # certificate
    update_policy(
        policy=get_or_create_policy(),
        actor=admin_user,
        lessons_required_for_completion=False,
        attendance_required_for_completion=False,
        assignment_required_for_completion=False,
        tests_required_for_completion=False,
        projects_required_for_completion=False,
        final_exam_required_for_completion=False,
    )
    completion = approve_completion(enrollment=enrollment, actor=admin_user, note="ok")
    save_template(actor=admin_user, name="Default", is_default=True)
    issue_certificate(completion=completion, actor=admin_user)

    until = now + timedelta(minutes=5)
    since = until - timedelta(days=365)

    timeline_for(admin_user, student_profile, since=since, until=until)  # warm

    with CaptureQueriesContext(connection) as captured:
        timeline_for(admin_user, student_profile, since=since, until=until)

    assert len(captured.captured_queries) <= len(TIMELINE_SOURCES)


# ---------------------------------------------------------------------------
# Permission: exactly `StudentActivityListView`'s rule, reused not reinvented
# ---------------------------------------------------------------------------


def test_a_caller_who_cannot_see_the_student_at_all_gets_a_404(
    admin_user, student_profile, other_branch_student
):
    response = _client(student_profile.user).get(_url(other_branch_student))
    assert response.status_code == 404


def test_a_caller_in_the_same_branch_without_audience_gets_a_403(
    admin_user, student_profile, other_student_profile
):
    response = _client(student_profile.user).get(_url(other_student_profile))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# A caller who passes the top-level gate is still scoped per source
# ---------------------------------------------------------------------------


def test_a_trainer_who_can_see_the_student_still_only_sees_activities_they_teach(
    admin_user, trainer_profile, trainer_profile_two, student_profile, enrollment, upcoming_batch
):
    """`trainer_profile` teaches `enrollment.batch`, so `can_view_student`
    passes through that shared enrolment. A second activity, tied to a batch
    only `trainer_profile_two` teaches, must not leak into
    `trainer_profile`'s timeline just because the student is reachable —
    exactly Phase 9's own caught bug, now checked at the composed-timeline
    layer too."""
    from apps.enrollments.services import enrol_student

    other_enrollment = enrol_student(
        student=student_profile, batch=upcoming_batch, actor=admin_user
    )
    other_activity = _completed_activity(
        actor=admin_user,
        student=student_profile,
        enrollment=other_enrollment,
        assigned_to=trainer_profile_two.user,
    )

    seen_by_trainer_one = _client(trainer_profile.user).get(_url(student_profile)).json()["results"]
    ids = {row["id"] for row in seen_by_trainer_one}
    assert f"activity:{other_activity.pk}" not in ids

    seen_by_admin = _client(admin_user).get(_url(student_profile)).json()["results"]
    admin_ids = {row["id"] for row in seen_by_admin}
    assert f"activity:{other_activity.pk}" in admin_ids


# ---------------------------------------------------------------------------
# `kinds` filtering: an excluded source is never even queried
# ---------------------------------------------------------------------------


def test_kinds_filtering_skips_querying_excluded_sources(admin_user, student_profile, monkeypatch):
    from apps.work import timeline as timeline_module

    calls = {"a": 0, "b": 0}

    def source_a(user, student, since, until, cursor_bound, limit):
        calls["a"] += 1
        return []

    def source_b(user, student, since, until, cursor_bound, limit):
        calls["b"] += 1
        return []

    monkeypatch.setattr(
        timeline_module,
        "TIMELINE_SOURCES",
        [
            timeline_module._Source("a", frozenset({"kind_a"}), source_a),
            timeline_module._Source("b", frozenset({"kind_b"}), source_b),
        ],
    )

    response = _client(admin_user).get(_url(student_profile, kinds="kind_a"))
    assert response.status_code == 200
    assert calls == {"a": 1, "b": 0}


# ---------------------------------------------------------------------------
# A student's own timeline is reduced the same way their own activity list is
# ---------------------------------------------------------------------------


def test_a_students_own_timeline_hides_a_non_student_visible_activity(
    admin_user, student_profile, enrollment
):
    hidden_type = _make_type(slug="tl-hidden", visible_to_student=False)
    hidden = _completed_activity(
        actor=admin_user, student=student_profile, enrollment=enrollment, activity_type=hidden_type
    )

    visible_type = _make_type(slug="tl-visible", visible_to_student=True)
    visible = _completed_activity(
        actor=admin_user, student=student_profile, enrollment=enrollment, activity_type=visible_type
    )

    own_view = _client(student_profile.user).get(_url(student_profile)).json()["results"]
    ids = {row["id"] for row in own_view}
    assert f"activity:{hidden.pk}" not in ids
    assert f"activity:{visible.pk}" in ids

    staff_view = _client(admin_user).get(_url(student_profile)).json()["results"]
    staff_ids = {row["id"] for row in staff_view}
    assert f"activity:{hidden.pk}" in staff_ids
