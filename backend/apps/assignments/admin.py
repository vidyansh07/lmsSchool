"""Django admin for assignments.

Read-mostly. Marks, statuses and files move through the service layer, which
validates the mark against the assignment's maximum and writes the audit
entry; an admin form that wrote them directly would bypass both.
"""

from django.contrib import admin

from .models import Assignment, AssignmentAttachment, AssignmentSubmission, SubmissionFile


class AttachmentInline(admin.TabularInline):
    model = AssignmentAttachment
    extra = 0
    fields = ("title", "original_filename", "content_type", "size_bytes")
    readonly_fields = fields
    can_delete = False


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "course", "batch", "status", "due_at", "max_marks")
    list_filter = ("status", "submission_kind", "allow_late", "allow_resubmission")
    search_fields = ("code", "title", "course__title", "batch__code")
    readonly_fields = ("id", "code", "published_at", "created_by", "created_at", "updated_at")
    inlines = (AttachmentInline,)
    ordering = ("-created_at",)


class SubmissionFileInline(admin.TabularInline):
    model = SubmissionFile
    extra = 0
    fields = ("original_filename", "extension", "size_bytes", "checksum")
    readonly_fields = fields
    can_delete = False


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "enrollment", "attempt", "status", "is_late", "marks_awarded")
    list_filter = ("status", "is_late")
    search_fields = (
        "assignment__code",
        "enrollment__student__student_id",
        "enrollment__student__user__email",
    )
    readonly_fields = (
        "id",
        "assignment",
        "enrollment",
        "attempt",
        "submitted_at",
        "is_late",
        "marks_awarded",
        "graded_by",
        "graded_at",
        "created_at",
        "updated_at",
    )
    inlines = (SubmissionFileInline,)
    ordering = ("-submitted_at",)

    def has_add_permission(self, request) -> bool:
        return False
