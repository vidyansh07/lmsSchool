"""Django admin for class sessions.

Status is read-only: transitions go through the service so the rules apply and
the change is audited.
"""

from django.contrib import admin

from .models import ClassSession, TrainerAssignmentHistory


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ("session_date", "start_time", "batch", "trainer", "topic", "status")
    list_filter = ("status", "session_date")
    search_fields = ("batch__code", "batch__name", "topic")
    readonly_fields = (
        "id",
        "status",
        "attendance_taken_at",
        "attendance_taken_by",
        "rescheduled_to",
        "created_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("batch",)
    date_hierarchy = "session_date"
    ordering = ("-session_date", "start_time")


@admin.register(TrainerAssignmentHistory)
class TrainerAssignmentHistoryAdmin(admin.ModelAdmin):
    list_display = ("batch", "trainer", "assigned_at", "ended_at", "is_current")
    list_filter = ("assigned_at",)
    search_fields = ("batch__code", "trainer__trainer_id")
    readonly_fields = [field.name for field in TrainerAssignmentHistory._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
