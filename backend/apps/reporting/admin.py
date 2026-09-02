"""Django admin for bulk imports. Read-only: the workflow lives in the service."""

from django.contrib import admin

from .models import BulkImport


@admin.register(BulkImport)
class BulkImportAdmin(admin.ModelAdmin):
    list_display = ("kind", "original_filename", "status", "row_count", "error_count", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("original_filename", "checksum")
    readonly_fields = tuple(field.name for field in BulkImport._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
