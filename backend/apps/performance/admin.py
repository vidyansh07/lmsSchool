"""Django admin for performance reviews and feedback."""

from django.contrib import admin

from .models import Feedback, PerformanceReview


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = (
        "subject_type",
        "student",
        "trainer",
        "period_start",
        "period_end",
        "rating",
        "reviewer",
        "deleted_at",
    )
    list_filter = ("subject_type", "rating", "deleted_at")
    search_fields = ("student__student_id", "trainer__trainer_id", "summary")
    readonly_fields = ("id", "snapshot", "reviewer", "created_at", "updated_at")
    autocomplete_fields = ("student", "trainer")
    ordering = ("-period_end",)

    def get_queryset(self, request):
        # The admin is where a withdrawn review is found again, so it reads
        # `all_objects` rather than the default filtering manager.
        return PerformanceReview.all_objects.select_related("student", "trainer", "reviewer")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "subject_type",
        "student",
        "trainer",
        "batch",
        "author",
        "visible_to_subject",
        "deleted_at",
    )
    list_filter = ("subject_type", "visible_to_subject", "deleted_at")
    search_fields = ("student__student_id", "trainer__trainer_id", "body")
    readonly_fields = ("id", "author", "created_at", "updated_at")
    autocomplete_fields = ("student", "trainer", "batch")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        return Feedback.all_objects.select_related("student", "trainer", "batch", "author")
