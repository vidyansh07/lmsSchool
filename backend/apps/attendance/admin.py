"""Django admin for attendance.

Corrections go through the service so the previous value is kept and the change
is audited; the admin is read-mostly.
"""

from django.contrib import admin

from .models import AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("session", "enrollment", "status", "was_corrected", "marked_at")
    list_filter = ("status", "marked_at")
    search_fields = (
        "enrollment__student__student_id",
        "enrollment__student__user__email",
        "session__batch__code",
    )
    readonly_fields = (
        "id",
        "session",
        "enrollment",
        "previous_status",
        "marked_by",
        "marked_at",
        "corrected_by",
        "corrected_at",
        "correction_reason",
        "created_at",
        "updated_at",
    )
    ordering = ("-marked_at",)

    def has_add_permission(self, request) -> bool:
        return False
