"""Course access is now decided by enrolment.

This is the §7 rule end to end: a student reaches non-preview content only
through a live enrolment, and losing that enrolment closes the door on the very
next request.
"""

from __future__ import annotations

import pytest

from apps.enrollments.models import EnrollmentStatus

COURSES_URL = "/api/v1/courses/"


def _lesson_url(lesson) -> str:
    return f"/api/v1/lessons/{lesson.id}/"


# ---------------------------------------------------------------------------
# Without an enrolment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_unenrolled_student_is_refused_paid_content(api_client_no_csrf, student, paid_lesson):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get(_lesson_url(paid_lesson))
    assert response.status_code == 403
    assert "Secret paid content" not in response.content.decode()


@pytest.mark.django_db
def test_an_unenrolled_student_still_reads_preview_lessons(
    api_client_no_csrf, student, preview_lesson
):
    """Previews are the sample a prospective student is shown."""
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get(_lesson_url(preview_lesson))
    assert response.status_code == 200
    assert response.json()["text_content"] == "Welcome to the course."


@pytest.mark.django_db
def test_an_unenrolled_student_still_sees_the_course_outline(
    api_client_no_csrf, student, published_course, paid_lesson
):
    """A gated course must stay browsable, or nobody would ever enrol."""
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/").json()
    titles = [lesson["title"] for module in body["modules"] for lesson in module["lessons"]]
    assert paid_lesson.title in titles
    assert "Secret paid content" not in str(body)


# ---------------------------------------------------------------------------
# With a live enrolment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_active_enrolment_opens_the_content(api_client_no_csrf, enrollment, paid_lesson):
    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.get(_lesson_url(paid_lesson))
    assert response.status_code == 200
    assert response.json()["text_content"] == "Secret paid content."


@pytest.mark.django_db
def test_enrolment_opens_resources_and_video(
    api_client_no_csrf, admin_user, enrollment, paid_lesson, pdf_bytes
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"/api/v1/lessons/{paid_lesson.id}/resources/",
        {
            "title": "Handout",
            "file": SimpleUploadedFile("h.pdf", pdf_bytes, content_type="application/pdf"),
        },
        format="multipart",
    )
    resource = paid_lesson.resources.first()

    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(f"/api/v1/lessons/{paid_lesson.id}/resources/").status_code == 200
    assert api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/").status_code == 200


# ---------------------------------------------------------------------------
# Losing the enrolment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspension_closes_access_on_the_next_request(
    api_client_no_csrf, admin_user, enrollment, paid_lesson
):
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 200

    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment,
        target=EnrollmentStatus.SUSPENDED,
        actor=admin_user,
        note="Fees overdue",
    )

    # No cache to invalidate: the check is live.
    response = api_client_no_csrf.get(_lesson_url(paid_lesson))
    assert response.status_code == 403
    assert "Secret paid content" not in response.content.decode()


@pytest.mark.django_db
def test_cancellation_closes_access_but_keeps_the_record(
    api_client_no_csrf, admin_user, enrollment, paid_lesson
):
    """§12: access changes, history does not disappear."""
    from apps.enrollments.models import Enrollment
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user, note="Withdrew"
    )

    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 403
    assert Enrollment.objects.filter(pk=enrollment.pk).exists()


@pytest.mark.django_db
def test_cancelling_the_batch_closes_access_for_everyone(
    api_client_no_csrf, admin_user, enrollment, other_enrollment, paid_lesson, batch
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"/api/v1/batches/{batch.id}/status/", {"status": "cancelled"})

    for row in (enrollment, other_enrollment):
        api_client_no_csrf.force_login(row.student.user)
        assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 403


@pytest.mark.django_db
def test_a_completed_enrolment_keeps_reading_the_material(
    api_client_no_csrf, admin_user, enrollment, paid_lesson
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.COMPLETED, actor=admin_user
    )
    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 200


@pytest.mark.django_db
def test_an_expired_access_window_closes_the_door(
    api_client_no_csrf, admin_user, student_profile, batch, paid_lesson
):
    from datetime import timedelta

    from django.utils import timezone

    from apps.enrollments.services import enrol_student

    enrol_student(
        student=student_profile,
        batch=batch,
        actor=admin_user,
        access_end_date=timezone.localdate() - timedelta(days=1),
    )
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 403


@pytest.mark.django_db
def test_enrolment_on_one_course_does_not_open_another(
    api_client_no_csrf, admin_user, enrollment, category
):
    """Access is per course, never a blanket "is a student" check."""
    from apps.courses import services as course_services
    from apps.courses.models import PublishStatus

    other = course_services.create_course(
        actor=admin_user,
        title="Unrelated Course",
        category=category,
        short_description="A course the student is not enrolled on.",
    )
    module = course_services.create_module(
        course=other, actor=admin_user, title="M", status=PublishStatus.PUBLISHED
    )
    lesson = course_services.create_lesson(
        module=module,
        actor=admin_user,
        title="L",
        content_type="text",
        text_content="Other course content.",
        status=PublishStatus.PUBLISHED,
    )
    course_services.set_course_status(
        course=other, target=PublishStatus.PUBLISHED, actor=admin_user, may_publish=True
    )

    api_client_no_csrf.force_login(enrollment.student.user)
    response = api_client_no_csrf.get(_lesson_url(lesson))
    assert response.status_code == 403
    assert "Other course content" not in response.content.decode()


@pytest.mark.django_db
def test_trainers_and_admins_are_not_gated_by_enrolment(
    api_client_no_csrf, admin_user, trainer, paid_lesson
):
    """Staff read the material they teach without holding a student place."""
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 200

    from apps.courses.models import CourseAuthorRole
    from apps.courses.services import assign_author

    assign_author(
        course=paid_lesson.module.course,
        user=trainer,
        role=CourseAuthorRole.EDITOR,
        actor=admin_user,
    )
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 200


@pytest.mark.django_db
def test_the_gate_can_be_lifted_for_an_open_catalogue(
    api_client_no_csrf, settings, student, paid_lesson
):
    """The flag stays configurable for a demo or open-catalogue deployment."""
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = False
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(_lesson_url(paid_lesson)).status_code == 200
