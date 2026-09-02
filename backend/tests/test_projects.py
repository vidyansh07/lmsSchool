"""Projects — §5.1 to §5.3.

The workflow is what makes a project different from an assignment: it goes back
and forth. So most of these tests are about the loop, not about storage.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.projects.models import (
    Project,
    ProjectFile,
    ProjectKind,
    ProjectStatus,
    StudentProject,
    WorkStatus,
)


def _file(name: str = "main.py", body: bytes = b"print('hi')\n"):
    return SimpleUploadedFile(name, body, content_type="text/x-python")


@pytest.fixture
def project(admin_user, published_course, batch):
    """A published, required project on the batch's course."""
    from apps.projects.services import create_project, set_project_status

    created = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Build a log analyser",
        description="A small command-line tool.",
        instructions="Read a log file and report the ten busiest hours.",
        deliverables="Source code and a short README.",
        kind=ProjectKind.MAJOR,
        is_required=True,
        end_date=timezone.localdate() + timedelta(days=14),
        max_marks=Decimal("100.00"),
        passing_marks=Decimal("40.00"),
    )
    return set_project_status(project=created, actor=admin_user, status=ProjectStatus.PUBLISHED)


@pytest.fixture
def work(project, enrollment, student_profile):
    from apps.projects.services import student_project_for

    return student_project_for(project=project, student=student_profile)


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_sets_a_project_on_the_batch_they_teach(
    api_client_no_csrf, trainer_profile, published_course, batch
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/projects/",
        {
            "title": "Capstone",
            "batch": str(batch.id),
            "kind": ProjectKind.CAPSTONE,
            "max_marks": "150.00",
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["code"].startswith("GRS-P-")
    assert body["status"] == ProjectStatus.DRAFT
    assert body["is_required"] is True


@pytest.mark.django_db
def test_a_student_cannot_set_a_project(
    api_client_no_csrf, student_profile, published_course, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/courses/{published_course.id}/projects/", {"title": "Mine"}, format="json"
    )

    assert response.status_code == 403
    assert Project.objects.count() == 0


@pytest.mark.django_db
def test_a_rubric_must_add_up_to_the_marks_the_project_is_out_of(admin_user, published_course):
    """Otherwise a perfect score would not be full marks."""
    from apps.common.exceptions import ApplicationError
    from apps.projects.services import create_project

    with pytest.raises(ApplicationError) as exc:
        create_project(
            actor=admin_user,
            course=published_course,
            title="Mismatched rubric",
            max_marks=Decimal("100.00"),
            rubric=[
                {"key": "design", "label": "Design", "max_marks": "30.00"},
                {"key": "code", "label": "Code", "max_marks": "40.00"},
            ],
        )
    assert "rubric" in exc.value.detail


@pytest.mark.django_db
def test_a_malformed_rubric_is_refused(admin_user, published_course):
    from apps.common.exceptions import ApplicationError
    from apps.projects.services import create_project

    for rubric in (
        [{"label": "No key", "max_marks": "100.00"}],
        [{"key": "a", "label": "A", "max_marks": "0"}],
        [
            {"key": "a", "label": "A", "max_marks": "50.00"},
            {"key": "a", "label": "Again", "max_marks": "50.00"},
        ],
        [{"key": "a", "label": "A", "max_marks": "not a number"}],
    ):
        with pytest.raises(ApplicationError):
            create_project(
                actor=admin_user,
                course=published_course,
                title=f"Bad {rubric}",
                max_marks=Decimal("100.00"),
                rubric=rubric,
            )


@pytest.mark.django_db
def test_a_draft_project_is_invisible_to_students(
    api_client_no_csrf, admin_user, published_course, student_profile, enrollment
):
    from apps.projects.services import create_project

    create_project(actor=admin_user, course=published_course, title="Still writing")

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/projects/mine/").json()["count"] == 0


@pytest.mark.django_db
def test_publishing_puts_the_project_in_front_of_the_student(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/projects/mine/").json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["code"] == project.code
    # The student's own row comes with the list, so the page needs no follow-up.
    assert row["my_work"]["status"] == WorkStatus.ASSIGNED


# ---------------------------------------------------------------------------
# Handing it out
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_assigning_gives_the_project_to_the_cohort(
    api_client_no_csrf, admin_user, project, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(f"/api/v1/projects/{project.id}/assign/", format="json")

    assert response.status_code == 200
    assert response.json() == {"assigned": 2, "already_had": 0}
    assert StudentProject.objects.filter(project=project).count() == 2


@pytest.mark.django_db
def test_assigning_twice_does_not_reset_work_in_progress(admin_user, project, enrollment, work):
    from apps.projects.services import assign_project, save_progress

    save_progress(work=work, actor=work.enrollment.student.user, notes="Started.")
    work.refresh_from_db()
    assert work.status == WorkStatus.IN_PROGRESS

    assign_project(project=project, actor=admin_user)

    work.refresh_from_db()
    assert work.status == WorkStatus.IN_PROGRESS
    assert work.notes == "Started."


@pytest.mark.django_db
def test_a_draft_project_cannot_be_assigned(admin_user, published_course):
    from apps.common.exceptions import ApplicationError
    from apps.projects.services import assign_project, create_project

    draft = create_project(actor=admin_user, course=published_course, title="Draft")
    with pytest.raises(ApplicationError):
        assign_project(project=draft, actor=admin_user)


@pytest.mark.django_db
def test_a_student_who_enrols_later_still_gets_the_project(
    project, other_student_profile, other_enrollment
):
    """Created on demand, so a roster change does not need remembering."""
    from apps.projects.services import student_project_for

    row = student_project_for(project=project, student=other_student_profile)
    assert row is not None
    assert row.status == WorkStatus.ASSIGNED


@pytest.mark.django_db
def test_a_student_on_another_course_gets_nothing(project, other_student_profile):
    from apps.projects.services import student_project_for

    assert student_project_for(project=project, student=other_student_profile) is None


# ---------------------------------------------------------------------------
# Doing the work
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_saves_progress_then_hands_in(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/projects/{project.id}/work/"

    saved = api_client_no_csrf.patch(
        url,
        {"repository_url": "https://git.example.test/me/log-analyser", "notes": "Half done."},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == WorkStatus.IN_PROGRESS

    handed = api_client_no_csrf.post(url, {"files": [_file()]}, format="multipart")
    assert handed.status_code == 200, handed.json()
    body = handed.json()
    assert body["status"] == WorkStatus.SUBMITTED
    assert body["submission_count"] == 1
    assert len(body["files"]) == 1


@pytest.mark.django_db
def test_handing_in_nothing_at_all_is_refused(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(f"/api/v1/projects/{project.id}/work/", {}, format="json")

    assert response.status_code == 400
    assert "files" in str(response.json())


@pytest.mark.django_db
def test_a_required_repository_url_is_enforced(
    api_client_no_csrf, admin_user, project, student_profile, enrollment
):
    from apps.projects.services import update_project

    update_project(project=project, actor=admin_user, requires_repository_url=True)

    api_client_no_csrf.force_login(student_profile.user)
    refused = api_client_no_csrf.post(
        f"/api/v1/projects/{project.id}/work/", {"files": [_file()]}, format="multipart"
    )
    assert refused.status_code == 400
    assert "repository_url" in str(refused.json())


@pytest.mark.django_db
def test_work_already_handed_in_cannot_be_edited(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/projects/{project.id}/work/"
    api_client_no_csrf.post(url, {"files": [_file()]}, format="multipart")

    response = api_client_no_csrf.patch(url, {"notes": "One more thing"}, format="json")
    assert response.status_code == 409


@pytest.mark.django_db
def test_a_late_hand_in_is_flagged(admin_user, project, work, student_profile):
    from apps.projects.services import submit_project, update_project

    update_project(
        project=project, actor=admin_user, end_date=timezone.localdate() - timedelta(days=1)
    )
    work.refresh_from_db()
    submit_project(work=work, actor=student_profile.user, files=[_file()])

    work.refresh_from_db()
    assert work.is_late is True


@pytest.mark.django_db
def test_a_student_cannot_touch_another_students_project_row(
    api_client_no_csrf, work, other_student_profile, other_enrollment
):
    """§4.8 student isolation, applied to projects."""
    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/projects/submissions/{work.id}/")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Reviewing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rework_sends_the_project_back_and_lets_the_student_resubmit(
    api_client_no_csrf, trainer_profile, project, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile.user)
    returned = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.REWORK, "feedback": "Handle an empty file."},
        format="json",
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == WorkStatus.REWORK

    api_client_no_csrf.force_login(student_profile.user)
    again = api_client_no_csrf.post(
        f"/api/v1/projects/{project.id}/work/", {"files": [_file("v2.py")]}, format="multipart"
    )
    assert again.status_code == 200
    assert again.json()["submission_count"] == 2


@pytest.mark.django_db
def test_rework_without_a_reason_is_refused(
    api_client_no_csrf, trainer_profile, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.REWORK, "feedback": "   "},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_approving_records_the_mark_and_the_student_sees_it(
    api_client_no_csrf, trainer_profile, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile.user)
    approved = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.APPROVED, "marks": "82.00", "feedback": "Good work."},
        format="json",
    )
    assert approved.status_code == 200
    assert approved.json()["marks_awarded"] == "82.00"

    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get(f"/api/v1/projects/submissions/{work.id}/").json()
    assert body["marks_awarded"] == "82.00"
    assert body["is_passing"] is True
    assert body["feedback"] == "Good work."
    # Whose review it was is staff information.
    assert "reviewer_name" not in body


@pytest.mark.django_db
def test_a_mark_above_the_maximum_is_refused(
    api_client_no_csrf, trainer_profile, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.APPROVED, "marks": "500.00"},
        format="json",
    )

    assert response.status_code == 400
    work.refresh_from_db()
    assert work.marks_awarded is None


@pytest.mark.django_db
def test_the_server_sums_the_rubric(
    admin_user, trainer_profile, published_course, batch, enrollment, student_profile
):
    """§5.5's rule applied to projects: the browser never sends a total."""
    from apps.projects.services import (
        create_project,
        set_project_status,
        student_project_for,
        submit_project,
    )

    project = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Rubric project",
        max_marks=Decimal("100.00"),
        rubric=[
            {"key": "design", "label": "Design", "max_marks": "30.00"},
            {"key": "code", "label": "Code quality", "max_marks": "50.00"},
            {"key": "docs", "label": "Documentation", "max_marks": "20.00"},
        ],
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)
    work = student_project_for(project=project, student=student_profile)
    submit_project(work=work, actor=student_profile.user, files=[_file()])

    from apps.projects.services import review_project

    review_project(
        work=work,
        actor=trainer_profile.user,
        outcome=WorkStatus.APPROVED,
        rubric_scores={"design": "25", "code": "40", "docs": "15"},
    )

    work.refresh_from_db()
    assert work.marks_awarded == Decimal("80.00")


@pytest.mark.django_db
def test_a_rubric_score_outside_its_criterion_is_refused(
    admin_user, trainer_profile, published_course, batch, enrollment, student_profile
):
    from apps.common.exceptions import ApplicationError
    from apps.projects.services import (
        create_project,
        review_project,
        set_project_status,
        student_project_for,
        submit_project,
    )

    project = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Bounded rubric",
        max_marks=Decimal("50.00"),
        rubric=[{"key": "code", "label": "Code", "max_marks": "50.00"}],
    )
    set_project_status(project=project, actor=admin_user, status=ProjectStatus.PUBLISHED)
    work = student_project_for(project=project, student=student_profile)
    submit_project(work=work, actor=student_profile.user, files=[_file()])

    for scores in ({"code": "60"}, {"code": "-1"}, {"unknown": "10"}, {}):
        with pytest.raises(ApplicationError):
            review_project(
                work=work,
                actor=trainer_profile.user,
                outcome=WorkStatus.APPROVED,
                rubric_scores=scores,
            )

    work.refresh_from_db()
    assert work.marks_awarded is None


@pytest.mark.django_db
def test_marks_cannot_be_recorded_without_approving(
    api_client_no_csrf, trainer_profile, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.REWORK, "feedback": "Redo it", "marks": "90.00"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_an_unrelated_trainer_cannot_review(
    api_client_no_csrf, trainer_profile_two, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(trainer_profile_two.user)
    response = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.APPROVED, "marks": "50.00"},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_student_cannot_approve_their_own_project(api_client_no_csrf, work, student_profile):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/projects/submissions/{work.id}/review/",
        {"outcome": WorkStatus.APPROVED, "marks": "100.00"},
        format="json",
    )

    assert response.status_code == 404
    work.refresh_from_db()
    assert work.marks_awarded is None


@pytest.mark.django_db
def test_an_impossible_transition_is_refused(trainer_profile, work):
    """Approving work that was never handed in."""
    from apps.common.exceptions import ConflictError
    from apps.projects.services import review_project

    with pytest.raises(ConflictError):
        review_project(
            work=work,
            actor=trainer_profile.user,
            outcome=WorkStatus.APPROVED,
            marks=Decimal("50.00"),
        )


# ---------------------------------------------------------------------------
# Required-project progress (§5.2)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_required_project_progress_reports_what_is_outstanding(
    admin_user, trainer_profile, project, work, enrollment, student_profile
):
    from apps.projects.services import required_project_progress, review_project, submit_project

    before = required_project_progress(enrollment)
    assert before["required"] == 1
    assert before["met"] is False
    assert before["outstanding"][0]["code"] == project.code

    submit_project(work=work, actor=student_profile.user, files=[_file()])
    review_project(
        work=work,
        actor=trainer_profile.user,
        outcome=WorkStatus.APPROVED,
        marks=Decimal("70.00"),
    )

    after = required_project_progress(enrollment)
    assert after["finished"] == 1
    assert after["met"] is True
    assert after["outstanding"] == []


@pytest.mark.django_db
def test_an_optional_project_never_blocks_completion(
    admin_user, published_course, batch, enrollment
):
    from apps.projects.services import create_project, required_project_progress, set_project_status

    optional = create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Extra credit",
        is_required=False,
    )
    set_project_status(project=optional, actor=admin_user, status=ProjectStatus.PUBLISHED)

    progress = required_project_progress(enrollment)
    assert progress["required"] == 0
    assert progress["met"] is True


@pytest.mark.django_db
def test_a_student_reads_their_own_required_progress(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/projects/mine/required/").json()

    assert body
    assert body[0]["required"] == 1
    assert body[0]["met"] is False


# ---------------------------------------------------------------------------
# Editing rules and audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_rubric_cannot_change_once_work_is_in(
    api_client_no_csrf, admin_user, project, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/projects/{project.id}/", {"max_marks": "10.00"}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_a_project_with_submitted_work_cannot_be_deleted(
    api_client_no_csrf, admin_user, project, work, student_profile
):
    from apps.projects.services import submit_project

    submit_project(work=work, actor=student_profile.user, files=[_file()])

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.delete(f"/api/v1/projects/{project.id}/").status_code == 409
    assert Project.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
def test_every_step_is_audited(admin_user, trainer_profile, project, work, student_profile):
    from apps.projects.services import assign_project, review_project, submit_project

    assign_project(project=project, actor=admin_user)
    submit_project(work=work, actor=student_profile.user, files=[_file()])
    review_project(
        work=work,
        actor=trainer_profile.user,
        outcome=WorkStatus.APPROVED,
        marks=Decimal("64.00"),
    )

    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.PROJECT_CREATED in actions
    assert AuditAction.PROJECT_STATUS_CHANGED in actions
    assert AuditAction.PROJECT_ASSIGNED in actions
    assert AuditAction.PROJECT_SUBMITTED in actions
    assert AuditAction.PROJECT_REVIEWED in actions

    entry = AuditLog.objects.filter(action=AuditAction.PROJECT_REVIEWED).first()
    assert entry.context["marks"] == "64.00"
    assert entry.context["outcome"] == WorkStatus.APPROVED


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf, project, work):
    for url in (
        "/api/v1/projects/",
        f"/api/v1/projects/{project.id}/",
        f"/api/v1/projects/{project.id}/work/",
        f"/api/v1/projects/submissions/{work.id}/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url


# ---------------------------------------------------------------------------
# File security (§5.3 — the same controls as §4.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_project_files_obey_the_assignment_upload_rules(
    api_client_no_csrf, project, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    url = f"/api/v1/projects/{project.id}/work/"

    refused = api_client_no_csrf.patch(
        url, {"files": [SimpleUploadedFile("tool.exe", b"MZ\x90\x00")]}, format="multipart"
    )
    assert refused.status_code == 400
    assert ProjectFile.objects.count() == 0

    accepted = api_client_no_csrf.patch(url, {"files": [_file()]}, format="multipart")
    assert accepted.status_code == 200
    assert ProjectFile.objects.count() == 1


@pytest.mark.django_db
def test_a_project_file_is_stored_inert(api_client_no_csrf, project, student_profile, enrollment):
    from pathlib import PurePosixPath

    api_client_no_csrf.force_login(student_profile.user)
    api_client_no_csrf.patch(
        f"/api/v1/projects/{project.id}/work/",
        {"files": [SimpleUploadedFile("../../etc/passwd.py", b"root:x:0:0\n")]},
        format="multipart",
    )

    stored = ProjectFile.objects.get()
    assert ".." not in stored.file.name
    assert PurePosixPath(stored.file.name).suffix == ".bin"


@pytest.mark.django_db
def test_a_project_file_is_served_as_an_opaque_attachment(
    api_client_no_csrf, project, student_profile, enrollment, trainer_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    api_client_no_csrf.patch(
        f"/api/v1/projects/{project.id}/work/",
        {"files": [SimpleUploadedFile("page.html", b"<script>alert(1)</script>")]},
        format="multipart",
    )
    stored = ProjectFile.objects.get()

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/projects/files/{stored.id}/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]


@pytest.mark.django_db
def test_a_classmate_cannot_download_a_project_file(
    api_client_no_csrf,
    project,
    student_profile,
    enrollment,
    other_student_profile,
    other_enrollment,
):
    api_client_no_csrf.force_login(student_profile.user)
    api_client_no_csrf.patch(
        f"/api/v1/projects/{project.id}/work/", {"files": [_file()]}, format="multipart"
    )
    stored = ProjectFile.objects.get()

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get(f"/api/v1/projects/files/{stored.id}/").status_code == 404


@pytest.mark.django_db
def test_the_student_project_list_is_one_request_not_one_per_project(
    api_client_no_csrf,
    admin_user,
    published_course,
    batch,
    student_profile,
    enrollment,
    django_assert_max_num_queries,
):
    """The row is created while the list is built, so the page needs no follow-up.

    Without this the client fetched each project's own row separately, and the
    page got slower with every project set on the course.
    """
    from apps.projects.services import create_project, set_project_status

    for index in range(5):
        created = create_project(
            actor=admin_user, course=published_course, batch=batch, title=f"Project {index}"
        )
        set_project_status(project=created, actor=admin_user, status=ProjectStatus.PUBLISHED)

    api_client_no_csrf.force_login(student_profile.user)
    with django_assert_max_num_queries(35):
        body = api_client_no_csrf.get("/api/v1/projects/mine/").json()

    assert body["count"] == 5
    # Every row already carries the student's own work; nothing to fetch after.
    assert all(row["my_work"] is not None for row in body["results"])
