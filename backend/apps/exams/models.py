"""Final examinations — §5.5.

The design turns on one idea: **an attempt owns its own paper.**

When a candidate starts, the server draws questions from the bank, freezes them
into ``AttemptQuestion`` rows with the marks they were worth at that moment, and
fixes the order the options will be shown in. Everything afterwards — refresh,
browser close, network drop, marking, a dispute six months later — reads that
frozen copy. Editing the bank cannot rewrite a paper somebody has already sat,
and two candidates drawing different questions is a property of the design
rather than an accident.

Time is the server's
--------------------
``expires_at`` is computed once, from ``started_at`` and the exam's duration,
and stored. Nothing the browser sends can move it. A clock the candidate
controls is not a clock.

Scores are the server's
-----------------------
§5.5: *never calculate final scores from browser-submitted totals*. The client
sends which options it chose and what it typed. Every mark in this module is
computed here from the frozen paper.

Expiry without a worker
-----------------------
There is no background worker in this deployment yet, so an attempt is not
swept: it is finalised **lazily**, the next time anybody touches it, and the
grading uses whatever was auto-saved before the deadline. That is the same
outcome a sweep would produce, without a component that does not exist.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.uploads import submission_upload_to
from apps.common.validators import validate_no_control_characters


class ExamStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    CLOSED = "closed", _("Closed")
    ARCHIVED = "archived", _("Archived")


STUDENT_VISIBLE_STATUSES = frozenset({ExamStatus.PUBLISHED, ExamStatus.CLOSED})


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("In progress")
    SUBMITTED = "submitted", _("Submitted, awaiting marking")
    GRADED = "graded", _("Graded")
    EXPIRED = "expired", _("Time expired")


#: An attempt in one of these is finished: it cannot be answered any further.
CLOSED_ATTEMPT_STATUSES = frozenset(
    {AttemptStatus.SUBMITTED, AttemptStatus.GRADED, AttemptStatus.EXPIRED}
)


class ExamQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("batch", "course", "created_by").prefetch_related("sections")

    def student_visible(self):
        return self.filter(status__in=list(STUDENT_VISIBLE_STATUSES))


class Exam(BaseModel):
    """A final examination set for one batch."""

    code = models.CharField(_("code"), max_length=20, unique=True, editable=False)
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="exams")
    #: Derived from ``batch.course`` and checked in ``clean``; stored so
    #: course-level reporting does not join through batches.
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="exams")

    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    description = models.TextField(_("description"), blank=True)
    instructions = models.TextField(_("instructions"), blank=True)

    opens_at = models.DateTimeField(_("opens at"), null=True, blank=True)
    closes_at = models.DateTimeField(_("closes at"), null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(_("duration in minutes"), default=60)
    max_attempts = models.PositiveSmallIntegerField(_("maximum attempts"), default=1)

    passing_marks = models.DecimalField(
        _("passing marks"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave empty to take the passing rule from the academic configuration."),
    )
    negative_marking = models.BooleanField(
        _("negative marking"),
        default=False,
        help_text=_("Deduct each question's negative marks for a wrong answer."),
    )
    shuffle_questions = models.BooleanField(_("shuffle questions"), default=True)
    shuffle_options = models.BooleanField(_("shuffle options"), default=True)

    results_published = models.BooleanField(
        _("results published"),
        default=False,
        help_text=_("Until this is on, a candidate sees that they submitted and nothing more."),
    )
    results_published_at = models.DateTimeField(_("results published at"), null=True, blank=True)

    status = models.CharField(
        _("status"), max_length=12, choices=ExamStatus.choices, default=ExamStatus.DRAFT
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exams_created",
    )

    objects = ExamQuerySet.as_manager()

    class Meta:
        verbose_name = _("examination")
        verbose_name_plural = _("examinations")
        ordering = ("-opens_at", "-created_at")
        indexes = [
            models.Index(fields=["batch", "status"], name="exam_batch_status_idx"),
            models.Index(fields=["opens_at"], name="exam_opens_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gte=1), name="exam_duration_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1), name="exam_attempts_at_least_one"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closes_at__isnull=True)
                    | models.Q(opens_at__isnull=True)
                    | models.Q(closes_at__gt=models.F("opens_at"))
                ),
                name="exam_window_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if self.batch_id and self.course_id and self.batch.course_id != self.course_id:
            raise ValidationError({"course": "The course must be the one the batch runs."})

    @property
    def is_open(self) -> bool:
        """Whether an attempt could be started right now."""
        if self.status != ExamStatus.PUBLISHED:
            return False
        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        return not (self.closes_at and now > self.closes_at)

    def deadline_for(self, started_at):
        """When an attempt started at ``started_at`` must end.

        The earlier of "the duration ran out" and "the exam window closed" —
        a candidate starting five minutes before the window shuts gets five
        minutes, not the full hour.
        """
        ends = started_at + timedelta(minutes=self.duration_minutes)
        if self.closes_at and self.closes_at < ends:
            return self.closes_at
        return ends

    @property
    def total_questions(self) -> int:
        return sum(section.question_count for section in self.sections.all())


class ExamSection(BaseModel):
    """A part of the paper, and the pool it draws from.

    A section is a *rule*, not a list: "five medium questions tagged `linux`".
    Which five a candidate gets is decided when they start.
    """

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(
        _("title"), max_length=200, validators=[validate_no_control_characters]
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    question_count = models.PositiveSmallIntegerField(_("questions to draw"), default=5)

    #: Optional filters on the pool. Empty means "no restriction".
    difficulty = models.CharField(_("difficulty"), max_length=8, blank=True)
    question_type = models.CharField(_("type"), max_length=14, blank=True)
    tags = models.JSONField(_("tags"), default=list, blank=True)

    class Meta:
        verbose_name = _("examination section")
        verbose_name_plural = _("examination sections")
        ordering = ("position", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(question_count__gte=1), name="section_draws_at_least_one"
            ),
            models.UniqueConstraint(
                fields=["exam", "position"],
                name="section_unique_position",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]

    def __str__(self) -> str:
        return self.title


class AttemptQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "exam",
            "exam__batch",
            "enrollment",
            "enrollment__student",
            "enrollment__student__user",
        )


class ExamAttempt(BaseModel):
    """One candidate's sitting, and the only place a score is stored."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    enrollment = models.ForeignKey(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="exam_attempts"
    )
    attempt_number = models.PositiveSmallIntegerField(_("attempt"), default=1)

    status = models.CharField(
        _("status"), max_length=12, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(_("started at"), default=timezone.now)
    #: Computed once, from the server's clock. Never accepted from a client.
    expires_at = models.DateTimeField(_("expires at"))
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    graded_at = models.DateTimeField(_("graded at"), null=True, blank=True)

    auto_score = models.DecimalField(
        _("auto-marked score"), max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    manual_score = models.DecimalField(
        _("manually marked score"), max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    total_score = models.DecimalField(
        _("total score"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    max_score = models.DecimalField(
        _("paper total"), max_digits=8, decimal_places=2, default=Decimal("0.00")
    )

    objects = AttemptQuerySet.as_manager()

    class Meta:
        verbose_name = _("examination attempt")
        verbose_name_plural = _("examination attempts")
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["exam", "status"], name="attempt_exam_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "enrollment", "attempt_number"],
                name="attempt_one_row_per_sitting",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_number__gte=1), name="attempt_number_at_least_one"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.exam_id} · attempt {self.attempt_number}"

    @property
    def is_open(self) -> bool:
        return self.status == AttemptStatus.IN_PROGRESS and timezone.now() <= self.expires_at

    @property
    def has_expired(self) -> bool:
        return self.status == AttemptStatus.IN_PROGRESS and timezone.now() > self.expires_at

    @property
    def seconds_remaining(self) -> int:
        """What the candidate's timer should show. Computed here, always."""
        if self.status != AttemptStatus.IN_PROGRESS:
            return 0
        return max(0, int((self.expires_at - timezone.now()).total_seconds()))

    @property
    def needs_manual_marking(self) -> bool:
        return self.questions.filter(answer__needs_manual_marking=True).exists()

    @property
    def is_passing(self) -> bool | None:
        """Derived on read, from the exam's threshold or the academic rules."""
        if self.total_score is None:
            return None

        from apps.academics.policies import policy_for

        threshold = self.exam.passing_marks
        if threshold is None:
            threshold = policy_for(self.exam.course_id).passing_mark_for(self.max_score)
        return self.total_score >= threshold

    @property
    def percentage(self) -> float | None:
        if self.total_score is None or not self.max_score:
            return None
        return round(float(self.total_score) / float(self.max_score) * 100, 2)


class AttemptQuestion(BaseModel):
    """One question as it appeared on one candidate's paper.

    ``marks`` and ``negative_marks`` are copied rather than read through the
    relation: the paper was worth what it was worth on the day, whatever the
    bank says later.
    """

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="questions")
    question = models.ForeignKey(
        "questions.Question", on_delete=models.PROTECT, related_name="exam_appearances"
    )
    section = models.ForeignKey(
        ExamSection, null=True, blank=True, on_delete=models.SET_NULL, related_name="drawn"
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    marks = models.DecimalField(_("marks"), max_digits=6, decimal_places=2)
    negative_marks = models.DecimalField(
        _("negative marks"), max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    #: Option ids in the order this candidate saw them.
    option_order = models.JSONField(_("option order"), default=list, blank=True)

    class Meta:
        verbose_name = _("attempt question")
        verbose_name_plural = _("attempt questions")
        ordering = ("position",)
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "position"],
                name="attemptquestion_unique_position",
                deferrable=models.Deferrable.DEFERRED,
            ),
            models.UniqueConstraint(
                fields=["attempt", "question"], name="attemptquestion_no_duplicates"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} Q{self.position}"


class AttemptAnswer(BaseModel):
    """What the candidate put down, and what it earned.

    One row per question, created on the first auto-save and updated after —
    so a refresh, a closed browser or a dropped connection all resume from the
    same place.
    """

    attempt_question = models.OneToOneField(
        AttemptQuestion, on_delete=models.CASCADE, related_name="answer"
    )

    selected_options = models.JSONField(_("selected options"), default=list, blank=True)
    text_answer = models.TextField(_("written answer"), blank=True)
    file = models.FileField(
        _("file"), upload_to=submission_upload_to, max_length=255, null=True, blank=True
    )
    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)

    is_correct = models.BooleanField(_("correct"), null=True, blank=True)
    awarded = models.DecimalField(
        _("marks awarded"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    needs_manual_marking = models.BooleanField(_("needs marking"), default=False)
    marker_feedback = models.TextField(_("marker feedback"), blank=True)

    answered_at = models.DateTimeField(_("answered at"), auto_now=True)

    class Meta:
        verbose_name = _("attempt answer")
        verbose_name_plural = _("attempt answers")
        ordering = ("attempt_question__position",)

    def __str__(self) -> str:
        return str(self.attempt_question_id)

    @property
    def is_blank(self) -> bool:
        """An unanswered question. Never attracts a negative mark."""
        return not (self.selected_options or self.text_answer.strip() or self.file)
