"""Django admin for the question bank."""

from django.contrib import admin

from .models import Question, QuestionOption


class OptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0
    fields = ("text", "is_correct", "position")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "question_type", "difficulty", "marks", "course", "is_active")
    list_filter = ("question_type", "difficulty", "is_active")
    search_fields = ("text", "course__title")
    readonly_fields = ("id", "created_by", "created_at", "updated_at")
    inlines = (OptionInline,)
    ordering = ("-created_at",)
