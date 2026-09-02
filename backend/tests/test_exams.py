"""Final examinations — §5.5, and every failure case §5.6 names.

The failure cases are the point of this file: refresh, a closed browser, a
dropped connection, a duplicate submission, an expired attempt, a tampered
timer, the attempt limit, an exam that is not yours and a result that is not
yours.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.exams.models import AttemptAnswer, AttemptStatus, Exam, ExamAttempt, ExamStatus
from apps.questions.models import QuestionType


@pytest.fixture
def bank(admin_user, published_course):
    """Eight auto-markable questions and one written one."""
    from apps.questions.services import create_question

    questions = []
    for index in range(8):
        questions.append(
            create_question(
                actor=admin_user,
                course=published_course,
                question_type=QuestionType.MCQ,
                text=f"Question {index}: which is right?",
                marks=Decimal("2.00"),
                negative_marks=Decimal("0.50"),
                tags=["linux"],
                explanation=f"Because of reason {index}.",
                options=[
                    {"text": f"right-{index}", "is_correct": True},
                    {"text": f"wrong-{index}", "is_correct": False},
                    {"text": f"also-wrong-{index}", "is_correct": False},
                ],
            )
        )
    questions.append(
        create_question(
            actor=admin_user,
            course=published_course,
            question_type=QuestionType.LONG_ANSWER,
            text="Explain the boot process.",
            marks=Decimal("10.00"),
            tags=["linux"],
        )
    )
    return questions


@pytest.fixture
def exam(admin_user, batch, bank):
    """A published exam drawing four auto-marked questions."""
    from apps.exams.services import create_exam, set_exam_status

    created = create_exam(
        actor=admin_user,
        batch=batch,
        title="Final examination",
        instructions="Answer every question.",
        duration_minutes=60,
        max_attempts=1,
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(days=1),
        sections=[
            {"title": "Multiple choice", "question_count": 4, "question_type": QuestionType.MCQ}
        ],
    )
    return set_exam_status(exam=created, actor=admin_user, status=ExamStatus.PUBLISHED)


def _start(client, exam):
    return client.post(f"/api/v1/exams/{exam.id}/start/", format="json")


def _answer_correctly(client, attempt_id, question):
    """Pick the option whose text marks it as the right one."""
    correct = next(option for option in question["options"] if option["text"].startswith("right-"))
    return client.post(
        f"/api/v1/attempts/{attempt_id}/questions/{question['id']}/answer/",
        {"selected_options": [correct["id"]]},
        format="json",
    )


def _answer_wrongly(client, attempt_id, question):
    wrong = next(option for option in question["options"] if option["text"].startswith("wrong-"))
    return client.post(
        f"/api/v1/attempts/{attempt_id}/questions/{question['id']}/answer/",
        {"selected_options": [wrong["id"]]},
        format="json",
    )


# ---------------------------------------------------------------------------
# Setting the paper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_sets_an_examination(api_client_no_csrf, trainer_profile, batch, bank):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/exams/",
        {
            "title": "Mid-term",
            "duration_minutes": 45,
            "sections": [{"title": "Part A", "question_count": 3}],
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["code"].startswith("GRS-F-")
    assert body["status"] == ExamStatus.DRAFT
    assert body["total_questions"] == 3


@pytest.mark.django_db
def test_an_exam_that_cannot_be_drawn_cannot_be_published(admin_user, batch, bank):
    """Publishing a paper with too few questions would fail at Start."""
    from apps.common.exceptions import ApplicationError
    from apps.exams.services import create_exam, set_exam_status

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Too big",
        sections=[{"title": "Impossible", "question_count": 50}],
    )
    with pytest.raises(ApplicationError) as excinfo:
        set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)
    assert "needs 50 questions" in str(excinfo.value.detail)


@pytest.mark.django_db
def test_readiness_reports_what_is_missing(api_client_no_csrf, admin_user, batch, bank):
    from apps.exams.services import create_exam

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Check me",
        sections=[{"title": "Part A", "question_count": 4, "question_type": QuestionType.MCQ}],
    )
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/readiness/").json()

    assert body["ready"] is True
    assert body["questions"] == 4


@pytest.mark.django_db
def test_a_student_cannot_set_an_examination(
    api_client_no_csrf, student_profile, batch, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.id}/exams/", {"title": "Free marks"}, format="json"
    )

    assert response.status_code == 403
    assert Exam.objects.count() == 0


# ---------------------------------------------------------------------------
# Sitting it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_starting_draws_a_paper_with_no_answers_in_it(
    api_client_no_csrf, exam, student_profile, enrollment
):
    """The candidate's shape carries no `is_correct`, key or explanation."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _start(api_client_no_csrf, exam)

    assert response.status_code == 200, response.json()
    body = response.json()
    assert len(body["questions"]) == 4
    assert body["attempt"]["status"] == AttemptStatus.IN_PROGRESS
    assert body["attempt"]["seconds_remaining"] > 0

    serialised = str(body)
    assert "is_correct" not in serialised
    assert "explanation" not in serialised
    assert "answer_key" not in serialised


@pytest.mark.django_db
def test_a_refresh_returns_the_same_paper(api_client_no_csrf, exam, student_profile, enrollment):
    """§5.6: refresh. Pressing Start again must not redraw or restart."""
    api_client_no_csrf.force_login(student_profile.user)
    first = _start(api_client_no_csrf, exam).json()
    second = _start(api_client_no_csrf, exam).json()

    assert first["attempt"]["id"] == second["attempt"]["id"]
    assert first["attempt"]["expires_at"] == second["attempt"]["expires_at"]
    assert [q["id"] for q in first["questions"]] == [q["id"] for q in second["questions"]]
    assert ExamAttempt.objects.count() == 1


@pytest.mark.django_db
def test_a_closed_browser_resumes_with_the_saved_answers(
    api_client_no_csrf, exam, student_profile, enrollment
):
    """§5.6: browser close and reopen."""
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    _answer_correctly(api_client_no_csrf, attempt_id, paper["questions"][0])

    api_client_no_csrf.logout()
    api_client_no_csrf.force_login(student_profile.user)
    resumed = api_client_no_csrf.get(f"/api/v1/attempts/{attempt_id}/").json()

    first = next(q for q in resumed["questions"] if q["id"] == paper["questions"][0]["id"])
    assert first["selected_options"] != []


@pytest.mark.django_db
def test_answers_auto_save_and_can_be_changed(
    api_client_no_csrf, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id, question = paper["attempt"]["id"], paper["questions"][0]

    assert _answer_wrongly(api_client_no_csrf, attempt_id, question).status_code == 200
    assert _answer_correctly(api_client_no_csrf, attempt_id, question).status_code == 200

    answer = AttemptAnswer.objects.get(attempt_question_id=question["id"])
    assert len(answer.selected_options) == 1


@pytest.mark.django_db
def test_an_option_from_another_paper_is_refused(
    api_client_no_csrf, exam, student_profile, enrollment
):
    """An option id the candidate was not given is not an answer."""
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    first, second = paper["questions"][0], paper["questions"][1]

    response = api_client_no_csrf.post(
        f"/api/v1/attempts/{attempt_id}/questions/{first['id']}/answer/",
        {"selected_options": [second["options"][0]["id"]]},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_single_choice_question_takes_one_option(
    api_client_no_csrf, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    question = paper["questions"][0]

    response = api_client_no_csrf.post(
        f"/api/v1/attempts/{paper['attempt']['id']}/questions/{question['id']}/answer/",
        {"selected_options": [option["id"] for option in question["options"][:2]]},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_server_computes_the_score(api_client_no_csrf, exam, student_profile, enrollment):
    """§5.5: never from a browser-submitted total. There is no such field."""
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]

    for question in paper["questions"][:3]:
        _answer_correctly(api_client_no_csrf, attempt_id, question)
    _answer_wrongly(api_client_no_csrf, attempt_id, paper["questions"][3])

    submitted = api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")
    assert submitted.status_code == 200

    attempt = ExamAttempt.objects.get(pk=attempt_id)
    assert attempt.status == AttemptStatus.GRADED
    assert attempt.max_score == Decimal("8.00")
    assert attempt.total_score == Decimal("6.00")  # three of four, no negative marking


@pytest.mark.django_db
def test_negative_marking_costs_a_wrong_answer_but_never_a_blank(
    api_client_no_csrf, admin_user, batch, bank, student_profile, enrollment
):
    from apps.exams.services import create_exam, set_exam_status

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Negatively marked",
        negative_marking=True,
        opens_at=timezone.now() - timedelta(minutes=1),
        sections=[{"title": "Part A", "question_count": 4, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]

    _answer_correctly(api_client_no_csrf, attempt_id, paper["questions"][0])
    _answer_wrongly(api_client_no_csrf, attempt_id, paper["questions"][1])
    # Two left blank.

    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    attempt = ExamAttempt.objects.get(pk=attempt_id)
    # 2 for the right one, minus 0.50 for the wrong one, nothing for the blanks.
    assert attempt.total_score == Decimal("1.50")


@pytest.mark.django_db
def test_a_score_never_goes_below_zero(
    api_client_no_csrf, admin_user, batch, bank, student_profile, enrollment
):
    from apps.exams.services import create_exam, set_exam_status

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="All wrong",
        negative_marking=True,
        opens_at=timezone.now() - timedelta(minutes=1),
        sections=[{"title": "Part A", "question_count": 4, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    for question in paper["questions"]:
        _answer_wrongly(api_client_no_csrf, attempt_id, question)

    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    assert ExamAttempt.objects.get(pk=attempt_id).total_score == Decimal("0.00")


@pytest.mark.django_db
def test_a_written_answer_waits_for_a_person(
    api_client_no_csrf, admin_user, trainer_profile, batch, bank, student_profile, enrollment
):
    from apps.exams.services import create_exam, set_exam_status

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="With an essay",
        opens_at=timezone.now() - timedelta(minutes=1),
        sections=[
            {"title": "Choice", "question_count": 2, "question_type": QuestionType.MCQ},
            {"title": "Essay", "question_count": 1, "question_type": QuestionType.LONG_ANSWER},
        ],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]

    essay = next(q for q in paper["questions"] if q["question_type"] == QuestionType.LONG_ANSWER)
    for question in paper["questions"]:
        if question["id"] == essay["id"]:
            api_client_no_csrf.post(
                f"/api/v1/attempts/{attempt_id}/questions/{question['id']}/answer/",
                {"text_answer": "The firmware hands over to the boot loader."},
                format="json",
            )
        else:
            _answer_correctly(api_client_no_csrf, attempt_id, question)

    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    attempt = ExamAttempt.objects.get(pk=attempt_id)
    assert attempt.status == AttemptStatus.SUBMITTED
    assert attempt.total_score is None  # not finished until a person marks it

    api_client_no_csrf.force_login(trainer_profile.user)
    queue = api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/marking/").json()
    assert len(queue) == 1

    marked = api_client_no_csrf.post(
        f"/api/v1/attempts/answers/{queue[0]['id']}/mark/",
        {"awarded": "7.00", "feedback": "Good, but omits initramfs."},
        format="json",
    )
    assert marked.status_code == 200

    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.GRADED
    assert attempt.total_score == Decimal("11.00")  # 2 + 2 + 7


@pytest.mark.django_db
def test_a_marker_cannot_award_more_than_the_question_is_worth(
    api_client_no_csrf, admin_user, trainer_profile, batch, bank, student_profile, enrollment
):
    from apps.exams.services import create_exam, set_exam_status

    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Essay only",
        opens_at=timezone.now() - timedelta(minutes=1),
        sections=[
            {"title": "Essay", "question_count": 1, "question_type": QuestionType.LONG_ANSWER}
        ],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    api_client_no_csrf.post(
        f"/api/v1/attempts/{attempt_id}/questions/{paper['questions'][0]['id']}/answer/",
        {"text_answer": "A short answer."},
        format="json",
    )
    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    api_client_no_csrf.force_login(trainer_profile.user)
    queue = api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/marking/").json()
    response = api_client_no_csrf.post(
        f"/api/v1/attempts/answers/{queue[0]['id']}/mark/", {"awarded": "99.00"}, format="json"
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# §5.6 — the failure cases
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_duplicate_submission_is_refused(api_client_no_csrf, exam, student_profile, enrollment):
    """§5.6: duplicate submission."""
    api_client_no_csrf.force_login(student_profile.user)
    attempt_id = _start(api_client_no_csrf, exam).json()["attempt"]["id"]

    assert (
        api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json").status_code
        == 200
    )
    second = api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")
    assert second.status_code == 409


@pytest.mark.django_db
def test_an_expired_attempt_is_marked_from_what_was_saved(
    api_client_no_csrf, exam, student_profile, enrollment
):
    """§5.6: expired attempt. Auto-saved answers still count."""
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    _answer_correctly(api_client_no_csrf, attempt_id, paper["questions"][0])

    # Wind the deadline into the past, as the clock would.
    attempt = ExamAttempt.objects.get(pk=attempt_id)
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])

    late = api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")
    assert late.status_code == 200

    attempt.refresh_from_db()
    assert attempt.status == AttemptStatus.GRADED
    assert attempt.total_score == Decimal("2.00")  # the one answered before time ran out
    assert AuditLog.objects.filter(action=AuditAction.EXAM_ATTEMPT_EXPIRED).exists()


@pytest.mark.django_db
def test_an_answer_after_time_is_refused(api_client_no_csrf, exam, student_profile, enrollment):
    """§5.6: timer manipulation. The deadline lives on the server."""
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]

    attempt = ExamAttempt.objects.get(pk=attempt_id)
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=["expires_at"])

    response = _answer_correctly(api_client_no_csrf, attempt_id, paper["questions"][0])

    assert response.status_code == 409
    assert "Time is up" in str(response.json())


@pytest.mark.django_db
def test_the_remaining_time_is_computed_by_the_server(
    api_client_no_csrf, exam, student_profile, enrollment
):
    """A client cannot send a time, and does not need to: it is in the response."""
    api_client_no_csrf.force_login(student_profile.user)
    body = _start(api_client_no_csrf, exam).json()

    remaining = body["attempt"]["seconds_remaining"]
    assert 0 < remaining <= 60 * 60


@pytest.mark.django_db
def test_the_attempt_limit_holds(api_client_no_csrf, exam, student_profile, enrollment):
    """§5.6: attempt limit."""
    api_client_no_csrf.force_login(student_profile.user)
    attempt_id = _start(api_client_no_csrf, exam).json()["attempt"]["id"]
    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    second = _start(api_client_no_csrf, exam)
    assert second.status_code == 409
    assert ExamAttempt.objects.count() == 1


@pytest.mark.django_db
def test_a_student_on_another_batch_cannot_sit_the_exam(
    api_client_no_csrf, exam, admin_user, other_student_profile, upcoming_batch
):
    """§5.6: unauthorized exam access."""
    from apps.enrollments.services import enrol_student

    enrol_student(student=other_student_profile, batch=upcoming_batch, actor=admin_user)

    api_client_no_csrf.force_login(other_student_profile.user)
    response = _start(api_client_no_csrf, exam)

    assert response.status_code in (403, 404)
    assert ExamAttempt.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_open_another_students_attempt(
    api_client_no_csrf, exam, student_profile, enrollment, other_student_profile, other_enrollment
):
    """§5.6: cross-student result access."""
    api_client_no_csrf.force_login(student_profile.user)
    attempt_id = _start(api_client_no_csrf, exam).json()["attempt"]["id"]

    api_client_no_csrf.force_login(other_student_profile.user)
    for url in (
        f"/api/v1/attempts/{attempt_id}/",
        f"/api/v1/attempts/{attempt_id}/result/",
        f"/api/v1/attempts/{attempt_id}/review/",
    ):
        assert api_client_no_csrf.get(url).status_code == 404, url


@pytest.mark.django_db
def test_a_student_cannot_answer_somebody_elses_paper(
    api_client_no_csrf, exam, student_profile, enrollment, other_student_profile, other_enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()

    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/attempts/{paper['attempt']['id']}/questions/{paper['questions'][0]['id']}/answer/",
        {"selected_options": []},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_closed_exam_cannot_be_started(
    api_client_no_csrf, admin_user, exam, student_profile, enrollment
):
    from apps.exams.services import set_exam_status

    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.CLOSED)

    api_client_no_csrf.force_login(student_profile.user)
    assert _start(api_client_no_csrf, exam).status_code == 400


@pytest.mark.django_db
def test_an_exam_outside_its_window_cannot_be_started(
    api_client_no_csrf, admin_user, batch, bank, student_profile, enrollment
):
    from apps.exams.services import create_exam, set_exam_status

    later = create_exam(
        actor=admin_user,
        batch=batch,
        title="Next week",
        opens_at=timezone.now() + timedelta(days=7),
        closes_at=timezone.now() + timedelta(days=8),
        sections=[{"title": "Part A", "question_count": 2, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=later, actor=admin_user, status=ExamStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    assert _start(api_client_no_csrf, later).status_code == 400


@pytest.mark.django_db
def test_a_late_start_gets_only_the_time_that_is_left(admin_user, batch, bank, enrollment):
    """Starting five minutes before the window shuts gives five minutes."""
    from apps.exams.services import create_exam, set_exam_status, start_attempt

    closes = timezone.now() + timedelta(minutes=5)
    exam = create_exam(
        actor=admin_user,
        batch=batch,
        title="Nearly over",
        duration_minutes=120,
        opens_at=timezone.now() - timedelta(hours=1),
        closes_at=closes,
        sections=[{"title": "Part A", "question_count": 2, "question_type": QuestionType.MCQ}],
    )
    set_exam_status(exam=exam, actor=admin_user, status=ExamStatus.PUBLISHED)

    attempt = start_attempt(exam=exam, enrollment=enrollment, actor=enrollment.student.user)
    assert attempt.expires_at == closes


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_result_is_withheld_until_it_is_published(
    api_client_no_csrf, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    for question in paper["questions"]:
        _answer_correctly(api_client_no_csrf, attempt_id, question)
    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    withheld = api_client_no_csrf.get(f"/api/v1/attempts/{attempt_id}/result/").json()
    assert withheld["total_score"] is None
    assert withheld["results_published"] is False

    review = api_client_no_csrf.get(f"/api/v1/attempts/{attempt_id}/review/")
    assert review.status_code == 403


@pytest.mark.django_db
def test_publishing_releases_the_result_and_the_explanations(
    api_client_no_csrf, admin_user, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    paper = _start(api_client_no_csrf, exam).json()
    attempt_id = paper["attempt"]["id"]
    for question in paper["questions"]:
        _answer_correctly(api_client_no_csrf, attempt_id, question)
    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    api_client_no_csrf.force_login(admin_user)
    published = api_client_no_csrf.post(
        f"/api/v1/exams/{exam.id}/results/publish/", {"published": True}, format="json"
    )
    assert published.status_code == 200

    api_client_no_csrf.force_login(student_profile.user)
    result = api_client_no_csrf.get(f"/api/v1/attempts/{attempt_id}/result/").json()
    assert result["total_score"] == "8.00"
    assert result["percentage"] == 100.0
    assert result["is_passing"] is True

    review = api_client_no_csrf.get(f"/api/v1/attempts/{attempt_id}/review/").json()
    assert len(review["questions"]) == 4
    assert review["questions"][0]["explanation"].startswith("Because of reason")


@pytest.mark.django_db
def test_the_marking_queue_is_staff_only(
    api_client_no_csrf, exam, student_profile, enrollment, trainer_profile_two
):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/marking/").status_code == 404

    api_client_no_csrf.force_login(trainer_profile_two.user)
    assert api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/marking/").status_code == 404


@pytest.mark.django_db
def test_the_trainer_sees_the_attempt_list(
    api_client_no_csrf, trainer_profile, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    _start(api_client_no_csrf, exam)

    api_client_no_csrf.force_login(trainer_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/exams/{exam.id}/attempts/").json()

    assert body["count"] == 1
    assert body["results"][0]["student_id"].startswith("GRS-S-")


@pytest.mark.django_db
def test_editing_a_sat_examination_is_refused(
    api_client_no_csrf, admin_user, exam, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    _start(api_client_no_csrf, exam)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/exams/{exam.id}/", {"duration_minutes": 5}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_a_question_that_has_been_sat_cannot_be_edited(
    admin_user, exam, student_profile, enrollment
):
    """The bank must not disagree with a paper already marked."""
    from apps.common.exceptions import ConflictError
    from apps.exams.services import start_attempt
    from apps.questions.services import update_question

    attempt = start_attempt(exam=exam, enrollment=enrollment, actor=student_profile.user)
    drawn = attempt.questions.first().question

    with pytest.raises(ConflictError):
        update_question(question=drawn, actor=admin_user, marks=Decimal("99.00"))


@pytest.mark.django_db
def test_every_step_is_audited(api_client_no_csrf, admin_user, exam, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    attempt_id = _start(api_client_no_csrf, exam).json()["attempt"]["id"]
    api_client_no_csrf.post(f"/api/v1/attempts/{attempt_id}/submit/", format="json")

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"/api/v1/exams/{exam.id}/results/publish/", {"published": True}, format="json"
    )

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.EXAM_CREATED in actions
    assert AuditAction.EXAM_STATUS_CHANGED in actions
    assert AuditAction.EXAM_ATTEMPT_STARTED in actions
    assert AuditAction.EXAM_ATTEMPT_SUBMITTED in actions
    assert AuditAction.EXAM_ATTEMPT_GRADED in actions
    assert AuditAction.EXAM_RESULTS_PUBLISHED in actions


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, exam):
    for url in ("/api/v1/exams/", f"/api/v1/exams/{exam.id}/", "/api/v1/attempts/mine/"):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_starts_return_the_same_attempt(exam, enrollment, student_profile):
    """§5.6, the case a single-threaded test cannot reach.

    A double-clicked Start, a re-rendered component or two tabs send two
    requests at once. The unique index stops the second row; the service has to
    hand back the first attempt rather than refuse the caller who asked for
    exactly that.
    """
    import threading

    from django.db import connection

    from apps.exams.services import start_attempt

    results: list = []
    errors: list = []
    barrier = threading.Barrier(2)

    def start():
        try:
            barrier.wait(timeout=5)
            results.append(
                start_attempt(exam=exam, enrollment=enrollment, actor=student_profile.user)
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2
    assert results[0].pk == results[1].pk
    assert ExamAttempt.objects.filter(exam=exam, enrollment=enrollment).count() == 1
