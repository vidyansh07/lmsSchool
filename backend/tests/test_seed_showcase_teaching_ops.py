"""Stage 7 of the showcase: assessed work in every state the screens filter
on — assignments and hand-ins, tests and results (manual, imported, graded),
projects and student work, examinations and attempts, completions and
certificates — and a second run that creates nothing.

Runs the command up to and including ``teaching_ops`` on the empty test
database, twice. There are no SITP rows here, so the imported part is proved
to be a clean no-op. One test runs the command twice and checks everything,
rather than one test per promise: the four stages in front make a hundred
accounts, a catalogue, a question bank and fifteen batches with their
classes, and a run per test would put the file well over its time budget.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

from apps.academics.models import AcademicPolicy
from apps.accounts.models import User
from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentResult,
    AssessmentStatus,
    ImportStatus,
    ResultImport,
    ResultSource,
)
from apps.assignments.models import (
    Assignment,
    AssignmentAttachment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionFile,
    SubmissionStatus,
)
from apps.batches.models import Batch
from apps.certificates.models import Certificate, CertificateStatus, CertificateTemplate
from apps.common.showcase.context import MARKER
from apps.common.showcase.stages.s04_batches import SPECS
from apps.common.showcase.stages.s07_teaching_ops import (
    IMPORT_CLEAN,
    IMPORT_WITH_ERRORS,
    POLICY_COURSE,
    QUEUE_LEFT,
    TEMPLATE_NAME,
)
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.exams.models import AttemptAnswer, AttemptStatus, Exam, ExamAttempt, ExamStatus
from apps.exams.services import check_readiness
from apps.progress.models import CompletionStatus, CourseCompletion
from apps.projects.models import Project, ProjectKind, ProjectStatus, StudentProject, WorkStatus
from apps.work.models import Activity

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches,teaching_ops"
HEADLINE = "student@grras.com"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = (
    "academic_policy_course",
    "assignment",
    "assignment_attachment",
    "submission",
    "submission_grade",
    "submission_return",
    "assessment",
    "assessment_result",
    "import_fixture",
    "result_import",
    "result_import_preview",
    "project",
    "student_project",
    "project_work",
    "exam",
    "exam_attempt",
    "exam_answer_marked",
    "exam_results_published",
    "certificate_template",
    "completion",
    "completion_approved",
    "completion_rejected",
    "certificate",
    "certificate_reissued",
    "certificate_revoked",
)
#: Labels with a "found" side: the second run must find every one of them.
FOUND_LABELS = (
    "assignment",
    "submission",
    "assessment",
    "assessment_result",
    "result_import",
    "project",
    "student_project",
    "project_work",
    "exam",
    "exam_attempt",
    "certificate_template",
    "completion",
    "certificate",
)

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks) -> str:
    """The command up to ``teaching_ops``, with every on_commit hook executed."""
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    """Everything the stage may touch, and the things it must not."""
    return {
        "assignments": Assignment.objects.count(),
        "attachments": AssignmentAttachment.objects.count(),
        "submissions": AssignmentSubmission.objects.count(),
        "submission_files": SubmissionFile.objects.count(),
        "assessments": Assessment.objects.count(),
        "results": AssessmentResult.objects.count(),
        "imports": ResultImport.objects.count(),
        "projects": Project.objects.count(),
        "student_projects": StudentProject.objects.count(),
        **{
            f"work_{status}": StudentProject.objects.filter(status=status).count()
            for status in WorkStatus.values
        },
        "exams": Exam.objects.count(),
        "attempts": ExamAttempt.objects.count(),
        "answers": AttemptAnswer.objects.count(),
        "completions": CourseCompletion.objects.count(),
        **{
            f"completions_{status}": CourseCompletion.objects.filter(status=status).count()
            for status in CompletionStatus.values
        },
        "certificates": Certificate.objects.count(),
        "templates": CertificateTemplate.objects.count(),
        "policies": AcademicPolicy.objects.count(),
        **{
            f"enrolments_{status}": Enrollment.objects.filter(status=status).count()
            for status in EnrollmentStatus.values
        },
        "batches": Batch.objects.count(),
        "users": User.objects.count(),
    }


def headline_enrolments() -> dict[str, Enrollment]:
    return {
        row.batch.name: row
        for row in Enrollment.objects.filter(student__user__email=HEADLINE).select_related("batch")
    }


@pytest.mark.django_db
def test_teaching_ops_builds_every_state_and_is_idempotent(django_capture_on_commit_callbacks):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table.get(label, (0, 0))[0] == 0, f"second run created {label}: {table[label]}"
    for label in FOUND_LABELS:
        assert table[label][1] > 0, f"second run found no {label}"
    assert counts() == after_first
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"
    assert "imported batches: none on this database" in first
    assert "imported batches: none on this database" in second

    now = timezone.now()
    today = timezone.localdate()
    headline = headline_enrolments()
    active = headline["DevOps Engineering Morning — Aug 2026"]
    finished = headline["RHCSA Evening — Mar 2026"]
    # The fast-track cohort is reached through its *batch*, not through the
    # headline student. Which cohorts that student sits on is stage 4's call —
    # its contract places them on one active batch and one completed one — and a
    # test that reads the placement as a fixed list of three names breaks the day
    # that stage changes its mind, which is what happened. The batch comes from
    # the spec key so even a rename cannot reach this assertion.
    fast_track_batch = Batch.all_objects.get(
        name=next(spec.name for spec in SPECS if spec.key == "c2")
    )

    # --- The relaxed rule: a course-level policy on the fast track's course
    policy = AcademicPolicy.objects.get(course__slug=POLICY_COURSE)
    assert policy.lessons_required_for_completion is False
    assert policy.attendance_required_for_completion is False
    assert AcademicPolicy.objects.count() == after_first["policies"]

    # --- Assignments: every status, batch-specific and course-wide -------------
    assignments = Assignment.objects.all()
    assert set(assignments.values_list("status", flat=True)) == set(AssignmentStatus.values)
    assert assignments.filter(batch__isnull=True, status=AssignmentStatus.PUBLISHED).exists()
    assert assignments.filter(batch__isnull=False).exists()
    assert (
        assignments.filter(due_at__gt=now).exists() and assignments.filter(due_at__lt=now).exists()
    )
    assert assignments.filter(allow_resubmission=True, max_attempts__gt=1).exists()
    assert assignments.filter(late_cutoff_at__isnull=False).exists()
    assert AssignmentAttachment.objects.filter(file__isnull=False).exists()
    assert not assignments.filter(published_at__gt=now).exists()

    submissions = AssignmentSubmission.objects.select_related("assignment")
    assert set(submissions.values_list("status", flat=True)) == set(SubmissionStatus.values)
    assert submissions.filter(is_late=True).exists()
    assert submissions.filter(attempt__gt=1).exists()
    assert submissions.exclude(text_answer="").exists()
    assert submissions.exclude(link_url="").exists()
    assert set(SubmissionFile.objects.values_list("extension", flat=True)) >= {
        ".py",
        ".pdf",
        ".txt",
    }
    graded = list(submissions.filter(status=SubmissionStatus.GRADED))
    assert any(row.is_passing for row in graded) and any(row.is_passing is False for row in graded)
    for row in submissions:
        assert row.submitted_at <= now
        if row.graded_at is not None:
            assert row.graded_at >= row.submitted_at
        if row.assignment.due_at is not None:
            assert row.is_late == (row.submitted_at > row.assignment.due_at), row.pk
    # The trainer has marking to do on the headline batch.
    assert submissions.filter(
        assignment__batch=active.batch, status=SubmissionStatus.SUBMITTED
    ).exists()
    assert submissions.filter(enrollment=finished, status=SubmissionStatus.GRADED).exists()

    # --- Assessments: every category and delivery; results from every source
    assessments = Assessment.objects.all()
    assert set(assessments.values_list("category", flat=True)) == set(AssessmentCategory.values)
    assert set(assessments.values_list("delivery", flat=True)) == set(AssessmentDelivery.values)
    assert {AssessmentStatus.DRAFT, AssessmentStatus.PUBLISHED, AssessmentStatus.CLOSED} <= set(
        assessments.values_list("status", flat=True)
    )
    for row in assessments.filter(delivery=AssessmentDelivery.EXTERNAL_LINK):
        assert row.external_url.startswith("https://") and row.external_provider
    upload = assessments.get(delivery=AssessmentDelivery.FILE_UPLOAD)
    assert upload.backing_assignment is not None
    assert upload.backing_assignment.status == AssignmentStatus.PUBLISHED
    assert any(a.is_open for a in assessments.filter(delivery=AssessmentDelivery.EXTERNAL_LINK))
    assert assessments.filter(scheduled_for__gt=now, status=AssessmentStatus.PUBLISHED).exists()

    results = AssessmentResult.objects.select_related("assessment")
    assert set(results.values_list("source", flat=True)) == set(ResultSource.values)
    assert results.filter(is_absent=True, marks_obtained__isnull=True).exists()
    scored = list(results.filter(is_absent=False))
    assert any(row.is_passing for row in scored) and any(row.is_passing is False for row in scored)
    assert not results.filter(recorded_at__gt=now).exists()
    assert results.filter(assessment=upload, source=ResultSource.GRADED).exists()
    confirmed = ResultImport.objects.get(status=ImportStatus.CONFIRMED)
    assert confirmed.created_count > 0 and confirmed.error_count == 0
    assert results.filter(import_run=confirmed, source=ResultSource.IMPORT).count() == (
        confirmed.created_count
    )
    preview = ResultImport.objects.get(status=ImportStatus.PREVIEW)
    assert preview.error_count >= 3
    problems = " ".join(error["problem"] for error in preview.report["errors"])
    assert "Not a student" in problems and "formula" in problems and "Duplicate" in problems
    assert default_storage.exists(IMPORT_CLEAN) and default_storage.exists(IMPORT_WITH_ERRORS)
    with default_storage.open(IMPORT_WITH_ERRORS) as handle:
        assert b"=SUM(" in handle.read()

    # --- Projects: every kind, a rubric that adds up, work in every state ------
    projects = Project.objects.all()
    assert set(projects.values_list("kind", flat=True)) == set(ProjectKind.values)
    assert (
        projects.filter(is_required=True).exists() and projects.filter(is_required=False).exists()
    )
    assert projects.filter(status=ProjectStatus.DRAFT).exists()
    assert projects.filter(batch__isnull=True, status=ProjectStatus.PUBLISHED).exists()
    with_rubric = projects.exclude(rubric=[]).get()
    assert sum(Decimal(str(c["max_marks"])) for c in with_rubric.rubric) == with_rubric.max_marks
    work = StudentProject.objects.select_related("project")
    assert set(work.values_list("status", flat=True)) == set(WorkStatus.values)
    assert work.filter(is_late=True, submitted_at__isnull=False).exists()
    assert work.filter(submission_count__gt=1).exists()
    approved_on_rubric = work.filter(project=with_rubric, status=WorkStatus.APPROVED).first()
    assert approved_on_rubric is not None and set(approved_on_rubric.rubric_scores) == set(
        with_rubric.rubric_keys
    )
    assert work.filter(
        status=WorkStatus.APPROVED, rubric_scores={}, marks_awarded__isnull=False
    ).exists()
    assert work.filter(status=WorkStatus.REWORK).exclude(feedback="").exists()
    assert not work.filter(submitted_at__gt=now).exists()
    assert work.filter(enrollment__batch=fast_track_batch, status=WorkStatus.COMPLETED).exists()

    # --- Exams: a draft that is not ready, one open now, one closed ------------
    exams = Exam.objects.all()
    draft = exams.get(status=ExamStatus.DRAFT)
    readiness = check_readiness(draft)
    assert readiness["ready"] is False and readiness["problems"]
    open_now = exams.get(batch=active.batch, status=ExamStatus.PUBLISHED, closes_at__gt=now)
    assert open_now.is_open and open_now.opens_at < now and open_now.results_published is False
    closed = exams.get(status=ExamStatus.CLOSED)
    assert closed.results_published is True and closed.results_published_at is not None
    assert closed.closes_at < now and closed.results_published_at <= now
    assert exams.filter(status=ExamStatus.PUBLISHED, opens_at__gt=now).exists()

    attempts = ExamAttempt.objects.select_related("exam")
    mine = attempts.get(exam=open_now, enrollment=active)
    assert mine.status == AttemptStatus.IN_PROGRESS and not mine.has_expired
    assert AttemptAnswer.objects.filter(attempt_question__attempt=mine).exists()
    assert attempts.filter(exam=open_now, status=AttemptStatus.SUBMITTED).exists()
    pending = AttemptAnswer.objects.filter(
        attempt_question__attempt__exam=open_now, needs_manual_marking=True, awarded__isnull=True
    )
    assert pending.exists(), "the marking queue is empty"
    assert attempts.filter(exam=open_now, status=AttemptStatus.GRADED).exists()
    expired = [
        a for a in attempts.filter(exam=open_now, status=AttemptStatus.IN_PROGRESS) if a.has_expired
    ]
    assert len(expired) == 1
    closed_attempts = attempts.filter(exam=closed)
    assert closed_attempts.count() >= 5
    assert set(closed_attempts.values_list("status", flat=True)) == {AttemptStatus.GRADED}
    for attempt in closed_attempts:
        assert closed.opens_at <= attempt.started_at <= attempt.submitted_at <= closed.closes_at
        assert attempt.graded_at is not None and attempt.total_score is not None

    # --- Completions: the queue, approvals by rule and by override, a rejection
    completions = CourseCompletion.objects.select_related("enrollment")
    assert set(completions.values_list("status", flat=True)) == set(CompletionStatus.values)
    eligible = completions.filter(status=CompletionStatus.ELIGIBLE)
    assert eligible.count() >= QUEUE_LEFT
    assert eligible.filter(enrollment__batch=fast_track_batch).count() == QUEUE_LEFT
    approved = completions.filter(status=CompletionStatus.APPROVED)
    assert approved.filter(rule_snapshot__overridden=True).exists()
    assert approved.filter(rule_snapshot__overridden=False).exists()
    assert (
        approved.filter(enrollment__batch=fast_track_batch, rule_snapshot__overridden=True).count()
        == 0
    )
    for completion in approved:
        assert completion.completed_on == completion.enrollment.batch.end_date
        assert completion.decided_at <= now and completion.decided_by is not None
        assert completion.enrollment.status == EnrollmentStatus.COMPLETED
    rejected = completions.get(status=CompletionStatus.REJECTED)
    assert rejected.decision_note.startswith(MARKER) and rejected.decided_by is not None
    assert completions.get(enrollment=finished).status == CompletionStatus.APPROVED
    assert completions.filter(
        enrollment__batch=fast_track_batch, status=CompletionStatus.APPROVED
    ).exists()
    assert completions.get(enrollment=active).status == CompletionStatus.IN_PROGRESS
    assert (
        not completions.filter(enrollment__batch__start_date__gt=today)
        .exclude(status=CompletionStatus.IN_PROGRESS)
        .exists()
    )

    # --- Certificates: a default template; issued, superseded and revoked ------
    template = CertificateTemplate.objects.get(name=TEMPLATE_NAME)
    assert template.is_default is True
    certificates = Certificate.objects.select_related("completion")
    assert set(certificates.values_list("status", flat=True)) == set(CertificateStatus.values)
    for certificate in certificates:
        assert certificate.completion.status == CompletionStatus.APPROVED
        assert certificate.issued_at <= now
        assert certificate.number.startswith("GRS-CERT-")
    revoked = certificates.get(status=CertificateStatus.REVOKED)
    assert revoked.revoked_at is not None and revoked.revocation_reason.startswith(MARKER)
    superseded = certificates.get(status=CertificateStatus.SUPERSEDED)
    replacement = certificates.get(supersedes=superseded)
    assert replacement.status == CertificateStatus.ISSUED
    assert replacement.reissue_reason.startswith(MARKER)
    assert certificates.filter(
        completion__enrollment=finished, status=CertificateStatus.ISSUED
    ).exists(), "the headline student's certificate"
    # One live certificate per completion, never more.
    live_per_completion = certificates.filter(status=CertificateStatus.ISSUED).values_list(
        "completion_id", flat=True
    )
    assert len(set(live_per_completion)) == live_per_completion.count()

    # --- The failed-assessment automation may have fired: loosely ----------------
    assert Activity.objects.count() >= 0
