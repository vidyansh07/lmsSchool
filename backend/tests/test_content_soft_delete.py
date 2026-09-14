"""Course content, assignments, projects, questions and tests are soft-deleted
(D-131): removed from every normal query, kept in the bin, restorable, never
purged by a schedule.

- a deleted lesson disappears from the course tree for an administrator and
  from the player for a student, and its resources go with it;
- deleting a module takes its lessons; restoring the module brings them back;
- the bin lists content by kind and an administrator restores from it;
- an assignment, a project, a question and a test each land in the bin.
"""

from __future__ import annotations

import pytest

from apps.courses.models import Lesson, LessonResource, Module

BIN_URL = "/api/v1/recovery/"


def _restore_url(label: str, pk) -> str:
    return f"{BIN_URL}{label}/{pk}/restore/"


@pytest.mark.django_db
def test_a_deleted_lesson_leaves_the_tree_and_comes_back(
    api_client_no_csrf, admin_user, published_course, published_module, paid_lesson
):
    from apps.courses.services import delete_lesson

    delete_lesson(lesson=paid_lesson, actor=admin_user, reason="Wrong module.")
    assert not Lesson.objects.filter(pk=paid_lesson.pk).exists()
    assert Lesson.all_objects.filter(pk=paid_lesson.pk).exists()

    api_client_no_csrf.force_login(admin_user)
    tree = api_client_no_csrf.get(f"/api/v1/courses/{published_course.pk}/").json()
    titles = {
        lesson["title"]
        for module in tree.get("modules", [])
        for lesson in module.get("lessons", [])
    }
    assert paid_lesson.title not in titles

    bin_rows = api_client_no_csrf.get(f"{BIN_URL}courses.lesson/").json()
    rows = bin_rows["results"] if isinstance(bin_rows, dict) else bin_rows
    assert any(row["id"] == str(paid_lesson.pk) for row in rows)
    assert any(row["delete_reason"] == "Wrong module." for row in rows)

    restored = api_client_no_csrf.post(
        _restore_url("courses.lesson", paid_lesson.pk), {}, format="json"
    )
    assert restored.status_code == 200, restored.data
    assert Lesson.objects.filter(pk=paid_lesson.pk).exists()


@pytest.mark.django_db
def test_a_deleted_module_takes_its_lessons_and_returns_with_them(
    admin_user, published_module, paid_lesson, preview_lesson
):
    from apps.common.deletion import restore
    from apps.courses.services import delete_module

    delete_module(module=published_module, actor=admin_user)
    assert not Module.objects.filter(pk=published_module.pk).exists()
    assert not Lesson.objects.filter(module=published_module).exists()
    assert Lesson.all_objects.filter(module=published_module).count() == 2

    module = Module.all_objects.get(pk=published_module.pk)
    restore(
        instance=module,
        actor=admin_user,
        cascade=(Lesson.all_objects.filter(module=module),),
    )
    assert Module.objects.filter(pk=published_module.pk).exists()
    assert Lesson.objects.filter(module=published_module).count() == 2


@pytest.mark.django_db
def test_a_student_no_longer_sees_a_deleted_lesson(
    api_client_no_csrf, admin_user, enrollment, published_course, paid_lesson
):
    from apps.courses.services import delete_lesson

    api_client_no_csrf.force_login(enrollment.student.user)
    before = api_client_no_csrf.get(f"/api/v1/courses/{published_course.slug}/")
    assert before.status_code == 200
    delete_lesson(lesson=paid_lesson, actor=admin_user)
    after = api_client_no_csrf.get(f"/api/v1/lessons/{paid_lesson.pk}/")
    assert after.status_code == 404


@pytest.mark.django_db
def test_a_resource_keeps_its_file_until_purged(admin_user, paid_lesson):
    from django.core.files.base import ContentFile

    from apps.courses.services import delete_resource

    resource = LessonResource.objects.create(
        lesson=paid_lesson, title="Slides", kind="file", position=1
    )
    resource.file.save("slides.txt", ContentFile(b"hello"), save=True)
    delete_resource(resource=resource, actor=admin_user)
    kept = LessonResource.all_objects.get(pk=resource.pk)
    assert kept.deleted_at is not None
    assert kept.file and kept.file.storage.exists(kept.file.name)


@pytest.mark.django_db
def test_assignment_project_question_and_test_land_in_the_bin(
    api_client_no_csrf, admin_user, batch, published_course, category
):
    from apps.assessments.services import create_assessment, delete_assessment
    from apps.assignments.services import create_assignment, delete_assignment
    from apps.projects.services import create_project, delete_project
    from apps.questions.models import QuestionType
    from apps.questions.services import create_question, delete_question

    assignment = create_assignment(
        actor=admin_user, course=published_course, batch=batch, title="Essay"
    )
    delete_assignment(assignment=assignment, actor=admin_user)
    project = create_project(
        actor=admin_user, course=published_course, batch=batch, title="Capstone"
    )
    delete_project(project=project, actor=admin_user)
    question = create_question(
        actor=admin_user,
        course=published_course,
        text="What is 2 + 2?",
        question_type=QuestionType.SHORT_ANSWER,
        answer_key=["4"],
    )
    delete_question(question=question, actor=admin_user)
    assessment = create_assessment(
        actor=admin_user, batch=batch, title="Week 1", delivery="offline"
    )
    delete_assessment(assessment=assessment, actor=admin_user)

    api_client_no_csrf.force_login(admin_user)
    summary = api_client_no_csrf.get(BIN_URL).json()
    labels = {row["label"]: row["deleted_count"] for row in summary}
    for label in (
        "assignments.assignment",
        "projects.project",
        "questions.question",
        "assessments.assessment",
    ):
        assert labels.get(label) == 1, (label, labels)


@pytest.mark.django_db
def test_restoring_a_module_from_the_bin_brings_its_lessons_back(
    api_client_no_csrf, admin_user, published_module, paid_lesson, preview_lesson
):
    from apps.courses.services import delete_module

    delete_module(module=published_module, actor=admin_user)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        _restore_url("courses.module", published_module.pk), {}, format="json"
    )
    assert response.status_code == 200, response.data
    assert Module.objects.filter(pk=published_module.pk).exists()
    assert Lesson.objects.filter(module=published_module).count() == 2


@pytest.mark.django_db
def test_a_deleted_lesson_does_not_reserve_its_slug_or_position(
    admin_user, published_module, paid_lesson
):
    """Partial uniqueness (D-131): the slot a deleted row held is free again.
    Making the same lesson again succeeds; restoring the old one while the new
    one holds its place is refused, not crashed."""
    from apps.common.deletion import restore
    from apps.common.exceptions import ConflictError
    from apps.courses.services import create_lesson, delete_lesson

    delete_lesson(lesson=paid_lesson, actor=admin_user, reason="Redo.")
    again = create_lesson(
        module=published_module,
        actor=admin_user,
        title=paid_lesson.title,
        slug=paid_lesson.slug,
        content_type=paid_lesson.content_type,
        text_content=paid_lesson.text_content or "Again.",
    )
    assert again.slug == paid_lesson.slug
    assert again.position == paid_lesson.position

    with pytest.raises(ConflictError):
        restore(instance=Lesson.all_objects.get(pk=paid_lesson.pk), actor=admin_user)
    assert Lesson.all_objects.get(pk=paid_lesson.pk).deleted_at is not None
    assert Lesson.objects.filter(pk=again.pk).exists()
