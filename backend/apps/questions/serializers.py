"""Question bank serializers.

Two shapes, and the difference is the point:

``QuestionSerializer``
    The author's view. Carries ``is_correct``, ``answer_key`` and
    ``explanation``.

``ExamQuestionSerializer`` (in ``apps.exams``)
    The candidate's view. Those fields are *absent from the class*, not
    filtered out at render time — so no future change to a view can leak them.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import StrictModelSerializer, StrictSerializer

from .models import Difficulty, Question, QuestionOption, QuestionType


class OptionSerializer(StrictModelSerializer):
    """Author-facing. Includes the answer."""

    class Meta:
        model = QuestionOption
        fields = ("id", "text", "is_correct", "position")
        read_only_fields = fields


class QuestionSerializer(StrictModelSerializer):
    """The author's view of a question."""

    options = OptionSerializer(many=True, read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    is_auto_graded = serializers.BooleanField(read_only=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "course",
            "course_title",
            "module",
            "question_type",
            "text",
            "difficulty",
            "marks",
            "negative_marks",
            "tags",
            "answer_key",
            "explanation",
            "is_active",
            "is_auto_graded",
            "options",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class OptionWriteSerializer(StrictSerializer):
    text = serializers.CharField(max_length=500)
    is_correct = serializers.BooleanField(required=False, default=False)


class QuestionWriteSerializer(StrictSerializer):
    course = serializers.UUIDField(required=False, allow_null=True)
    module = serializers.UUIDField(required=False, allow_null=True)
    question_type = serializers.ChoiceField(choices=QuestionType.choices, required=False)
    text = serializers.CharField(max_length=5000)
    difficulty = serializers.ChoiceField(choices=Difficulty.choices, required=False)
    marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    negative_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False
    )
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, allow_empty=True
    )
    answer_key = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, allow_empty=True
    )
    explanation = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    is_active = serializers.BooleanField(required=False)
    options = serializers.ListField(child=OptionWriteSerializer(), required=False)
