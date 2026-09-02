"""Learning-surface serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import LessonBookmark, LessonNote


class LessonRefSerializer(StrictSerializer):
    lesson_id = serializers.CharField()
    lesson_title = serializers.CharField()
    module_title = serializers.CharField()
    course_slug = serializers.CharField()
    last_accessed_at = serializers.DateTimeField(allow_null=True)


class RecentLessonSerializer(LessonRefSerializer):
    status = serializers.CharField()


class HistoryEntrySerializer(StrictSerializer):
    lesson_title = serializers.CharField()
    module_title = serializers.CharField()
    status = serializers.CharField()
    first_accessed_at = serializers.DateTimeField()
    last_accessed_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class UpcomingSerializer(StrictSerializer):
    kind = serializers.CharField()
    title = serializers.CharField()
    start = serializers.DateTimeField()
    course_title = serializers.CharField(allow_blank=True)
    batch_code = serializers.CharField(allow_blank=True)
    metadata = serializers.DictField()


class BookmarkSerializer(StrictModelSerializer):
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    module_title = serializers.CharField(source="lesson.module.title", read_only=True)
    course_slug = serializers.CharField(source="lesson.module.course.slug", read_only=True)

    class Meta:
        model = LessonBookmark
        fields = (
            "id",
            "lesson",
            "lesson_title",
            "module_title",
            "course_slug",
            "note",
            "created_at",
        )
        read_only_fields = fields


class NoteSerializer(StrictModelSerializer):
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    module_title = serializers.CharField(source="lesson.module.title", read_only=True)
    course_slug = serializers.CharField(source="lesson.module.course.slug", read_only=True)

    class Meta:
        model = LessonNote
        fields = (
            "id",
            "lesson",
            "lesson_title",
            "module_title",
            "course_slug",
            "body",
            "updated_at",
        )
        read_only_fields = fields


class BookmarkWriteSerializer(StrictSerializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class NoteWriteSerializer(StrictSerializer):
    body = serializers.CharField(allow_blank=True, max_length=20000)


class LearningHomeSerializer(StrictSerializer):
    """Everything the student's home screen needs, in one call."""

    enrollment_id = serializers.CharField()
    course_title = serializers.CharField()
    course_slug = serializers.CharField()
    batch_code = serializers.CharField()
    continue_learning = LessonRefSerializer(allow_null=True)
    recent = RecentLessonSerializer(many=True)


class PeerSerializer(StrictSerializer):
    """§7.7 — a classmate, with nothing that could contact them.

    Written as an explicit list rather than a model serializer: the risk is a
    field being added to the student profile later and appearing here.
    """

    full_name = serializers.CharField()
    student_code = serializers.CharField()
    is_you = serializers.BooleanField()
