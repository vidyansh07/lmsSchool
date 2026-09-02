"""Question bank services.

Options are written with the question in one transaction, and the option set is
validated *after* they exist — a half-built multiple-choice question with no
correct answer is worse than no question, because an exam would happily draw it
and mark every student wrong.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError

from .models import Question, QuestionOption, QuestionType


@transaction.atomic
def create_question(
    *, actor: User, course=None, options: list | None = None, **fields: Any
) -> Question:
    """Create a question and its options together."""
    question = Question(
        course=course,
        created_by=actor if getattr(actor, "pk", None) else None,
        **fields,
    )
    _validate(question)
    question.save()

    _replace_options(question, options or [])
    _validate_options(question)

    record(
        action=AuditAction.QUESTION_CREATED,
        actor=actor,
        resource_type="question",
        resource_id=question.pk,
        context={
            "type": question.question_type,
            "course_id": str(course.pk) if course else None,
            "marks": str(question.marks),
        },
        durable=False,
    )
    return question


@transaction.atomic
def update_question(
    *, question: Question, actor: User, options: list | None = None, **fields: Any
) -> Question:
    """Edit a question.

    A question already drawn into a *sat* paper is frozen: the attempt holds its
    own copy, so editing here would not rewrite history — but it would make the
    bank disagree with what was marked, which is worse than refusing.
    """
    if _has_been_sat(question):
        raise ConflictError(
            {
                "question": [
                    "This question has been used in an examination. "
                    "Retire it and write a new one instead."
                ]
            }
        )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(question, field) != value:
            setattr(question, field, value)
            changed.append(field)

    if options is not None:
        _replace_options(question, options)
        changed.append("options")

    if not changed:
        return question

    _validate(question)
    question.save()
    _validate_options(question)

    record(
        action=AuditAction.QUESTION_UPDATED,
        actor=actor,
        resource_type="question",
        resource_id=question.pk,
        context={"fields": sorted(set(changed))},
        durable=False,
    )
    return question


@transaction.atomic
def delete_question(*, question: Question, actor: User) -> None:
    """Remove a question nobody has answered.

    Once it has been sat, deactivating is the only safe move: deleting would
    orphan the marks awarded for it.
    """
    if _has_been_sat(question):
        raise ConflictError(
            {"question": ["This question has been answered. Deactivate it instead."]}
        )
    pk = question.pk
    question.delete()
    record(
        action=AuditAction.QUESTION_DELETED,
        actor=actor,
        resource_type="question",
        resource_id=pk,
        context={},
        durable=False,
    )


def _has_been_sat(question: Question) -> bool:
    from apps.exams.models import AttemptQuestion

    return AttemptQuestion.objects.filter(question=question).exists()


def _replace_options(question: Question, options: list) -> None:
    question.options.all().delete()
    if question.question_type == QuestionType.TRUE_FALSE and not options:
        options = [{"text": "True", "is_correct": True}, {"text": "False", "is_correct": False}]

    rows = []
    for position, option in enumerate(options):
        if not isinstance(option, dict):
            raise ApplicationError({"options": ["Each option must be an object."]})
        text = str(option.get("text", "")).strip()
        if not text:
            raise ApplicationError({"options": ["Every option needs text."]})
        rows.append(
            QuestionOption(
                question=question,
                text=text[:500],
                is_correct=bool(option.get("is_correct", False)),
                position=position,
            )
        )
    QuestionOption.objects.bulk_create(rows)


def _validate(question: Question) -> None:
    try:
        question.full_clean(exclude=["course", "created_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


def _validate_options(question: Question) -> None:
    try:
        question.validate_options()
    except DjangoValidationError as exc:
        raise ApplicationError(
            exc.message_dict if hasattr(exc, "message_dict") else {"options": exc.messages}
        ) from exc
