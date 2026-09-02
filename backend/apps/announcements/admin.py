"""Django admin for announcements."""

from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "status", "is_pinned", "published_at", "expires_at")
    list_filter = ("audience", "status", "is_pinned")
    search_fields = ("title", "body")
    readonly_fields = ("id", "published_at", "created_by", "created_at", "updated_at")
    filter_horizontal = ("recipients",)
