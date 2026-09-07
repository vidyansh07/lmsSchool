"""Django admin for trainer profiles."""

from django.contrib import admin

from .models import TrainerProfile


@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "trainer_id",
        "user",
        "branch",
        "professional_title",
        "years_of_experience",
        "is_accepting_assignments",
    )
    list_filter = ("branch", "is_accepting_assignments", "created_at")
    search_fields = ("trainer_id", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("id", "trainer_id", "created_at", "updated_at")
    autocomplete_fields = ("user", "branch")
    ordering = ("-created_at",)
