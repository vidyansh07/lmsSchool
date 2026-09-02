"""The batch seeder is safe, idempotent and produces the §20 shape."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.batches.models import Batch, BatchSchedule, BatchStatus
from apps.enrollments.models import Enrollment, EnrollmentStatus, LessonProgress

SEED_PASSWORD = "Staging-Demo-Passw0rd!"


def _seed_prerequisites() -> None:
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")
    call_command("seed_courses")


@pytest.mark.django_db
def test_seed_creates_batches_schedules_and_enrolments():
    _seed_prerequisites()
    call_command("seed_batches")

    assert Batch.objects.count() == 8
    assert BatchSchedule.objects.exists()
    assert Enrollment.objects.exists()


@pytest.mark.django_db
def test_seed_covers_the_required_edge_cases():
    _seed_prerequisites()
    call_command("seed_batches")

    # A full batch, so the capacity refusal is reachable in a browser.
    full = Batch.objects.get(name__endswith="Full cohort")
    assert full.seats_taken() == full.capacity

    # A cancelled batch whose students lost access.
    cancelled = Batch.objects.get(status=BatchStatus.CANCELLED)
    assert cancelled.enrollments.exists()
    assert all(not row.grants_access() for row in cancelled.enrollments.all())

    # A completed batch whose students kept it.
    completed = Batch.objects.get(status=BatchStatus.COMPLETED)
    assert completed.enrollments.filter(status=EnrollmentStatus.COMPLETED).exists()
    assert all(row.grants_access() for row in completed.enrollments.all())

    # A suspended enrolment.
    assert Enrollment.objects.filter(status=EnrollmentStatus.SUSPENDED).exists()


@pytest.mark.django_db
def test_seed_produces_progress_for_a_dashboard_to_show():
    _seed_prerequisites()
    call_command("seed_batches")
    assert LessonProgress.objects.filter(status="completed").exists()


@pytest.mark.django_db
def test_seed_leaves_no_schedule_conflicts_behind():
    """The seeder attempts a clash on purpose; none may survive it."""
    from apps.batches.conflicts import find_conflicts

    _seed_prerequisites()
    call_command("seed_batches")

    for schedule in BatchSchedule.objects.select_related("batch").all():
        assert find_conflicts(schedule) == [], schedule


@pytest.mark.django_db
def test_seed_is_idempotent():
    _seed_prerequisites()
    call_command("seed_batches")
    batches, schedules, enrollments = (
        Batch.objects.count(),
        BatchSchedule.objects.count(),
        Enrollment.objects.count(),
    )

    call_command("seed_batches")
    assert Batch.objects.count() == batches
    assert BatchSchedule.objects.count() == schedules
    assert Enrollment.objects.count() == enrollments


@pytest.mark.django_db
def test_seed_requires_its_prerequisites():
    with pytest.raises(CommandError, match="seed_demo_data"):
        call_command("seed_batches")


@pytest.mark.django_db
def test_seed_is_blocked_where_demo_data_is_not_allowed(settings):
    _seed_prerequisites()
    settings.ALLOW_DEMO_SEED = False
    with pytest.raises(CommandError, match="must never run against production"):
        call_command("seed_batches")


@pytest.mark.django_db
def test_a_seeded_student_can_open_their_course(api_client_no_csrf):
    """End to end on seeded data: an active enrolment opens the content."""
    from apps.courses.models import Lesson, PublishStatus

    _seed_prerequisites()
    call_command("seed_batches")

    enrollment = (
        Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE)
        .select_related("student__user", "batch", "course")
        .first()
    )
    assert enrollment is not None and enrollment.grants_access()

    lesson = Lesson.objects.filter(
        module__course=enrollment.course,
        module__status=PublishStatus.PUBLISHED,
        status=PublishStatus.PUBLISHED,
        is_preview=False,
    ).first()
    assert lesson is not None

    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(f"/api/v1/lessons/{lesson.id}/").status_code == 200
