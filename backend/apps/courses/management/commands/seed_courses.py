"""Create fake course catalogue data for local and staging environments.

Same safety rules as the account seeder: refuses to run where demo data is not
allowed, is idempotent, and uses obviously fake material — placeholder copy,
``.invalid`` video URLs that can never resolve, and generated sample files
rather than anything copied from real course material.

Produces the shape §21 asks for: 5 categories, 5 courses, 3 modules each, 4
lessons per module, mixed content types, resources and video metadata.
"""

from __future__ import annotations

from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.common.identifiers import next_course_code
from apps.courses.models import (
    Category,
    Course,
    CourseAssignment,
    CourseAuthorRole,
    CourseDifficulty,
    CourseVisibility,
    Lesson,
    LessonContentType,
    LessonResource,
    Module,
    PublishStatus,
    ResourceKind,
    VideoAsset,
    VideoProvider,
    VideoStatus,
)

MODULES_PER_COURSE = 3
LESSONS_PER_MODULE = 4

CATEGORIES = [
    ("Linux & Systems", "linux-systems", "Operating systems and administration."),
    ("Programming", "programming", "Languages, frameworks and tooling."),
    ("Cloud & DevOps", "cloud-devops", "Cloud platforms, containers and pipelines."),
    ("Networking", "networking", "Routing, switching and network security."),
    ("Data & Analytics", "data-analytics", "Databases, analysis and visualisation."),
]

COURSES = [
    {
        "title": "Linux Administration Foundations",
        "category": "linux-systems",
        "difficulty": CourseDifficulty.BEGINNER,
        "duration": 2400,
        "short": "Install, configure and operate a Linux server with confidence.",
        "objectives": [
            "Navigate the filesystem from the shell",
            "Manage users, groups and permissions",
            "Install and update software with the package manager",
        ],
        "prerequisites": ["Comfortable using a computer", "No prior Linux experience needed"],
        "status": PublishStatus.PUBLISHED,
    },
    {
        "title": "Python Programming in Practice",
        "category": "programming",
        "difficulty": CourseDifficulty.BEGINNER,
        "duration": 3000,
        "short": "Write, test and structure real Python programs.",
        "objectives": [
            "Work with core data types",
            "Write functions and classes",
            "Test your code",
        ],
        "prerequisites": ["Basic computer literacy"],
        "status": PublishStatus.PUBLISHED,
    },
    {
        "title": "Containers and Kubernetes",
        "category": "cloud-devops",
        "difficulty": CourseDifficulty.INTERMEDIATE,
        "duration": 2700,
        "short": "Package applications in containers and run them on a cluster.",
        "objectives": [
            "Build container images",
            "Compose multi-service apps",
            "Deploy to a cluster",
        ],
        "prerequisites": ["Linux command line", "Basic networking"],
        "status": PublishStatus.PUBLISHED,
    },
    {
        "title": "Network Fundamentals",
        "category": "networking",
        "difficulty": CourseDifficulty.BEGINNER,
        "duration": 1800,
        "short": "How networks actually move a packet from one machine to another.",
        "objectives": ["Explain the OSI layers", "Configure addressing", "Diagnose common faults"],
        "prerequisites": [],
        "status": PublishStatus.PUBLISHED,
    },
    {
        # Deliberately left in draft so the seeded environment exercises the
        # "students must not see unpublished courses" path in a real browser.
        "title": "Data Analysis with SQL",
        "category": "data-analytics",
        "difficulty": CourseDifficulty.INTERMEDIATE,
        "duration": 2100,
        "short": "Answer business questions with SQL. Still being written.",
        "objectives": ["Write joins and aggregates", "Design a reporting query"],
        "prerequisites": ["Spreadsheet experience"],
        "status": PublishStatus.DRAFT,
    },
]

MODULE_TITLES = ["Getting started", "Core concepts", "Putting it together"]

#: (content type, title suffix). Cycled so every module carries a mix.
LESSON_SHAPES = [
    (LessonContentType.TEXT, "Overview"),
    (LessonContentType.VIDEO, "Walkthrough"),
    (LessonContentType.DOCUMENT, "Reference sheet"),
    (LessonContentType.EXTERNAL_LINK, "Further reading"),
]

SAMPLE_TEXT = (
    "This is placeholder course material for a demo environment. It exists so "
    "the player, navigation and access rules can be exercised end to end. "
    "Nothing here is real teaching content.\n\n"
    "Key points:\n\n"
    "- Placeholder point one\n"
    "- Placeholder point two\n"
    "- Placeholder point three\n"
)


def _sample_pdf(title: str) -> SimpleUploadedFile:
    """A minimal, structurally valid PDF built in memory.

    Generated rather than committed: no binary sample files in the repository,
    and nothing copied from real material.
    """
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    return SimpleUploadedFile(f"{title}.pdf", body, content_type="application/pdf")


def _sample_thumbnail() -> SimpleUploadedFile:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (640, 360), (18, 74, 56)).save(buffer, format="JPEG")
    return SimpleUploadedFile("thumb.jpg", buffer.getvalue(), content_type="image/jpeg")


class Command(BaseCommand):
    help = "Create or refresh fake course catalogue data (local/staging only)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--with-files",
            action="store_true",
            help="Also generate sample PDF resources and thumbnails (slower).",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Course seeding is disabled in the "
                f"{getattr(settings, 'ENVIRONMENT', 'unknown')} environment. "
                "This command must never run against production data."
            )

        author = User.objects.filter(role=UserRole.ADMIN).order_by("email").first()
        if author is None:
            raise CommandError(
                "No administrator account exists. Run `manage.py seed_demo_data` first."
            )
        trainers = list(User.objects.filter(role=UserRole.TRAINER).order_by("email")[:5])

        categories = self._seed_categories()
        counts = self._seed_courses(categories, author, trainers, with_files=options["with_files"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Course data ready: {len(categories)} categories, "
                f"{counts['courses']} courses, {counts['modules']} modules, "
                f"{counts['lessons']} lessons, {counts['resources']} resources."
            )
        )

    def _seed_categories(self) -> dict[str, Category]:
        categories: dict[str, Category] = {}
        for position, (name, slug, description) in enumerate(CATEGORIES):
            category, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "position": position,
                    "is_active": True,
                },
            )
            categories[slug] = category
        return categories

    def _seed_courses(self, categories, author, trainers, *, with_files: bool) -> dict[str, int]:
        counts = {"courses": 0, "modules": 0, "lessons": 0, "resources": 0}

        for index, spec in enumerate(COURSES):
            slug = spec["title"].lower().replace(" ", "-").replace("&", "and")
            course = Course.objects.filter(slug=slug).first()
            if course is None:
                course = Course(slug=slug, code=next_course_code())

            course.title = spec["title"]
            course.category = categories[spec["category"]]
            course.difficulty = spec["difficulty"]
            course.estimated_duration_minutes = spec["duration"]
            course.short_description = spec["short"]
            course.description = (
                f"{spec['short']}\n\nThis is demo content for a staging environment. "
                "It contains no real course material."
            )
            course.learning_objectives = spec["objectives"]
            course.prerequisites = spec["prerequisites"]
            course.visibility = CourseVisibility.PUBLIC
            course.created_by = course.created_by or author
            course.updated_by = author
            course.save()
            counts["courses"] += 1

            if with_files and not course.thumbnail:
                course.thumbnail.save(f"{slug}.jpg", _sample_thumbnail(), save=True)

            # One trainer owns each course, so the assigned-author path is
            # exercised in the seeded environment rather than only in tests.
            if trainers:
                CourseAssignment.objects.update_or_create(
                    course=course,
                    user=trainers[index % len(trainers)],
                    defaults={"role": CourseAuthorRole.OWNER, "assigned_by": author},
                )

            child_counts = self._seed_modules(course, spec, author, with_files=with_files)
            counts["modules"] += child_counts["modules"]
            counts["lessons"] += child_counts["lessons"]
            counts["resources"] += child_counts["resources"]

            # Status is set last, so the publishing checklist sees real content.
            course.status = spec["status"]
            if spec["status"] == PublishStatus.PUBLISHED and course.published_at is None:
                from django.utils import timezone

                course.published_at = timezone.now()
            course.save(update_fields=["status", "published_at", "updated_at"])

        return counts

    def _seed_modules(self, course: Course, spec, author, *, with_files: bool) -> dict[str, int]:
        counts = {"modules": 0, "lessons": 0, "resources": 0}
        published = spec["status"] == PublishStatus.PUBLISHED

        for position in range(MODULES_PER_COURSE):
            module, _ = Module.objects.update_or_create(
                course=course,
                position=position,
                defaults={
                    "title": f"{position + 1}. {MODULE_TITLES[position]}",
                    "description": f"Demo module {position + 1} of {course.title}.",
                    "status": PublishStatus.PUBLISHED if published else PublishStatus.DRAFT,
                    "is_visible": True,
                },
            )
            counts["modules"] += 1
            lesson_counts = self._seed_lessons(
                course, module, published=published, author=author, with_files=with_files
            )
            counts["lessons"] += lesson_counts["lessons"]
            counts["resources"] += lesson_counts["resources"]
        return counts

    def _seed_lessons(
        self, course: Course, module: Module, *, published: bool, author, with_files: bool
    ) -> dict[str, int]:
        counts = {"lessons": 0, "resources": 0}

        for position in range(LESSONS_PER_MODULE):
            content_type, suffix = LESSON_SHAPES[position % len(LESSON_SHAPES)]
            slug = f"{module.position}-{position}-{suffix.lower().replace(' ', '-')}"

            lesson = Lesson.objects.filter(module=module, slug=slug).first() or Lesson(
                module=module, slug=slug
            )
            lesson.position = position
            lesson.title = f"{suffix}: {module.title.split('. ', 1)[-1]}"
            lesson.description = f"Demo lesson {position + 1} of {module.title}."
            lesson.content_type = content_type
            lesson.duration_minutes = 10 + position * 5
            lesson.status = PublishStatus.PUBLISHED if published else PublishStatus.DRAFT
            # The first lesson of the first module is the free sample.
            lesson.is_preview = module.position == 0 and position == 0
            lesson.is_required = position < 3

            if content_type == LessonContentType.TEXT:
                lesson.text_content = SAMPLE_TEXT
            elif content_type == LessonContentType.EXTERNAL_LINK:
                # `.invalid` is reserved by RFC 2606 and can never resolve.
                lesson.external_url = f"https://docs.example.invalid/{course.slug}/{slug}"
            elif content_type == LessonContentType.VIDEO and lesson.video_id is None:
                lesson.video = VideoAsset.objects.create(
                    provider=VideoProvider.EXTERNAL_URL,
                    # Fake metadata: the URL is undeliverable by construction.
                    source_url=f"https://videos.example.invalid/{course.slug}/{slug}.m3u8",
                    thumbnail_url=f"https://videos.example.invalid/{course.slug}/{slug}.jpg",
                    duration_seconds=(10 + position * 5) * 60,
                    asset_identifier=f"demo-{course.code}-{slug}",
                    status=VideoStatus.READY,
                )

            lesson.save()
            counts["lessons"] += 1

            if content_type == LessonContentType.DOCUMENT:
                counts["resources"] += self._seed_resource(lesson, author, with_files=with_files)

        return counts

    def _seed_resource(self, lesson: Lesson, author, *, with_files: bool) -> int:
        """A document lesson needs a file; every lesson also gets a link."""
        created = 0

        if not lesson.resources.filter(kind=ResourceKind.LINK).exists():
            LessonResource.objects.create(
                lesson=lesson,
                kind=ResourceKind.LINK,
                title="Reference documentation",
                description="Demo link. Points at a reserved, unreachable domain.",
                external_url=f"https://docs.example.invalid/{lesson.slug}",
                position=1,
                uploaded_by=author,
            )
            created += 1

        if with_files and not lesson.resources.filter(kind=ResourceKind.FILE).exists():
            upload = _sample_pdf(lesson.slug)
            resource = LessonResource(
                lesson=lesson,
                kind=ResourceKind.FILE,
                title=f"{lesson.title} handout",
                description="Generated sample PDF. Contains no real material.",
                original_filename=upload.name,
                content_type="application/pdf",
                size_bytes=upload.size,
                position=0,
                uploaded_by=author,
            )
            resource.file.save(f"{lesson.slug}.pdf", upload, save=False)
            resource.save()
            created += 1

        return created
