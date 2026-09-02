"""Django admin for assessments and results.

Read-mostly: marks are written through the service so the bound check and the
audit entry cannot be bypassed.
"""

from django.contrib import admin

from .models import Assessment, AssessmentResult, ResultImport


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "batch", "category", "delivery", "status", "scheduled_for")
    list_filter = ("category", "delivery", "status")
    search_fields = ("code", "title", "batch__code", "course__title")
    readonly_fields = (
        "id",
        "code",
        "course",
        "published_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("assessment", "enrollment", "marks_obtained", "is_absent", "source")
    list_filter = ("source", "is_absent")
    search_fields = ("assessment__code", "enrollment__student__student_id")
    readonly_fields = (
        "id",
        "assessment",
        "enrollment",
        "source",
        "import_run",
        "recorded_by",
        "recorded_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(ResultImport)
class ResultImportAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "assessment",
        "status",
        "row_count",
        "error_count",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("original_filename", "assessment__code", "checksum")
    readonly_fields = tuple(field.name for field in ResultImport._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
