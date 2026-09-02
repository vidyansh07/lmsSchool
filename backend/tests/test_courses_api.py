"""Course, module and lesson CRUD, ordering, publishing and search."""

from __future__ import annotations

import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.courses.models import (
    Course,
    LessonContentType,
    Module,
    PublishStatus,
)

COURSES_URL = "/api/v1/courses/"
CATEGORIES_URL = "/api/v1/categories/"


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_creates_a_category_with_a_generated_slug(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(CATEGORIES_URL, {"name": "Cloud Computing"}, format="json")
    assert response.status_code == 201
    assert response.json()["slug"] == "cloud-computing"


@pytest.mark.django_db
def test_duplicate_category_slug_is_rejected(api_client_no_csrf, admin_user, category):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        CATEGORIES_URL, {"name": "Linux Again", "slug": category.slug}, format="json"
    )
    assert response.status_code == 400
    assert "slug" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_reserved_slugs_are_refused(api_client_no_csrf, admin_user):
    """`/courses/new` must not be ambiguous between a route and a record."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        CATEGORIES_URL, {"name": "New", "slug": "new"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_students_only_see_active_categories(api_client_no_csrf, student, category):
    from apps.courses.models import Category

    Category.objects.create(name="Retired", slug="retired", is_active=False)
    api_client_no_csrf.force_login(student)
    slugs = {row["slug"] for row in api_client_no_csrf.get(CATEGORIES_URL).json()["results"]}
    assert category.slug in slugs
    assert "retired" not in slugs


@pytest.mark.django_db
def test_students_cannot_create_categories(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert (
        api_client_no_csrf.post(CATEGORIES_URL, {"name": "Nope"}, format="json").status_code == 403
    )


# ---------------------------------------------------------------------------
# Course CRUD
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_creates_a_course_with_a_generated_code_and_slug(
    api_client_no_csrf, admin_user, category
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        COURSES_URL,
        {
            "title": "Docker Fundamentals",
            "category": str(category.id),
            "short_description": "Containers from scratch.",
            "learning_objectives": ["Build images", "Run containers"],
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["code"].startswith("GRS-C-")
    assert body["slug"] == "docker-fundamentals"
    assert body["status"] == PublishStatus.DRAFT
    assert body["learning_objectives"] == ["Build images", "Run containers"]


@pytest.mark.django_db
def test_course_codes_are_unique_and_sequential(api_client_no_csrf, admin_user, category):
    api_client_no_csrf.force_login(admin_user)
    codes = []
    for index in range(3):
        response = api_client_no_csrf.post(
            COURSES_URL, {"title": f"Course {index}", "category": str(category.id)}, format="json"
        )
        codes.append(response.json()["code"])
    assert len(set(codes)) == 3
    assert codes == sorted(codes)


@pytest.mark.django_db
def test_colliding_titles_get_distinct_slugs(api_client_no_csrf, admin_user, category):
    api_client_no_csrf.force_login(admin_user)
    first = api_client_no_csrf.post(
        COURSES_URL, {"title": "Same Title", "category": str(category.id)}, format="json"
    ).json()
    second = api_client_no_csrf.post(
        COURSES_URL, {"title": "Same Title", "category": str(category.id)}, format="json"
    ).json()
    assert first["slug"] != second["slug"]


@pytest.mark.django_db
def test_course_can_be_fetched_by_slug_or_id(api_client_no_csrf, admin_user, published_course):
    api_client_no_csrf.force_login(admin_user)
    by_id = api_client_no_csrf.get(f"{COURSES_URL}{published_course.id}/")
    by_slug = api_client_no_csrf.get(f"{COURSES_URL}{published_course.slug}/")
    assert by_id.status_code == by_slug.status_code == 200
    assert by_id.json()["code"] == by_slug.json()["code"]


@pytest.mark.django_db
def test_admin_updates_a_course(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"{COURSES_URL}{draft_course.id}/",
        {"short_description": "Updated summary.", "difficulty": "advanced"},
        format="json",
    )
    assert response.status_code == 200
    draft_course.refresh_from_db()
    assert draft_course.difficulty == "advanced"


@pytest.mark.django_db
def test_course_creation_and_update_are_audited(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"{COURSES_URL}{draft_course.id}/", {"description": "New body"}, format="json"
    )
    assert AuditLog.objects.filter(action=AuditAction.COURSE_CREATED).exists()
    entry = AuditLog.objects.filter(action=AuditAction.COURSE_UPDATED).first()
    assert entry.context["changed_fields"] == ["description"]


@pytest.mark.django_db
def test_editing_a_published_course_records_the_previous_value(
    api_client_no_csrf, admin_user, published_course
):
    """§9: published content must not change without a trace."""
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"{COURSES_URL}{published_course.id}/", {"title": "Renamed After Publish"}, format="json"
    )
    entry = AuditLog.objects.filter(action=AuditAction.COURSE_UPDATED).first()
    assert entry.context["published_course_edited"] is True
    assert entry.context["previous_values"]["title"] == "Linux Essentials"


# ---------------------------------------------------------------------------
# Publishing workflow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_empty_course_cannot_be_published(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/status/", {"status": "published"}
    )
    assert response.status_code == 400
    problems = response.json()["error"]["details"]["status"]
    assert any("published module" in problem for problem in problems)


@pytest.mark.django_db
def test_publish_checklist_reports_what_is_missing(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{COURSES_URL}{draft_course.id}/publish-checklist/").json()
    assert body["ready"] is False
    assert body["blockers"]


@pytest.mark.django_db
def test_a_complete_course_publishes_and_records_the_time(
    api_client_no_csrf, admin_user, published_course
):
    assert published_course.status == PublishStatus.PUBLISHED
    assert published_course.published_at is not None
    assert AuditLog.objects.filter(action=AuditAction.COURSE_STATUS_CHANGED).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "target"),
    [
        (PublishStatus.ARCHIVED, PublishStatus.PUBLISHED),
        (PublishStatus.DRAFT, PublishStatus.ARCHIVED),
    ],
)
def test_invalid_status_transitions_are_refused(
    api_client_no_csrf, admin_user, draft_course, start, target
):
    Course.objects.filter(pk=draft_course.pk).update(status=start)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/status/", {"status": target}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_transition"


@pytest.mark.django_db
def test_a_published_course_can_be_archived_and_restored(
    api_client_no_csrf, admin_user, published_course
):
    api_client_no_csrf.force_login(admin_user)
    url = f"{COURSES_URL}{published_course.id}/status/"

    assert api_client_no_csrf.post(url, {"status": "archived"}).status_code == 200
    published_course.refresh_from_db()
    assert published_course.status == PublishStatus.ARCHIVED

    assert api_client_no_csrf.post(url, {"status": "draft"}).status_code == 200
    published_course.refresh_from_db()
    assert published_course.status == PublishStatus.DRAFT


@pytest.mark.django_db
def test_archived_courses_leave_the_student_catalogue(
    api_client_no_csrf, admin_user, student, published_course
):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"{COURSES_URL}{published_course.id}/status/", {"status": "archived"})

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(COURSES_URL).json()["count"] == 0


# ---------------------------------------------------------------------------
# Modules and lessons
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_modules_get_sequential_positions(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    positions = []
    for index in range(3):
        response = api_client_no_csrf.post(
            f"{COURSES_URL}{draft_course.id}/modules/", {"title": f"Module {index}"}, format="json"
        )
        positions.append(response.json()["position"])
    assert positions == [0, 1, 2]


@pytest.mark.django_db
def test_modules_can_be_reordered(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    ids = [
        api_client_no_csrf.post(
            f"{COURSES_URL}{draft_course.id}/modules/", {"title": f"M{index}"}, format="json"
        ).json()["id"]
        for index in range(3)
    ]
    reversed_ids = list(reversed(ids))

    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/modules/reorder/",
        {"ordered_ids": reversed_ids},
        format="json",
    )
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == reversed_ids

    positions = list(
        Module.objects.filter(course=draft_course).order_by("position").values_list("id", flat=True)
    )
    assert [str(value) for value in positions] == reversed_ids


@pytest.mark.django_db
def test_a_partial_reorder_is_refused(api_client_no_csrf, admin_user, draft_course):
    """Half an ordering leaves the rest ambiguous, so it is rejected."""
    api_client_no_csrf.force_login(admin_user)
    ids = [
        api_client_no_csrf.post(
            f"{COURSES_URL}{draft_course.id}/modules/", {"title": f"M{index}"}, format="json"
        ).json()["id"]
        for index in range(3)
    ]
    response = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/modules/reorder/",
        {"ordered_ids": ids[:2]},
        format="json",
    )
    assert response.status_code == 400
    assert "ordered_ids" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_lessons_get_positions_and_can_be_reordered(api_client_no_csrf, admin_user, draft_course):
    api_client_no_csrf.force_login(admin_user)
    module_id = api_client_no_csrf.post(
        f"{COURSES_URL}{draft_course.id}/modules/", {"title": "Module"}, format="json"
    ).json()["id"]

    ids = []
    for index in range(3):
        response = api_client_no_csrf.post(
            f"/api/v1/modules/{module_id}/lessons/",
            {
                "title": f"Lesson {index}",
                "content_type": LessonContentType.TEXT,
                "text_content": "Body",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["position"] == index
        ids.append(response.json()["id"])

    reordered = [ids[2], ids[0], ids[1]]
    response = api_client_no_csrf.post(
        f"/api/v1/modules/{module_id}/lessons/reorder/", {"ordered_ids": reordered}, format="json"
    )
    assert [row["id"] for row in response.json()] == reordered


@pytest.mark.django_db
def test_lesson_slugs_are_unique_within_a_module(api_client_no_csrf, admin_user, published_module):
    api_client_no_csrf.force_login(admin_user)
    payload = {
        "title": "Welcome",
        "content_type": LessonContentType.TEXT,
        "text_content": "Another welcome",
    }
    response = api_client_no_csrf.post(
        f"/api/v1/modules/{published_module.id}/lessons/", payload, format="json"
    )
    assert response.status_code == 201
    # The existing lesson already owns "welcome", so this one is suffixed.
    assert response.json()["slug"] != "welcome"


@pytest.mark.django_db
def test_a_video_lesson_requires_a_video(api_client_no_csrf, admin_user, published_module):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/modules/{published_module.id}/lessons/",
        {"title": "Broken video", "content_type": LessonContentType.VIDEO},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_video_lesson_stores_provider_metadata(api_client_no_csrf, admin_user, published_module):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/modules/{published_module.id}/lessons/",
        {
            "title": "Intro video",
            "content_type": LessonContentType.VIDEO,
            "video": {
                "provider": "external_url",
                "source_url": "https://videos.example.test/intro.m3u8",
                "duration_seconds": 620,
                "status": "ready",
            },
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["video"]["provider"] == "external_url"
    assert body["video"]["duration_seconds"] == 620
    # The playable URL is never in the lesson payload.
    assert "source_url" not in str(body)


@pytest.mark.django_db
def test_insecure_video_and_lesson_urls_are_refused(
    api_client_no_csrf, admin_user, published_module
):
    api_client_no_csrf.force_login(admin_user)
    insecure_video = api_client_no_csrf.post(
        f"/api/v1/modules/{published_module.id}/lessons/",
        {
            "title": "Insecure",
            "content_type": LessonContentType.VIDEO,
            "video": {"provider": "external_url", "source_url": "http://videos.example.test/x"},
        },
        format="json",
    )
    insecure_link = api_client_no_csrf.post(
        f"/api/v1/modules/{published_module.id}/lessons/",
        {
            "title": "Insecure link",
            "content_type": LessonContentType.EXTERNAL_LINK,
            "external_url": "http://example.test/doc",
        },
        format="json",
    )
    assert insecure_video.status_code == 400
    assert insecure_link.status_code == 400


@pytest.mark.django_db
def test_module_and_lesson_changes_are_audited(api_client_no_csrf, admin_user, published_module):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        f"/api/v1/modules/{published_module.id}/", {"title": "Renamed"}, format="json"
    )
    assert AuditLog.objects.filter(action=AuditAction.MODULE_UPDATED).exists()
    assert AuditLog.objects.filter(action=AuditAction.MODULE_CREATED).exists()
    assert AuditLog.objects.filter(action=AuditAction.LESSON_CREATED).exists()


@pytest.mark.django_db
def test_content_changes_touch_the_course(api_client_no_csrf, admin_user, published_course):
    """An edit under a published course must be visible at course level."""
    published_course.refresh_from_db()
    assert published_course.content_updated_at is not None


# ---------------------------------------------------------------------------
# Search, filtering and pagination
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_matches_title_code_and_description(
    api_client_no_csrf, admin_user, published_course
):
    api_client_no_csrf.force_login(admin_user)
    for term in (
        "Linux Essentials",
        published_course.code,
        "published course",
    ):
        body = api_client_no_csrf.get(f"{COURSES_URL}?search={term}").json()
        assert body["count"] >= 1, term

    assert api_client_no_csrf.get(f"{COURSES_URL}?search=nothing-matches-this").json()["count"] == 0


@pytest.mark.django_db
def test_courses_can_be_filtered_by_category_and_status(
    api_client_no_csrf, admin_user, published_course, draft_course, category
):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{COURSES_URL}?category={category.slug}").json()["count"] == 2
    assert api_client_no_csrf.get(f"{COURSES_URL}?status=draft").json()["count"] == 1
    assert api_client_no_csrf.get(f"{COURSES_URL}?status=published").json()["count"] == 1


@pytest.mark.django_db
def test_course_listing_is_paginated_and_capped(
    api_client_no_csrf, admin_user, category, published_course, draft_course
):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"{COURSES_URL}?page_size=1").json()
    assert body["count"] == 2
    assert len(body["results"]) == 1
    assert body["total_pages"] == 2

    capped = api_client_no_csrf.get(f"{COURSES_URL}?page_size=10000").json()
    assert capped["page_size"] <= 100


@pytest.mark.django_db
def test_courses_can_be_sorted(api_client_no_csrf, admin_user, published_course, draft_course):
    api_client_no_csrf.force_login(admin_user)
    titles = [
        row["title"]
        for row in api_client_no_csrf.get(f"{COURSES_URL}?ordering=title").json()["results"]
    ]
    assert titles == sorted(titles)


@pytest.mark.django_db
def test_list_payload_carries_counts_without_lesson_bodies(
    api_client_no_csrf, student, published_course
):
    api_client_no_csrf.force_login(student)
    row = api_client_no_csrf.get(COURSES_URL).json()["results"][0]
    assert row["module_count"] == 1
    assert row["lesson_count"] == 2
    assert "text_content" not in str(row)
