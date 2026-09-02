"""Django admin for the course catalogue.

System-owned fields stay read-only here too. The admin is an operator
convenience, not a way around the rules the API enforces.
"""

from django.contrib import admin

from .models import Category, Course, CourseAssignment, Lesson, LessonResource, Module, VideoAsset


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ("position", "title", "status", "is_visible")
    ordering = ("position",)
    show_change_link = True


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("position", "title", "content_type", "status", "is_preview")
    ordering = ("position",)
    show_change_link = True


class AssignmentInline(admin.TabularInline):
    model = CourseAssignment
    extra = 0
    fields = ("user", "role", "assigned_by")
    readonly_fields = ("assigned_by",)
    autocomplete_fields = ("user",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "position")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("position", "name")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "category", "difficulty", "status", "visibility", "created_at")
    list_filter = ("status", "visibility", "difficulty", "category")
    search_fields = ("code", "title", "slug", "short_description")
    readonly_fields = (
        "id",
        "code",
        "published_at",
        "content_updated_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    prepopulated_fields = {"slug": ("title",)}
    inlines = (ModuleInline, AssignmentInline)
    ordering = ("-created_at",)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("course", "position", "title", "status", "is_visible")
    list_filter = ("status", "is_visible")
    search_fields = ("title", "course__code", "course__title")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (LessonInline,)
    ordering = ("course", "position")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("module", "position", "title", "content_type", "status", "is_preview")
    list_filter = ("content_type", "status", "is_preview")
    search_fields = ("title", "slug", "module__title", "module__course__code")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("module", "position")


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "kind", "content_type", "size_bytes", "is_downloadable")
    list_filter = ("kind", "is_downloadable")
    search_fields = ("title", "lesson__title", "original_filename")
    readonly_fields = (
        "id",
        "original_filename",
        "content_type",
        "size_bytes",
        "uploaded_by",
        "created_at",
        "updated_at",
    )


@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "status", "duration_seconds", "created_at")
    list_filter = ("provider", "status")
    readonly_fields = ("id", "created_at", "updated_at")
