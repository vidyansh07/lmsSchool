"""Django admin for student profiles.

System-owned fields are read-only here too. The admin is a convenience for
operators, not a way around the rules the API enforces.
"""

from django.contrib import admin

from .models import StudentProfile


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "city", "qualification", "fee_status", "created_at")
    list_filter = ("fee_status", "qualification", "country", "created_at")
    search_fields = ("student_id", "user__email", "user__first_name", "user__last_name")
    readonly_fields = (
        "id",
        "student_id",
        "fee_status_updated_at",
        "fee_status_updated_by",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)
