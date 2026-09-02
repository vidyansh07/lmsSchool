"""Progress and completion — §6.1 to §6.6.

The theme: there is one progress calculation and one rule engine reading it, and
changing a rule changes the answer immediately without rewriting anything that
was already decided.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.batches.models import DeliveryMode
from apps.progress.models import CompletionStatus, CourseCompletion


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


def _set_rules(admin_user, **fields):
    from apps.academics.services import get_or_create_policy, update_policy
    from apps.common.request_context import clear_scope

    policy = update_policy(policy=get_or_create_policy(), actor=admin_user, **fields)
    clear_scope()
    return policy


@pytest.fixture
def relaxed_rules(admin_user):
    """Nothing required. Each test switches on the one rule it is about."""
    return _set_rules(
        admin_user,
        lessons_required_for_completion=False,
        attendance_required_for_completion=False,
        assignment_required_for_completion=False,
        tests_required_for_completion=False,
        projects_required_for_completion=False,
        final_exam_required_for_completion=False,
    )


def _complete_lessons(enrollment, count):
    from apps.courses.models import Lesson, PublishStatus
    from apps.enrollments.services import set_lesson_completion

    lessons = Lesson.objects.filter(
        module__course_id=enrollment.course_id,
        module__status=PublishStatus.PUBLISHED,
        status=PublishStatus.PUBLISHED,
    ).order_by("module__position", "position")[:count]
    for lesson in lessons:
        set_lesson_completion(student=enrollment.student, lesson=lesson, completed=True)


# ---------------------------------------------------------------------------
# 6.1 to 6.3 - one progress calculation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_progress_counts_published_lessons_only(enrollment, published_course, admin_user):
    """A draft lesson must not make a progress bar go backwards."""
    from apps.courses.models import PublishStatus
    from apps.courses.services import create_lesson
    from apps.progress.reports import progress_report

    module = published_course.modules.first()
    before = progress_report(enrollment)["lessons"]["total"]

    create_lesson(
        module=module,
        actor=admin_user,
        title="Still being written",
        text_content="Draft body.",
    )

    after = progress_report(enrollment)["lessons"]["total"]
    assert after == before

    # And it counts once it is published.
    draft = module.lessons.get(title="Still being written")
    draft.status = PublishStatus.PUBLISHED
    draft.save(update_fields=["status"])
    assert progress_report(enrollment)["lessons"]["total"] == before + 1


@pytest.mark.django_db
def test_lesson_and_module_progress_agree(enrollment):
    from apps.progress.reports import progress_report

    _complete_lessons(enrollment, 1)
    report = progress_report(enrollment)

    assert report["lessons"]["completed"] == 1
    assert report["lessons"]["percent"] == 50  # the fixture course has two lessons
    module_done = sum(module["completed_lessons"] for module in report["modules"])
    assert module_done == report["lessons"]["completed"]


@pytest.mark.django_db
def test_module_progress_does_not_grow_a_query_per_module(
    enrollment, django_assert_max_num_queries
):
    from apps.progress.reports import module_progress

    # Three: the modules, their published lessons, and this student's progress
    # rows. Flat in the number of modules, which is what this asserts — Phase 9
    # traded one grouped query for three that a cohort report can share across
    # every student in it.
    with django_assert_max_num_queries(3):
        rows = module_progress(enrollment)
    assert rows


@pytest.mark.django_db
def test_the_report_covers_every_activity(enrollment):
    """One call answers the whole completion screen."""
    from apps.progress.reports import progress_report

    report = progress_report(enrollment)
    for section in ("lessons", "modules", "attendance", "assignments", "tests", "projects", "exam"):
        assert section in report, section


@pytest.mark.django_db
def test_progress_is_isolated_per_enrolment(enrollment, other_enrollment, other_student_profile):
    """§6.9 enrolment isolation."""
    from apps.progress.reports import progress_report

    _complete_lessons(enrollment, 2)

    assert progress_report(enrollment)["lessons"]["completed"] == 2
    assert progress_report(other_enrollment)["lessons"]["completed"] == 0


# ---------------------------------------------------------------------------
# §6.4 — rules, and combinations of them
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_with_no_rules_required_a_student_is_eligible(relaxed_rules, enrollment):
    from apps.progress.services import evaluate_enrollment

    result = evaluate_enrollment(enrollment)
    assert result["eligible"] is True
    assert result["required_count"] == 0
    # Every rule is still reported, switched off or not.
    assert len(result["rules"]) == 7


@pytest.mark.django_db
def test_a_rule_that_is_off_is_reported_not_hidden(relaxed_rules, enrollment):
    """A student is entitled to see where they stand on an optional condition."""
    from apps.progress.services import evaluate_enrollment

    rules = {rule["key"]: rule for rule in evaluate_enrollment(enrollment)["rules"]}
    assert rules["attendance"]["required"] is False
    assert "detail" in rules["attendance"]


@pytest.mark.django_db
def test_the_lesson_rule_gates_eligibility(admin_user, relaxed_rules, enrollment):
    from apps.progress.services import evaluate_enrollment

    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("80.00"),
    )
    assert evaluate_enrollment(enrollment)["eligible"] is False

    _complete_lessons(enrollment, 2)
    assert evaluate_enrollment(enrollment)["eligible"] is True


@pytest.mark.django_db
def test_lowering_a_threshold_makes_a_student_eligible_at_once(
    admin_user, relaxed_rules, enrollment
):
    """§6.9 rule changes. No deployment, no nightly job."""
    from apps.progress.services import evaluate_enrollment

    _complete_lessons(enrollment, 1)  # 50%
    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("80.00"),
    )
    assert evaluate_enrollment(enrollment)["eligible"] is False

    _set_rules(admin_user, minimum_lesson_completion_percent=Decimal("50.00"))
    assert evaluate_enrollment(enrollment)["eligible"] is True


@pytest.mark.django_db
def test_the_attendance_rule_uses_the_configured_threshold(
    admin_user, relaxed_rules, trainer_profile, batch, schedule, enrollment
):
    from apps.attendance.services import mark_attendance
    from apps.progress.services import evaluate_enrollment
    from apps.sessions.services import create_session

    today = timezone.localdate()
    for offset, status in enumerate(["present", "absent"]):
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

    _set_rules(
        admin_user,
        attendance_required_for_completion=True,
        minimum_attendance_percent=Decimal("75.00"),
    )
    assert evaluate_enrollment(enrollment)["eligible"] is False  # 50%

    _set_rules(admin_user, minimum_attendance_percent=Decimal("50.00"))
    assert evaluate_enrollment(enrollment)["eligible"] is True


@pytest.mark.django_db
def test_a_course_with_no_projects_cannot_fail_its_project_rule(
    admin_user, relaxed_rules, enrollment
):
    """The alternative blocks everybody on a course that sets no projects."""
    from apps.progress.services import evaluate_enrollment

    _set_rules(admin_user, projects_required_for_completion=True)
    rules = {rule["key"]: rule for rule in evaluate_enrollment(enrollment)["rules"]}

    assert rules["projects"]["required"] is True
    assert rules["projects"]["met"] is True
    assert "No required projects" in rules["projects"]["detail"]


@pytest.mark.django_db
def test_an_outstanding_required_project_blocks_completion(
    admin_user, relaxed_rules, published_course, batch, enrollment, student_profile, trainer_profile
):
    from apps.progress.services import evaluate_enrollment
    from apps.projects.models import ProjectStatus, WorkStatus
    from apps.projects.services import (
        create_project,
        review_project,
        set_project_status,
        student_project_for,
        submit_project,
    )

    project = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Required capstone",
        is_required=True,
        max_marks=Decimal("100.00"),
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)
    _set_rules(admin_user, projects_required_for_completion=True)

    assert evaluate_enrollment(enrollment)["eligible"] is False

    work = student_project_for(project=project, student=student_profile)
    submit_project(
        work=work,
        actor=student_profile.user,
        files=[SimpleUploadedFile("a.py", b"pass\n")],
    )
    review_project(
        work=work,
        actor=trainer_profile.user,
        outcome=WorkStatus.APPROVED,
        marks=Decimal("70.00"),
    )

    from apps.common.request_context import clear_scope

    clear_scope()
    assert evaluate_enrollment(enrollment)["eligible"] is True


@pytest.mark.django_db
def test_the_final_exam_rule_is_off_by_default(relaxed_rules, enrollment):
    """Not every course ends in an examination."""
    from apps.academics.policies import policy_for

    assert policy_for(enrollment.course_id).final_exam_required_for_completion is False


@pytest.mark.django_db
def test_several_rules_must_all_be_met(admin_user, relaxed_rules, enrollment):
    from apps.progress.services import evaluate_enrollment

    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("50.00"),
        assignment_required_for_completion=True,
    )

    _complete_lessons(enrollment, 1)
    result = evaluate_enrollment(enrollment)
    # Lessons met, assignments vacuously met (none set) — so eligible.
    assert result["eligible"] is True
    assert result["required_count"] == 2
    assert result["met_count"] == 2


# ---------------------------------------------------------------------------
# §6.5 — online and offline under one model
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_follows_their_batch_unless_they_differ(enrollment, batch):
    assert batch.delivery_mode == DeliveryMode.OFFLINE
    assert enrollment.effective_delivery_mode == DeliveryMode.OFFLINE

    enrollment.delivery_mode = DeliveryMode.ONLINE
    enrollment.save(update_fields=["delivery_mode"])
    assert enrollment.effective_delivery_mode == DeliveryMode.ONLINE


@pytest.mark.django_db
def test_an_offline_cohort_uses_the_same_everything(admin_user, relaxed_rules, batch, enrollment):
    """§6.5: a field, not a second architecture.

    An institution teaching offline switches the lesson requirement off; every
    other rule, and every other table, is unchanged.
    """
    from apps.progress.reports import progress_report
    from apps.progress.services import evaluate_enrollment

    batch.delivery_mode = DeliveryMode.OFFLINE
    batch.save(update_fields=["delivery_mode"])

    _set_rules(
        admin_user,
        lessons_required_for_completion=False,
        attendance_required_for_completion=True,
        minimum_attendance_percent=Decimal("0.00"),
    )

    report = progress_report(enrollment)
    assert report["delivery_mode"] == DeliveryMode.OFFLINE
    assert evaluate_enrollment(enrollment)["eligible"] is True


# ---------------------------------------------------------------------------
# §6.6 — the workflow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_eligible_student_reaches_the_approval_queue(
    api_client_no_csrf, admin_user, relaxed_rules, enrollment
):
    from apps.progress.services import refresh_completion

    completion = refresh_completion(enrollment=enrollment, actor=admin_user)
    assert completion.status == CompletionStatus.ELIGIBLE
    assert completion.became_eligible_at is not None

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/completions/?status=eligible").json()
    assert body["count"] == 1


@pytest.mark.django_db
def test_an_administrator_approves_and_the_enrolment_follows(
    api_client_no_csrf, admin_user, relaxed_rules, enrollment
):
    from apps.enrollments.models import EnrollmentStatus

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/approve/",
        {"note": "Verified against the register."},
        format="json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == CompletionStatus.APPROVED
    assert body["completed_on"] is not None

    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.COMPLETED


@pytest.mark.django_db
def test_a_student_who_does_not_meet_the_rules_cannot_be_approved(
    api_client_no_csrf, admin_user, relaxed_rules, enrollment
):
    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("100.00"),
    )

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/approve/", {}, format="json"
    )

    assert response.status_code == 400
    assert "lessons" in str(response.json())


@pytest.mark.django_db
def test_an_override_is_allowed_and_recorded_as_one(
    api_client_no_csrf, admin_user, relaxed_rules, enrollment
):
    """A decision that bends the rules must stay explainable afterwards."""
    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("100.00"),
    )

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/approve/",
        {"override": True, "note": "Prior learning recognised."},
        format="json",
    )

    assert response.status_code == 200
    snapshot = response.json()["rule_snapshot"]
    assert snapshot["overridden"] is True
    assert snapshot["eligible"] is False
    # The rules as they stood are kept, so the decision can be explained later.
    assert len(snapshot["rules"]) == 7


@pytest.mark.django_db
def test_an_approved_completion_is_not_undone_by_a_later_rule_change(
    admin_user, relaxed_rules, enrollment
):
    """A student who dips below the line after graduating has not un-graduated."""
    from apps.progress.services import approve_completion, refresh_completion

    approve_completion(enrollment=enrollment, actor=admin_user)
    _set_rules(
        admin_user,
        lessons_required_for_completion=True,
        minimum_lesson_completion_percent=Decimal("100.00"),
    )

    completion = refresh_completion(enrollment=enrollment, actor=admin_user)
    assert completion.status == CompletionStatus.APPROVED


@pytest.mark.django_db
def test_a_rejection_needs_a_reason(api_client_no_csrf, admin_user, relaxed_rules, enrollment):
    api_client_no_csrf.force_login(admin_user)
    refused = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/reject/", {"note": "  "}, format="json"
    )
    assert refused.status_code == 400

    given = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/reject/",
        {"note": "Attendance disputed; awaiting the register."},
        format="json",
    )
    assert given.status_code == 200
    assert given.json()["status"] == CompletionStatus.REJECTED


@pytest.mark.django_db
def test_a_decision_can_be_reopened(api_client_no_csrf, admin_user, relaxed_rules, enrollment):
    from apps.progress.services import reject_completion

    reject_completion(enrollment=enrollment, actor=admin_user, note="Too early.")

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/reopen/",
        {"note": "Register corrected."},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == CompletionStatus.ELIGIBLE


@pytest.mark.django_db
def test_approving_twice_is_refused(admin_user, relaxed_rules, enrollment):
    from apps.common.exceptions import ConflictError
    from apps.progress.services import approve_completion

    approve_completion(enrollment=enrollment, actor=admin_user)
    with pytest.raises(ConflictError):
        approve_completion(enrollment=enrollment, actor=admin_user)


# ---------------------------------------------------------------------------
# Who may see and decide
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_reads_their_own_progress(
    api_client_no_csrf, relaxed_rules, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/progress/mine/").json()

    assert len(body) == 1
    assert body[0]["progress"]["course_title"] == enrollment.course.title
    assert "rules" in body[0]
    # Who decided, and the note, are staff information.
    assert "decision_note" not in (body[0]["completion"] or {})


@pytest.mark.django_db
def test_a_student_cannot_read_another_students_progress(
    api_client_no_csrf, relaxed_rules, other_student_profile, other_enrollment, enrollment
):
    """§6.9 enrolment isolation, through the API."""
    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/progress/enrollments/{enrollment.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_trainer_cannot_approve_a_completion(
    api_client_no_csrf, relaxed_rules, trainer_profile, enrollment
):
    """Approving is an institutional act, not a teaching one."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/approve/", {}, format="json"
    )

    assert response.status_code == 403
    assert not CourseCompletion.objects.filter(status=CompletionStatus.APPROVED).exists()


@pytest.mark.django_db
def test_a_student_cannot_approve_their_own_completion(
    api_client_no_csrf, relaxed_rules, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/completions/enrollments/{enrollment.id}/approve/", {}, format="json"
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, enrollment):
    for url in (
        "/api/v1/progress/mine/",
        f"/api/v1/progress/enrollments/{enrollment.id}/",
        "/api/v1/completions/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


@pytest.mark.django_db
def test_the_workflow_is_audited(admin_user, relaxed_rules, enrollment):
    from apps.progress.services import approve_completion, refresh_completion

    refresh_completion(enrollment=enrollment, actor=admin_user)
    approve_completion(enrollment=enrollment, actor=admin_user, note="Fine.")

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.COMPLETION_ELIGIBLE in actions
    assert AuditAction.COMPLETION_APPROVED in actions


# ---------------------------------------------------------------------------
# The rest of the progress calculation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_assignment_progress_counts_the_latest_attempt(
    admin_user, trainer_profile, student_profile, published_course, batch, enrollment
):
    """A student with three attempts has handed in one assignment, not three."""
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
        update_assignment,
    )
    from apps.progress.reports import assignment_progress

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Worksheet",
        max_marks=Decimal("100.00"),
        passing_marks=Decimal("40.00"),
        allow_resubmission=True,
        max_attempts=3,
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
    create_assignment(
        actor=admin_user, course=published_course, batch=batch, title="Never published"
    )

    before = assignment_progress(enrollment)
    assert before["total"] == 1  # the draft is not set work
    assert before["submitted"] == 0

    for _ in range(2):
        submit_assignment(
            assignment=work,
            enrollment=enrollment,
            actor=student_profile.user,
            files=[SimpleUploadedFile("a.py", b"pass\n")],
        )
    update_assignment(assignment=work, actor=admin_user, allow_resubmission=True)

    middle = assignment_progress(enrollment)
    assert middle["submitted"] == 1
    assert middle["percent"] == 100
    assert middle["graded"] == 0

    latest = work.submissions.order_by("-attempt").first()
    grade_submission(submission=latest, actor=trainer_profile.user, marks=Decimal("75.00"))

    from apps.common.request_context import clear_scope

    clear_scope()
    after = assignment_progress(enrollment)
    assert after["graded"] == 1
    assert after["passed"] == 1


@pytest.mark.django_db
def test_test_progress_averages_across_what_was_recorded(admin_user, batch, enrollment):
    from apps.assessments.models import AssessmentDelivery, AssessmentStatus
    from apps.assessments.services import create_assessment, record_result, set_assessment_status
    from apps.progress.reports import test_progress

    tests = []
    for index in range(2):
        test = create_assessment(
            actor=admin_user,
            batch=batch,
            title=f"Week {index + 1}",
            delivery=AssessmentDelivery.OFFLINE,
            max_marks=Decimal("20.00"),
        )
        set_assessment_status(assessment=test, actor=admin_user, status=AssessmentStatus.PUBLISHED)
        tests.append(test)

    empty = test_progress(enrollment)
    assert empty["total"] == 2
    assert empty["recorded"] == 0
    assert empty["average_percent"] is None

    record_result(
        assessment=tests[0], enrollment=enrollment, actor=admin_user, marks=Decimal("15.00")
    )
    record_result(
        assessment=tests[1], enrollment=enrollment, actor=admin_user, marks=Decimal("5.00")
    )

    after = test_progress(enrollment)
    assert after["recorded"] == 2
    assert after["percent"] == 100
    # 20 of 40 across both papers.
    assert after["average_percent"] == 50.0


@pytest.mark.django_db
def test_an_absence_counts_as_sat_but_not_scored(admin_user, batch, enrollment):
    from apps.assessments.models import AssessmentDelivery, AssessmentStatus
    from apps.assessments.services import create_assessment, record_result, set_assessment_status
    from apps.progress.reports import test_progress

    test = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Missed it",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )
    set_assessment_status(assessment=test, actor=admin_user, status=AssessmentStatus.PUBLISHED)
    record_result(assessment=test, enrollment=enrollment, actor=admin_user, is_absent=True)

    numbers = test_progress(enrollment)
    assert numbers["recorded"] == 1
    assert numbers["average_percent"] is None


@pytest.mark.django_db
def test_exam_progress_reads_the_best_graded_attempt(
    admin_user, batch, enrollment, student_profile, published_course
):
    """A candidate allowed two sittings is judged on the better one."""
    from apps.exams.models import ExamStatus
    from apps.exams.services import create_exam, set_exam_status, start_attempt, submit_attempt
    from apps.progress.reports import exam_progress
    from apps.questions.models import QuestionType
    from apps.questions.services import create_question

    for index in range(4):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.MCQ,
            text=f"Q{index}?",
            marks=Decimal("5.00"),
            options=[
                {"text": "right", "is_correct": True},
                {"text": "wrong", "is_correct": False},
            ],
        )

    none_yet = exam_progress(enrollment)
    assert none_yet["exists"] is False

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Finals",
        opens_at=timezone.now() - timedelta(minutes=1),
        passing_marks=Decimal("10.00"),
        sections=[{"title": "A", "question_count": 4, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    unsat = exam_progress(enrollment)
    assert unsat == {"exists": True, "sat": False, "passed": False, "best_percent": None}

    attempt = start_attempt(exam=exam, enrollment=enrollment, actor=student_profile.user)
    for attempt_question in attempt.questions.select_related("question"):
        correct = attempt_question.question.options.get(is_correct=True)
        from apps.exams.services import save_answer

        save_answer(
            attempt=attempt,
            attempt_question=attempt_question,
            actor=student_profile.user,
            selected_options=[str(correct.pk)],
        )
    submit_attempt(attempt=attempt, actor=student_profile.user)

    from apps.common.request_context import clear_scope

    clear_scope()
    sat = exam_progress(enrollment)
    assert sat["sat"] is True
    assert sat["passed"] is True
    assert sat["best_percent"] == 100.0


@pytest.mark.django_db
def test_the_final_exam_rule_blocks_until_it_is_passed(
    admin_user, relaxed_rules, batch, enrollment, published_course
):
    from apps.exams.models import ExamStatus
    from apps.exams.services import create_exam, set_exam_status
    from apps.progress.services import evaluate_enrollment
    from apps.questions.models import QuestionType
    from apps.questions.services import create_question

    for index in range(2):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.MCQ,
            text=f"E{index}?",
            marks=Decimal("5.00"),
            options=[
                {"text": "right", "is_correct": True},
                {"text": "wrong", "is_correct": False},
            ],
        )
    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Finals",
        opens_at=timezone.now() - timedelta(minutes=1),
        sections=[{"title": "A", "question_count": 2, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    _set_rules(admin_user, final_exam_required_for_completion=True)

    result = evaluate_enrollment(enrollment)
    assert result["eligible"] is False
    assert "final_exam" in result["unmet"]
