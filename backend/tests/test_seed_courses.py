"""The course seeder is safe, idempotent and produces the shape §21 asks for."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.courses.models import (
    Category,
    Course,
    CourseAssignment,
    Lesson,
    LessonContentType,
    LessonResource,
    Module,
    PublishStatus,
)

SEED_PASSWORD = "Staging-Demo-Passw0rd!"


def _seed_people() -> None:
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_demo_data")


@pytest.mark.django_db
def test_seed_creates_the_required_catalogue_shape():
    _seed_people()
    call_command("seed_courses")

    assert Category.objects.count() == 5
    assert Course.objects.count() == 5
    assert Module.objects.count() == 5 * 3
    assert Lesson.objects.count() == 5 * 3 * 4


@pytest.mark.django_db
def test_seed_produces_mixed_content_types_and_video_metadata():
    _seed_people()
    call_command("seed_courses")

    types = set(Lesson.objects.values_list("content_type", flat=True))
    assert types == {
        LessonContentType.TEXT,
        LessonContentType.VIDEO,
        LessonContentType.DOCUMENT,
        LessonContentType.EXTERNAL_LINK,
    }

    video_lesson = Lesson.objects.filter(content_type=LessonContentType.VIDEO).first()
    assert video_lesson.video is not None
    assert video_lesson.video.duration_seconds
    # Fake by construction: `.invalid` is reserved and can never resolve.
    assert ".invalid" in video_lesson.video.source_url


@pytest.mark.django_db
def test_seed_creates_resources_and_assigns_authors():
    _seed_people()
    call_command("seed_courses")

    assert LessonResource.objects.exists()
    assert all(
        ".invalid" in url
        for url in LessonResource.objects.exclude(external_url="").values_list(
            "external_url", flat=True
        )
    )
    # Every course has an owning trainer, so the assignment path is exercised.
    assert CourseAssignment.objects.count() == 5


@pytest.mark.django_db
def test_seed_leaves_one_course_in_draft():
    """So the "students cannot see drafts" path is real in a seeded environment."""
    _seed_people()
    call_command("seed_courses")

    assert Course.objects.filter(status=PublishStatus.PUBLISHED).count() == 4
    assert Course.objects.filter(status=PublishStatus.DRAFT).count() == 1


@pytest.mark.django_db
def test_seed_is_idempotent():
    _seed_people()
    call_command("seed_courses")
    call_command("seed_courses")

    assert Course.objects.count() == 5
    assert Module.objects.count() == 15
    assert Lesson.objects.count() == 60
    # Positions stay dense and unique after a re-run.
    for module in Module.objects.all():
        positions = sorted(module.lessons.values_list("position", flat=True))
        assert positions == list(range(len(positions)))


@pytest.mark.django_db
def test_seed_requires_an_administrator():
    with pytest.raises(CommandError, match="seed_demo_data"):
        call_command("seed_courses")


@pytest.mark.django_db
def test_seed_is_blocked_where_demo_data_is_not_allowed(settings):
    _seed_people()
    settings.ALLOW_DEMO_SEED = False
    with pytest.raises(CommandError, match="must never run against production"):
        call_command("seed_courses")


@pytest.mark.django_db
def test_seeded_files_are_valid_when_requested():
    _seed_people()
    call_command("seed_courses", "--with-files")

    resource = LessonResource.objects.filter(kind="file").first()
    assert resource is not None
    with resource.file.open("rb") as handle:
        assert handle.read(5) == b"%PDF-"


@pytest.mark.django_db
def test_students_see_only_the_published_seeded_courses(api_client_no_csrf):
    from apps.accounts.models import User

    _seed_people()
    call_command("seed_courses")

    student = User.objects.filter(role="student").first()
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get("/api/v1/courses/").json()
    assert body["count"] == 4
    assert "Data Analysis with SQL" not in str(body)
