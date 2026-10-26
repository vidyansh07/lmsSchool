"""The last step of the desk's registration flow: a course line becomes a batch.

Until this endpoint existed, the desk flow created the person, their
guardians and the charges, and then stopped. The student was registered and
billed and on no batch at all — a student the timetable does not know about —
because `attach_enrollment` was a service with nothing to call it.

What is pinned:

- enrolling a line puts the student on the batch *and* records on the line
  which enrolment it became, in one transaction;
- a line can be enrolled once; asking twice is a conflict, not a second
  enrolment;
- the batch has to teach that line's own course;
- an additional-fee line is not a thing you enrol;
- a cancelled admission enrols nothing;
- the batch is resolved inside the caller's visible set, so another centre's
  batch is the 404 a guessed id gets;
- it needs `enrolment.create` — the capability that governs enrolments, not
  the admission's own right.
"""

from __future__ import annotations

import pytest

from apps.admissions import services as admission_services
from apps.admissions.models import Admission
from apps.common.exceptions import ApplicationError, ConflictError
from apps.enrollments.models import Enrollment

pytestmark = pytest.mark.django_db


def _admission(actor, student_profile, course, **overrides) -> Admission:
    payload = {
        "actor": actor,
        "student": student_profile,
        "lines": [{"kind": "course", "course": course, "quantity": 1, "unit_fee": "20000"}],
    }
    payload.update(overrides)
    return admission_services.create_admission(**payload)


def _course_line(admission: Admission):
    return next(line for line in admission.lines.all() if line.kind == "course")


def url(admission, line) -> str:
    return f"/api/v1/admissions/{admission.pk}/lines/{line.pk}/enrol/"


def test_enrolling_a_line_places_the_student_and_records_which_enrolment(
    admin_user, student_profile, published_course, batch
):
    admission = _admission(admin_user, student_profile, published_course)
    line = _course_line(admission)

    admission_services.enrol_line(actor=admin_user, line=line, batch=batch)

    line.refresh_from_db()
    assert line.enrollment_id is not None
    enrollment = Enrollment.objects.get(pk=line.enrollment_id)
    assert enrollment.student_id == student_profile.pk
    assert enrollment.batch_id == batch.pk


def test_a_line_is_enrolled_once(admin_user, student_profile, published_course, batch):
    admission = _admission(admin_user, student_profile, published_course)
    line = _course_line(admission)
    admission_services.enrol_line(actor=admin_user, line=line, batch=batch)

    with pytest.raises(ConflictError):
        admission_services.enrol_line(actor=admin_user, line=line, batch=batch)

    assert Enrollment.objects.filter(student=student_profile).count() == 1


def test_the_batch_has_to_teach_the_line_s_course(
    admin_user, student_profile, published_course, draft_course, batch
):
    # `batch` teaches `published_course`; this line is for another course.
    admission = _admission(
        admin_user,
        student_profile,
        published_course,
        lines=[{"kind": "course", "course": draft_course, "quantity": 1, "unit_fee": "20000"}],
    )
    line = _course_line(admission)

    with pytest.raises(ApplicationError):
        admission_services.enrol_line(actor=admin_user, line=line, batch=batch)


def test_an_additional_fee_is_not_enrolled(admin_user, student_profile, published_course, batch):
    admission = _admission(
        admin_user,
        student_profile,
        published_course,
        lines=[
            {"kind": "course", "course": published_course, "quantity": 1, "unit_fee": "20000"},
            {"kind": "additional_fee", "label": "Exam fee", "quantity": 1, "unit_fee": "500"},
        ],
    )
    fee_line = next(line for line in admission.lines.all() if line.kind == "additional_fee")

    with pytest.raises(ApplicationError):
        admission_services.enrol_line(actor=admin_user, line=fee_line, batch=batch)


def test_a_cancelled_admission_enrols_nothing(admin_user, student_profile, published_course, batch):
    admission = _admission(admin_user, student_profile, published_course)
    admission_services.cancel_admission(
        actor=admin_user, admission=admission, reason="Changed their mind."
    )
    admission.refresh_from_db()
    line = _course_line(admission)

    with pytest.raises(ApplicationError):
        admission_services.enrol_line(actor=admin_user, line=line, batch=batch)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_enrols_and_returns_the_admission(
    api_client_no_csrf, admin_user, student_profile, published_course, batch
):
    admission = _admission(admin_user, student_profile, published_course)
    line = _course_line(admission)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        url(admission, line), {"batch": str(batch.pk)}, format="json"
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    enrolled = next(row for row in body["lines"] if row["kind"] == "course")
    assert enrolled["enrollment_id"] is not None


def test_a_batch_at_another_centre_is_a_404(
    api_client_no_csrf,
    counsellor_user,
    student_profile,
    published_course,
    other_branch_batch,
):
    admission = _admission(counsellor_user, student_profile, published_course)
    line = _course_line(admission)

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        url(admission, line), {"batch": str(other_branch_batch.pk)}, format="json"
    )

    # Narrowed through `visible_batches`, so this is the 404 a guessed id
    # gets rather than a 403 that would confirm the batch exists.
    assert response.status_code == 404


def test_a_trainer_cannot_enrol_anybody(
    api_client_no_csrf, admin_user, trainer, student_profile, published_course, batch
):
    admission = _admission(admin_user, student_profile, published_course)
    line = _course_line(admission)

    api_client_no_csrf.force_login(trainer)
    response = api_client_no_csrf.post(
        url(admission, line), {"batch": str(batch.pk)}, format="json"
    )

    assert response.status_code == 403
    line.refresh_from_db()
    assert line.enrollment_id is None
