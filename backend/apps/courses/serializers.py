"""Course serializers, scoped by audience.

Three read shapes exist per resource, and the difference between them is a
security boundary, not a convenience:

* **List** — what appears in a catalogue row. Small, and free of anything the
  caller has not earned.
* **Detail** — the course page. Structure and marketing copy; lesson *bodies*
  are not included.
* **Content** — the lesson body, resources and video. Only ever produced after
  ``access.can_view_content`` has said yes.

Write serializers are separate again, and reject unknown fields, so a client
cannot set ``status``, ``code`` or ``created_by`` by including them.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import (
    CONTENT_STATUS_CHOICES,
    MAX_OBJECTIVE_LENGTH,
    MAX_OBJECTIVES,
    MAX_PREREQUISITES,
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


class StringListField(serializers.ListField):
    """Bounded list of short strings (objectives, prerequisites)."""

    def __init__(self, *, max_items: int, **kwargs):
        kwargs.setdefault("child", SafeCharField(max_length=MAX_OBJECTIVE_LENGTH))
        kwargs.setdefault("max_length", max_items)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        return [value.strip() for value in values if value.strip()]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategorySerializer(serializers.ModelSerializer):
    course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "is_active", "position", "course_count")
        read_only_fields = fields


class CategoryWriteSerializer(StrictModelSerializer):
    name = SafeCharField(max_length=100)
    slug = serializers.SlugField(max_length=120, required=False, allow_blank=True)

    class Meta:
        model = Category
        fields = ("name", "slug", "description", "is_active", "position")


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------


class VideoAssetSerializer(serializers.ModelSerializer):
    """Video metadata *without* the playable URL.

    ``source_url`` is deliberately absent. A caller that is entitled to watch
    fetches it from the lesson playback endpoint, which authorises first — so a
    private URL never appears in a catalogue or lesson listing.
    """

    class Meta:
        model = VideoAsset
        fields = ("id", "provider", "duration_seconds", "thumbnail_url", "status")
        read_only_fields = fields


class VideoAssetWriteSerializer(StrictSerializer):
    provider = serializers.ChoiceField(
        choices=VideoProvider.choices, default=VideoProvider.EXTERNAL_URL
    )
    source_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    asset_identifier = SafeCharField(max_length=255, required=False, allow_blank=True)
    thumbnail_url = serializers.URLField(max_length=500, required=False, allow_blank=True)
    duration_seconds = serializers.IntegerField(
        min_value=0, max_value=86400, required=False, allow_null=True
    )
    status = serializers.ChoiceField(choices=VideoStatus.choices, default=VideoStatus.READY)

    def validate(self, attrs):
        provider = attrs.get("provider", VideoProvider.EXTERNAL_URL)
        if provider == VideoProvider.EXTERNAL_URL:
            url = attrs.get("source_url", "")
            if not url:
                raise serializers.ValidationError(
                    {"source_url": ["A source URL is required for the external-URL provider."]}
                )
            if not url.startswith("https://"):
                raise serializers.ValidationError({"source_url": ["Video URLs must use https."]})
        elif not attrs.get("asset_identifier"):
            raise serializers.ValidationError(
                {"asset_identifier": ["An asset identifier is required for this provider."]}
            )
        return attrs


class VideoPlaybackSerializer(serializers.Serializer):
    """What the player needs, returned only to an authorised caller."""

    provider = serializers.CharField(read_only=True)
    playback_url = serializers.CharField(read_only=True, allow_null=True)
    duration_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class LessonResourceSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = LessonResource
        fields = (
            "id",
            "title",
            "description",
            "kind",
            "original_filename",
            "content_type",
            "size_bytes",
            "external_url",
            "position",
            "is_downloadable",
            "download_url",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_download_url(self, obj: LessonResource) -> str | None:
        """Path to the authenticated download view — never a storage path."""
        if obj.kind != ResourceKind.FILE or not obj.file or not obj.is_downloadable:
            return None
        return f"/api/v1/resources/{obj.pk}/download/"


class ResourceFileUploadSerializer(StrictSerializer):
    title = SafeCharField(max_length=200)
    description = SafeCharField(max_length=500, required=False, allow_blank=True, default="")
    file = serializers.FileField(write_only=True)
    is_downloadable = serializers.BooleanField(default=True)


class ResourceLinkSerializer(StrictSerializer):
    title = SafeCharField(max_length=200)
    description = SafeCharField(max_length=500, required=False, allow_blank=True, default="")
    external_url = serializers.URLField(max_length=500)


class ResourceUpdateSerializer(StrictModelSerializer):
    title = SafeCharField(max_length=200, required=False)

    class Meta:
        model = LessonResource
        fields = ("title", "description", "is_downloadable", "position")


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------


class LessonSummarySerializer(serializers.ModelSerializer):
    """Navigation entry. Carries no lesson body.

    This is what a student sees in the module outline before they are entitled
    to the content itself, so it must stay free of ``text_content`` and of
    anything that would let the body be reconstructed.
    """

    resource_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lesson
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "content_type",
            "duration_minutes",
            "position",
            "status",
            "is_preview",
            "is_required",
            "resource_count",
        )
        read_only_fields = fields


class LessonContentSerializer(serializers.ModelSerializer):
    """The lesson body. Only produced after an access check has passed."""

    video = VideoAssetSerializer(read_only=True)
    resources = LessonResourceSerializer(many=True, read_only=True)
    module_id = serializers.UUIDField(source="module.id", read_only=True)
    course_id = serializers.UUIDField(source="module.course.id", read_only=True)

    class Meta:
        model = Lesson
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "content_type",
            "text_content",
            "external_url",
            "video",
            "resources",
            "duration_minutes",
            "position",
            "status",
            "is_preview",
            "is_required",
            "module_id",
            "course_id",
        )
        read_only_fields = fields


class LessonWriteSerializer(StrictModelSerializer):
    title = SafeCharField(max_length=200)
    slug = serializers.SlugField(max_length=160, required=False, allow_blank=True)
    content_type = serializers.ChoiceField(choices=LessonContentType.choices)
    video = VideoAssetWriteSerializer(required=False, allow_null=True)

    class Meta:
        model = Lesson
        # `position` and `status` are absent: ordering has its own endpoint and
        # status has its own transition rules.
        fields = (
            "title",
            "slug",
            "description",
            "content_type",
            "text_content",
            "external_url",
            "video",
            "duration_minutes",
            "is_preview",
            "is_required",
        )

    def validate_external_url(self, value: str) -> str:
        if value and not value.startswith("https://"):
            raise serializers.ValidationError("External links must use https.")
        return value


class LessonStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=CONTENT_STATUS_CHOICES)


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = (
            "id",
            "title",
            "description",
            "position",
            "status",
            "is_visible",
            "lessons",
        )
        read_only_fields = fields


class ModuleWriteSerializer(StrictModelSerializer):
    title = SafeCharField(max_length=200)

    class Meta:
        model = Module
        fields = ("title", "description", "is_visible")


class ModuleStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=CONTENT_STATUS_CHOICES)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseAssignmentSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = CourseAssignment
        fields = ("id", "user_id", "email", "full_name", "role", "created_at")
        read_only_fields = fields


class CourseListSerializer(serializers.ModelSerializer):
    """Catalogue row. Flat, small, and safe for an unauthenticated-adjacent view."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    module_count = serializers.IntegerField(read_only=True, default=0)
    lesson_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Course
        fields = (
            "id",
            "code",
            "slug",
            "title",
            "short_description",
            "category_name",
            "category_slug",
            "difficulty",
            "estimated_duration_minutes",
            "status",
            "visibility",
            "thumbnail_url",
            "module_count",
            "lesson_count",
            "published_at",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_thumbnail_url(self, obj: Course) -> str | None:
        return f"/api/v1/courses/{obj.pk}/thumbnail/" if obj.thumbnail else None


class CourseDetailSerializer(CourseListSerializer):
    """Course page: structure and marketing copy, no lesson bodies."""

    description = serializers.CharField(read_only=True)
    learning_objectives = serializers.ListField(read_only=True)
    prerequisites = serializers.ListField(read_only=True)
    modules = serializers.SerializerMethodField()
    instructors = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    can_publish = serializers.SerializerMethodField()

    class Meta(CourseListSerializer.Meta):
        fields = (
            *CourseListSerializer.Meta.fields,
            "description",
            "learning_objectives",
            "prerequisites",
            "content_updated_at",
            "updated_at",
            "modules",
            "instructors",
            "can_manage",
            "can_publish",
        )
        read_only_fields = fields

    @extend_schema_field(ModuleSerializer(many=True))
    def get_modules(self, obj: Course):
        """Only the modules and lessons this caller may see.

        Filtering happens here, through the access layer, rather than in the
        view — so every route that serialises a course gets the same rule.
        """
        from . import access

        user = self.context["request"].user
        modules = access.visible_modules(user, obj).prefetch_related("lessons")
        payload = []
        for module in modules:
            lessons = access.visible_lessons(user, module)
            data = ModuleSerializer(module).data
            data["lessons"] = LessonSummarySerializer(lessons, many=True).data
            payload.append(data)
        return payload

    @extend_schema_field(
        serializers.ListField(child=serializers.DictField(child=serializers.CharField()))
    )
    def get_instructors(self, obj: Course):
        """Assigned authors, as names only — never their contact details."""
        return [
            {
                "full_name": assignment.user.full_name or assignment.user.email.split("@")[0],
                "role": assignment.role,
            }
            for assignment in obj.assignments.select_related("user").all()
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_can_manage(self, obj: Course) -> bool:
        from . import access

        return access.can_manage_course(self.context["request"].user, obj)

    @extend_schema_field(serializers.BooleanField())
    def get_can_publish(self, obj: Course) -> bool:
        from . import access

        return access.can_publish_course(self.context["request"].user, obj)


class CourseWriteSerializer(StrictModelSerializer):
    """Create/update input.

    Absent on purpose: ``code`` (system-allocated), ``status`` (its own endpoint
    and transition rules), ``published_at``, ``created_by``, ``updated_by`` and
    every timestamp. Unknown fields are rejected, so sending any of them returns
    400 naming the field.
    """

    title = SafeCharField(max_length=200)
    slug = serializers.SlugField(max_length=160, required=False, allow_blank=True)
    short_description = SafeCharField(max_length=300, required=False, allow_blank=True)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    difficulty = serializers.ChoiceField(choices=CourseDifficulty.choices, required=False)
    visibility = serializers.ChoiceField(choices=CourseVisibility.choices, required=False)
    learning_objectives = StringListField(max_items=MAX_OBJECTIVES)
    prerequisites = StringListField(max_items=MAX_PREREQUISITES)

    class Meta:
        model = Course
        fields = (
            "title",
            "slug",
            "short_description",
            "description",
            "category",
            "difficulty",
            "visibility",
            "estimated_duration_minutes",
            "learning_objectives",
            "prerequisites",
        )


class CourseStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=PublishStatus.choices)
    note = SafeCharField(max_length=255, required=False, allow_blank=True, default="")


class AssignAuthorSerializer(StrictSerializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=CourseAuthorRole.choices, default=CourseAuthorRole.EDITOR
    )


class ReorderSerializer(StrictSerializer):
    """The complete new order, as ids.

    Every child must appear exactly once. A partial list would leave the
    remainder in an ambiguous position, so it is rejected rather than guessed at.
    """

    ordered_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class CourseThumbnailSerializer(StrictSerializer):
    image = serializers.ImageField(write_only=True)


class PublishChecklistSerializer(serializers.Serializer):
    """What is stopping a course from being published."""

    ready = serializers.BooleanField(read_only=True)
    blockers = serializers.ListField(child=serializers.CharField(), read_only=True)
