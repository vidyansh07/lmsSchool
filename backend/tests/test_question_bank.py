"""The question bank — §5.4.

The bank holds the answers, so most of these tests are about who cannot read it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.questions.models import Difficulty, Question, QuestionOption, QuestionType


def _mcq(**overrides):
    payload = {
        "question_type": QuestionType.MCQ,
        "text": "Which command lists files?",
        "difficulty": Difficulty.EASY,
        "marks": "2.00",
        "tags": ["linux", "shell"],
        "explanation": "`ls` lists directory contents.",
        "options": [
            {"text": "ls", "is_correct": True},
            {"text": "cd", "is_correct": False},
            {"text": "rm", "is_correct": False},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def question(admin_user, published_course):
    from apps.questions.services import create_question

    return create_question(
        actor=admin_user,
        course=published_course,
        question_type=QuestionType.MCQ,
        text="Which command lists files?",
        marks=Decimal("2.00"),
        tags=["linux"],
        explanation="`ls` lists directory contents.",
        options=[
            {"text": "ls", "is_correct": True},
            {"text": "cd", "is_correct": False},
        ],
    )


# ---------------------------------------------------------------------------
# Writing questions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_author_creates_a_multiple_choice_question(
    api_client_no_csrf, admin_user, published_course
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/questions/create/", {**_mcq(), "course": str(published_course.id)}, format="json"
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert len(body["options"]) == 3
    assert body["is_auto_graded"] is True
    assert sum(1 for option in body["options"] if option["is_correct"]) == 1


@pytest.mark.django_db
def test_a_true_false_question_gets_its_options_for_free(admin_user, published_course):
    from apps.questions.services import create_question

    question = create_question(
        actor=admin_user,
        course=published_course,
        question_type=QuestionType.TRUE_FALSE,
        text="The shell is a program.",
        marks=Decimal("1.00"),
    )

    assert question.options.count() == 2
    assert question.options.filter(is_correct=True).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "options,reason",
    [
        ([], "at least two"),
        ([{"text": "only one", "is_correct": True}], "at least two"),
        ([{"text": "a"}, {"text": "b"}], "at least one option correct"),
        (
            [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}],
            "Exactly one",
        ),
    ],
)
def test_a_broken_option_set_is_refused(admin_user, published_course, options, reason):
    """A question with no correct answer would mark every candidate wrong."""
    from apps.common.exceptions import ApplicationError
    from apps.questions.services import create_question

    with pytest.raises(ApplicationError) as exc:
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.MCQ,
            text="Broken",
            marks=Decimal("1.00"),
            options=options,
        )
    assert reason.lower() in str(exc.value.detail).lower()
    assert Question.objects.count() == 0


@pytest.mark.django_db
def test_a_short_answer_question_needs_an_answer_key(admin_user, published_course):
    from apps.common.exceptions import ApplicationError
    from apps.questions.services import create_question

    with pytest.raises(ApplicationError):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.SHORT_ANSWER,
            text="Name the kernel.",
            marks=Decimal("1.00"),
        )


@pytest.mark.django_db
def test_a_written_question_takes_no_options(admin_user, published_course):
    from apps.common.exceptions import ApplicationError
    from apps.questions.services import create_question

    with pytest.raises(ApplicationError):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.LONG_ANSWER,
            text="Explain the boot process.",
            marks=Decimal("10.00"),
            options=[{"text": "nope"}],
        )


@pytest.mark.django_db
def test_tags_must_be_lower_case_and_unspaced(admin_user, published_course):
    from apps.common.exceptions import ApplicationError
    from apps.questions.services import create_question

    with pytest.raises(ApplicationError):
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.TRUE_FALSE,
            text="Tagged badly",
            marks=Decimal("1.00"),
            tags=["File Systems"],
        )


@pytest.mark.django_db
def test_a_short_answer_is_matched_case_and_whitespace_insensitively(admin_user, published_course):
    from apps.questions.services import create_question

    question = create_question(
        actor=admin_user,
        course=published_course,
        question_type=QuestionType.SHORT_ANSWER,
        text="What lists files?",
        marks=Decimal("1.00"),
        answer_key=["ls", "ls -l"],
    )

    assert question.matches_short_answer("  LS  ") is True
    assert question.matches_short_answer("ls   -l") is True
    assert question.matches_short_answer("dir") is False


# ---------------------------------------------------------------------------
# Who may read it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_read_the_bank_at_all(
    api_client_no_csrf, question, student_profile, enrollment
):
    """It contains the answers. There is no student-facing read."""
    api_client_no_csrf.force_login(student_profile.user)

    listing = api_client_no_csrf.get("/api/v1/questions/")
    assert listing.status_code == 200
    assert listing.json()["count"] == 0

    detail = api_client_no_csrf.get(f"/api/v1/questions/{question.id}/")
    assert detail.status_code == 404


@pytest.mark.django_db
def test_a_student_cannot_write_a_question(
    api_client_no_csrf, student_profile, published_course, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        "/api/v1/questions/create/", {**_mcq(), "course": str(published_course.id)}, format="json"
    )

    assert response.status_code in (403, 404)
    assert Question.objects.count() == 0


@pytest.mark.django_db
def test_a_trainer_reads_the_bank_for_the_course_they_teach(
    api_client_no_csrf, trainer_profile, question, batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get("/api/v1/questions/").json()

    assert body["count"] == 1
    assert body["results"][0]["text"] == question.text


@pytest.mark.django_db
def test_a_trainer_cannot_write_into_the_shared_bank(api_client_no_csrf, trainer_profile, batch):
    """A shared question is used by papers this trainer cannot see."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post("/api/v1/questions/create/", _mcq(), format="json")

    assert response.status_code == 403
    assert Question.objects.count() == 0


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, question):
    for url in ("/api/v1/questions/", f"/api/v1/questions/{question.id}/"):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


# ---------------------------------------------------------------------------
# Editing and retiring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_question_can_be_edited_before_it_is_used(api_client_no_csrf, admin_user, question):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/questions/{question.id}/", {"marks": "5.00"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["marks"] == "5.00"


@pytest.mark.django_db
def test_a_question_can_be_deactivated_rather_than_deleted(admin_user, question):
    from apps.questions.services import update_question

    update_question(question=question, actor=admin_user, is_active=False)
    question.refresh_from_db()

    assert question.is_active is False
    assert Question.objects.usable().count() == 0


@pytest.mark.django_db
def test_replacing_options_removes_the_old_ones(admin_user, question):
    from apps.questions.services import update_question

    update_question(
        question=question,
        actor=admin_user,
        options=[
            {"text": "ls", "is_correct": True},
            {"text": "dir", "is_correct": False},
            {"text": "list", "is_correct": False},
        ],
    )

    assert QuestionOption.objects.filter(question=question).count() == 3
    assert QuestionOption.objects.filter(question=question, text="cd").count() == 0


@pytest.mark.django_db
def test_writing_a_question_is_audited(admin_user, question):
    entry = AuditLog.objects.filter(action=AuditAction.QUESTION_CREATED).first()
    assert entry is not None
    assert entry.context["type"] == QuestionType.MCQ
