from django.contrib import admin

from .models import BrandingSetting


@admin.register(BrandingSetting)
class BrandingSettingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "brand_color", "updated_at")
    readonly_fields = ("created_at", "updated_at", "updated_by")
