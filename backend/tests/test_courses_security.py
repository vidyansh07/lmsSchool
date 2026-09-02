"""Phase 2 security tests.

These call the API directly rather than driving the UI, because the UI is not
the control — hiding a button proves nothing about what an HTTP client can do.
Each test names the attack it defends.
"""

from __future__ import annotations

import uuid

import pytest

from apps.courses.models import Course, CourseAuthorRole, Lesson, PublishStatus
from apps.courses.services import assign_author, create_course

COURSES_URL = "/api/v1/courses/"


# ---------------------------------------------------------------------------
# Unauthorised access to unpublished content
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_students_never_see_draft_courses_in_the_catalogue(
    api_client_no_csrf, student, draft_course, published_course
):
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get(COURSES_URL).json()
    assert body["count"] == 1
    assert body["results"][0]["code"] == published_course.code
    assert draft_course.code not in str(body)


@pytest.mark.django_db
def test_a_student_requesting_a_draft_course_by_id_gets_nothing(
    api_client_no_csrf, student, draft_course
):
    """The core §20 test: swapping the id in the URL must not expose a course."""
    api_client_no_csrf.force_login(student)
    for identifier in (draft_course.id, draft_course.slug):
        response = api_client_no_csrf.get(f"{COURSES_URL}{identifier}/")
        assert response.status_code == 404
        assert draft_course.title not in response.content.decode()


@pytest.mark.django_db
def test_a_student_cannot_reach_a_draft_courses_modules_or_lessons(
    api_client_no_csrf, student, admin_user, draft_course
):
    from apps.courses import services

    module = services.create_module(course=draft_course, actor=admin_user, title="Hidden module")
    lesson = services.create_lesson(
        module=module,
        actor=admin_user,
        title="Hidden lesson",
        content_type="text",
        text_content="Confidential draft body.",
    )

    api_client_no_csrf.force_login(student)
    for url in (
        f"{COURSES_URL}{draft_course.id}/modules/",
        f"/api/v1/modules/{module.id}/",
        f"/api/v1/modules/{module.id}/lessons/",
        f"/api/v1/lessons/{lesson.id}/",
    ):
        response = api_client_no_csrf.get(url)
        assert response.status_code in (403, 404), url
        assert "Confidential draft body" not in response.content.decode()


@pytest.mark.django_db
def test_a_draft_lesson_inside_a_published_course_is_hidden(
    api_client_no_csrf, student, admin_user, published_module
):
    """Filtering one level up is not enough — the next level must filter too."""
    from apps.courses import services

    hidden = services.create_lesson(
        module=published_module,
        actor=admin_user,
        title="Unfinished",
        content_type="text",
        text_content="Draft body that must not leak.",
    )
    assert hidden.status == PublishStatus.DRAFT

    api_client_no_csrf.force_login(student)
    detail = api_client_no_csrf.get(
        f"{COURSES_URL}{published_module.course.slug}/"
    ).content.decode()
    assert "Unfinished" not in detail

    response = api_client_no_csrf.get(f"/api/v1/lessons/{hidden.id}/")
    assert response.status_code == 404
    assert "must not leak" not in response.content.decode()


@pytest.mark.django_db
def test_a_private_course_is_invisible_to_students(
    api_client_no_csrf, student, admin_user, category
):
    course = create_course(
        actor=admin_user, title="Private Programme", category=category, visibility="private"
    )
    Course.objects.filter(pk=course.pk).update(status=PublishStatus.PUBLISHED)

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(COURSES_URL).json()["count"] == 0
    assert api_client_no_csrf.get(f"{COURSES_URL}{course.id}/").status_code == 404


@pytest.mark.django_db
def test_anonymous_callers_are_refused_everywhere(
    api_client_no_csrf, published_course, published_module, preview_lesson
):
    for url in (
        COURSES_URL,
        "/api/v1/categories/",
        f"{COURSES_URL}{published_course.id}/",
        f"/api/v1/modules/{published_module.id}/",
        f"/api/v1/lessons/{preview_lesson.id}/",
        f"/api/v1/lessons/{preview_lesson.id}/video/",
    ):
        response = api_client_no_csrf.get(url)
        assert response.status_code in (401, 403), url


# ---------------------------------------------------------------------------
# IDOR
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_cannot_touch_a_course_they_are_not_assigned_to(
    api_client_no_csrf, trainer, admin_user, category, draft_course
):
    """Assignment is per course. Rights on one grant nothing on another."""
    other = create_course(actor=admin_user, title="Someone Else's Course", category=category)
    assign_author(course=draft_course, user=trainer, role=CourseAuthorRole.OWNER, actor=admin_user)

    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(f"{COURSES_URL}{draft_course.id}/").status_code == 200
    assert api_client_no_csrf.get(f"{COURSES_URL}{other.id}/").status_code == 404
    assert (
        api_client_no_csrf.patch(
            f"{COURSES_URL}{other.id}/", {"title": "Hijacked"}, format="json"
        ).status_code
        == 404
    )
    other.refresh_from_db()
    assert other.title == "Someone Else's Course"


@pytest.mark.django_db
def test_a_trainer_cannot_add_content_to_an_unassigned_course(
    api_client_no_csrf, assigned_trainer, admin_user, category
):
    other = create_course(actor=admin_user, title="Not Mine", category=category)
    api_client_no_csrf.force_login(assigned_trainer)
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{other.id}/modules/", {"title": "Injected"}, format="json"
    )
    assert response.status_code == 404
    assert other.modules.count() == 0


@pytest.mark.django_db
def test_a_trainer_cannot_edit_a_module_belonging_to_another_course(
    api_client_no_csrf, assigned_trainer, published_module
):
    """The module id alone must not be enough — its course is what is checked."""
    api_client_no_csrf.force_login(assigned_trainer)
    response = api_client_no_csrf.patch(
        f"/api/v1/modules/{published_module.id}/", {"title": "Tampered"}, format="json"
    )
    assert response.status_code == 404
    published_module.refresh_from_db()
    assert published_module.title != "Tampered"


@pytest.mark.django_db
def test_a_random_identifier_is_not_found_rather_than_erroring(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    for url in (
        f"{COURSES_URL}{uuid.uuid4()}/",
        f"/api/v1/modules/{uuid.uuid4()}/",
        f"/api/v1/lessons/{uuid.uuid4()}/",
        f"/api/v1/resources/{uuid.uuid4()}/download/",
    ):
        response = api_client_no_csrf.get(url)
        assert response.status_code == 404, url
        assert "Traceback" not in response.content.decode()


# ---------------------------------------------------------------------------
# Unauthorised modification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_students_cannot_create_or_modify_courses(
    api_client_no_csrf, student, category, published_course
):
    api_client_no_csrf.force_login(student)
    assert (
        api_client_no_csrf.post(
            COURSES_URL, {"title": "Student course", "category": str(category.id)}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.patch(
            f"{COURSES_URL}{published_course.id}/", {"title": "Hijacked"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"{COURSES_URL}{published_course.id}/status/", {"status": "archived"}
        ).status_code
        == 403
    )
    published_course.refresh_from_db()
    assert published_course.title == "Linux Essentials"
    assert published_course.status == PublishStatus.PUBLISHED


@pytest.mark.django_db
def test_trainers_hold_no_global_course_rights_by_default(
    api_client_no_csrf, trainer, category, published_course
):
    """§8: a trainer must not get platform-wide course editing for free."""
    from apps.accounts.roles import Capability, UserRole, capabilities_for

    trainer_capabilities = capabilities_for(UserRole.TRAINER)
    for capability in (
        Capability.COURSE_CREATE,
        Capability.COURSE_UPDATE_ANY,
        Capability.COURSE_PUBLISH_ANY,
        Capability.COURSE_VIEW_ANY,
        Capability.CATEGORY_MANAGE,
        Capability.COURSE_ASSIGN_AUTHORS,
    ):
        assert capability not in trainer_capabilities

    api_client_no_csrf.force_login(trainer)
    assert (
        api_client_no_csrf.post(
            COURSES_URL, {"title": "Trainer course", "category": str(category.id)}, format="json"
        ).status_code
        == 403
    )
    assert api_client_no_csrf.get(f"{COURSES_URL}{published_course.id}/authors/").status_code == 403


@pytest.mark.django_db
def test_an_editor_may_edit_but_not_publish(
    api_client_no_csrf, assigned_trainer, draft_course, admin_user
):
    from apps.courses import services

    module = services.create_module(
        course=draft_course, actor=admin_user, title="M", status=PublishStatus.PUBLISHED
    )
    services.create_lesson(
        module=module,
        actor=admin_user,
        title="L",
        content_type="text",
        text_content="Body",
        status=PublishStatus.PUBLISHED,
    )

    api_client_no_csrf.force_login(assigned_trainer)
    assert (
        api_client_no_csrf.patch(
            f"{COURSES_URL}{draft_course.id}/", {"short_description": "Edited"}, format="json"
        ).status_code
        == 200
    )

    # Publishing is refused, but submitting for review is not.
    refused = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/status/", {"status": "published"}
    )
    assert refused.status_code == 400
    assert "review" in str(refused.json()["error"]["details"])

    submitted = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/status/", {"status": "in_review"}
    )
    assert submitted.status_code == 200
    draft_course.refresh_from_db()
    assert draft_course.status == PublishStatus.IN_REVIEW


@pytest.mark.django_db
def test_an_owner_may_publish_their_own_course(
    api_client_no_csrf, owning_trainer, draft_course, admin_user
):
    from apps.courses import services

    module = services.create_module(
        course=draft_course, actor=admin_user, title="M", status=PublishStatus.PUBLISHED
    )
    services.create_lesson(
        module=module,
        actor=admin_user,
        title="L",
        content_type="text",
        text_content="Body",
        status=PublishStatus.PUBLISHED,
    )

    api_client_no_csrf.force_login(owning_trainer)
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/status/", {"status": "published"}
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_only_authorised_roles_can_be_assigned_as_authors(
    api_client_no_csrf, admin_user, student, draft_course
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/authors/",
        {"user_id": str(student.id), "role": "owner"},
        format="json",
    )
    assert response.status_code == 400
    assert "user" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_removing_an_assignment_removes_the_access(
    api_client_no_csrf, owning_trainer, draft_course, admin_user
):
    api_client_no_csrf.force_login(owning_trainer)
    assert api_client_no_csrf.get(f"{COURSES_URL}{draft_course.id}/").status_code == 200

    from apps.courses.services import remove_author

    remove_author(course=draft_course, user=owning_trainer, actor=admin_user)
    assert api_client_no_csrf.get(f"{COURSES_URL}{draft_course.id}/").status_code == 404


# ---------------------------------------------------------------------------
# Mass assignment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "published"},
        {"code": "GRS-C-99999"},
        {"published_at": "2020-01-01T00:00:00Z"},
        {"created_by": "00000000-0000-0000-0000-000000000000"},
        {"content_updated_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_protected_course_fields_cannot_be_set_through_the_editor(
    api_client_no_csrf, admin_user, draft_course, payload
):
    """Status and identifiers have their own endpoints and rules."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(f"{COURSES_URL}{draft_course.id}/", payload, format="json")
    assert response.status_code == 400
    assert set(payload) & set(response.json()["error"]["details"])

    draft_course.refresh_from_db()
    assert draft_course.status == PublishStatus.DRAFT
    assert draft_course.code.startswith("GRS-C-")


@pytest.mark.django_db
def test_lesson_position_and_status_cannot_be_set_through_the_editor(
    api_client_no_csrf, admin_user, preview_lesson
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/lessons/{preview_lesson.id}/", {"position": 99, "status": "draft"}, format="json"
    )
    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert "position" in details or "status" in details


# ---------------------------------------------------------------------------
# The enrolment gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_preview_lessons_stay_readable_when_enrolment_is_required(
    api_client_no_csrf, settings, student, preview_lesson
):
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get(f"/api/v1/lessons/{preview_lesson.id}/")
    assert response.status_code == 200
    assert response.json()["text_content"] == "Welcome to the course."


@pytest.mark.django_db
def test_paid_lesson_content_is_withheld_when_enrolment_is_required(
    api_client_no_csrf, settings, student, paid_lesson
):
    """Proves the enrolment seam works before enrolment itself exists."""
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    api_client_no_csrf.force_login(student)

    response = api_client_no_csrf.get(f"/api/v1/lessons/{paid_lesson.id}/")
    assert response.status_code == 403
    assert "Secret paid content" not in response.content.decode()
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_the_outline_stays_visible_when_content_is_gated(
    api_client_no_csrf, settings, student, published_course, paid_lesson
):
    """A gated course must still be browsable, or nobody would ever enrol."""
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    api_client_no_csrf.force_login(student)

    body = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/").json()
    lesson_titles = [lesson["title"] for module in body["modules"] for lesson in module["lessons"]]
    assert paid_lesson.title in lesson_titles
    assert "Secret paid content" not in str(body)


@pytest.mark.django_db
def test_authors_still_see_their_own_gated_content(
    api_client_no_csrf, settings, owning_trainer, draft_course, admin_user
):
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    from apps.courses import services

    module = services.create_module(course=draft_course, actor=admin_user, title="M")
    lesson = services.create_lesson(
        module=module, actor=admin_user, title="L", content_type="text", text_content="Author body"
    )

    api_client_no_csrf.force_login(owning_trainer)
    response = api_client_no_csrf.get(f"/api/v1/lessons/{lesson.id}/")
    assert response.status_code == 200
    assert response.json()["text_content"] == "Author body"


# ---------------------------------------------------------------------------
# Excessive data exposure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_video_url_is_never_in_a_lesson_or_course_payload(
    api_client_no_csrf, admin_user, student, published_module
):
    from apps.courses import services

    lesson = services.create_lesson(
        module=published_module,
        actor=admin_user,
        title="Video lesson",
        content_type="video",
        status=PublishStatus.PUBLISHED,
        is_preview=True,
        video={
            "provider": "external_url",
            "source_url": "https://videos.example.test/private-asset.m3u8",
            "status": "ready",
        },
    )

    api_client_no_csrf.force_login(student)
    for url in (
        f"{COURSES_URL}{published_module.course.slug}/",
        f"/api/v1/lessons/{lesson.id}/",
        f"/api/v1/modules/{published_module.id}/",
    ):
        body = api_client_no_csrf.get(url).content.decode()
        assert "private-asset.m3u8" not in body, url

    # It is available from the playback endpoint, which authorises first.
    playback = api_client_no_csrf.get(f"/api/v1/lessons/{lesson.id}/video/")
    assert playback.status_code == 200
    assert playback.json()["playback_url"] == "https://videos.example.test/private-asset.m3u8"


@pytest.mark.django_db
def test_video_playback_is_refused_without_content_access(
    api_client_no_csrf, settings, admin_user, student, published_module
):
    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    from apps.courses import services

    lesson = services.create_lesson(
        module=published_module,
        actor=admin_user,
        title="Paid video",
        content_type="video",
        status=PublishStatus.PUBLISHED,
        video={
            "provider": "external_url",
            "source_url": "https://videos.example.test/paid.m3u8",
            "status": "ready",
        },
    )
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.get(f"/api/v1/lessons/{lesson.id}/video/")
    assert response.status_code == 403
    assert "paid.m3u8" not in response.content.decode()


@pytest.mark.django_db
def test_instructor_contact_details_are_not_exposed(
    api_client_no_csrf, student, published_course, trainer, admin_user
):
    assign_author(
        course=published_course, user=trainer, role=CourseAuthorRole.OWNER, actor=admin_user
    )
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/").content.decode()
    assert trainer.email not in body
    assert "Tina" in body  # the name is shown, the address is not


@pytest.mark.django_db
def test_internal_notes_style_fields_are_absent_from_student_payloads(
    api_client_no_csrf, student, published_course
):
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/").json()
    for field in ("created_by", "updated_by"):
        assert field not in body


@pytest.mark.django_db
def test_lesson_summaries_never_carry_the_body(api_client_no_csrf, student, published_course):
    """The outline is public within a course; the body is not."""
    api_client_no_csrf.force_login(student)
    body = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/").json()
    lessons = [lesson for module in body["modules"] for lesson in module["lessons"]]
    assert lessons
    for lesson in lessons:
        assert "text_content" not in lesson


@pytest.mark.django_db
def test_no_endpoint_returns_a_stack_trace(api_client_no_csrf, student, published_course):
    api_client_no_csrf.force_login(student)
    response = api_client_no_csrf.patch(
        f"{COURSES_URL}{published_course.id}/", {"category": "not-a-uuid"}, format="json"
    )
    body = response.content.decode()
    assert "Traceback" not in body
    assert "django" not in body.lower() or "error" in body.lower()


@pytest.mark.django_db
def test_the_visible_queryset_bounds_every_listing(api_client_no_csrf, student, draft_course):
    """Paging or sorting must not reach past what the caller may see."""
    api_client_no_csrf.force_login(student)
    for query in (
        "?page_size=100",
        "?ordering=-created_at",
        "?status=draft",
        "?visibility=private",
    ):
        body = api_client_no_csrf.get(f"{COURSES_URL}{query}").json()
        assert body["count"] == 0, query


@pytest.mark.django_db
def test_lessons_of_an_archived_course_become_unreachable(
    api_client_no_csrf, admin_user, student, published_course, preview_lesson
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"{COURSES_URL}{published_course.id}/status/", {"status": "archived"})

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(f"/api/v1/lessons/{preview_lesson.id}/").status_code == 404
    assert Lesson.objects.filter(pk=preview_lesson.pk).exists()
