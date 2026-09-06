"""Django admin for daily status reports.

Read-mostly, like `apps.attendance.admin`: the workflow belongs to the API
and its services, which are what write the audit trail. The admin exists for
support staff tracking down a specific report, not for running reviews from.
"""

from django.contrib import admin

from .models import DSR


@admin.register(DSR)
class DSRAdmin(admin.ModelAdmin):
    list_display = ("session", "batch", "trainer", "report_date", "status", "submitted_at")
    list_filter = ("status", "report_date")
    search_fields = (
        "batch__code",
        "batch__name",
        "trainer__trainer_id",
        "trainer__user__email",
    )
    readonly_fields = (
        "id",
        "session",
        "batch",
        "trainer",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("module",)
    ordering = ("-report_date",)

    def has_add_permission(self, request) -> bool:
        return False
