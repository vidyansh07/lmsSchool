"""Django admin for batches and schedules."""

from django.contrib import admin

from .models import Batch, BatchSchedule


class ScheduleInline(admin.TabularInline):
    model = BatchSchedule
    extra = 0
    fields = ("weekday", "start_time", "end_time", "timezone_name", "location", "is_active")
    ordering = ("weekday", "start_time")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "course",
        "trainer",
        "start_date",
        "end_date",
        "capacity",
        "status",
    )
    list_filter = ("status", "course", "start_date")
    search_fields = ("code", "name", "course__code", "course__title")
    readonly_fields = ("id", "code", "created_by", "created_at", "updated_at")
    autocomplete_fields = ("course", "trainer")
    inlines = (ScheduleInline,)
    ordering = ("-start_date",)


@admin.register(BatchSchedule)
class BatchScheduleAdmin(admin.ModelAdmin):
    list_display = ("batch", "weekday", "start_time", "end_time", "timezone_name", "is_active")
    list_filter = ("weekday", "is_active")
    search_fields = ("batch__code", "batch__name", "location")
    readonly_fields = ("id", "created_at", "updated_at")
