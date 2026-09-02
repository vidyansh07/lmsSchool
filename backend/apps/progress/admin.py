"""Django admin for completions. Read-only: decisions go through the service."""

from django.contrib import admin

from .models import CourseCompletion


@admin.register(CourseCompletion)
class CourseCompletionAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "status", "completed_on", "decided_by", "decided_at")
    list_filter = ("status",)
    search_fields = (
        "enrollment__student__student_id",
        "enrollment__course__title",
        "enrollment__batch__code",
    )
    readonly_fields = tuple(field.name for field in CourseCompletion._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
