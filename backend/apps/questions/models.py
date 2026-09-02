"""The question bank — §5.4.

Reusable questions, kept separate from any exam that draws on them. That
separation is the whole point: a question written once is used by several
papers, and editing it must not silently rewrite a paper somebody has already
sat — which is why an exam attempt *freezes* the questions it drew (see
``apps.exams``).

What must never leak
--------------------
``QuestionOption.is_correct``, ``Question.answer_key`` and
``Question.explanation`` are the answers. They live on the model, and the
student-facing serializer simply does not contain those fields — not filtered
out downstream, not blanked at render time. A field a student must not see is
absent from their serializer, so no future change to a view can expose it by
accident.

Grading
-------
``MCQ``, ``MULTIPLE``, ``TRUE_FALSE`` and ``SHORT_ANSWER`` are auto-gradable.
``LONG_ANSWER`` and ``FILE`` are not, and are marked by a person. The model
knows which is which so the exam engine never has to guess.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class QuestionType(models.TextChoices):
    MCQ = "mcq", _("Multiple choice, one answer")
    MULTIPLE = "multiple", _("Multiple choice, several answers")
    TRUE_FALSE = "true_false", _("True or false")
    SHORT_ANSWER = "short_answer", _("Short answer")
    LONG_ANSWER = "long_answer", _("Long answer")
    FILE = "file", _("File upload")


#: Types the server can mark on its own.
AUTO_GRADED_TYPES = frozenset(
    {
        QuestionType.MCQ,
        QuestionType.MULTIPLE,
        QuestionType.TRUE_FALSE,
        QuestionType.SHORT_ANSWER,
    }
)

#: Types that carry a list of options.
OPTION_TYPES = frozenset({QuestionType.MCQ, QuestionType.MULTIPLE, QuestionType.TRUE_FALSE})

#: Types a person must read.
MANUAL_TYPES = frozenset({QuestionType.LONG_ANSWER, QuestionType.FILE})


class Difficulty(models.TextChoices):
    EASY = "easy", _("Easy")
    MEDIUM = "medium", _("Medium")
    HARD = "hard", _("Hard")


class QuestionQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("course", "created_by").prefetch_related("options")

    def usable(self):
        """Active questions only — an exam must never draw a retired question."""
        return self.filter(is_active=True)


class Question(BaseModel):
    """One reusable question."""

    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="questions",
        help_text=_("Leave empty for a question shared across every course."),
    )
    module = models.ForeignKey(
        "courses.Module", null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )

    question_type = models.CharField(
        _("type"), max_length=14, choices=QuestionType.choices, default=QuestionType.MCQ
    )
    text = models.TextField(_("question"), validators=[validate_no_control_characters])
    difficulty = models.CharField(
        _("difficulty"), max_length=8, choices=Difficulty.choices, default=Difficulty.MEDIUM
    )

    marks = models.DecimalField(_("marks"), max_digits=6, decimal_places=2, default=Decimal("1.00"))
    negative_marks = models.DecimalField(
        _("negative marks"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Deducted for a wrong answer when the exam has negative marking on."),
    )

    tags = ArrayField(
        models.CharField(max_length=40),
        verbose_name=_("tags"),
        default=list,
        blank=True,
        help_text=_("Used to draw a paper from a topic. Lower-case, no spaces."),
    )

    #: The answers. Never present in a student-facing serializer.
    answer_key = ArrayField(
        models.CharField(max_length=200),
        verbose_name=_("accepted answers"),
        default=list,
        blank=True,
        help_text=_("Short-answer only. Compared case- and whitespace-insensitively."),
    )
    explanation = models.TextField(
        _("explanation"), blank=True, help_text=_("Shown after results are published.")
    )

    is_active = models.BooleanField(_("active"), default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="questions_created",
    )

    objects = QuestionQuerySet.as_manager()

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["course", "is_active"], name="question_course_active_idx"),
            models.Index(fields=["question_type", "difficulty"], name="question_type_diff_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(marks__gt=0), name="question_marks_positive"),
            models.CheckConstraint(
                condition=models.Q(negative_marks__gte=0), name="question_negative_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.text[:60]

    @property
    def is_auto_graded(self) -> bool:
        return self.question_type in AUTO_GRADED_TYPES

    @property
    def needs_options(self) -> bool:
        return self.question_type in OPTION_TYPES

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.module_id and self.course_id and self.module.course_id != self.course_id:
            errors["module"] = "That module belongs to a different course."
        if self.question_type == QuestionType.SHORT_ANSWER and not self.answer_key:
            errors["answer_key"] = "A short-answer question needs at least one accepted answer."
        if self.question_type != QuestionType.SHORT_ANSWER and self.answer_key:
            errors["answer_key"] = "Only a short-answer question carries accepted answers."
        if self.tags and any(tag != tag.strip().lower() or " " in tag for tag in self.tags):
            errors["tags"] = "Tags must be lower-case and contain no spaces."
        if errors:
            raise ValidationError(errors)

    def validate_options(self) -> None:
        """Check the option set. Called by the service after options are saved.

        A model ``clean`` cannot do this: the options do not exist until after
        the question row does.
        """
        from django.core.exceptions import ValidationError

        options = list(self.options.all())
        correct = [option for option in options if option.is_correct]

        if not self.needs_options:
            if options:
                raise ValidationError({"options": "This question type does not take options."})
            return

        if self.question_type == QuestionType.TRUE_FALSE:
            if len(options) != 2:
                raise ValidationError(
                    {"options": "A true/false question needs exactly two options."}
                )
        elif len(options) < 2:
            raise ValidationError({"options": "Give at least two options."})

        if not correct:
            raise ValidationError({"options": "Mark at least one option correct."})
        if self.question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE) and len(correct) != 1:
            raise ValidationError({"options": "Exactly one option may be correct."})

    def matches_short_answer(self, given: str) -> bool:
        """Whether a short answer counts as correct.

        Compared on a normalised form — trimmed, lower-cased, inner whitespace
        collapsed — because "  Paris " and "paris" are the same answer and
        marking them differently would be indefensible.
        """
        import re

        def normalise(value: str) -> str:
            return re.sub(r"\s+", " ", (value or "")).strip().lower()

        target = normalise(given)
        return any(normalise(accepted) == target for accepted in self.answer_key)


class QuestionOption(BaseModel):
    """One choice on a question. ``is_correct`` is never sent to a student."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(_("option"), max_length=500)
    is_correct = models.BooleanField(_("correct"), default=False)
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("question option")
        verbose_name_plural = _("question options")
        ordering = ("position", "created_at")
        indexes = [models.Index(fields=["question", "position"], name="option_question_pos_idx")]

    def __str__(self) -> str:
        return self.text[:60]
