"""Enrolment rules: capacity, duplicates, status transitions, history."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.enrollments.models import Enrollment, EnrollmentStatus, LessonProgress

ENROLLMENTS_URL = "/api/v1/enrollments/"


def _enrol(client, student, batch, **extra):
    return client.post(
        ENROLLMENTS_URL,
        {"student_id": str(student.id), "batch_id": str(batch.id), **extra},
        format="json",
    )


@pytest.mark.django_db
def test_admin_enrols_a_student(api_client_no_csrf, admin_user, student_profile, batch):
    api_client_no_csrf.force_login(admin_user)
    response = _enrol(api_client_no_csrf, student_profile, batch)
    assert response.status_code == 201

    body = response.json()
    assert body["code"].startswith("GRS-E-")
    assert body["status"] == EnrollmentStatus.ACTIVE
    assert body["grants_access"] is True
    # The course is derived from the batch, never taken from the client.
    assert body["course_id"] == str(batch.course_id)


@pytest.mark.django_db
def test_the_course_is_always_the_batch_course(admin_user, student_profile, batch):
    from apps.enrollments.services import enrol_student

    created = enrol_student(student=student_profile, batch=batch, actor=admin_user)
    assert created.course_id == batch.course_id


@pytest.mark.django_db
def test_a_duplicate_live_enrolment_is_refused(
    api_client_no_csrf, admin_user, student_profile, batch, enrollment
):
    api_client_no_csrf.force_login(admin_user)
    response = _enrol(api_client_no_csrf, student_profile, batch)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_enrollment"
    assert Enrollment.objects.filter(student=student_profile, batch=batch).count() == 1


@pytest.mark.django_db
def test_the_duplicate_rule_is_enforced_by_the_database(
    admin_user, student_profile, batch, enrollment
):
    """The service check is a friendly message; the index is the real guard."""
    from django.db import IntegrityError, transaction

    from apps.common.identifiers import next_enrolment_code

    duplicate = Enrollment(
        code=next_enrolment_code(),
        student=student_profile,
        batch=batch,
        course=batch.course,
        status=EnrollmentStatus.ACTIVE,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        duplicate.save()


@pytest.mark.django_db
def test_a_student_may_re_enrol_after_cancelling(
    api_client_no_csrf, admin_user, student_profile, batch, enrollment
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user, note="Left"
    )
    api_client_no_csrf.force_login(admin_user)
    response = _enrol(api_client_no_csrf, student_profile, batch)
    assert response.status_code == 201
    # Both rows survive: the cancelled one is history.
    assert Enrollment.objects.filter(student=student_profile, batch=batch).count() == 2


@pytest.mark.django_db
def test_a_full_batch_refuses_further_enrolments(
    api_client_no_csrf, admin_user, batch, published_course
):
    from apps.students.services import create_student

    api_client_no_csrf.force_login(admin_user)
    students = [
        create_student(
            email=f"seat{index}@example.test",
            first_name=f"Seat{index}",
            actor=admin_user,
            send_invitation=False,
        )
        for index in range(4)
    ]

    statuses = [_enrol(api_client_no_csrf, student, batch).status_code for student in students]
    # Capacity is 3, so the first three succeed and the fourth is refused.
    assert statuses[:3] == [201, 201, 201]
    assert statuses[3] == 409

    body = _enrol(api_client_no_csrf, students[3], batch).json()
    assert body["error"]["code"] == "batch_full"


@pytest.mark.django_db(transaction=True)
def test_capacity_holds_under_concurrent_enrolment(admin_user, published_course, trainer_profile):
    """Two threads racing for the last seat: exactly one wins.

    Capacity is a count of other rows, so it cannot be a column constraint. The
    batch row is locked before the count is taken — this proves the lock works.
    """
    import threading
    from datetime import timedelta

    from django.db import connections
    from django.utils import timezone

    from apps.batches.models import BatchStatus
    from apps.batches.services import create_batch, set_batch_status
    from apps.enrollments.services import CapacityError, enrol_student
    from apps.students.services import create_student

    today = timezone.localdate()
    created = create_batch(
        actor=admin_user,
        name="One seat",
        course=published_course,
        trainer=trainer_profile,
        start_date=today,
        end_date=today + timedelta(days=30),
        capacity=1,
    )
    single = set_batch_status(batch=created, target=BatchStatus.ACTIVE, actor=admin_user)

    students = [
        create_student(
            email=f"racer{index}@example.test",
            first_name=f"Racer{index}",
            actor=admin_user,
            send_invitation=False,
        )
        for index in range(2)
    ]

    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def attempt(student):
        try:
            barrier.wait(timeout=5)
            enrol_student(student=student, batch=single, actor=admin_user)
            outcomes.append("enrolled")
        except CapacityError:
            outcomes.append("full")
        except Exception as exc:
            outcomes.append(f"error:{type(exc).__name__}")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=attempt, args=(student,)) for student in students]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert outcomes.count("enrolled") == 1, outcomes
    assert single.enrollments.count() == 1


@pytest.mark.django_db
def test_an_inactive_student_cannot_be_enrolled(
    api_client_no_csrf, admin_user, student_profile, batch
):
    student_profile.user.is_active = False
    student_profile.user.save()

    api_client_no_csrf.force_login(admin_user)
    response = _enrol(api_client_no_csrf, student_profile, batch)
    assert response.status_code == 400
    assert "student" in response.json()["error"]["details"]


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_a_closed_batch_refuses_enrolments(
    api_client_no_csrf, admin_user, student_profile, batch, status
):
    from apps.batches.models import Batch

    Batch.objects.filter(pk=batch.pk).update(status=status)
    api_client_no_csrf.force_login(admin_user)
    response = _enrol(api_client_no_csrf, student_profile, batch)
    assert response.status_code == 400
    assert "batch" in response.json()["error"]["details"]


# ---------------------------------------------------------------------------
# Status transitions and history
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suspending_removes_access_and_reactivating_restores_it(
    api_client_no_csrf, admin_user, enrollment
):
    api_client_no_csrf.force_login(admin_user)
    url = f"{ENROLLMENTS_URL}{enrollment.id}/status/"

    suspended = api_client_no_csrf.post(url, {"status": "suspended", "note": "Fees overdue"})
    assert suspended.status_code == 200
    assert suspended.json()["grants_access"] is False

    restored = api_client_no_csrf.post(url, {"status": "active", "note": "Fees cleared"})
    assert restored.status_code == 200
    assert restored.json()["grants_access"] is True


@pytest.mark.django_db
def test_a_completed_enrolment_keeps_course_access(api_client_no_csrf, admin_user, enrollment):
    """Finishing a course does not take the material away."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{ENROLLMENTS_URL}{enrollment.id}/status/", {"status": "completed"}
    )
    assert response.status_code == 200
    assert response.json()["grants_access"] is True
    assert response.json()["completed_at"] is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "target"),
    [("cancelled", "active"), ("completed", "active"), ("pending", "suspended")],
)
def test_invalid_enrolment_transitions_are_refused(
    api_client_no_csrf, admin_user, enrollment, start, target
):
    Enrollment.objects.filter(pk=enrollment.pk).update(status=start)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{ENROLLMENTS_URL}{enrollment.id}/status/", {"status": target}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_cancelling_preserves_the_record_and_its_progress(
    api_client_no_csrf, admin_user, enrollment, preview_lesson
):
    """§12: educational history is never destroyed casually."""
    from apps.enrollments.services import set_lesson_completion

    set_lesson_completion(student=enrollment.student, lesson=preview_lesson, completed=True)
    assert LessonProgress.objects.filter(enrollment=enrollment).count() == 1

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"{ENROLLMENTS_URL}{enrollment.id}/status/",
        {"status": "cancelled", "note": "Withdrew"},
    )

    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.CANCELLED
    assert enrollment.status_note == "Withdrew"
    # The row and its progress both survive.
    assert Enrollment.objects.filter(pk=enrollment.pk).exists()
    assert LessonProgress.objects.filter(enrollment=enrollment).count() == 1


@pytest.mark.django_db
def test_cancelling_a_batch_cancels_its_enrolments(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/status/",
        {"status": "cancelled", "note": "Not enough students"},
    )
    assert response.status_code == 200

    for row in (enrollment, other_enrollment):
        row.refresh_from_db()
        assert row.status == EnrollmentStatus.CANCELLED
        assert row.grants_access() is False


@pytest.mark.django_db
def test_completing_a_batch_completes_only_its_active_enrolments(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    from apps.enrollments.services import set_enrollment_status

    set_enrollment_status(
        enrollment=other_enrollment,
        target=EnrollmentStatus.SUSPENDED,
        actor=admin_user,
        note="Absent",
    )

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"/api/v1/batches/{batch.id}/status/", {"status": "completed"})

    enrollment.refresh_from_db()
    other_enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.COMPLETED
    # A suspended student did not finish the course, so saying they did would be
    # a false statement in a record a certificate may be issued from.
    assert other_enrollment.status == EnrollmentStatus.SUSPENDED


@pytest.mark.django_db
def test_enrolment_actions_are_audited(api_client_no_csrf, admin_user, enrollment):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"{ENROLLMENTS_URL}{enrollment.id}/status/", {"status": "suspended", "note": "Absent"}
    )
    api_client_no_csrf.post(f"{ENROLLMENTS_URL}{enrollment.id}/status/", {"status": "cancelled"})

    assert AuditLog.objects.filter(action=AuditAction.ENROLLMENT_CREATED).exists()
    suspended = AuditLog.objects.filter(action=AuditAction.ENROLLMENT_SUSPENDED).first()
    assert suspended.context["note"] == "Absent"
    cancelled = AuditLog.objects.filter(action=AuditAction.ENROLLMENT_CANCELLED).first()
    assert cancelled.context["history_preserved"] is True


@pytest.mark.django_db
def test_access_end_date_closes_access(admin_user, student_profile, batch):
    from datetime import timedelta

    from django.utils import timezone

    from apps.enrollments.services import enrol_student

    yesterday = timezone.localdate() - timedelta(days=1)
    created = enrol_student(
        student=student_profile,
        batch=batch,
        actor=admin_user,
        access_end_date=yesterday,
    )
    assert created.status == EnrollmentStatus.ACTIVE
    assert created.grants_access() is False


@pytest.mark.django_db
def test_a_future_start_date_defers_access(admin_user, student_profile, upcoming_batch):
    from apps.enrollments.services import enrol_student

    created = enrol_student(student=student_profile, batch=upcoming_batch, actor=admin_user)
    # The batch starts in a fortnight, so access has not opened yet.
    assert created.grants_access() is False


@pytest.mark.django_db
def test_my_enrollments_returns_only_my_own(
    api_client_no_csrf, student_profile, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(f"{ENROLLMENTS_URL}mine/").json()
    assert len(body) == 1
    assert body[0]["code"] == enrollment.code
