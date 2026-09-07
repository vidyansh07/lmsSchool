"""Django admin for branches."""

from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "city", "is_active")
    list_filter = ("is_active", "city")
    search_fields = ("code", "name", "city")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("code",)
