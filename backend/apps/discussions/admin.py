"""Django admin for discussions."""

from django.contrib import admin

from .models import Reply, Thread


class ReplyInline(admin.TabularInline):
    model = Reply
    extra = 0
    fields = ("author", "body", "is_trainer_response", "is_hidden", "hidden_reason")
    readonly_fields = ("author", "body", "is_trainer_response")


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("title", "batch", "author", "reply_count", "is_pinned", "is_closed")
    list_filter = ("is_pinned", "is_closed", "has_trainer_reply")
    search_fields = ("title", "body", "batch__code")
    readonly_fields = ("id", "reply_count", "last_reply_at", "created_at", "updated_at")
    inlines = (ReplyInline,)
