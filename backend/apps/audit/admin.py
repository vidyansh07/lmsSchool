"""Read-only admin view of the audit trail.

Every field is read-only and no add/change/delete permission is granted, so the
admin cannot be used to rewrite history.
"""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "result", "actor_label", "resource_type", "resource_id")
    list_filter = ("action", "result", "resource_type", "created_at")
    search_fields = ("actor_label", "resource_id", "request_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
