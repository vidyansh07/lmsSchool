"""Examination services.

Three invariants hold everywhere in this module, and every §5.6 failure case is
a consequence of one of them.

**The paper is drawn once.** ``start_attempt`` is idempotent: an in-progress
attempt is *resumed*, never duplicated. Refresh, a closed browser, a dropped
connection and a double-clicked button all land on the same rows.

**Time is the server's.** ``expires_at`` is written when the attempt starts and
never recomputed. A client that lies about the time changes nothing.

**Scores are the server's.** The client sends option ids and text. Marks are
computed here from the frozen paper — there is no field on any serializer in
which a total could arrive.
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_exam_code
from apps.common.uploads import validate_submission_upload
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.questions.models import MANUAL_TYPES, OPTION_TYPES, Question, QuestionType

from .models import (
    CLOSED_ATTEMPT_STATUSES,
    AttemptAnswer,
    AttemptQuestion,
    AttemptStatus,
    Exam,
    ExamAttempt,
    ExamSection,
    ExamStatus,
)

#: A cryptographically-seeded generator, not `random`.
#:
#: Which questions a candidate draws, and the order their options appear in, are
#: the difference between two papers. A predictable stream would let anyone who
#: could observe one paper narrow down another's, which is a cheating vector in
#: an examination even though it is harmless in a shuffle.
_rng = secrets.SystemRandom()

TRANSITIONS: dict[str, frozenset[str]] = {
    ExamStatus.DRAFT: frozenset({ExamStatus.PUBLISHED, ExamStatus.ARCHIVED}),
    ExamStatus.PUBLISHED: frozenset({ExamStatus.CLOSED, ExamStatus.ARCHIVED}),
    ExamStatus.CLOSED: frozenset({ExamStatus.PUBLISHED, ExamStatus.ARCHIVED}),
    ExamStatus.ARCHIVED: frozenset(),
}

SITTABLE_STATUSES = frozenset(
    {EnrollmentStatus.ACTIVE, EnrollmentStatus.SUSPENDED, EnrollmentStatus.COMPLETED}
)


# ---------------------------------------------------------------------------
# The paper
# ---------------------------------------------------------------------------


@transaction.atomic
def create_exam(*, actor: User, batch, sections: list | None = None, **fields: Any) -> Exam:
    """Create an examination in draft, with its sections."""
    fields.pop("status", None)
    exam = Exam(
        code=next_exam_code(),
        batch=batch,
        course=batch.course,
        created_by=actor if getattr(actor, "pk", None) else None,
        status=ExamStatus.DRAFT,
        **fields,
    )
    _validate(exam)
    exam.save()

    if sections:
        replace_sections(exam=exam, sections=sections)

    record(
        action=AuditAction.EXAM_CREATED,
        actor=actor,
        resource_type="exam",
        resource_id=exam.pk,
        context={"code": exam.code, "batch": str(batch.pk), "duration": exam.duration_minutes},
        durable=False,
    )
    return exam


@transaction.atomic
def update_exam(*, exam: Exam, actor: User, sections: list | None = None, **fields: Any) -> Exam:
    """Edit an examination.

    Once anybody has sat it, the shape of the paper and how it is marked are
    fixed. Candidates already graded were graded under those rules, and quietly
    changing them would make two sittings incomparable.
    """
    fields.pop("status", None)
    if exam.attempts.exists():
        locked = {"duration_minutes", "negative_marking", "max_attempts"}
        blocked = sorted(locked & set(fields))
        if blocked or sections is not None:
            raise ConflictError(
                {
                    field: ["This cannot change once the examination has been sat."]
                    for field in (blocked or ["sections"])
                }
            )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(exam, field) != value:
            setattr(exam, field, value)
            changed.append(field)

    if sections is not None:
        replace_sections(exam=exam, sections=sections)
        changed.append("sections")

    if not changed:
        return exam

    _validate(exam)
    exam.save()

    record(
        action=AuditAction.EXAM_UPDATED,
        actor=actor,
        resource_type="exam",
        resource_id=exam.pk,
        context={"code": exam.code, "fields": sorted(set(changed))},
        durable=False,
    )
    return exam


def replace_sections(*, exam: Exam, sections: list) -> None:
    exam.sections.all().delete()
    rows = []
    for position, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ApplicationError({"sections": ["Each section must be an object."]})
        title = str(section.get("title", "")).strip()
        if not title:
            raise ApplicationError({"sections": ["Every section needs a title."]})
        try:
            count = int(section.get("question_count", 0))
        except (TypeError, ValueError) as exc:
            raise ApplicationError({"sections": ["'question_count' must be a number."]}) from exc
        if count < 1:
            raise ApplicationError({"sections": [f"'{title}' must draw at least one question."]})
        rows.append(
            ExamSection(
                exam=exam,
                title=title[:200],
                position=position,
                question_count=count,
                difficulty=str(section.get("difficulty", "") or ""),
                question_type=str(section.get("question_type", "") or ""),
                tags=list(section.get("tags") or []),
            )
        )
    ExamSection.objects.bulk_create(rows)


@transaction.atomic
def set_exam_status(*, exam: Exam, actor: User, status: str) -> Exam:
    if status == exam.status:
        return exam
    if status not in TRANSITIONS.get(exam.status, frozenset()):
        raise ConflictError(
            {"status": [f"An examination cannot go from {exam.status} to {status}."]}
        )
    if status == ExamStatus.PUBLISHED:
        # Publishing a paper that cannot be drawn would hand every candidate an
        # error the moment they pressed Start.
        readiness = check_readiness(exam)
        if not readiness["ready"]:
            raise ApplicationError({"sections": readiness["problems"]})

    previous = exam.status
    exam.status = status
    if status == ExamStatus.PUBLISHED and exam.published_at is None:
        exam.published_at = timezone.now()
    exam.save(update_fields=["status", "published_at", "updated_at"])

    record(
        action=AuditAction.EXAM_STATUS_CHANGED,
        actor=actor,
        resource_type="exam",
        resource_id=exam.pk,
        context={"code": exam.code, "from": previous, "to": status},
        durable=False,
    )
    return exam


def _validate(exam: Exam) -> None:
    try:
        exam.full_clean(exclude=["code"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


# ---------------------------------------------------------------------------
# Drawing a paper
# ---------------------------------------------------------------------------


def _pool_for(exam: Exam, section: ExamSection):
    """The questions a section may draw from.

    Restricted to the exam's own course plus the shared bank, and to active
    questions only — a retired question must never appear on a new paper.
    """
    from django.db.models import Q

    pool = Question.objects.usable().filter(Q(course_id=exam.course_id) | Q(course__isnull=True))
    if section.difficulty:
        pool = pool.filter(difficulty=section.difficulty)
    if section.question_type:
        pool = pool.filter(question_type=section.question_type)
    if section.tags:
        pool = pool.filter(tags__overlap=list(section.tags))
    return pool


def check_readiness(exam: Exam) -> dict[str, Any]:
    """Whether every section can actually be filled.

    Surfaced to staff before publishing, because "not enough questions" is a
    thing to discover while writing the paper, not while sitting it.
    """
    problems: list[str] = []
    sections = list(exam.sections.all())
    if not sections:
        problems.append("The examination has no sections.")

    total_marks = Decimal("0")
    for section in sections:
        available = _pool_for(exam, section).count()
        if available < section.question_count:
            problems.append(
                f"'{section.title}' needs {section.question_count} questions "
                f"but only {available} match."
            )
        else:
            cheapest = (
                _pool_for(exam, section)
                .order_by("marks")
                .values_list("marks", flat=True)[: section.question_count]
            )
            total_marks += sum(cheapest, Decimal("0"))

    return {
        "ready": not problems,
        "problems": problems,
        "sections": len(sections),
        "questions": sum(section.question_count for section in sections),
        "approximate_total_marks": str(total_marks),
    }


def _draw_paper(attempt: ExamAttempt) -> Decimal:
    """Pick this candidate's questions and freeze them. Returns the paper total."""
    exam = attempt.exam
    rows: list[AttemptQuestion] = []
    position = 0
    max_score = Decimal("0")
    used: set = set()

    for section in exam.sections.all():
        pool = list(_pool_for(exam, section).exclude(pk__in=used).prefetch_related("options"))
        if len(pool) < section.question_count:
            raise ApplicationError(
                {
                    "exam": [
                        f"'{section.title}' does not have enough questions to draw. "
                        "Ask your trainer."
                    ]
                }
            )
        drawn = _rng.sample(pool, section.question_count)
        if not exam.shuffle_questions:
            drawn.sort(key=lambda question: str(question.pk))

        for question in drawn:
            used.add(question.pk)
            option_ids = [str(option.pk) for option in question.options.all()]
            if exam.shuffle_options and question.question_type in OPTION_TYPES:
                _rng.shuffle(option_ids)
            rows.append(
                AttemptQuestion(
                    attempt=attempt,
                    question=question,
                    section=section,
                    position=position,
                    marks=question.marks,
                    negative_marks=question.negative_marks,
                    option_order=option_ids,
                )
            )
            max_score += question.marks
            position += 1

    AttemptQuestion.objects.bulk_create(rows)
    return max_score


# ---------------------------------------------------------------------------
# Sitting it
# ---------------------------------------------------------------------------


def enrollment_for(*, exam: Exam, student) -> Enrollment | None:
    return (
        Enrollment.objects.filter(
            student=student, batch_id=exam.batch_id, status__in=SITTABLE_STATUSES
        )
        .select_related("batch")
        .first()
    )


@transaction.atomic
def start_attempt(*, exam: Exam, enrollment: Enrollment, actor: User) -> ExamAttempt:
    """Start, or resume, this candidate's attempt.

    Idempotent by design. A candidate who refreshes, whose browser crashes, or
    who double-clicks Start gets the attempt they already have, with the paper
    they were already given and the clock that was already running.
    """
    existing = (
        ExamAttempt.objects.select_for_update()
        .filter(exam=exam, enrollment=enrollment)
        .order_by("-attempt_number")
        .first()
    )

    if existing is not None and existing.status == AttemptStatus.IN_PROGRESS:
        if existing.has_expired:
            return finalise_expired(attempt=existing, actor=actor)
        return existing

    if not exam.is_open:
        raise ApplicationError({"exam": ["This examination is not open."]})

    used = ExamAttempt.objects.filter(exam=exam, enrollment=enrollment).count()
    if used >= exam.max_attempts:
        raise ConflictError(
            {"exam": [f"You have used all {exam.max_attempts} attempts for this examination."]}
        )

    started = timezone.now()
    attempt = ExamAttempt(
        exam=exam,
        enrollment=enrollment,
        attempt_number=used + 1,
        status=AttemptStatus.IN_PROGRESS,
        started_at=started,
        expires_at=exam.deadline_for(started),
    )
    try:
        # A savepoint, so that losing the race leaves the outer transaction
        # usable and we can go and read the row that won.
        with transaction.atomic():
            attempt.save()
    except IntegrityError as exc:
        # Two starts arrived at once — a double-clicked button, a re-rendered
        # component, two tabs. The unique index is what actually prevents the
        # second row; idempotence means handing back the attempt that exists
        # rather than refusing the caller who asked for exactly that.
        winner = (
            ExamAttempt.objects.filter(exam=exam, enrollment=enrollment)
            .order_by("-attempt_number")
            .first()
        )
        if winner is not None and winner.status == AttemptStatus.IN_PROGRESS:
            return refresh_if_expired(winner, actor)
        raise ConflictError(
            {"exam": ["An attempt was already started. Reload to continue it."]}
        ) from exc

    attempt.max_score = _draw_paper(attempt)
    attempt.save(update_fields=["max_score", "updated_at"])

    record(
        action=AuditAction.EXAM_ATTEMPT_STARTED,
        actor=actor,
        resource_type="exam_attempt",
        resource_id=attempt.pk,
        context={
            "exam": exam.code,
            "attempt": attempt.attempt_number,
            "expires_at": attempt.expires_at.isoformat(),
            "questions": attempt.questions.count(),
        },
        durable=False,
    )
    return attempt


@transaction.atomic
def save_answer(
    *,
    attempt: ExamAttempt,
    attempt_question: AttemptQuestion,
    actor: User,
    selected_options: list | None = None,
    text_answer: str | None = None,
    uploaded_file=None,
) -> AttemptAnswer:
    """Auto-save one answer.

    Deliberately forgiving about *content* and strict about *time*: a candidate
    may change their mind as often as they like until the deadline, and not one
    millisecond after it.
    """
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise ConflictError({"attempt": ["This attempt has already been submitted."]})
    if attempt.has_expired:
        finalise_expired(attempt=attempt, actor=actor)
        raise ConflictError({"attempt": ["Time is up. Your saved answers have been submitted."]})

    answer, _created = AttemptAnswer.objects.get_or_create(attempt_question=attempt_question)

    if selected_options is not None:
        allowed = set(attempt_question.option_order)
        chosen = [str(value) for value in selected_options]
        unknown = [value for value in chosen if value not in allowed]
        if unknown:
            # An option id that is not on this candidate's paper.
            raise ApplicationError({"selected_options": ["That option is not on this question."]})
        question_type = attempt_question.question.question_type
        if question_type in (QuestionType.MCQ, QuestionType.TRUE_FALSE) and len(chosen) > 1:
            raise ApplicationError({"selected_options": ["Choose one option."]})
        answer.selected_options = chosen

    if text_answer is not None:
        answer.text_answer = text_answer

    if uploaded_file is not None:
        try:
            validate_submission_upload(uploaded_file)
        except DjangoValidationError as exc:
            raise ApplicationError({"file": list(exc.messages)}) from exc
        answer.file = uploaded_file
        answer.original_filename = (getattr(uploaded_file, "name", "") or "")[:255]

    answer.save()
    return answer


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


def _grade_answer(attempt_question: AttemptQuestion, answer: AttemptAnswer, *, negative: bool):
    """Mark one answer. Returns ``(awarded, is_correct, needs_manual)``."""
    question = attempt_question.question

    if question.question_type in MANUAL_TYPES:
        return None, None, True

    if answer is None or answer.is_blank:
        # Unanswered. Never penalised: a blank is not a wrong answer.
        return Decimal("0.00"), False, False

    correct = False
    if question.question_type in OPTION_TYPES:
        expected = {str(option.pk) for option in question.options.all() if option.is_correct}
        given = set(answer.selected_options or [])
        correct = bool(expected) and given == expected
    elif question.question_type == QuestionType.SHORT_ANSWER:
        correct = question.matches_short_answer(answer.text_answer)

    if correct:
        return attempt_question.marks, True, False
    penalty = attempt_question.negative_marks if negative else Decimal("0.00")
    return -penalty, False, False


@transaction.atomic
def grade_attempt(*, attempt: ExamAttempt, actor: User | None = None) -> ExamAttempt:
    """Mark everything the server can, and total it.

    Called on submission and again after a marker finishes the written answers,
    so the total is always the sum of what is currently known.
    """
    negative = attempt.exam.negative_marking
    rows = list(
        attempt.questions.select_related("question")
        .prefetch_related("question__options")
        .order_by("position")
    )
    answers = {
        row.attempt_question_id: row
        for row in AttemptAnswer.objects.filter(attempt_question__attempt=attempt)
    }

    auto = Decimal("0.00")
    manual = Decimal("0.00")
    pending = False

    for attempt_question in rows:
        answer = answers.get(attempt_question.pk)
        if answer is None:
            answer = AttemptAnswer.objects.create(attempt_question=attempt_question)
            answers[attempt_question.pk] = answer

        awarded, is_correct, needs_manual = _grade_answer(
            attempt_question, answer, negative=negative
        )

        if needs_manual:
            answer.needs_manual_marking = True
            if answer.awarded is None:
                pending = True
            else:
                manual += answer.awarded
            answer.save(update_fields=["needs_manual_marking", "updated_at"])
            continue

        answer.needs_manual_marking = False
        answer.awarded = awarded
        answer.is_correct = is_correct
        answer.save(update_fields=["needs_manual_marking", "awarded", "is_correct", "updated_at"])
        auto += awarded

    attempt.auto_score = auto
    attempt.manual_score = manual
    # Clamped at zero: negative marking may cost a candidate their marks, but a
    # paper worth less than nothing is not a result anybody can act on.
    attempt.total_score = None if pending else max(Decimal("0.00"), auto + manual)
    attempt.status = AttemptStatus.SUBMITTED if pending else AttemptStatus.GRADED
    attempt.graded_at = None if pending else timezone.now()
    attempt.save(
        update_fields=[
            "auto_score",
            "manual_score",
            "total_score",
            "status",
            "graded_at",
            "updated_at",
        ]
    )

    if not pending:
        record(
            action=AuditAction.EXAM_ATTEMPT_GRADED,
            actor=actor,
            resource_type="exam_attempt",
            resource_id=attempt.pk,
            context={
                "exam": attempt.exam.code,
                "score": str(attempt.total_score),
                "max_score": str(attempt.max_score),
            },
            durable=False,
        )
    return attempt


@transaction.atomic
def submit_attempt(*, attempt: ExamAttempt, actor: User) -> ExamAttempt:
    """Hand the paper in."""
    if attempt.status in CLOSED_ATTEMPT_STATUSES:
        raise ConflictError({"attempt": ["This attempt has already been submitted."]})

    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["submitted_at", "updated_at"])

    record(
        action=AuditAction.EXAM_ATTEMPT_SUBMITTED,
        actor=actor,
        resource_type="exam_attempt",
        resource_id=attempt.pk,
        context={
            "exam": attempt.exam.code,
            "attempt": attempt.attempt_number,
            "on_time": timezone.now() <= attempt.expires_at,
        },
        durable=False,
    )
    return grade_attempt(attempt=attempt, actor=actor)


@transaction.atomic
def finalise_expired(*, attempt: ExamAttempt, actor: User | None = None) -> ExamAttempt:
    """Close an attempt whose time ran out, marking what was saved.

    There is no background sweep in this deployment, so expiry is applied the
    next time anybody touches the attempt. The outcome is identical: answers
    were auto-saved as they were given, and those are what get marked.
    """
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt

    attempt.submitted_at = attempt.expires_at
    attempt.save(update_fields=["submitted_at", "updated_at"])

    record(
        action=AuditAction.EXAM_ATTEMPT_EXPIRED,
        actor=actor,
        resource_type="exam_attempt",
        resource_id=attempt.pk,
        context={"exam": attempt.exam.code, "attempt": attempt.attempt_number},
        durable=False,
    )
    graded = grade_attempt(attempt=attempt, actor=actor)
    if graded.status == AttemptStatus.SUBMITTED:
        # Written answers still to mark, but the sitting itself is over.
        graded.status = AttemptStatus.SUBMITTED
        graded.save(update_fields=["status", "updated_at"])
    return graded


def refresh_if_expired(attempt: ExamAttempt, actor: User | None = None) -> ExamAttempt:
    """Apply expiry lazily on any read. Safe to call on every request."""
    if attempt.has_expired:
        return finalise_expired(attempt=attempt, actor=actor)
    return attempt


@transaction.atomic
def mark_written_answer(
    *, answer: AttemptAnswer, actor: User, awarded: Decimal, feedback: str = ""
) -> AttemptAnswer:
    """A marker's score for one written answer, bounded by what it is worth."""
    attempt_question = answer.attempt_question
    if not answer.needs_manual_marking:
        raise ApplicationError({"answer": ["This answer is marked by the server."]})
    value = Decimal(awarded)
    if value < 0 or value > attempt_question.marks:
        raise ApplicationError({"awarded": [f"This question is worth {attempt_question.marks}."]})

    answer.awarded = value
    answer.marker_feedback = feedback
    answer.is_correct = value >= attempt_question.marks
    answer.save(update_fields=["awarded", "marker_feedback", "is_correct", "updated_at"])

    grade_attempt(attempt=attempt_question.attempt, actor=actor)
    return answer


@transaction.atomic
def publish_results(*, exam: Exam, actor: User, published: bool = True) -> Exam:
    """Release results to candidates.

    Separate from grading on purpose: an institution marks, checks, and *then*
    releases. Until this is on, a candidate sees that they submitted and
    nothing more.
    """
    exam.results_published = published
    exam.results_published_at = timezone.now() if published else None
    exam.save(update_fields=["results_published", "results_published_at", "updated_at"])

    if published:
        from apps.notifications.models import NotificationKind
        from apps.notifications.services import notify_many

        sitters = [
            attempt.enrollment.student.user
            for attempt in exam.attempts.select_related("enrollment__student__user")
        ]
        notify_many(
            recipients=sitters,
            kind=NotificationKind.RESULT_PUBLISHED,
            title=f"Results published: {exam.title}",
            body="Your examination result is available.",
            link_path="/exams",
            resource_type="exam",
            resource_id=exam.pk,
        )

    record(
        action=AuditAction.EXAM_RESULTS_PUBLISHED,
        actor=actor,
        resource_type="exam",
        resource_id=exam.pk,
        context={"code": exam.code, "published": published},
        durable=False,
    )
    return exam
