"""Assignments: authoring, the submission window, attempts and grading.

§4.3 and the §4.8 test list — assignment submission, trainer scope, student
isolation and transaction behaviour.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionKind,
    SubmissionStatus,
)
from apps.audit.models import AuditAction, AuditLog


def _code_file(name: str = "solution.py", body: bytes = b"print('hello')\n"):
    return SimpleUploadedFile(name, body, content_type="text/x-python")


@pytest.fixture
def assignment(admin_user, published_course, batch):
    """A published file assignment, open, on the batch's course."""
    from apps.assignments.services import create_assignment, set_assignment_status

    created = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Shell scripting exercise",
        instructions="Write a script that lists the ten largest files.",
        max_marks=Decimal("50.00"),
        passing_marks=Decimal("25.00"),
        due_at=timezone.now() + timedelta(days=3),
    )
    return set_assignment_status(
        assignment=created, actor=admin_user, status=AssignmentStatus.PUBLISHED
    )


@pytest.fixture
def submission(assignment, enrollment, student_profile):
    from apps.assignments.services import submit_assignment

    return submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[_code_file()],
    )


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_sets_work_on_the_course_they_teach(
    api_client_no_csrf, trainer_profile, published_course, batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/assignments/",
        {
            "title": "Week one exercise",
            "instructions": "Hand in your script.",
            "batch": str(batch.id),
            "max_marks": "20.00",
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    # New work starts as a draft whatever the client asked for, so a
    # half-written brief never appears in front of a student.
    assert body["status"] == AssignmentStatus.DRAFT
    assert body["code"].startswith("GRS-A-")
    assert body["batch"] == str(batch.id)


@pytest.mark.django_db
def test_a_trainer_cannot_set_work_on_somebody_elses_batch(
    api_client_no_csrf, trainer_profile, published_course, upcoming_batch
):
    """`upcoming_batch` is taught by a different trainer. §4.8 trainer scope.

    The answer is 404 rather than 403, and deliberately so: the batch id is
    resolved inside the caller's own visible set, so a trainer probing ids does
    not even learn that this batch exists.
    """
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/assignments/",
        {"title": "Not mine", "batch": str(upcoming_batch.id)},
        format="json",
    )

    assert response.status_code == 404
    assert not Assignment.objects.filter(title="Not mine").exists()


@pytest.mark.django_db
def test_a_student_cannot_set_work(
    api_client_no_csrf, student_profile, published_course, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/assignments/",
        {"title": "Homework for everyone"},
        format="json",
    )

    assert response.status_code == 403
    assert Assignment.objects.count() == 0


@pytest.mark.django_db
def test_unknown_fields_are_rejected_not_ignored(api_client_no_csrf, admin_user, published_course):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/assignments/",
        {"title": "Probing", "status": "published", "created_by": "someone"},
        format="json",
    )

    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert "status" in details and "created_by" in details


@pytest.mark.django_db
def test_a_module_from_another_course_is_refused(admin_user, published_course, draft_course):
    """The course/module chain is validated, not assumed."""
    from apps.common.exceptions import ApplicationError
    from apps.courses.services import create_module

    stray = create_module(course=draft_course, actor=admin_user, title="Elsewhere")

    from apps.assignments.services import create_assignment

    with pytest.raises(ApplicationError) as exc:
        create_assignment(
            actor=admin_user, course=published_course, title="Mismatched", module=stray
        )
    assert "module" in exc.value.detail


@pytest.mark.django_db
def test_a_draft_is_invisible_to_students(
    api_client_no_csrf, admin_user, published_course, student_profile, enrollment
):
    from apps.assignments.services import create_assignment

    create_assignment(actor=admin_user, course=published_course, title="Still drafting")

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/assignments/mine/").json()
    assert body["count"] == 0


@pytest.mark.django_db
def test_publishing_puts_the_work_in_front_of_the_student(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/assignments/mine/").json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["code"] == assignment.code
    assert row["my_submission"] is None
    assert row["is_open"] is True


@pytest.mark.django_db
def test_batch_specific_work_stays_on_its_own_batch(
    api_client_no_csrf, admin_user, published_course, upcoming_batch, student_profile, enrollment
):
    """A student on batch 1 must not see work set for batch 2 of the same course."""
    from apps.assignments.services import create_assignment, set_assignment_status

    other = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Evening cohort only",
        batch=upcoming_batch,
    )
    set_assignment_status(assignment=other, actor=admin_user, status=AssignmentStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/assignments/mine/").json()
    assert [row["title"] for row in body["results"]] == []


@pytest.mark.django_db
def test_status_moves_follow_the_lifecycle(api_client_no_csrf, admin_user, assignment):
    api_client_no_csrf.force_login(admin_user)
    url = f"/api/v1/assignments/{assignment.id}/status/"

    # published -> draft is not a move that exists.
    refused = api_client_no_csrf.post(url, {"status": "draft"}, format="json")
    assert refused.status_code == 409

    closed = api_client_no_csrf.post(url, {"status": "closed"}, format="json")
    assert closed.status_code == 200
    assert closed.json()["status"] == AssignmentStatus.CLOSED
    assert closed.json()["is_open"] is False


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_submits_and_sees_their_attempt(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["attempt"] == 1
    assert body["is_late"] is False
    assert body["status"] == SubmissionStatus.SUBMITTED
    assert len(body["files"]) == 1
    assert body["files"][0]["original_filename"] == "solution.py"


@pytest.mark.django_db
def test_a_student_not_enrolled_on_the_course_cannot_submit(
    api_client_no_csrf, assignment, other_student_profile
):
    """No enrolment, no submission — §4.8 student isolation."""
    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    # The assignment is not in their visible set at all.
    assert response.status_code in (403, 404)
    assert AssignmentSubmission.objects.count() == 0


@pytest.mark.django_db
def test_a_second_submission_is_refused_unless_resubmission_is_allowed(
    api_client_no_csrf, assignment, submission, student_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 409
    assert AssignmentSubmission.objects.count() == 1


@pytest.mark.django_db
def test_resubmission_creates_a_new_attempt_and_keeps_the_first(
    api_client_no_csrf, admin_user, assignment, submission, student_profile
):
    from apps.assignments.services import update_assignment

    update_assignment(
        assignment=assignment, actor=admin_user, allow_resubmission=True, max_attempts=3
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file("v2.py")]},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.json()["attempt"] == 2
    # The first attempt survives — a resubmission is a new row, not an edit.
    assert AssignmentSubmission.objects.filter(assignment=assignment).count() == 2


@pytest.mark.django_db
def test_attempts_run_out(api_client_no_csrf, admin_user, assignment, submission, student_profile):
    from apps.assignments.services import update_assignment

    update_assignment(
        assignment=assignment, actor=admin_user, allow_resubmission=True, max_attempts=2
    )
    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/assignments/{assignment.id}/submit/"

    second = api_client_no_csrf.post(url, {"files": [_code_file()]}, format="multipart")
    assert second.status_code == 201
    third = api_client_no_csrf.post(url, {"files": [_code_file()]}, format="multipart")

    assert third.status_code == 409
    assert "all 2 attempts" in str(third.json())


@pytest.mark.django_db
def test_work_handed_in_after_the_deadline_is_flagged_late(
    api_client_no_csrf, admin_user, assignment, student_profile, enrollment
):
    from apps.assignments.services import update_assignment

    update_assignment(
        assignment=assignment, actor=admin_user, due_at=timezone.now() - timedelta(hours=2)
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.json()["is_late"] is True


@pytest.mark.django_db
def test_late_work_is_refused_when_the_trainer_disallowed_it(
    api_client_no_csrf, admin_user, assignment, student_profile, enrollment
):
    from apps.assignments.services import update_assignment

    update_assignment(
        assignment=assignment,
        actor=admin_user,
        due_at=timezone.now() - timedelta(hours=2),
        allow_late=False,
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 400
    assert AssignmentSubmission.objects.count() == 0


@pytest.mark.django_db
def test_nothing_is_accepted_after_the_cutoff(
    api_client_no_csrf, admin_user, assignment, student_profile, enrollment
):
    from apps.assignments.services import update_assignment

    now = timezone.now()
    update_assignment(
        assignment=assignment,
        actor=admin_user,
        due_at=now - timedelta(days=2),
        late_cutoff_at=now - timedelta(hours=1),
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 400
    assert "closed" in str(response.json())


@pytest.mark.django_db
def test_a_written_assignment_needs_words_not_a_file(
    api_client_no_csrf, admin_user, published_course, student_profile, enrollment
):
    from apps.assignments.services import create_assignment, set_assignment_status

    written = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Explain inodes",
        submission_kind=SubmissionKind.TEXT,
    )
    set_assignment_status(assignment=written, actor=admin_user, status=AssignmentStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/assignments/{written.id}/submit/"

    empty = api_client_no_csrf.post(url, {"text_answer": "   "}, format="json")
    assert empty.status_code == 400

    answered = api_client_no_csrf.post(
        url, {"text_answer": "An inode holds the metadata for a file."}, format="json"
    )
    assert answered.status_code == 201
    assert answered.json()["text_answer"].startswith("An inode")


@pytest.mark.django_db
def test_submitting_to_a_closed_assignment_is_refused(
    api_client_no_csrf, admin_user, assignment, student_profile, enrollment
):
    from apps.assignments.services import set_assignment_status

    set_assignment_status(assignment=assignment, actor=admin_user, status=AssignmentStatus.CLOSED)

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_trainer_sees_the_marking_queue(
    api_client_no_csrf, trainer_profile, assignment, submission
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["student_id"].startswith("GRS-S-")
    assert row["status"] == SubmissionStatus.SUBMITTED


@pytest.mark.django_db
def test_another_trainer_cannot_reach_the_queue(
    api_client_no_csrf, trainer_profile_two, assignment, submission
):
    """§4.8 trainer scope: an assignment id from another course buys nothing."""
    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.get(f"/api/v1/assignments/{assignment.id}/submissions/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_marks_above_the_maximum_are_refused_by_the_server(
    api_client_no_csrf, trainer_profile, submission
):
    """§5.5: the server calculates, the browser does not get to assert."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/grade/",
        {"marks": "500.00", "feedback": "Wonderful"},
        format="json",
    )

    assert response.status_code == 400
    submission.refresh_from_db()
    assert submission.marks_awarded is None


@pytest.mark.django_db
def test_grading_records_the_mark_and_the_student_sees_it(
    api_client_no_csrf, trainer_profile, student_profile, submission
):
    api_client_no_csrf.force_login(trainer_profile.user)
    graded = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/grade/",
        {"marks": "40.00", "feedback": "Good use of find."},
        format="json",
    )
    assert graded.status_code == 200
    assert graded.json()["marks_awarded"] == "40.00"

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/submissions/{submission.id}/").json()
    assert body["marks_awarded"] == "40.00"
    assert body["feedback"] == "Good use of find."
    # 40 of 50, pass mark 25.
    assert body["is_passing"] is True
    # Who marked it is staff information and is not in the student's shape.
    assert "graded_by_name" not in body


@pytest.mark.django_db
def test_graded_work_cannot_be_resubmitted(
    api_client_no_csrf, admin_user, trainer_profile, assignment, submission, student_profile
):
    from apps.assignments.services import grade_submission, update_assignment

    update_assignment(
        assignment=assignment, actor=admin_user, allow_resubmission=True, max_attempts=5
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("30.00"))

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file()]},
        format="multipart",
    )

    assert response.status_code == 409
    assert "graded" in str(response.json())


@pytest.mark.django_db
def test_returning_work_opens_one_more_attempt(
    api_client_no_csrf, trainer_profile, assignment, submission, student_profile
):
    """Rework is allowed even though `allow_resubmission` is off."""
    assert assignment.allow_resubmission is False

    api_client_no_csrf.force_login(trainer_profile.user)
    returned = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/return/",
        {"feedback": "Handle the empty-directory case."},
        format="json",
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == SubmissionStatus.RETURNED

    api_client_no_csrf.force_login(student_profile.user)
    again = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": [_code_file("fixed.py")]},
        format="multipart",
    )
    assert again.status_code == 201
    assert again.json()["attempt"] == 2


@pytest.mark.django_db
def test_returning_work_without_saying_why_is_refused(
    api_client_no_csrf, trainer_profile, submission
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/return/", {"feedback": "   "}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_superseded_attempt_cannot_be_graded(
    admin_user, trainer_profile, assignment, submission, student_profile, enrollment
):
    from apps.assignments.services import grade_submission, submit_assignment, update_assignment
    from apps.common.exceptions import ConflictError

    update_assignment(
        assignment=assignment, actor=admin_user, allow_resubmission=True, max_attempts=3
    )
    submit_assignment(
        assignment=assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[_code_file()],
    )

    with pytest.raises(ConflictError):
        grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("10.00"))


# ---------------------------------------------------------------------------
# Isolation and audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_read_a_classmates_submission(
    api_client_no_csrf, submission, other_student_profile, other_enrollment
):
    """§4.8 student isolation. A submission id is not an entitlement."""
    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/submissions/{submission.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_student_cannot_grade_their_own_work(api_client_no_csrf, submission, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/grade/", {"marks": "50.00"}, format="json"
    )

    assert response.status_code == 404
    submission.refresh_from_db()
    assert submission.marks_awarded is None


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, assignment, submission):
    for url in (
        "/api/v1/assignments/",
        f"/api/v1/assignments/{assignment.id}/",
        f"/api/v1/submissions/{submission.id}/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


@pytest.mark.django_db
def test_every_state_change_is_audited(
    admin_user, trainer_profile, assignment, submission, student_profile
):
    from apps.assignments.services import grade_submission

    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("31.00"))

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.ASSIGNMENT_CREATED in actions
    assert AuditAction.ASSIGNMENT_STATUS_CHANGED in actions
    assert AuditAction.SUBMISSION_CREATED in actions
    assert AuditAction.SUBMISSION_GRADED in actions

    entry = AuditLog.objects.filter(action=AuditAction.SUBMISSION_GRADED).first()
    assert entry.context["marks"] == "31.00"
    assert entry.context["max_marks"] == "50.00"


# ---------------------------------------------------------------------------
# Editing rules
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_marks_out_of_cannot_change_once_work_is_in(
    api_client_no_csrf, admin_user, assignment, submission
):
    """Moving the goalposts under a student who has already submitted."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/assignments/{assignment.id}/", {"max_marks": "10.00"}, format="json"
    )

    assert response.status_code == 409
    assignment.refresh_from_db()
    assert assignment.max_marks == Decimal("50.00")


@pytest.mark.django_db
def test_a_deadline_can_still_be_extended_after_submissions(
    api_client_no_csrf, admin_user, assignment, submission
):
    later = timezone.now() + timedelta(days=10)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/assignments/{assignment.id}/",
        {"due_at": later.isoformat()},
        format="json",
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_an_answered_assignment_cannot_be_deleted(
    api_client_no_csrf, admin_user, assignment, submission
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.delete(f"/api/v1/assignments/{assignment.id}/")

    assert response.status_code == 409
    assert Assignment.objects.filter(pk=assignment.pk).exists()


@pytest.mark.django_db
def test_an_unanswered_assignment_can_be_deleted(api_client_no_csrf, admin_user, assignment):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.delete(f"/api/v1/assignments/{assignment.id}/")

    assert response.status_code == 204
    assert not Assignment.objects.filter(pk=assignment.pk).exists()


@pytest.mark.django_db
def test_the_student_work_list_does_not_grow_a_query_per_assignment(
    api_client_no_csrf,
    admin_user,
    published_course,
    student_profile,
    enrollment,
    django_assert_max_num_queries,
):
    from apps.assignments.services import (
        create_assignment,
        set_assignment_status,
        submit_assignment,
    )

    for index in range(6):
        created = create_assignment(
            actor=admin_user, course=published_course, title=f"Exercise {index}"
        )
        set_assignment_status(
            assignment=created, actor=admin_user, status=AssignmentStatus.PUBLISHED
        )
        submit_assignment(
            assignment=created,
            enrollment=enrollment,
            actor=student_profile.user,
            files=[_code_file()],
        )

    api_client_no_csrf.force_login(student_profile.user)
    with django_assert_max_num_queries(20):
        body = api_client_no_csrf.get("/api/v1/assignments/mine/").json()

    assert body["count"] == 6
    assert all(row["my_submission"] is not None for row in body["results"])
