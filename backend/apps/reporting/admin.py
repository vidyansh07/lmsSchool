"""Django admin for bulk imports and export jobs. Read-only: the workflow lives in the service."""

from django.contrib import admin

from .models import BulkImport, ExportJob


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


@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = (
        "report_key",
        "format",
        "status",
        "requested_by",
        "row_count",
        "created_at",
        "expires_at",
    )
    list_filter = ("format", "status")
    search_fields = ("report_key", "original_filename", "checksum")
    readonly_fields = tuple(field.name for field in ExportJob._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def get_queryset(self, request):
        # The admin is where an operator would look for a job everyone else's
        # view has hidden — including a soft-deleted one — so it reads through
        # `all_objects` rather than the filtering default manager.
        return ExportJob.all_objects.with_related()
