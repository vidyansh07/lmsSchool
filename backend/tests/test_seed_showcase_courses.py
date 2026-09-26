"""Stage 3 of the showcase: the catalogue exists once, in every state the
course, learning and exam screens need, and a second run creates nothing.

Runs the command up to and including ``courses`` on the empty test database.
There are no SITP rows here, so the imported-course upgrade is exercised on
two stand-ins made the way the workbook import makes them — a track titled
``SITP ACE 2026 — …`` and the junk-titled ``python pro progamming`` — each
with the draft *Syllabus* module the import leaves behind. A third, unrelated
draft course stands by to prove the stage leaves alone what is not its own.

One test runs the command twice and checks everything, rather than one test
per promise: the people stage in front of it makes a hundred accounts, and a
run per test would put the file well over its time budget.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db.models import Q

from apps.academics.models import AcademicPolicy, PolicyScope
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.common.showcase.stages.s03_courses import _status_path
from apps.common.showcase.stages.s03_courses_content import (
    CATEGORIES,
    COURSES,
    QUESTIONS,
    RETIRED_QUESTION,
    SHARED_QUESTIONS,
    sitp_lessons,
    track_for,
)
from apps.courses.models import (
    Category,
    Course,
    CourseAssignment,
    Lesson,
    LessonContentType,
    LessonResource,
    Module,
    PublishStatus,
    ResourceKind,
    VideoAsset,
    VideoProvider,
)
from apps.courses.services import create_category, create_course, create_module
from apps.questions.models import Difficulty, Question, QuestionOption, QuestionType

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = (
    "category",
    "course",
    "course_author",
    "module",
    "lesson",
    "lesson_resource",
    "video_asset",
    "academic_policy",
    "question",
)

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks) -> str:
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    return {
        "categories": Category.objects.count(),
        "courses": Course.objects.count(),
        "authors": CourseAssignment.objects.count(),
        "modules": Module.objects.count(),
        "lessons": Lesson.objects.count(),
        "resources": LessonResource.objects.count(),
        "videos": VideoAsset.objects.count(),
        "questions": Question.objects.count(),
        "options": QuestionOption.objects.count(),
        "policies": AcademicPolicy.objects.count(),
        "course_audit": AuditLog.objects.filter(
            resource_type__in=[
                "category",
                "course",
                "module",
                "lesson",
                "lesson_resource",
                "question",
                "academic_policy",
            ]
        ).count(),
    }


@pytest.fixture
def imported(db):
    """Two stand-ins for what the SITP workbook import leaves behind, plus a
    bystander course the stage has no business with."""
    actor = User.objects.create_superuser(
        email="importer@sitp.grras.invalid", password="Importer-Passw0rd!", first_name="Import"
    )
    category = create_category(actor=actor, name="Internship Training", slug="internship-training")
    made = {}
    for slug, title in (
        ("sitp-ace-2026-cloud-computing-with-ai", "SITP ACE 2026 — Cloud Computing With AI"),
        ("python-pro-progamming", "python pro progamming"),
        ("bystander", "An unrelated draft course"),
    ):
        course = create_course(
            actor=actor,
            title=title,
            slug=slug,
            category=category,
            short_description="Imported from the SITP workbook.",
        )
        create_module(course=course, actor=actor, title="Syllabus", status=PublishStatus.DRAFT)
        made[slug] = course
    return made


@pytest.mark.django_db
def test_courses_stage_builds_the_catalogue_and_is_idempotent(
    imported, django_capture_on_commit_callbacks
):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table[label][0] == 0, f"second run created {label}: {table[label]}"
        assert table[label][1] > 0, f"second run found no {label}"
    assert counts() == after_first
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"

    # --- Categories ---------------------------------------------------------
    for slug, name, _description, _position, active in CATEGORIES:
        category = Category.objects.get(slug=slug)
        assert category.name == name
        assert category.is_active is active
    assert Category.objects.get(slug="hardware-repair").is_active is False

    # --- The eight showcase courses -----------------------------------------
    by_slug = {course.slug: course for course in Course.objects.all()}
    for spec in COURSES:
        course = by_slug[spec.slug]
        assert course.status == spec.status, spec.slug
        assert re.fullmatch(r"GRS-C-\d{5}", course.code)
        assert course.default_fee == spec.fee
        assert course.category.slug == spec.category
        assert course.visibility == spec.visibility
        assert course.difficulty == spec.difficulty
        assert len(course.learning_objectives) == len(spec.objectives)
        assert course.created_by.email == "owner@grras.com"

        published_modules = course.modules.filter(status=PublishStatus.PUBLISHED)
        assert published_modules.count() == 3, spec.slug
        lessons = Lesson.objects.filter(module__course=course)
        kinds = set(lessons.values_list("content_type", flat=True))
        assert kinds == set(LessonContentType.values), spec.slug
        assert lessons.filter(is_preview=True).count() == 1, spec.slug
        assert lessons.filter(is_required=False).count() == 1, spec.slug
        assert LessonResource.objects.filter(
            lesson__module__course=course, kind=ResourceKind.LINK
        ).exists(), spec.slug

        for lesson in lessons.filter(content_type=LessonContentType.DOCUMENT):
            assert lesson.status == PublishStatus.PUBLISHED
            resource = lesson.resources.get(kind=ResourceKind.FILE)
            assert resource.content_type == "application/pdf"
            assert resource.file.name.startswith("course-resources/")
            with resource.file.open("rb") as handle:
                assert handle.read(5) == b"%PDF-"
        for lesson in lessons.filter(content_type=LessonContentType.VIDEO):
            assert lesson.video.provider == VideoProvider.EXTERNAL_URL
            assert lesson.video.source_url.startswith("https://videos.example.invalid/")
        for lesson in lessons.filter(content_type=LessonContentType.EXTERNAL_LINK):
            assert lesson.external_url.startswith("https://")
        for lesson in lessons.filter(content_type=LessonContentType.TEXT):
            assert len(lesson.text_content) > 200

    statuses = {spec.status for spec in COURSES}
    assert statuses == set(PublishStatus.values)
    archived = by_slug["ccna"]
    assert archived.published_at is not None, "archived through published"

    devops = by_slug["devops-engineering"]
    assert devops.modules.filter(status=PublishStatus.DRAFT).count() == 1
    assert devops.modules.filter(status=PublishStatus.ARCHIVED).count() == 1
    assert devops.modules.count() == 5

    # --- Authors: the trainers see their courses ----------------------------
    assert CourseAssignment.objects.filter(
        course=by_slug["rhcsa"], user__email="trainer@grras.com", role="owner"
    ).exists()
    assert CourseAssignment.objects.filter(
        course=devops, user__email="shivani.nair@grras.com", role="editor"
    ).exists()
    assert CourseAssignment.objects.filter(
        course=by_slug["python-django-full-stack"], user__email="neha.saxena@grras.com"
    ).exists()

    # --- Course-level policy ------------------------------------------------
    policy = AcademicPolicy.objects.get(scope=PolicyScope.COURSE, course=by_slug["rhcsa"])
    assert policy.minimum_attendance_percent == Decimal("80.00")
    assert AcademicPolicy.objects.filter(scope=PolicyScope.COURSE).count() == 1

    # --- The imported stand-ins: upgraded, once -----------------------------
    sitp = Course.objects.get(slug="sitp-ace-2026-cloud-computing-with-ai")
    assert sitp.status == PublishStatus.PUBLISHED
    programme = sitp.modules.get(title="Programme content")
    assert programme.status == PublishStatus.PUBLISHED
    assert list(programme.lessons.values_list("slug", flat=True)) == [
        "syllabus-overview",
        "lab-guide",
        "assessment-guide",
    ]
    assert "cloud computing" in programme.lessons.get(slug="syllabus-overview").text_content
    assert sitp.modules.get(title="Syllabus").status == PublishStatus.DRAFT, "left as found"
    assert sitp.modules.count() == 2
    renamed = Course.objects.get(slug="python-pro-progamming")
    assert renamed.title == "Python Pro Programming"
    assert renamed.status == PublishStatus.PUBLISHED
    assert "imported courses: 2 published" in first
    assert "imported courses: 2 published" in second, "the renamed course is still found"
    assert "renamed to 'Python Pro Programming'" in first
    assert "renamed" not in second

    # --- The bystander: untouched ---------------------------------------
    bystander = Course.objects.get(slug="bystander")
    assert bystander.status == PublishStatus.DRAFT
    assert bystander.modules.count() == 1
    assert not Lesson.objects.filter(module__course=bystander).exists()
    assert not Question.objects.filter(course=bystander).exists()

    # --- The question bank --------------------------------------------------
    for slug, items in QUESTIONS.items():
        course = by_slug[slug]
        assert course.status == PublishStatus.PUBLISHED
        bank = Question.objects.filter(course=course, is_active=True)
        assert bank.count() == len(items), slug
        for difficulty in Difficulty.values:
            assert bank.filter(question_type=QuestionType.MCQ, difficulty=difficulty).count() == 4
        assert bank.filter(question_type=QuestionType.TRUE_FALSE).count() == 4
        assert bank.filter(question_type=QuestionType.SHORT_ANSWER).count() == 3
        assert bank.filter(question_type=QuestionType.LONG_ANSWER).count() == 2
        assert bank.filter(question_type=QuestionType.MULTIPLE).count() == 2
        assert bank.filter(negative_marks__gt=0).count() == 4, "hard MCQs carry a penalty"
        for question in bank:
            assert all(tag == tag.lower() and " " not in tag for tag in question.tags)
            if question.question_type == QuestionType.SHORT_ANSWER:
                assert question.answer_key
            if question.question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
                assert question.options.filter(is_correct=True).count() == 1
        # What an exam's readiness check counts: the course's active questions
        # plus the shared bank, per section filter. Two sections of ten
        # single-answer questions and five true/false must be drawable.
        pool = Question.objects.usable().filter(Q(course=course) | Q(course__isnull=True))
        assert pool.filter(question_type=QuestionType.MCQ).count() >= 10
        assert pool.filter(question_type=QuestionType.TRUE_FALSE).count() >= 5

    draft_or_unpublished = [s.slug for s in COURSES if s.status != PublishStatus.PUBLISHED]
    assert not Question.objects.filter(course__slug__in=draft_or_unpublished).exists()

    shared = Question.objects.filter(course__isnull=True)
    assert shared.count() == len(SHARED_QUESTIONS)

    retired_slug, retired_item = RETIRED_QUESTION
    retired = Question.objects.get(course__slug=retired_slug, text=retired_item[2])
    assert retired.is_active is False
    assert not Question.objects.usable().filter(pk=retired.pk).exists()
    assert "retired question on rhcsa: retired" in first
    assert "retired question on rhcsa: found retired" in second

    # Every question was written by a service: an audit row per question.
    assert AuditLog.objects.filter(resource_type="question").count() >= (Question.objects.count())
    assert SEED_PASSWORD not in first + second


@pytest.mark.django_db
def test_without_an_import_the_upgrade_is_a_no_op(django_capture_on_commit_callbacks):
    output = run(django_capture_on_commit_callbacks)
    assert "imported courses: none on this database" in output
    assert Course.objects.count() == len(COURSES)
    assert not Module.objects.filter(title="Programme content").exists()


def test_status_paths_follow_the_transition_table():
    assert _status_path("draft", "draft") == []
    assert _status_path("draft", "published") == ["published"]
    assert _status_path("draft", "archived") == ["published", "archived"]
    assert _status_path("archived", "in_review") == ["draft", "in_review"]
    assert _status_path("published", "in_review") == ["draft", "in_review"]


def test_sitp_tracks_get_material_about_their_own_subject():
    assert track_for("SITP ACE 2026 — Agentic AI").subject == "agentic AI systems"
    assert "Power BI" in track_for("SITP ACE 2026 — MS-PL300 (Microsoft Power BI)").subject
    assert "foundation" in track_for("SITP ACE 2026 — Group C").subject
    lessons = sitp_lessons("SITP ACE 2026 — SOC Cyber Security")
    assert [lesson.slug for lesson in lessons] == [
        "syllabus-overview",
        "lab-guide",
        "assessment-guide",
    ]
    assert "Wazuh" in lessons[1].body
    assert lessons[0].preview is True
    # The same text every run: it is a key the stage finds lessons by.
    assert sitp_lessons("SITP ACE 2026 — Group A") == sitp_lessons("SITP ACE 2026 — Group A")
