"""Django admin for academic configuration.

Editable here as well as through the API — an administrator locked out of the
frontend still needs a way in — but every field is the same one the API writes,
so there is one vocabulary of rules and not two.
"""

from django.contrib import admin

from .models import AcademicPolicy


@admin.register(AcademicPolicy)
class AcademicPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "scope",
        "minimum_attendance_percent",
        "passing_percent",
        "updated_at",
    )
    list_filter = ("scope",)
    readonly_fields = ("id", "updated_by", "created_at", "updated_at")
    search_fields = ("course__title", "course__code")
