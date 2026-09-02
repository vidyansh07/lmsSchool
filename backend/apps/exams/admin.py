"""Django admin for examinations. Read-only: scores come from the service."""

from django.contrib import admin

from .models import AttemptAnswer, AttemptQuestion, Exam, ExamAttempt, ExamSection


class SectionInline(admin.TabularInline):
    model = ExamSection
    extra = 0
    fields = ("title", "position", "question_count", "difficulty", "question_type", "tags")


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "batch", "status", "opens_at", "results_published")
    list_filter = ("status", "results_published", "negative_marking")
    search_fields = ("code", "title", "batch__code")
    readonly_fields = (
        "id",
        "code",
        "course",
        "published_at",
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = (SectionInline,)
    ordering = ("-created_at",)


class AttemptQuestionInline(admin.TabularInline):
    model = AttemptQuestion
    extra = 0
    fields = ("position", "question", "marks", "negative_marks")
    readonly_fields = fields
    can_delete = False


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("exam", "enrollment", "attempt_number", "status", "total_score", "max_score")
    list_filter = ("status",)
    search_fields = ("exam__code", "enrollment__student__student_id")
    readonly_fields = tuple(field.name for field in ExamAttempt._meta.fields)
    inlines = (AttemptQuestionInline,)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(AttemptAnswer)
class AttemptAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt_question", "is_correct", "awarded", "needs_manual_marking")
    list_filter = ("needs_manual_marking", "is_correct")
    readonly_fields = tuple(field.name for field in AttemptAnswer._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False
