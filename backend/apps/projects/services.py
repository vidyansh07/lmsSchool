"""Project services.

The workflow is the interesting part. A project is not marked once and finished;
it goes back and forth. So every move is a named transition with a table behind
it, and there is no code path that sets ``status`` directly.

    ASSIGNED ─▸ IN_PROGRESS ─▸ SUBMITTED ─▸ UNDER_REVIEW ─┬▸ REWORK ─▸ IN_PROGRESS
                                                          └▸ APPROVED ─▸ COMPLETED

The rule that never bends: **the server computes the mark.** A reviewer sends
scores against named rubric criteria, or a single mark when there is no rubric.
The total is summed here and bounded by the project's own maximum.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_project_code
from apps.common.uploads import (
    MAX_SUBMISSION_FILES,
    MAX_SUBMISSION_TOTAL_BYTES,
    validate_submission_upload,
)
from apps.enrollments.models import Enrollment, EnrollmentStatus

from .models import (
    FINISHED_STATUSES,
    OPEN_TO_STUDENT,
    Project,
    ProjectFile,
    ProjectStatus,
    StudentProject,
    WorkStatus,
)

PROJECT_TRANSITIONS: dict[str, frozenset[str]] = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.PUBLISHED, ProjectStatus.ARCHIVED}),
    ProjectStatus.PUBLISHED: frozenset({ProjectStatus.CLOSED, ProjectStatus.ARCHIVED}),
    ProjectStatus.CLOSED: frozenset({ProjectStatus.PUBLISHED, ProjectStatus.ARCHIVED}),
    ProjectStatus.ARCHIVED: frozenset(),
}

#: Who may make each move. A student drives their own work forward; a reviewer
#: decides what happens after it is handed in.
WORK_TRANSITIONS: dict[str, frozenset[str]] = {
    WorkStatus.ASSIGNED: frozenset({WorkStatus.IN_PROGRESS, WorkStatus.SUBMITTED}),
    WorkStatus.IN_PROGRESS: frozenset({WorkStatus.SUBMITTED}),
    WorkStatus.SUBMITTED: frozenset(
        {WorkStatus.UNDER_REVIEW, WorkStatus.REWORK, WorkStatus.APPROVED}
    ),
    WorkStatus.UNDER_REVIEW: frozenset({WorkStatus.REWORK, WorkStatus.APPROVED}),
    WorkStatus.REWORK: frozenset({WorkStatus.SUBMITTED, WorkStatus.IN_PROGRESS}),
    WorkStatus.APPROVED: frozenset({WorkStatus.COMPLETED, WorkStatus.REWORK}),
    WorkStatus.COMPLETED: frozenset(),
}

#: Enrolments that get a project when it is assigned. Same rule as the register.
ASSIGNABLE_STATUSES = frozenset(
    {EnrollmentStatus.ACTIVE, EnrollmentStatus.SUSPENDED, EnrollmentStatus.COMPLETED}
)


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------


@transaction.atomic
def create_project(*, actor: User, course, **fields: Any) -> Project:
    """Create a project in draft."""
    fields.pop("status", None)
    if fields.get("max_marks") is None:
        from apps.academics.policies import policy_for

        fields["max_marks"] = policy_for(course).assignment_default_max_marks

    project = Project(
        code=next_project_code(),
        course=course,
        created_by=actor if getattr(actor, "pk", None) else None,
        status=ProjectStatus.DRAFT,
        **fields,
    )
    _validate(project)
    project.save()

    record(
        action=AuditAction.PROJECT_CREATED,
        actor=actor,
        resource_type="project",
        resource_id=project.pk,
        context={
            "code": project.code,
            "course_id": str(course.pk),
            "kind": project.kind,
            "required": project.is_required,
        },
        durable=False,
    )
    return project


@transaction.atomic
def update_project(*, project: Project, actor: User, **fields: Any) -> Project:
    """Edit a brief.

    Once anybody has handed work in, the marks it is out of and the rubric it
    is judged by are fixed: changing them would re-score work already reviewed.
    """
    fields.pop("status", None)
    if project.student_projects.filter(submission_count__gt=0).exists():
        locked = {"max_marks", "rubric"}
        blocked = sorted(locked & set(fields))
        if blocked:
            raise ConflictError(
                {field: ["This cannot change once work has been submitted."] for field in blocked}
            )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(project, field) != value:
            setattr(project, field, value)
            changed.append(field)
    if not changed:
        return project

    _validate(project)
    project.save()

    record(
        action=AuditAction.PROJECT_UPDATED,
        actor=actor,
        resource_type="project",
        resource_id=project.pk,
        context={"code": project.code, "fields": changed},
        durable=False,
    )
    return project


@transaction.atomic
def set_project_status(*, project: Project, actor: User, status: str) -> Project:
    if status == project.status:
        return project
    if status not in PROJECT_TRANSITIONS.get(project.status, frozenset()):
        raise ConflictError({"status": [f"A project cannot go from {project.status} to {status}."]})

    previous = project.status
    project.status = status
    if status == ProjectStatus.PUBLISHED and project.published_at is None:
        project.published_at = timezone.now()
    project.save(update_fields=["status", "published_at", "updated_at"])

    record(
        action=AuditAction.PROJECT_STATUS_CHANGED,
        actor=actor,
        resource_type="project",
        resource_id=project.pk,
        context={"code": project.code, "from": previous, "to": status},
        durable=False,
    )
    return project


@transaction.atomic
def delete_project(*, project: Project, actor: User) -> None:
    if project.student_projects.filter(submission_count__gt=0).exists():
        raise ConflictError(
            {"project": ["Work has been submitted. Archive it instead of deleting."]}
        )
    code, pk = project.code, project.pk
    project.delete()
    record(
        action=AuditAction.PROJECT_DELETED,
        actor=actor,
        resource_type="project",
        resource_id=pk,
        context={"code": code},
        durable=False,
    )


def _validate(project: Project) -> None:
    try:
        project.full_clean(exclude=["code"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc


# ---------------------------------------------------------------------------
# Handing it out
# ---------------------------------------------------------------------------


def cohort_for(project: Project):
    """Who this project is for.

    A batch-specific project goes to that batch; a course-wide one goes to
    every batch running the course.
    """
    rows = Enrollment.objects.filter(course_id=project.course_id, status__in=ASSIGNABLE_STATUSES)
    if project.batch_id:
        rows = rows.filter(batch_id=project.batch_id)
    return rows.select_related("student", "student__user", "batch").order_by("student__student_id")


@transaction.atomic
def assign_project(*, project: Project, actor: User) -> dict[str, int]:
    """Give the project to its cohort.

    Idempotent: running it again after new students enrol picks up only the new
    ones, and never resets work already in progress.
    """
    if project.status != ProjectStatus.PUBLISHED:
        raise ApplicationError({"project": ["Publish the project before assigning it."]})

    existing = set(project.student_projects.values_list("enrollment_id", flat=True))
    rows = [
        StudentProject(
            project=project,
            enrollment=enrollment,
            reviewer=project.reviewer or enrollment.batch.trainer,
            status=WorkStatus.ASSIGNED,
        )
        for enrollment in cohort_for(project)
        if enrollment.pk not in existing
    ]
    StudentProject.objects.bulk_create(rows, ignore_conflicts=True)

    record(
        action=AuditAction.PROJECT_ASSIGNED,
        actor=actor,
        resource_type="project",
        resource_id=project.pk,
        context={"code": project.code, "assigned": len(rows), "already_had": len(existing)},
        durable=False,
    )
    return {"assigned": len(rows), "already_had": len(existing)}


def student_project_for(*, project: Project, student) -> StudentProject | None:
    """This student's row, created on demand if the project is theirs to do.

    Created lazily so a student who enrols after the project was handed out is
    not left without one — the alternative is an assignment step that has to be
    remembered every time the roster changes.
    """
    enrollment = _enrollment_for(project=project, student=student)
    if enrollment is None:
        return None

    row, _created = StudentProject.objects.get_or_create(
        project=project,
        enrollment=enrollment,
        defaults={
            "reviewer": project.reviewer or enrollment.batch.trainer,
            "status": WorkStatus.ASSIGNED,
        },
    )
    return row


def ensure_student_projects(*, projects: list[Project], student) -> dict:
    """Create this student's rows for several projects at once.

    The per-project version resolves the student's enrolments each time, which
    is fine for one project and quadratic for a page of them. This resolves them
    once and inserts what is missing in a single statement.

    Returns ``{project_id: StudentProject}`` for everything the student may do.
    """
    if not projects:
        return {}

    live = [
        row
        for row in Enrollment.objects.granting_access()
        .filter(student=student)
        .select_related("batch")
        if row.grants_access()
    ]
    if not live:
        return {}

    by_course: dict = {}
    for enrollment in live:
        by_course.setdefault(enrollment.course_id, []).append(enrollment)

    existing = {
        row.project_id: row
        for row in StudentProject.objects.filter(
            project__in=projects, enrollment__student=student
        ).select_related("project")
    }

    to_create: list[StudentProject] = []
    pairs: list[tuple] = []
    for project in projects:
        if project.pk in existing:
            continue
        for enrollment in by_course.get(project.course_id, []):
            if project.applies_to_batch(enrollment.batch_id):
                to_create.append(
                    StudentProject(
                        project=project,
                        enrollment=enrollment,
                        reviewer=project.reviewer or enrollment.batch.trainer,
                        status=WorkStatus.ASSIGNED,
                    )
                )
                pairs.append((project.pk, enrollment.pk))
                break

    if to_create:
        StudentProject.objects.bulk_create(to_create, ignore_conflicts=True)
        for row in StudentProject.objects.filter(
            project__in=[project for project, _ in pairs], enrollment__student=student
        ):
            existing[row.project_id] = row

    return existing


def _enrollment_for(*, project: Project, student) -> Enrollment | None:
    rows = (
        Enrollment.objects.granting_access()
        .filter(student=student, course_id=project.course_id)
        .select_related("batch")
    )
    for enrollment in rows:
        if enrollment.grants_access() and project.applies_to_batch(enrollment.batch_id):
            return enrollment
    return None


# ---------------------------------------------------------------------------
# Doing the work
# ---------------------------------------------------------------------------


def _move(work: StudentProject, target: str) -> None:
    if target not in WORK_TRANSITIONS.get(work.status, frozenset()):
        raise ConflictError({"status": [f"A project cannot go from {work.status} to {target}."]})
    work.status = target


@transaction.atomic
def save_progress(
    *,
    work: StudentProject,
    actor: User,
    repository_url: str | None = None,
    deployment_url: str | None = None,
    notes: str | None = None,
    files: list | None = None,
) -> StudentProject:
    """A student's working save. Does not submit anything."""
    if not work.is_open_to_student:
        raise ConflictError(
            {"project": ["This project is with your reviewer and cannot be edited."]}
        )

    if repository_url is not None:
        work.repository_url = repository_url
    if deployment_url is not None:
        work.deployment_url = deployment_url
    if notes is not None:
        work.notes = notes
    if work.status == WorkStatus.ASSIGNED:
        work.status = WorkStatus.IN_PROGRESS
    work.save()

    if files:
        _store_files(work, files)
    return work


@transaction.atomic
def submit_project(
    *,
    work: StudentProject,
    actor: User,
    repository_url: str | None = None,
    deployment_url: str | None = None,
    notes: str | None = None,
    files: list | None = None,
) -> StudentProject:
    """Hand the project in for review."""
    if work.project.status != ProjectStatus.PUBLISHED:
        raise ApplicationError({"project": ["This project is not open for submission."]})
    if not work.is_open_to_student:
        raise ConflictError({"project": ["This project has already been handed in."]})

    if repository_url is not None:
        work.repository_url = repository_url
    if deployment_url is not None:
        work.deployment_url = deployment_url
    if notes is not None:
        work.notes = notes

    stored = _store_files(work, files or [])

    problems: dict[str, list[str]] = {}
    project = work.project
    if project.requires_repository_url and not work.repository_url:
        problems["repository_url"] = ["This project requires a repository URL."]
    if project.requires_deployment_url and not work.deployment_url:
        problems["deployment_url"] = ["This project requires a deployment URL."]
    if not (work.files.exists() or stored or work.repository_url or work.deployment_url):
        problems["files"] = ["Hand in a file, a repository URL or a deployment URL."]
    if problems:
        raise ApplicationError(problems)

    _move(work, WorkStatus.SUBMITTED)
    work.submitted_at = timezone.now()
    work.submission_count += 1
    work.is_late = work.mark_late()
    work.save()

    record(
        action=AuditAction.PROJECT_SUBMITTED,
        actor=actor,
        resource_type="student_project",
        resource_id=work.pk,
        context={
            "project": project.code,
            "attempt": work.submission_count,
            "late": work.is_late,
            "files": work.files.count(),
        },
        durable=False,
    )
    return work


def _store_files(work: StudentProject, files: list) -> list[ProjectFile]:
    """Validate every file, then store them. §5.3: identical rules to §4.4."""
    files = list(files or [])
    if not files:
        return []

    already = work.files.count()
    if already + len(files) > MAX_SUBMISSION_FILES:
        raise ApplicationError(
            {"files": [f"A project may hold at most {MAX_SUBMISSION_FILES} files."]}
        )

    problems: dict[str, list[str]] = {}
    checked: list[tuple[Any, str, str]] = []
    total = 0
    for uploaded in files:
        try:
            extension, checksum = validate_submission_upload(uploaded)
        except DjangoValidationError as exc:
            name = (getattr(uploaded, "name", "") or "this file")[:120]
            problems.setdefault("files", []).extend(
                f"{name}: {message}" for message in exc.messages
            )
            continue
        total += uploaded.size
        checked.append((uploaded, extension, checksum))

    if problems:
        raise ApplicationError(problems)
    if total > MAX_SUBMISSION_TOTAL_BYTES:
        raise ApplicationError(
            {
                "files": [
                    "The files add up to more than "
                    f"{MAX_SUBMISSION_TOTAL_BYTES // (1024 * 1024)} MB."
                ]
            }
        )

    stored: list[ProjectFile] = []
    for uploaded, extension, checksum in checked:
        row = ProjectFile(
            student_project=work,
            original_filename=(getattr(uploaded, "name", "") or "")[:255],
            extension=extension,
            size_bytes=uploaded.size,
            checksum=checksum,
        )
        row.file = uploaded
        row.save()
        stored.append(row)
    return stored


@transaction.atomic
def remove_file(*, stored: ProjectFile, actor: User) -> None:
    work = stored.student_project
    if not work.is_open_to_student:
        raise ConflictError({"project": ["Handed-in work cannot be changed."]})
    stored.file.delete(save=False)
    stored.delete()


# ---------------------------------------------------------------------------
# Reviewing
# ---------------------------------------------------------------------------


def score_from_rubric(project: Project, scores: dict[str, Any]) -> Decimal:
    """Sum a rubric, refusing anything that does not belong to it.

    This is the §5.5 rule applied to projects: a reviewer sends per-criterion
    scores, and the *server* produces the total. A client that sends a total
    has sent a field the API does not accept.
    """
    criteria = {str(item.get("key")): item for item in (project.rubric or [])}
    unknown = sorted(set(scores) - set(criteria))
    if unknown:
        raise ApplicationError({"rubric_scores": [f"Unknown criteria: {', '.join(unknown)}."]})
    missing = sorted(set(criteria) - set(scores))
    if missing:
        raise ApplicationError(
            {"rubric_scores": [f"Score every criterion. Missing: {', '.join(missing)}."]}
        )

    total = Decimal("0")
    for key, raw in scores.items():
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ApplicationError({"rubric_scores": [f"'{key}' is not a number."]}) from exc
        ceiling = Decimal(str(criteria[key].get("max_marks", "0")))
        if value < 0 or value > ceiling:
            raise ApplicationError({"rubric_scores": [f"'{key}' must be between 0 and {ceiling}."]})
        total += value
    return total


@transaction.atomic
def review_project(
    *,
    work: StudentProject,
    actor: User,
    outcome: str,
    feedback: str = "",
    marks: Decimal | None = None,
    rubric_scores: dict[str, Any] | None = None,
) -> StudentProject:
    """Approve, request rework, or take the project under review.

    ``outcome`` is one of ``under_review``, ``rework``, ``approved`` or
    ``completed``. Marks are required to approve and refused otherwise, because
    a mark on work being sent back would be read as final.
    """
    if outcome not in {
        WorkStatus.UNDER_REVIEW,
        WorkStatus.REWORK,
        WorkStatus.APPROVED,
        WorkStatus.COMPLETED,
    }:
        raise ApplicationError({"outcome": [f"'{outcome}' is not a review outcome."]})

    if outcome == WorkStatus.REWORK and not feedback.strip():
        raise ApplicationError(
            {
                "feedback": [
                    "Say what needs reworking — sending work back without a reason is not useful."
                ]
            }
        )

    if outcome == WorkStatus.APPROVED:
        project = work.project
        if project.rubric:
            if not rubric_scores:
                raise ApplicationError(
                    {"rubric_scores": ["This project is marked against a rubric."]}
                )
            total = score_from_rubric(project, rubric_scores)
            work.rubric_scores = {key: str(value) for key, value in rubric_scores.items()}
        else:
            if marks is None:
                raise ApplicationError({"marks": ["A mark is required to approve a project."]})
            total = Decimal(marks)
            if total < 0 or total > project.max_marks:
                raise ApplicationError(
                    {"marks": [f"The maximum for this project is {project.max_marks}."]}
                )
        work.marks_awarded = total
    elif marks is not None or rubric_scores:
        raise ApplicationError(
            {"marks": ["Marks are recorded when the project is approved, not before."]}
        )

    _move(work, outcome)
    if feedback:
        work.feedback = feedback
    work.reviewed_at = timezone.now()

    trainer = getattr(actor, "trainer_profile", None)
    if trainer is not None:
        work.reviewer = trainer
    work.save()

    from apps.notifications.models import NotificationKind
    from apps.notifications.services import notify

    notify(
        recipient=work.enrollment.student.user,
        kind=NotificationKind.PROJECT_REVIEWED,
        title=f"{work.project.title}: {outcome.replace('_', ' ')}",
        body=work.feedback[:300],
        link_path="/my-projects",
        resource_type="project",
        resource_id=work.project_id,
    )

    record(
        action=AuditAction.PROJECT_REVIEWED,
        actor=actor,
        resource_type="student_project",
        resource_id=work.pk,
        context={
            "project": work.project.code,
            "outcome": outcome,
            "marks": None if work.marks_awarded is None else str(work.marks_awarded),
            "max_marks": str(work.project.max_marks),
        },
        durable=False,
    )
    return work


# ---------------------------------------------------------------------------
# Completion (§5.2, read by Phase 6)
# ---------------------------------------------------------------------------


def required_project_progress(enrollment: Enrollment, *, inputs: Any = None) -> dict[str, Any]:
    """How this student stands against the *required* projects on their course.

    Returned as counts plus a verdict rather than a bare boolean, so a student
    asking "why am I not complete?" can be answered.

    ``inputs`` is a :class:`~apps.progress.bulk.ProgressInputs` from a caller
    reporting on a whole cohort; without it the two queries below run for this
    one student, which is what a student's own screen wants.
    """
    if inputs is None:
        projects = list(
            Project.objects.student_visible().filter(
                course_id=enrollment.course_id, is_required=True
            )
        )
    else:
        projects = inputs.required_projects.get(enrollment.course_id, [])

    applicable = [p for p in projects if p.applies_to_batch(enrollment.batch_id)]
    if not applicable:
        return {"required": 0, "finished": 0, "outstanding": [], "met": True}

    applicable_ids = {project.pk for project in applicable}
    if inputs is None:
        finished = set(
            StudentProject.objects.filter(
                enrollment=enrollment,
                project__in=applicable,
                status__in=list(FINISHED_STATUSES),
            ).values_list("project_id", flat=True)
        )
    else:
        finished = {
            row.project_id
            for row in inputs.student_projects.get(enrollment.pk, [])
            if row.project_id in applicable_ids and row.status in FINISHED_STATUSES
        }
    outstanding = [
        {"id": str(p.pk), "code": p.code, "title": p.title}
        for p in applicable
        if p.pk not in finished
    ]
    return {
        "required": len(applicable),
        "finished": len(finished),
        "outstanding": outstanding,
        "met": not outstanding,
    }


def open_to_student(status: str) -> bool:
    return status in OPEN_TO_STUDENT
