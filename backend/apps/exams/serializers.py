"""Examination serializers.

The important one is :class:`CandidateQuestionSerializer`. It is the shape a
person sitting the exam sees, and it does not contain ``is_correct``,
``answer_key`` or ``explanation`` — not blanked, not filtered, **absent**. A
field that is not on the class cannot be leaked by a later change to a view.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import AttemptQuestion, Exam, ExamAttempt, ExamSection, ExamStatus

EXAM_STATUS_CHOICES = list(ExamStatus.choices)


class SectionSerializer(StrictModelSerializer):
    class Meta:
        model = ExamSection
        fields = (
            "id",
            "title",
            "position",
            "question_count",
            "difficulty",
            "question_type",
            "tags",
        )
        read_only_fields = fields


class ExamSerializer(StrictModelSerializer):
    """The staff view."""

    batch_code = serializers.CharField(source="batch.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    sections = SectionSerializer(many=True, read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    total_questions = serializers.IntegerField(read_only=True)
    attempt_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Exam
        fields = (
            "id",
            "code",
            "batch",
            "batch_code",
            "course",
            "course_title",
            "title",
            "description",
            "instructions",
            "opens_at",
            "closes_at",
            "duration_minutes",
            "max_attempts",
            "passing_marks",
            "negative_marking",
            "shuffle_questions",
            "shuffle_options",
            "results_published",
            "results_published_at",
            "status",
            "published_at",
            "is_open",
            "total_questions",
            "attempt_count",
            "sections",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SectionWriteSerializer(StrictSerializer):
    title = SafeCharField(max_length=200)
    question_count = serializers.IntegerField(min_value=1, max_value=200)
    difficulty = serializers.CharField(required=False, allow_blank=True, max_length=8)
    question_type = serializers.CharField(required=False, allow_blank=True, max_length=14)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, allow_empty=True
    )


class ExamWriteSerializer(StrictSerializer):
    """Create and edit. ``status`` and ``results_published`` have own endpoints."""

    title = SafeCharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    opens_at = serializers.DateTimeField(required=False, allow_null=True)
    closes_at = serializers.DateTimeField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(required=False, min_value=1, max_value=1440)
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10)
    passing_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    negative_marking = serializers.BooleanField(required=False)
    shuffle_questions = serializers.BooleanField(required=False)
    shuffle_options = serializers.BooleanField(required=False)
    sections = serializers.ListField(child=SectionWriteSerializer(), required=False)


class ExamStatusSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=EXAM_STATUS_CHOICES)


class PublishResultsSerializer(StrictSerializer):
    published = serializers.BooleanField(default=True)


class ReadinessSerializer(StrictSerializer):
    """Whether the paper can actually be drawn."""

    ready = serializers.BooleanField()
    problems = serializers.ListField(child=serializers.CharField())
    sections = serializers.IntegerField()
    questions = serializers.IntegerField()
    approximate_total_marks = serializers.CharField()


# ---------------------------------------------------------------------------
# What a candidate sees
# ---------------------------------------------------------------------------


class CandidateOptionSerializer(StrictSerializer):
    """One option, in the order this candidate was given. No ``is_correct``."""

    id = serializers.CharField()
    text = serializers.CharField()


class CandidateQuestionSerializer(StrictSerializer):
    """A question as it appears on the paper. Carries no answer, by construction."""

    id = serializers.UUIDField()
    position = serializers.IntegerField()
    section = serializers.CharField(allow_null=True)
    question_type = serializers.CharField()
    text = serializers.CharField()
    marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    negative_marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    options = CandidateOptionSerializer(many=True)
    selected_options = serializers.ListField(child=serializers.CharField())
    text_answer = serializers.CharField(allow_blank=True)
    answered_filename = serializers.CharField(allow_blank=True)


class AttemptSerializer(StrictModelSerializer):
    """The candidate's view of their own sitting.

    ``seconds_remaining`` is computed on the server for every response, so the
    browser's clock is a display detail rather than a source of truth.
    """

    exam_code = serializers.CharField(source="exam.code", read_only=True)
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    seconds_remaining = serializers.IntegerField(read_only=True)
    results_published = serializers.BooleanField(source="exam.results_published", read_only=True)

    class Meta:
        model = ExamAttempt
        fields = (
            "id",
            "exam",
            "exam_code",
            "exam_title",
            "attempt_number",
            "status",
            "started_at",
            "expires_at",
            "submitted_at",
            "seconds_remaining",
            "results_published",
        )
        read_only_fields = fields


class AttemptPaperSerializer(StrictSerializer):
    """An attempt plus its questions — one request renders the whole screen."""

    attempt = AttemptSerializer()
    questions = CandidateQuestionSerializer(many=True)


class AttemptResultSerializer(StrictModelSerializer):
    """A candidate's result. Empty of scores until the exam publishes them."""

    exam_code = serializers.CharField(source="exam.code", read_only=True)
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    is_passing = serializers.BooleanField(read_only=True, allow_null=True)
    percentage = serializers.FloatField(read_only=True, allow_null=True)
    results_published = serializers.BooleanField(source="exam.results_published", read_only=True)

    class Meta:
        model = ExamAttempt
        fields = (
            "id",
            "exam",
            "exam_code",
            "exam_title",
            "attempt_number",
            "status",
            "submitted_at",
            "graded_at",
            "total_score",
            "max_score",
            "is_passing",
            "percentage",
            "results_published",
        )
        read_only_fields = fields


class StaffAttemptSerializer(AttemptResultSerializer):
    """The marker's view. Adds who sat it and the split of the score."""

    student_id = serializers.CharField(source="enrollment.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="enrollment.student.user.get_full_name", read_only=True
    )
    batch_code = serializers.CharField(source="enrollment.batch.code", read_only=True)
    needs_manual_marking = serializers.BooleanField(read_only=True)

    class Meta(AttemptResultSerializer.Meta):
        fields = (
            *AttemptResultSerializer.Meta.fields,
            "enrollment",
            "student_id",
            "student_name",
            "batch_code",
            "auto_score",
            "manual_score",
            "needs_manual_marking",
            "started_at",
            "expires_at",
        )
        read_only_fields = fields


class SaveAnswerSerializer(StrictSerializer):
    """An auto-save. There is no score field — the server decides that."""

    selected_options = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, allow_empty=True
    )
    text_answer = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    file = serializers.FileField(required=False)


class MarkAnswerSerializer(StrictSerializer):
    awarded = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal(0))
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class MarkableAnswerSerializer(StrictSerializer):
    """A written answer waiting for a marker."""

    id = serializers.UUIDField()
    attempt = serializers.UUIDField()
    position = serializers.IntegerField()
    question_text = serializers.CharField()
    question_type = serializers.CharField()
    marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    text_answer = serializers.CharField(allow_blank=True)
    answered_filename = serializers.CharField(allow_blank=True)
    awarded = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    marker_feedback = serializers.CharField(allow_blank=True)
    student_id = serializers.CharField()
    student_name = serializers.CharField()


class ReviewedQuestionSerializer(StrictSerializer):
    """A question with its outcome, shown only after results are published."""

    position = serializers.IntegerField()
    question_text = serializers.CharField()
    question_type = serializers.CharField()
    marks = serializers.DecimalField(max_digits=6, decimal_places=2)
    awarded = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    is_correct = serializers.BooleanField(allow_null=True)
    explanation = serializers.CharField(allow_blank=True)
    marker_feedback = serializers.CharField(allow_blank=True)


class AttemptReviewSerializer(StrictSerializer):
    attempt = AttemptResultSerializer()
    questions = ReviewedQuestionSerializer(many=True)


def candidate_question_payload(attempt_question: AttemptQuestion) -> dict:
    """Build a candidate-safe question, in the order they were given.

    Written as a function rather than a serializer field so the ordering of the
    options — which is per attempt — is applied in one place.
    """
    question = attempt_question.question
    by_id = {str(option.pk): option for option in question.options.all()}
    ordered = [by_id[key] for key in attempt_question.option_order if key in by_id]
    answer = getattr(attempt_question, "answer", None)

    return {
        "id": attempt_question.pk,
        "position": attempt_question.position,
        "section": attempt_question.section.title if attempt_question.section_id else None,
        "question_type": question.question_type,
        "text": question.text,
        "marks": attempt_question.marks,
        "negative_marks": attempt_question.negative_marks,
        "options": [{"id": str(option.pk), "text": option.text} for option in ordered],
        "selected_options": list(answer.selected_options) if answer else [],
        "text_answer": answer.text_answer if answer else "",
        "answered_filename": answer.original_filename if answer else "",
    }
