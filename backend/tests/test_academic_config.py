"""Academic configuration — §4.7.

    "Do not hard-code business rules into views."

So the tests are not about storing a number. They are about the number changing
the answer somewhere it matters, without a deployment.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.academics.models import DEFAULT_POLICY, AcademicPolicy, PolicyScope
from apps.academics.policies import attendance_requirement, policy_for
from apps.audit.models import AuditAction, AuditLog


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    """The resolver memoises per request; tests call it directly, so clear it.

    Without this a test that changes a rule would keep reading the value the
    previous assertion resolved.
    """
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


def _set_global(admin_user, **fields):
    from apps.academics.services import get_or_create_policy, update_policy

    return update_policy(policy=get_or_create_policy(), actor=admin_user, **fields)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_with_nothing_configured_the_code_defaults_apply(published_course):
    """No row, no crash. An institution that never opens this screen still works."""
    assert AcademicPolicy.objects.count() == 0
    policy = policy_for(published_course)

    assert policy.passing_percent == DEFAULT_POLICY["passing_percent"]
    assert policy.minimum_attendance_percent == DEFAULT_POLICY["minimum_attendance_percent"]


@pytest.mark.django_db
def test_a_course_override_beats_the_institution(admin_user, published_course):
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.request_context import clear_scope

    _set_global(admin_user, passing_percent=Decimal("40.00"))
    update_policy(
        policy=get_or_create_policy(course=published_course),
        actor=admin_user,
        passing_percent=Decimal("60.00"),
    )
    clear_scope()

    assert policy_for(published_course).passing_percent == Decimal("60.00")
    # Everything the course did not state still comes from the institution.
    assert (
        policy_for(published_course).minimum_attendance_percent
        == DEFAULT_POLICY["minimum_attendance_percent"]
    )
    assert policy_for().passing_percent == Decimal("40.00")


@pytest.mark.django_db
def test_clearing_a_course_override_restores_inheritance(
    api_client_no_csrf, admin_user, published_course
):
    api_client_no_csrf.force_login(admin_user)
    url = f"/api/v1/academics/policy/courses/{published_course.id}/"

    api_client_no_csrf.patch(url, {"passing_percent": "70.00"}, format="json")
    assert policy_for(published_course).passing_percent == Decimal("70.00")

    assert api_client_no_csrf.delete(url).status_code == 204

    from apps.common.request_context import clear_scope

    clear_scope()
    assert policy_for(published_course).passing_percent == DEFAULT_POLICY["passing_percent"]


@pytest.mark.django_db
def test_there_is_exactly_one_institution_wide_row(admin_user):
    from django.db import IntegrityError, transaction

    from apps.academics.services import get_or_create_policy

    get_or_create_policy()
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicPolicy.objects.create(scope=PolicyScope.GLOBAL)


# ---------------------------------------------------------------------------
# Who may change the rules
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_changes_the_rules(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        "/api/v1/academics/policy/",
        {"minimum_attendance_percent": "80.00", "passing_percent": "50.00"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert response.json()["minimum_attendance_percent"] == "80.00"


@pytest.mark.django_db
def test_a_trainer_cannot_change_the_rules(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.patch(
        "/api/v1/academics/policy/", {"passing_percent": "1.00"}, format="json"
    )

    assert response.status_code == 403
    assert AcademicPolicy.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_change_the_rules(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    assert (
        api_client_no_csrf.patch(
            "/api/v1/academics/policy/", {"passing_percent": "0.00"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_student_may_read_what_is_required_of_them(
    api_client_no_csrf, admin_user, student_profile, enrollment, published_course
):
    """Knowing the pass mark is not a privilege."""
    _set_global(admin_user, passing_percent=Decimal("45.00"))

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(
        f"/api/v1/academics/policy/effective/?course={published_course.id}"
    )

    assert response.status_code == 200
    assert response.json()["passing_percent"] == "45.00"


@pytest.mark.django_db
def test_a_nonsensical_rule_is_refused(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    for payload in (
        {"passing_percent": "140.00"},
        {"minimum_attendance_percent": "-5.00"},
        {"assignment_default_max_attempts": 0},
        {"assignment_default_max_marks": "0.00"},
    ):
        assert (
            api_client_no_csrf.patch(
                "/api/v1/academics/policy/", payload, format="json"
            ).status_code
            == 400
        ), payload


@pytest.mark.django_db
def test_an_unknown_rule_is_rejected_not_ignored(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        "/api/v1/academics/policy/", {"free_marks_for_everyone": True}, format="json"
    )

    assert response.status_code == 400
    assert "free_marks_for_everyone" in str(response.json())


@pytest.mark.django_db
def test_a_rule_change_records_what_it_was_and_what_it_became(admin_user):
    _set_global(admin_user, passing_percent=Decimal("40.00"))
    _set_global(admin_user, passing_percent=Decimal("55.00"))

    entry = AuditLog.objects.filter(action=AuditAction.ACADEMIC_POLICY_UPDATED).first()
    assert entry.context["to"]["passing_percent"] == "55.00"
    assert entry.context["from"]["passing_percent"] == "40.00"


# ---------------------------------------------------------------------------
# The rules actually decide things
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_passing_percentage_decides_an_assignment_with_no_threshold_of_its_own(
    admin_user, trainer_profile, student_profile, published_course, enrollment
):
    """The heart of §4.7: change the rule, the verdict changes. No deployment."""
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )
    from apps.common.request_context import clear_scope

    _set_global(admin_user, passing_percent=Decimal("40.00"))
    clear_scope()

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Scored 50 out of 100",
        max_marks=Decimal("100.00"),
    )
    assert work.passing_marks is None  # no opinion of its own

    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
    submission = submit_assignment(
        assignment=work,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("answer.py", b"pass\n")],
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("50.00"))

    clear_scope()
    assert submission.is_passing is True

    # Raise the bar. The stored mark does not move; the verdict does.
    _set_global(admin_user, passing_percent=Decimal("60.00"))
    clear_scope()
    submission.refresh_from_db()

    assert submission.marks_awarded == Decimal("50.00")
    assert submission.is_passing is False
    assert submission.passing_mark == Decimal("60.00")


@pytest.mark.django_db
def test_an_assignment_with_its_own_threshold_ignores_the_policy(
    admin_user, trainer_profile, student_profile, published_course, enrollment
):
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )
    from apps.common.request_context import clear_scope

    _set_global(admin_user, passing_percent=Decimal("90.00"))
    clear_scope()

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Pass at 10",
        max_marks=Decimal("100.00"),
        passing_marks=Decimal("10.00"),
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
    submission = submit_assignment(
        assignment=work,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("answer.py", b"pass\n")],
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("20.00"))

    clear_scope()
    assert submission.is_passing is True


@pytest.mark.django_db
def test_the_configuration_supplies_assignment_defaults(admin_user, published_course):
    from apps.assignments.services import create_assignment
    from apps.common.request_context import clear_scope

    _set_global(
        admin_user,
        assignment_default_max_marks=Decimal("25.00"),
        assignment_default_max_attempts=3,
        assignment_allow_late=False,
    )
    clear_scope()

    work = create_assignment(actor=admin_user, course=published_course, title="Defaulted")

    assert work.max_marks == Decimal("25.00")
    assert work.max_attempts == 3
    assert work.allow_late is False


@pytest.mark.django_db
def test_a_stated_value_still_beats_the_default(admin_user, published_course):
    from apps.assignments.services import create_assignment
    from apps.common.request_context import clear_scope

    _set_global(admin_user, assignment_default_max_marks=Decimal("25.00"))
    clear_scope()

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Explicit",
        max_marks=Decimal("80.00"),
    )
    assert work.max_marks == Decimal("80.00")


@pytest.mark.django_db
def test_the_passing_percentage_decides_a_weekly_test_too(admin_user, batch, enrollment):
    from apps.assessments.models import AssessmentDelivery
    from apps.assessments.services import create_assessment, record_result
    from apps.common.request_context import clear_scope

    _set_global(admin_user, passing_percent=Decimal("50.00"))
    clear_scope()

    test = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Week 3",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )
    result, _ = record_result(
        assessment=test, enrollment=enrollment, actor=admin_user, marks=Decimal("9.00")
    )

    clear_scope()
    assert result.is_passing is False  # 9 of 20 is 45%

    _set_global(admin_user, passing_percent=Decimal("40.00"))
    clear_scope()
    assert result.is_passing is True


@pytest.mark.django_db
def test_the_attendance_requirement_is_the_configured_one(
    admin_user, trainer_profile, batch, schedule, enrollment
):
    from apps.attendance.services import mark_attendance
    from apps.common.request_context import clear_scope
    from apps.sessions.services import create_session

    today = timezone.localdate()
    for offset, status in enumerate(["present", "present", "absent"]):
        session = create_session(
            batch=batch,
            actor=admin_user,
            session_date=today - timedelta(days=offset + 1),
            start_time=time(9, 0),
            end_time=time(11, 0),
            topic=f"Class {offset}",
        )
        mark_attendance(
            session=session,
            actor=trainer_profile.user,
            entries=[{"enrollment_id": str(enrollment.pk), "status": status}],
        )

    _set_global(admin_user, minimum_attendance_percent=Decimal("60.00"))
    clear_scope()
    verdict = attendance_requirement(enrollment)

    assert verdict["percentage"] == 67  # two of three
    assert verdict["minimum_percent"] == Decimal("60.00")
    assert verdict["met"] is True

    _set_global(admin_user, minimum_attendance_percent=Decimal("90.00"))
    clear_scope()
    assert attendance_requirement(enrollment)["met"] is False


@pytest.mark.django_db
def test_turning_the_attendance_requirement_off_means_nobody_fails_it(
    admin_user, trainer_profile, batch, schedule, enrollment
):
    from apps.attendance.services import mark_attendance
    from apps.common.request_context import clear_scope
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Missed it",
    )
    mark_attendance(
        session=session,
        actor=trainer_profile.user,
        entries=[{"enrollment_id": str(enrollment.pk), "status": "absent"}],
    )

    _set_global(
        admin_user,
        minimum_attendance_percent=Decimal("90.00"),
        attendance_required_for_completion=False,
    )
    clear_scope()

    verdict = attendance_requirement(enrollment)
    assert verdict["percentage"] == 0
    assert verdict["met"] is True


@pytest.mark.django_db
def test_a_student_sees_the_requirement_alongside_their_attendance(
    api_client_no_csrf, admin_user, student_profile, enrollment
):
    from apps.common.request_context import clear_scope

    _set_global(admin_user, minimum_attendance_percent=Decimal("85.00"))
    clear_scope()

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/attendance/mine/").json()

    summary = body[0]["summary"]
    assert summary["minimum_percent"] == "85.00"
    assert summary["required"] is True
    # No classes marked yet, so nothing has been failed.
    assert summary["met"] is None


@pytest.mark.django_db
def test_the_policy_is_resolved_once_per_request_not_once_per_row(
    api_client_no_csrf,
    admin_user,
    trainer_profile,
    student_profile,
    published_course,
    enrollment,
    django_assert_max_num_queries,
):
    """A page of results must not ask the database for the same rules per row."""
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )

    _set_global(admin_user, passing_percent=Decimal("40.00"))

    for index in range(6):
        work = create_assignment(actor=admin_user, course=published_course, title=f"Task {index}")
        set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
        submission = submit_assignment(
            assignment=work,
            enrollment=enrollment,
            actor=student_profile.user,
            files=[SimpleUploadedFile("a.py", b"pass\n")],
        )
        grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("50.00"))

    api_client_no_csrf.force_login(student_profile.user)
    with django_assert_max_num_queries(22):
        body = api_client_no_csrf.get("/api/v1/submissions/mine/").json()

    assert body["count"] == 6
    assert all(row["is_passing"] is True for row in body["results"])
