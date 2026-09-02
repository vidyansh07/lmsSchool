"""Weekly tests and external assessments — §4.5.

The abstraction under test: the LMS holds a test whatever it is delivered
through, and the results table is the same shape whichever door the mark came
in by.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ResultSource,
)
from apps.audit.models import AuditAction, AuditLog


@pytest.fixture
def weekly_test(admin_user, batch):
    """A published Google-Form weekly test on the batch."""
    from apps.assessments.services import create_assessment, set_assessment_status

    created = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Week 1 — Linux basics",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.EXTERNAL_LINK,
        external_url="https://docs.google.com/forms/d/e/abc/viewform",
        external_provider="Google Forms",
        scheduled_for=timezone.now() + timedelta(days=1),
        duration_minutes=45,
        max_marks=Decimal("20.00"),
        passing_marks=Decimal("8.00"),
    )
    return set_assessment_status(
        assessment=created, actor=admin_user, status=AssessmentStatus.PUBLISHED
    )


# ---------------------------------------------------------------------------
# Creating a test
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_schedules_a_weekly_test_on_their_batch(
    api_client_no_csrf, trainer_profile, batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/assessments/",
        {
            "title": "Week 2 test",
            "delivery": AssessmentDelivery.EXTERNAL_LINK,
            "external_url": "https://forms.example.test/week2",
            "max_marks": "25.00",
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["code"].startswith("GRS-X-")
    assert body["status"] == AssessmentStatus.DRAFT
    # The course is derived from the batch, never taken from the request.
    assert body["course"] == str(batch.course_id)


@pytest.mark.django_db
def test_an_external_test_without_a_link_is_refused(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/assessments/",
        {"title": "Nowhere to go", "delivery": AssessmentDelivery.EXTERNAL_LINK},
        format="json",
    )

    assert response.status_code == 400
    assert "external_url" in str(response.json())


@pytest.mark.django_db
def test_an_insecure_link_is_refused(api_client_no_csrf, admin_user, batch):
    """http:// would downgrade a student part-way through a test."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/assessments/",
        {
            "title": "Insecure",
            "delivery": AssessmentDelivery.EXTERNAL_LINK,
            "external_url": "http://forms.example.test/x",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "https" in str(response.json())


@pytest.mark.django_db
def test_a_trainer_cannot_set_a_test_on_another_trainers_batch(
    api_client_no_csrf, trainer_profile, upcoming_batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{upcoming_batch.id}/assessments/",
        {
            "title": "Not mine",
            "delivery": AssessmentDelivery.EXTERNAL_LINK,
            "external_url": "https://forms.example.test/x",
        },
        format="json",
    )

    assert response.status_code in (403, 404)
    assert Assessment.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_set_a_test(api_client_no_csrf, student_profile, batch, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/assessments/",
        {
            "title": "Free marks",
            "delivery": AssessmentDelivery.EXTERNAL_LINK,
            "external_url": "https://forms.example.test/x",
        },
        format="json",
    )

    assert response.status_code == 403
    assert Assessment.objects.count() == 0


# ---------------------------------------------------------------------------
# What the student sees
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_draft_test_is_invisible_to_students(
    api_client_no_csrf, admin_user, batch, student_profile, enrollment
):
    from apps.assessments.services import create_assessment

    create_assessment(
        actor=admin_user,
        batch=batch,
        title="Unannounced",
        delivery=AssessmentDelivery.OFFLINE,
    )

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/assessments/mine/").json()["count"] == 0


@pytest.mark.django_db
def test_a_published_test_shows_the_student_where_to_take_it(
    api_client_no_csrf, weekly_test, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/assessments/mine/").json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["external_url"].startswith("https://")
    assert row["external_provider"] == "Google Forms"
    assert row["my_result"] is None


@pytest.mark.django_db
def test_a_student_on_another_batch_sees_nothing(
    api_client_no_csrf, weekly_test, other_student_profile, admin_user, upcoming_batch
):
    from apps.enrollments.services import enrol_student

    enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get("/api/v1/assessments/mine/").json()["count"] == 0


# ---------------------------------------------------------------------------
# Recording marks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_marks_sheet_lists_the_whole_cohort_unmarked(
    api_client_no_csrf, trainer_profile, weekly_test, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/assessments/{weekly_test.id}/marks/").json()

    assert body["can_record"] is True
    assert len(body["entries"]) == 2
    assert all(entry["marks_obtained"] is None for entry in body["entries"])
    codes = [entry["student_code"] for entry in body["entries"]]
    assert codes == sorted(codes)


@pytest.mark.django_db
def test_a_mark_above_the_maximum_is_refused(
    api_client_no_csrf, trainer_profile, weekly_test, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "marks": "80.00"},
        format="json",
    )

    assert response.status_code == 400
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_an_absent_student_has_no_mark(
    api_client_no_csrf, trainer_profile, weekly_test, enrollment
):
    """Absent is not zero — reporting has to be able to tell them apart."""
    api_client_no_csrf.force_login(trainer_profile.user)
    both = api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "marks": "5.00", "is_absent": True},
        format="json",
    )
    assert both.status_code == 400

    absent = api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "is_absent": True},
        format="json",
    )
    assert absent.status_code == 200
    assert absent.json()["marks_obtained"] is None
    assert absent.json()["is_passing"] is False


@pytest.mark.django_db
def test_a_recorded_mark_reaches_the_student_with_pass_and_percentage(
    api_client_no_csrf, trainer_profile, student_profile, weekly_test, enrollment
):
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "marks": "15.00", "remarks": "Well done."},
        format="json",
    )

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/results/mine/").json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["marks_obtained"] == "15.00"
    assert row["max_marks"] == "20.00"
    assert row["is_passing"] is True
    assert row["percentage"] == 75.0


@pytest.mark.django_db
def test_a_student_cannot_see_a_classmates_mark(
    api_client_no_csrf,
    trainer_profile,
    other_student_profile,
    weekly_test,
    enrollment,
    other_enrollment,
):
    """§4.8 student isolation."""
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "marks": "18.00"},
        format="json",
    )

    api_client_no_csrf.force_login(other_student_profile.user)
    body = api_client_no_csrf.get("/api/v1/results/mine/").json()
    assert body["count"] == 0


@pytest.mark.django_db
def test_a_student_cannot_record_their_own_mark(
    api_client_no_csrf, student_profile, weekly_test, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        {"enrollment_id": str(enrollment.id), "marks": "20.00"},
        format="json",
    )

    assert response.status_code == 404
    assert AssessmentResult.objects.count() == 0


@pytest.mark.django_db
def test_a_student_from_another_batch_cannot_be_marked(
    admin_user, weekly_test, other_student_profile, upcoming_batch
):
    from apps.assessments.services import record_result
    from apps.common.exceptions import ApplicationError
    from apps.enrollments.services import enrol_student

    stray = enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    with pytest.raises(ApplicationError):
        record_result(
            assessment=weekly_test, enrollment=stray, actor=admin_user, marks=Decimal("5")
        )


# ---------------------------------------------------------------------------
# File-upload delivery, backed by the assignment machinery
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_file_upload_test_is_backed_by_an_assignment(admin_user, batch):
    from apps.assessments.services import create_assessment

    assessment = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Practical: write a backup script",
        delivery=AssessmentDelivery.FILE_UPLOAD,
        max_marks=Decimal("40.00"),
        passing_marks=Decimal("16.00"),
    )

    backing = assessment.backing_assignment
    assert backing is not None
    assert backing.max_marks == Decimal("40.00")
    assert backing.batch_id == batch.pk
    # Reusing the assignment path is what gives this the §4.4 file rules for
    # free rather than a second upload pipeline.
    assert backing.submission_kind == "file"


@pytest.mark.django_db
def test_publishing_the_test_publishes_what_students_submit_to(admin_user, batch):
    from apps.assessments.services import create_assessment, set_assessment_status
    from apps.assignments.models import AssignmentStatus

    assessment = create_assessment(
        actor=admin_user, batch=batch, title="Practical", delivery=AssessmentDelivery.FILE_UPLOAD
    )
    set_assessment_status(
        assessment=assessment, actor=admin_user, status=AssessmentStatus.PUBLISHED
    )

    assessment.backing_assignment.refresh_from_db()
    assert assessment.backing_assignment.status == AssignmentStatus.PUBLISHED


@pytest.mark.django_db
def test_grading_the_submission_records_the_result(
    api_client_no_csrf, admin_user, trainer_profile, student_profile, batch, enrollment
):
    """One mark, one place. Grading a backing assignment writes the result."""
    from apps.assessments.services import create_assessment, set_assessment_status
    from apps.assignments.services import submit_assignment

    assessment = create_assessment(
        actor=admin_user,
        batch=batch,
        title="Practical",
        delivery=AssessmentDelivery.FILE_UPLOAD,
        max_marks=Decimal("40.00"),
        passing_marks=Decimal("16.00"),
    )
    set_assessment_status(
        assessment=assessment, actor=admin_user, status=AssessmentStatus.PUBLISHED
    )
    assessment.backing_assignment.refresh_from_db()

    submission = submit_assignment(
        assignment=assessment.backing_assignment,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("backup.sh", b"#!/bin/sh\necho hi\n")],
    )

    api_client_no_csrf.force_login(trainer_profile.user)
    graded = api_client_no_csrf.post(
        f"/api/v1/submissions/{submission.id}/grade/",
        {"marks": "32.00", "feedback": "Solid."},
        format="json",
    )
    assert graded.status_code == 200

    result = AssessmentResult.objects.get(assessment=assessment, enrollment=enrollment)
    assert result.marks_obtained == Decimal("32.00")
    assert result.source == ResultSource.GRADED
    assert result.is_passing is True


@pytest.mark.django_db
def test_an_ordinary_assignment_does_not_create_a_result(
    admin_user, trainer_profile, student_profile, published_course, enrollment
):
    """Not every assignment is a test."""
    from apps.assignments.models import AssignmentStatus as AStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )

    homework = create_assignment(
        actor=admin_user, course=published_course, title="Reading", max_marks=Decimal("10")
    )
    set_assignment_status(assignment=homework, actor=admin_user, status=AStatus.PUBLISHED)
    submission = submit_assignment(
        assignment=homework,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("notes.md", b"# read\n")],
    )
    grade_submission(submission=submission, actor=trainer_profile.user, marks=Decimal("9"))

    assert AssessmentResult.objects.count() == 0


# ---------------------------------------------------------------------------
# Lifecycle and audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_delivery_mechanism_is_fixed_once_results_exist(
    api_client_no_csrf, admin_user, weekly_test, enrollment
):
    from apps.assessments.services import record_result

    record_result(
        assessment=weekly_test, enrollment=enrollment, actor=admin_user, marks=Decimal("10")
    )

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/assessments/{weekly_test.id}/",
        {"delivery": AssessmentDelivery.OFFLINE},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_a_marked_assessment_cannot_be_deleted(
    api_client_no_csrf, admin_user, weekly_test, enrollment
):
    from apps.assessments.services import record_result

    record_result(
        assessment=weekly_test, enrollment=enrollment, actor=admin_user, marks=Decimal("10")
    )

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.delete(f"/api/v1/assessments/{weekly_test.id}/").status_code == 409


@pytest.mark.django_db
def test_recording_a_result_is_audited(admin_user, weekly_test, enrollment):
    from apps.assessments.services import record_result

    record_result(
        assessment=weekly_test, enrollment=enrollment, actor=admin_user, marks=Decimal("11.50")
    )

    entry = AuditLog.objects.filter(action=AuditAction.RESULT_RECORDED).first()
    assert entry is not None
    assert entry.context["marks"] == "11.50"
    assert entry.context["assessment"] == weekly_test.code

    # Re-recording is an update, not a second creation.
    record_result(
        assessment=weekly_test, enrollment=enrollment, actor=admin_user, marks=Decimal("12.00")
    )
    assert AuditLog.objects.filter(action=AuditAction.RESULT_UPDATED).exists()
    assert AssessmentResult.objects.count() == 1


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, weekly_test):
    for url in (
        "/api/v1/assessments/",
        f"/api/v1/assessments/{weekly_test.id}/",
        f"/api/v1/assessments/{weekly_test.id}/marks/",
        "/api/v1/results/mine/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url
