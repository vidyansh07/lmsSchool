"""Django admin for notifications and the outbox.

Read-only. A notification is a record of something the product said; editing one
would make the audit trail disagree with what was delivered.
"""

from django.contrib import admin

from .models import EmailMessage, Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "title", "read_at", "created_at")
    list_filter = ("kind", "category")
    search_fields = ("recipient__email", "title")
    readonly_fields = tuple(field.name for field in Notification._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("to_email", "subject", "status", "attempts", "sent_at", "created_at")
    list_filter = ("status", "template")
    search_fields = ("to_email", "subject")
    readonly_fields = tuple(field.name for field in EmailMessage._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_academic", "email_schedule", "email_announcements")
    search_fields = ("user__email",)
