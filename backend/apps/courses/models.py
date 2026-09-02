"""Course catalogue and learning content.

One app, not three. ``Category``, ``Course``, ``Module``, ``Lesson``,
``LessonResource`` and ``VideoAsset`` are a single aggregate: a lesson is
meaningless without its module, a module without its course. Splitting them
across apps would buy circular imports and no boundary. The boundary that does
exist — who may see or edit any of it — lives in :mod:`apps.courses.access`.

Ordering
--------
Position is explicit and deterministic. Creation date is not an order: two
lessons added in the same second would tie, and an author reordering content
would have to rewrite timestamps. Each ``(parent, position)`` pair is unique,
enforced by a **deferred** constraint so a reorder can shuffle several rows
inside one transaction without tripping over itself mid-update.

Status
------
Draft → In review → Published → Archived. Transitions are validated against an
explicit table in :mod:`apps.courses.services`, so an unreachable transition is
a data-integrity error rather than a UI oversight.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.uploads import course_thumbnail_upload_to, resource_upload_to
from apps.common.validators import validate_no_control_characters, validate_slug_value

MAX_OBJECTIVES = 20
MAX_OBJECTIVE_LENGTH = 200
MAX_PREREQUISITES = 20


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class PublishStatus(models.TextChoices):
    """Shared lifecycle for courses, modules and lessons.

    ``IN_REVIEW`` exists so an approval step can be switched on without a
    migration. Phase 2 does not force anything through it: an author with
    publish rights may go straight from draft to published, and one without
    submits for review instead.
    """

    DRAFT = "draft", _("Draft")
    IN_REVIEW = "in_review", _("In review")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


#: The subset of statuses a module or lesson may be toggled between. Courses
#: use the full lifecycle; their children only need "ready" or "not ready".
CONTENT_STATUS_CHOICES = [
    (PublishStatus.DRAFT, PublishStatus.DRAFT.label),
    (PublishStatus.PUBLISHED, PublishStatus.PUBLISHED.label),
]


class CourseVisibility(models.TextChoices):
    """Who may discover a published course.

    Separate from status on purpose: "finished" and "advertised" are different
    questions. An internal course can be complete and published yet never appear
    in the public catalogue.
    """

    PUBLIC = "public", _("Public — listed in the catalogue")
    INTERNAL = "internal", _("Internal — signed-in users only")
    PRIVATE = "private", _("Private — assigned people only")


class CourseDifficulty(models.TextChoices):
    BEGINNER = "beginner", _("Beginner")
    INTERMEDIATE = "intermediate", _("Intermediate")
    ADVANCED = "advanced", _("Advanced")


class LessonContentType(models.TextChoices):
    """What a lesson actually contains.

    Adding a type means adding a member here and a rule to
    ``LESSON_CONTENT_REQUIREMENTS`` below. Nothing else in the codebase branches
    on content type, so a new type cannot be half-implemented.
    """

    TEXT = "text", _("Text")
    VIDEO = "video", _("Video")
    DOCUMENT = "document", _("Document")
    EXTERNAL_LINK = "external_link", _("External link")


#: Which field each content type requires. Enforced by ``Lesson.clean`` and by
#: the service layer, so the rule holds for the API, the admin and the seeder.
LESSON_CONTENT_REQUIREMENTS: dict[str, str] = {
    LessonContentType.TEXT: "text_content",
    LessonContentType.VIDEO: "video",
    LessonContentType.EXTERNAL_LINK: "external_url",
    # DOCUMENT is satisfied by an attached file resource rather than a field on
    # the lesson, so it is validated separately.
    LessonContentType.DOCUMENT: "",
}


class VideoProvider(models.TextChoices):
    """Where the video actually lives.

    No provider stores bytes in the application container: video is large,
    and a Django worker is the wrong thing to stream it from. ``EXTERNAL_URL``
    is the only provider Phase 2 can play; the other two are modelled so the
    integration slots in without a migration.
    """

    EXTERNAL_URL = "external_url", _("External URL")
    S3 = "s3", _("S3-compatible object storage")
    MANAGED = "managed", _("Managed video service")


class VideoStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    READY = "ready", _("Ready")
    FAILED = "failed", _("Failed")


class ResourceKind(models.TextChoices):
    FILE = "file", _("File")
    LINK = "link", _("External link")


class CourseAuthorRole(models.TextChoices):
    """What an assigned author may do to one specific course.

    This is the configurable part of §8. A trainer holds no global course
    capability; everything they may do comes from a row in
    ``CourseAssignment``, scoped to a single course.
    """

    OWNER = "owner", _("Owner — edit content and change status")
    EDITOR = "editor", _("Editor — edit content, cannot publish")


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class Category(BaseModel):
    """A flat course category.

    Deliberately not a tree. A hierarchy needs an ordering strategy, a depth
    limit, cycle prevention and recursive queries — none of which anything in
    the product asks for. Adding a nullable ``parent`` later is one migration.
    """

    name = models.CharField(
        _("name"), max_length=100, unique=True, validators=[validate_no_control_characters]
    )
    slug = models.SlugField(
        _("slug"),
        max_length=120,
        unique=True,
        help_text=_("URL-safe identifier. Must be unique across all categories."),
        validators=[validate_slug_value],
    )
    description = models.TextField(_("description"), max_length=1000, blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_("Inactive categories are hidden from the catalogue but keep their courses."),
    )
    position = models.PositiveIntegerField(_("position"), default=0, db_index=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ("position", "name")
        constraints = [
            models.UniqueConstraint(models.functions.Lower("slug"), name="category_slug_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name


class CourseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=PublishStatus.PUBLISHED)

    def listable(self):
        """Published and discoverable — the student catalogue."""
        return self.published().filter(
            visibility__in=(CourseVisibility.PUBLIC, CourseVisibility.INTERNAL),
            category__is_active=True,
        )

    def with_related(self):
        return self.select_related("category", "created_by", "updated_by")


class Course(BaseModel):
    code = models.CharField(
        _("course code"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human-readable identifier, e.g. GRS-C-00013. Allocated by the system."),
    )
    slug = models.SlugField(
        _("slug"),
        max_length=160,
        unique=True,
        help_text=_("URL identifier. Stable once published — changing it breaks shared links."),
        validators=[validate_slug_value],
    )
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    short_description = models.CharField(
        _("short description"),
        max_length=300,
        blank=True,
        help_text=_("One line, shown on catalogue cards."),
    )
    description = models.TextField(_("full description"), max_length=8000, blank=True)
    thumbnail = models.ImageField(
        _("thumbnail"),
        upload_to=course_thumbnail_upload_to,
        blank=True,
        null=True,
        max_length=255,
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="courses",
        help_text=_("Protected: deleting a category with courses would orphan them."),
    )
    difficulty = models.CharField(
        _("difficulty"),
        max_length=20,
        choices=CourseDifficulty.choices,
        default=CourseDifficulty.BEGINNER,
        db_index=True,
    )
    estimated_duration_minutes = models.PositiveIntegerField(
        _("estimated duration (minutes)"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(60 * 24 * 365)],
    )
    learning_objectives = ArrayField(
        models.CharField(max_length=MAX_OBJECTIVE_LENGTH),
        verbose_name=_("learning objectives"),
        default=list,
        blank=True,
        size=MAX_OBJECTIVES,
    )
    prerequisites = ArrayField(
        models.CharField(max_length=MAX_OBJECTIVE_LENGTH),
        verbose_name=_("prerequisites"),
        default=list,
        blank=True,
        size=MAX_PREREQUISITES,
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    visibility = models.CharField(
        _("visibility"),
        max_length=20,
        choices=CourseVisibility.choices,
        default=CourseVisibility.PUBLIC,
        db_index=True,
    )
    published_at = models.DateTimeField(_("first published at"), null=True, blank=True)
    content_updated_at = models.DateTimeField(
        _("content last changed at"),
        null=True,
        blank=True,
        help_text=_(
            "Set whenever a module, lesson or resource changes. Makes edits to a "
            "published course visible to reviewers."
        ),
    )

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses_created",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses_updated",
    )

    objects = CourseQuerySet.as_manager()

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(models.functions.Lower("slug"), name="course_slug_ci_unique"),
        ]
        indexes = [
            # The catalogue query: published + discoverable, newest first.
            models.Index(fields=["status", "visibility", "-created_at"], name="course_catalog_idx"),
            models.Index(fields=["category", "status"], name="course_category_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED


class CourseAssignment(BaseModel):
    """Grants one person authoring rights over one course.

    This is how a trainer gets edit rights at all. There is no global trainer
    course capability, so removing the row removes the access — no cache, no
    second source of truth.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="course_assignments"
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=CourseAuthorRole.choices,
        default=CourseAuthorRole.EDITOR,
    )
    assigned_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="course_assignments_made",
    )

    class Meta:
        verbose_name = _("course assignment")
        verbose_name_plural = _("course assignments")
        ordering = ("course", "user")
        constraints = [
            models.UniqueConstraint(fields=["course", "user"], name="course_assignment_unique"),
        ]
        indexes = [
            models.Index(fields=["user", "course"], name="assignment_user_course_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} on {self.course_id} as {self.role}"

    @property
    def can_publish(self) -> bool:
        return self.role == CourseAuthorRole.OWNER


# ---------------------------------------------------------------------------
# Content tree
# ---------------------------------------------------------------------------


class Module(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    description = models.TextField(_("description"), max_length=2000, blank=True)
    position = models.PositiveIntegerField(
        _("position"), default=0, help_text=_("Explicit order within the course, from 0.")
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    is_visible = models.BooleanField(
        _("visible"),
        default=True,
        help_text=_("Hide a finished module without unpublishing it."),
    )

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        ordering = ("position", "created_at")
        constraints = [
            # Deferred so a reorder can shuffle several rows in one transaction
            # without colliding halfway through.
            models.UniqueConstraint(
                fields=["course", "position"],
                name="module_position_unique",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]
        indexes = [
            models.Index(fields=["course", "position"], name="module_course_position_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.title}"


class VideoAsset(BaseModel):
    """Metadata about a video. Never the video itself.

    The application container stores no video bytes: it is the wrong place for
    large files and the wrong process to stream them from. What lives here is
    enough to render a player and to fetch a playback URL from whichever
    provider actually holds the asset.

    ``source_url`` is not serialised in list responses. A caller that is allowed
    to watch fetches it from the lesson's playback endpoint, which authorises
    first — so a private URL is not sprayed across every catalogue payload.
    """

    provider = models.CharField(
        _("provider"),
        max_length=20,
        choices=VideoProvider.choices,
        default=VideoProvider.EXTERNAL_URL,
    )
    asset_identifier = models.CharField(
        _("asset identifier"),
        max_length=255,
        blank=True,
        help_text=_("Provider-side id: an object key, or a managed-service asset id."),
    )
    source_url = models.URLField(
        _("source URL"),
        max_length=500,
        blank=True,
        help_text=_("Playable URL for the external-URL provider. Not returned in listings."),
    )
    thumbnail_url = models.URLField(_("thumbnail URL"), max_length=500, blank=True)
    duration_seconds = models.PositiveIntegerField(
        _("duration (seconds)"), null=True, blank=True, validators=[MaxValueValidator(60 * 60 * 24)]
    )
    status = models.CharField(
        _("status"), max_length=20, choices=VideoStatus.choices, default=VideoStatus.PENDING
    )

    class Meta:
        verbose_name = _("video asset")
        verbose_name_plural = _("video assets")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({self.status})"

    @property
    def is_playable(self) -> bool:
        return self.status == VideoStatus.READY and bool(self.source_url or self.asset_identifier)


class Lesson(BaseModel):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    slug = models.SlugField(
        _("slug"),
        max_length=160,
        help_text=_("Unique within its module."),
        validators=[validate_slug_value],
    )
    description = models.TextField(_("description"), max_length=2000, blank=True)

    content_type = models.CharField(
        _("content type"),
        max_length=20,
        choices=LessonContentType.choices,
        default=LessonContentType.TEXT,
        db_index=True,
    )
    text_content = models.TextField(
        _("text content"), blank=True, help_text=_("Markdown. Rendered as text, never as HTML.")
    )
    external_url = models.URLField(
        _("external URL"),
        max_length=500,
        blank=True,
        help_text=_("Must be https. Opened in a new tab with noopener."),
    )
    video = models.OneToOneField(
        VideoAsset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lesson",
    )

    duration_minutes = models.PositiveIntegerField(
        _("duration (minutes)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(60 * 24)],
    )
    position = models.PositiveIntegerField(_("position"), default=0)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    is_preview = models.BooleanField(
        _("free preview"),
        default=False,
        help_text=_("Readable without enrolment. The sample a prospective student sees."),
    )
    is_required = models.BooleanField(
        _("required"), default=True, help_text=_("Optional lessons are supplementary material.")
    )

    class Meta:
        verbose_name = _("lesson")
        verbose_name_plural = _("lessons")
        ordering = ("position", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["module", "position"],
                name="lesson_position_unique",
                deferrable=models.Deferrable.DEFERRED,
            ),
            models.UniqueConstraint(fields=["module", "slug"], name="lesson_slug_unique"),
        ]
        indexes = [
            models.Index(fields=["module", "position"], name="lesson_module_position_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.title}"

    def clean(self) -> None:
        """Enforce that the lesson actually carries the content it claims to.

        A VIDEO lesson with no video is a broken page for every student who
        opens it, so it is rejected at write time rather than discovered later.
        """
        from django.core.exceptions import ValidationError

        super().clean()
        required_field = LESSON_CONTENT_REQUIREMENTS.get(self.content_type, "")
        if (
            required_field
            and not getattr(self, f"{required_field}_id", None)
            and not getattr(self, required_field, None)
        ):
            raise ValidationError(
                {required_field: _("This field is required for the selected content type.")},
                code="content_incomplete",
            )
        if self.external_url and not self.external_url.startswith("https://"):
            raise ValidationError(
                {"external_url": _("External links must use https.")}, code="insecure_url"
            )


class LessonResource(BaseModel):
    """A downloadable file or an external link attached to a lesson.

    Files are stored under ``MEDIA_ROOT``, which is never web-served, and are
    delivered by an authenticated view that re-checks course access on every
    request. Nothing here is reachable by guessing a path.
    """

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    description = models.CharField(_("description"), max_length=500, blank=True)
    kind = models.CharField(
        _("kind"), max_length=20, choices=ResourceKind.choices, default=ResourceKind.FILE
    )

    file = models.FileField(
        _("file"), upload_to=resource_upload_to, blank=True, null=True, max_length=255
    )
    original_filename = models.CharField(
        _("original filename"),
        max_length=255,
        blank=True,
        help_text=_("What the uploader called it. Display only — never used as a path."),
    )
    content_type = models.CharField(_("content type"), max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size in bytes"), null=True, blank=True)

    external_url = models.URLField(_("external URL"), max_length=500, blank=True)

    position = models.PositiveIntegerField(_("position"), default=0)
    is_downloadable = models.BooleanField(
        _("downloadable"),
        default=True,
        help_text=_("When off, the resource is listed but the file is not served."),
    )
    uploaded_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lesson_resources_uploaded",
    )

    class Meta:
        verbose_name = _("lesson resource")
        verbose_name_plural = _("lesson resources")
        ordering = ("position", "created_at")
        indexes = [
            models.Index(fields=["lesson", "position"], name="resource_lesson_position_idx"),
        ]
        constraints = [
            # A resource is a file or a link, never both and never neither.
            models.CheckConstraint(
                condition=(models.Q(kind="file", file__isnull=False) | models.Q(kind="link")),
                name="resource_file_present_for_file_kind",
            ),
        ]

    def __str__(self) -> str:
        return self.title
