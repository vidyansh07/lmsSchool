"""Django admin for enrolments and progress.

Status is read-only here: changing it must go through the service layer so the
transition rules apply and the change is audited.
"""

from django.contrib import admin

from .models import Enrollment, LessonProgress


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("code", "student", "batch", "course", "status", "enrolled_at")
    list_filter = ("status", "batch__status", "enrolled_at")
    search_fields = ("code", "student__student_id", "student__user__email", "batch__code")
    readonly_fields = (
        "id",
        "code",
        "status",
        "status_changed_at",
        "status_note",
        "completed_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("student", "batch", "course")
    ordering = ("-enrolled_at",)


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "status", "last_accessed_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("enrollment__code", "lesson__title")
    readonly_fields = ("id", "created_at", "updated_at")
