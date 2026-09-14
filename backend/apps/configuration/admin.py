"""Django admin for the institution's settings.

Editable here as well as through the API — an administrator locked out of the
frontend still needs a way in — and every field is the one the API writes, so
there is one vocabulary of settings and not two.
"""

from django.contrib import admin

from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = (
        "institution_name",
        "support_email",
        "notification_email_enabled",
        "updated_at",
    )
    readonly_fields = ("id", "singleton", "updated_by", "created_at", "updated_at")

    def has_add_permission(self, request) -> bool:
        """No "add" button once the row exists.

        Without this the unique constraint surfaces as an `IntegrityError`
        page, which reads to an operator like a crash rather than like "there is
        only one of these".
        """
        return not SystemSetting.objects.exists()
