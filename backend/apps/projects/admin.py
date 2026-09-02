"""Django admin for projects. Read-mostly: the workflow lives in the service."""

from django.contrib import admin

from .models import Project, ProjectFile, StudentProject


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "course", "batch", "kind", "is_required", "status", "end_date")
    list_filter = ("status", "kind", "is_required")
    search_fields = ("code", "title", "course__title", "batch__code")
    readonly_fields = ("id", "code", "published_at", "created_by", "created_at", "updated_at")
    ordering = ("-created_at",)


class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0
    fields = ("original_filename", "extension", "size_bytes", "checksum")
    readonly_fields = fields
    can_delete = False


@admin.register(StudentProject)
class StudentProjectAdmin(admin.ModelAdmin):
    list_display = ("project", "enrollment", "status", "submission_count", "marks_awarded")
    list_filter = ("status", "is_late")
    search_fields = ("project__code", "enrollment__student__student_id")
    readonly_fields = (
        "id",
        "project",
        "enrollment",
        "submitted_at",
        "submission_count",
        "marks_awarded",
        "rubric_scores",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    inlines = (ProjectFileInline,)

    def has_add_permission(self, request) -> bool:
        return False
