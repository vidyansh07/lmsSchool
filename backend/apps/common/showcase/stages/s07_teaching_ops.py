"""Stage 7 — assessed work: assignments, tests, projects, exams, completions.

Stage 4 made the batches and stage 6 held the classes; this stage sets the
work a batch is judged on and has the students do it — through the same
services a trainer's screen and a student's phone call, so audit rows, the
backing assignment behind a file-upload test, the result behind a graded
upload, the risk recompute and every notification happen the way they do in
production. Scope: the showcase batches (``ctx.showcase_batches``) for
everything, and the twelve **completed** SITP batches for completions and
certificates only. Every date is relative to ``ctx.today``.

Creates, idempotently — by title within a batch or course for the briefs, by
``(enrolment, brief)`` existence for hand-ins, attempts and results, and by
state for completions and certificates:

* **Assignments** (``apps.assignments.services``): :data:`ASSIGNMENTS`, in
  every status — ``create_assignment`` always makes a draft, and
  ``set_assignment_status`` walks it to published, closed or archived —
  batch-specific and course-wide, due in the past and the future, with
  ``allow_resubmission``/``max_attempts`` and one ``late_cutoff_at``; a brief
  attached through ``add_attachment``. Students hand in through
  ``submit_assignment`` *as themselves* — a ``.py``, a ``.pdf`` and a
  ``.txt`` through the upload path, written answers, repository links —
  some late, some left ungraded so the trainer has marking to do; the
  grader (``grade_submission``) awards above and below the pass mark and
  ``return_submission`` sends a few back, which is what makes attempt 2
  possible. A course-wide brief is answered on every showcase batch that has
  started, and on a finished batch only when it was due before that batch
  ended — alumni do not hand in new work. ``submitted_at``/``graded_at`` are
  backdated around the due date; ``is_late`` is the service's reading of the
  clock at the moment of the call, so it is backdated with ``submitted_at``
  as one fact.
* **Assessments** (``apps.assessments.services``): :data:`ASSESSMENTS`
  across every category and delivery — an external link (https, with a
  provider) open right now, offline tests already sat, a file-upload test
  whose backing assignment is submitted to and graded (the result row with
  ``source=graded`` is the grading's mirror; ``record_result`` is never
  called on it), a draft mock. Results are recorded manually — one
  **absent**, passes and **fails** (a fail fires the ASSESSMENT_FAILED
  automation on commit; under eager Celery the seeded "failed twice" rule may
  create a doubt-session activity) — and once by **import**: a clean CSV is
  previewed and confirmed through ``apps.assessments.importers`` (``source=
  import``), and a second CSV with valid *and* invalid rows (an unknown
  student, a mark over the maximum, a spreadsheet formula, a duplicate) is
  previewed and left in *preview* with its error report. Both files are
  written under ``showcase/`` on the default storage, so a reviewer can
  upload them again from the import screen.
* **Projects** (``apps.projects.services``): :data:`PROJECTS` — small, major
  and capstone, required and optional, one with a rubric whose criteria sum
  to ``max_marks``; ``assign_project`` hands each to its cohort and the
  students' work is walked to every state — in progress (``save_progress``),
  submitted (``submit_project`` with a repository and a deployment URL),
  under review, rework with feedback and a second submission, approved with
  marks or rubric scores, completed — one of them late.
* **Exams** (``apps.exams.services``): :data:`EXAMS`, with sections drawn
  from stage 3's question bank. One **draft that is not ready** (a section
  wanting twenty hard questions the pool cannot supply — publishing it is
  what the readiness check refuses); one published and **open now** on the
  headline student's active batch (opened yesterday, closes in ten days)
  with the headline student **mid-attempt** (``start_attempt`` and
  ``save_answer``, never submitted), submitted attempts waiting for their
  written answer to be marked, a graded one, and one that has **expired**
  (started, then its clock backdated into yesterday); one **closed** exam
  with every attempt marked (``mark_written_answer``) and
  ``publish_results`` on — it is created with a window that is open, so the
  attempts can be started, and the window is moved into the past through
  ``update_exam`` once they are in, which is the service's own way of moving
  one; and one published in Pune that opens in three days. Because the
  headline attempt is live, a re-run on a *later* day finds it expired and
  starts a fresh one when an attempt is left — the one row this stage adds
  on another day.
* **Completions** (``apps.progress.services``): ``refresh_completion`` for
  every showcase cohort enrolment; the completed cohorts are approved —
  by the rules on the online fast track, where a course-level policy
  (``AcademicPolicy`` for ``python-django-full-stack``: lessons and
  attendance not required — an online fast track is judged on its tests and
  its capstone) makes the rules meetable on a database with no attendance or
  lesson history, and with ``override=True`` everywhere else; one is
  rejected with a note, and the fast track keeps :data:`QUEUE_LEFT` eligible
  students in the approval queue, which is the ``/admin/completions``
  default view. For the twelve completed SITP batches: ``refresh_completion``
  for every completed enrolment, ~:data:`SITP_APPROVE_SHARE` of each batch
  approved with ``override=True`` and ``completed_on`` the batch's end date,
  five rejected with notes, the rest left as computed.
* **Certificates** (``apps.certificates.services``): the default template
  through ``save_template``; ``issue_certificate`` for every approved
  showcase completion and about two thirds of the approved SITP ones;
  ``reissue_certificate`` (superseded) and ``revoke_certificate`` with a
  reason — one of each on the headline's finished batch, two and three on
  SITP. Decisions and issues are backdated to shortly after the batch ended.

Every draw comes from a generator seeded by the row's **natural key**
(batch name, title, student email) rather than from ``ctx.rng`` in sequence,
so a re-run that finds half its rows decides exactly the same about the rest.
Risk recomputes are coalesced the way stage 6 does it: the debounce key is
claimed for every enrolment a grade or result may touch and released on
commit with one recompute per student.

Leaves in ``ctx``: nothing new.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.academics.services import get_or_create_policy
from apps.academics.services import update_policy as update_academic_policy
from apps.accounts.models import User
from apps.assessments.importers import confirm_import, preview_import
from apps.assessments.models import (
    Assessment,
    AssessmentCategory,
    AssessmentDelivery,
    AssessmentStatus,
    ImportStatus,
    ResultImport,
)
from apps.assessments.services import create_assessment, record_result, set_assessment_status
from apps.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentSubmission,
    SubmissionKind,
)
from apps.assignments.services import (
    add_attachment,
    create_assignment,
    grade_submission,
    return_submission,
    set_assignment_status,
    submit_assignment,
)
from apps.batches.models import Batch, BatchStatus
from apps.certificates.models import Certificate, CertificateStatus, CertificateTemplate
from apps.certificates.services import (
    issue_certificate,
    reissue_certificate,
    revoke_certificate,
    save_template,
)
from apps.courses.models import Course
from apps.enrollments.models import Enrollment, EnrollmentStatus
from apps.exams.models import AttemptAnswer, AttemptStatus, Exam, ExamAttempt, ExamStatus
from apps.exams.services import (
    check_readiness,
    create_exam,
    mark_written_answer,
    publish_results,
    save_answer,
    set_exam_status,
    start_attempt,
    submit_attempt,
    update_exam,
)
from apps.performance import tasks as risk_tasks
from apps.progress.models import CompletionStatus, CourseCompletion
from apps.progress.services import approve_completion, refresh_completion, reject_completion
from apps.projects.models import Project, ProjectKind, ProjectStatus, StudentProject, WorkStatus
from apps.projects.services import (
    assign_project,
    create_project,
    review_project,
    save_progress,
    set_project_status,
    submit_project,
)
from apps.questions.models import QuestionType

from ..context import RUN_SEED, Context, batch_key
from ..roster import DOMAIN, MAIN
from .s04_batches import SPECS

STAGE = "teaching_ops"

#: Stage 4's spec keys for the batches this stage leans on by name.
HEADLINE_ACTIVE = "a2"  # DevOps Engineering Morning — the headline student's live batch
HEADLINE_COMPLETED = "c1"  # RHCSA Evening — finished, certificates due
FAST_TRACK = "c2"  # Python Django Fast Track — finished, approved by the rules
PUNE_COMPLETED = "pc1"
ARCHIVED = "x1"

#: The course whose completion rules this stage relaxes, and why: see the
#: module docstring. Idempotent — ``update_policy`` is a no-op on an
#: unchanged value.
POLICY_COURSE = "python-django-full-stack"
POLICY_RULES: dict[str, Any] = {
    "lessons_required_for_completion": False,
    "attendance_required_for_completion": False,
}

#: Eligible fast-track students left un-approved, so the approval queue —
#: the default filter on /admin/completions — has rows on it.
QUEUE_LEFT = 3
#: Fast-track students who never finish: one assignment, one test and the
#: capstone short.
FAST_TRACK_SHORT = 2

#: The SITP part: the share of each completed batch approved (~150 of ~860),
#: the share of those certified (~100), how many rejected/reissued/revoked.
SITP_APPROVE_SHARE = 0.175
SITP_CERTIFICATE_SHARE = 0.67
SITP_REJECTS = 5
SITP_REISSUES = 2
SITP_REVOKES = 3

#: Debounce claims for the risk recompute, held while the stage runs.
CLAIM_SECONDS = 3600

#: Where the result-import fixtures live on the default storage.
IMPORT_DIR = "showcase"
IMPORT_CLEAN = f"{IMPORT_DIR}/week-4-docker-results.csv"
IMPORT_WITH_ERRORS = f"{IMPORT_DIR}/week-4-docker-results-with-errors.csv"

PROVIDER_FORMS = "Google Forms"
TEMPLATE_NAME = "Grras certificate of completion"

# ---------------------------------------------------------------------------
# What the stage creates: written out, so every run makes the same work
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssignmentSpec:
    """One brief. ``batch`` is a stage-4 spec key, or ``None`` for a
    course-wide brief on ``course``. Days are relative to today.

    The hand-in plan: ``submit`` is the share of the cohort that hands in,
    ``late`` the share of those who do so after the due date (needs a past
    ``due`` and ``allow_late``), ``graded`` the share of hand-ins the trainer
    has marked, ``fail`` the share of those below the pass mark, ``returned``
    how many are sent back and handed in again (needs ``resubmission``).
    ``headline`` says what the headline student does: ``"pass"`` (hands in on
    time, graded above the pass mark), ``"pending"`` (hands in, not yet
    marked) or ``None`` (nothing; the due date stays ahead of them).
    ``skip_short``: the fast-track students who fall short skip this brief.
    """

    key: str
    batch: str | None
    course: str
    title: str
    instructions: str
    kind: str
    status: str
    due: int | None
    allow_late: bool = True
    resubmission: bool = False
    max_attempts: int = 1
    passing: Decimal | None = None
    late_cutoff: int | None = None
    attachment: tuple[str, str] | None = None
    submit: float = 0.0
    late: float = 0.0
    graded: float = 0.0
    fail: float = 0.0
    returned: int = 0
    headline: str | None = None
    skip_short: bool = False


ASSIGNMENTS: tuple[AssignmentSpec, ...] = (
    # --- The headline batch: DevOps Morning (Vikram) ---------------------
    AssignmentSpec(
        "a2-closed", HEADLINE_ACTIVE, "devops-engineering",
        "Lab 3 — Containerise the inventory service",
        "Write a Dockerfile for the inventory service, build it with a multi-stage build and "
        "hand in the Dockerfile plus a one-page note on the image size before and after.",
        SubmissionKind.FILE, AssignmentStatus.CLOSED, due=-21, resubmission=True, max_attempts=3,
        attachment=("lab-3-brief.md", "Lab 3 brief"),
        submit=0.85, late=0.2, graded=0.8, fail=0.2, returned=2, headline="pass",
    ),
    AssignmentSpec(
        "a2-open", HEADLINE_ACTIVE, "devops-engineering",
        "Lab 5 — Kubernetes deployment manifests",
        "Deploy the inventory service to the class cluster: a Deployment, a Service and a "
        "ConfigMap. Submit the manifests and a screenshot of `kubectl get all`.",
        SubmissionKind.ANY, AssignmentStatus.PUBLISHED, due=5, allow_late=False,
        submit=0.3, graded=0.4, headline=None,
    ),
    AssignmentSpec(
        "a2-draft", HEADLINE_ACTIVE, "devops-engineering",
        "Lab 6 — Ansible playbook for the web tier",
        "Draft — wording to be finished after Friday's class.",
        SubmissionKind.FILE, AssignmentStatus.DRAFT, due=12,
    ),
    AssignmentSpec(
        "a2-archived", HEADLINE_ACTIVE, "devops-engineering",
        "Lab 1 — Linux refresher (retired)",
        "Retired: replaced by the shell refresher in the RHCSA prerequisites.",
        SubmissionKind.TEXT, AssignmentStatus.ARCHIVED, due=-40, allow_late=False,
    ),
    AssignmentSpec(
        "devops-wide", None, "devops-engineering",
        "Docker Compose — a three-tier stack",
        "Course-wide: compose a web tier, an API and a database with a named volume and a "
        "health check on each service. Hand in the compose file as a repository link.",
        SubmissionKind.LINK, AssignmentStatus.PUBLISHED, due=10,
        submit=0.25, graded=0.3, headline=None,
    ),
    # --- AWS Evening: a brief with a hard cut-off -------------------------
    AssignmentSpec(
        "a1-open", "a1", "aws-solutions-architect",
        "Week 2 — VPC design exercise",
        "Design a two-AZ VPC for the case study: subnets, route tables, NAT. Submit the "
        "diagram as a PDF.",
        SubmissionKind.FILE, AssignmentStatus.PUBLISHED, due=3, late_cutoff=6,
        submit=0.4, graded=0.5, fail=0.1,
    ),
    # --- Python Weekend (Neha): open, with resubmission ---------------------
    AssignmentSpec(
        "a3-open", "a3", "python-django-full-stack",
        "Weekend Lab — Forms & validation",
        "Build the registration form with server-side validation and hand in a link to "
        "your branch.",
        SubmissionKind.LINK, AssignmentStatus.PUBLISHED, due=4, resubmission=True,
        max_attempts=3, submit=0.3, graded=0.6, returned=1,
    ),
    AssignmentSpec(
        "a3-next", "a3", "python-django-full-stack",
        "Weekend Lab — Authentication & sessions",
        "Log-in, log-out and a password reset flow on the registration app. Set on Sunday; "
        "nobody has handed in yet.",
        SubmissionKind.LINK, AssignmentStatus.PUBLISHED, due=11,
    ),
    # --- Course-wide RHCSA: answered by the finished evening cohort ------------
    AssignmentSpec(
        "rhcsa-wide", None, "rhcsa",
        "Shell scripting — the backup script",
        "Course-wide: a script that archives /srv/data nightly, keeps seven copies and logs "
        "to the journal. Paste the script and a sample log line.",
        SubmissionKind.TEXT, AssignmentStatus.PUBLISHED, due=-100, resubmission=True,
        max_attempts=3, submit=0.85, late=0.2, graded=1.0, fail=0.15, returned=1,
        headline="pass",
    ),
    # --- Finished cohorts: everything closed ----------------------------------
    AssignmentSpec(
        "c1-lab2", HEADLINE_COMPLETED, "rhcsa",
        "Lab 2 — Users, groups and permissions",
        "Create the accounts in the brief, set the group ownership and the setgid bit, and "
        "hand in the transcript.",
        SubmissionKind.FILE, AssignmentStatus.CLOSED, due=-98,
        submit=0.9, late=0.15, graded=1.0, fail=0.15, headline="pass",
    ),
    AssignmentSpec(
        "c1-lab5", HEADLINE_COMPLETED, "rhcsa",
        "Lab 5 — LVM and file systems",
        "Extend the volume group, grow the logical volume online and hand in the commands "
        "you used with their output.",
        SubmissionKind.TEXT, AssignmentStatus.CLOSED, due=-77,
        submit=0.85, late=0.1, graded=1.0, fail=0.2, headline="pass",
    ),
    AssignmentSpec(
        "c2-views", FAST_TRACK, "python-django-full-stack",
        "Views, templates and the ORM",
        "Build the catalogue pages with class-based views and paginate the listing.",
        SubmissionKind.LINK, AssignmentStatus.CLOSED, due=-210,
        submit=1.0, late=0.1, graded=1.0, fail=0.1, headline="pass", skip_short=True,
    ),
    AssignmentSpec(
        "c2-api", FAST_TRACK, "python-django-full-stack",
        "A REST API with Django REST framework",
        "Expose the catalogue as an API with token authentication and hand in the "
        "repository link.",
        SubmissionKind.LINK, AssignmentStatus.CLOSED, due=-175,
        submit=1.0, late=0.15, graded=1.0, fail=0.1, headline="pass",
    ),
    AssignmentSpec(
        "pc1-lab", PUNE_COMPLETED, "devops-engineering",
        "Pipeline lab — build, test, deploy",
        "A GitHub Actions workflow that builds the image, runs the tests and deploys to "
        "the staging namespace.",
        SubmissionKind.LINK, AssignmentStatus.CLOSED, due=-70,
        submit=0.8, late=0.2, graded=1.0, fail=0.2,
    ),
    # --- Pune: MERN and Analytics ------------------------------------------------
    AssignmentSpec(
        "pa1-open", "pa1", "mern-full-stack",
        "Express API — the orders service",
        "Routes, validation and a Mongo model for orders; hand in the repository link.",
        SubmissionKind.LINK, AssignmentStatus.PUBLISHED, due=-3, resubmission=True,
        max_attempts=2, submit=0.6, late=0.3, graded=0.5, fail=0.2, returned=1,
    ),
    AssignmentSpec(
        "pa2-open", "pa2", "data-science-ml",
        "Week 3 — Pandas cleaning notebook",
        "Clean the sales extract: types, duplicates, missing values. Hand in the notebook "
        "exported as a .py file.",
        SubmissionKind.FILE, AssignmentStatus.PUBLISHED, due=6, submit=0.2, graded=0.0,
    ),
    # --- Upcoming: published ahead of the first class ---------------------------
    AssignmentSpec(
        "u1-ahead", "u1", "rhcsa",
        "Pre-course — set up your lab VM",
        "Before the first class: install the lab VM from the image on the portal and hand "
        "in the output of `hostnamectl`.",
        SubmissionKind.TEXT, AssignmentStatus.PUBLISHED, due=12,
    ),
)  # fmt: skip


@dataclass(frozen=True)
class AssessmentSpec:
    """One test. ``results`` is ``None`` (no results), ``"manual"`` (recorded
    one by one: ``absent`` absences, ``fail`` fails, ``share`` of the cohort
    recorded), ``"import"`` (through a CSV) or ``"graded"`` (a file-upload
    test whose backing assignment is submitted to by ``share`` of the cohort
    and graded for ``graded`` of them, ``fail`` of those below the pass
    mark). On the fast track the absences and fails land on the students who
    fall short, so the rest keep a passing average."""

    key: str
    batch: str
    title: str
    description: str
    category: str
    delivery: str
    status: str
    scheduled: int | None = None
    opens: int | None = None
    closes: int | None = None
    duration: int | None = 60
    external_url: str = ""
    provider: str = ""
    max_marks: Decimal | None = None
    results: str | None = None
    share: float = 1.0
    absent: int = 0
    fail: int = 0
    graded: float = 1.0
    skip_short: bool = False


ASSESSMENTS: tuple[AssessmentSpec, ...] = (
    AssessmentSpec(
        "a2-week2", HEADLINE_ACTIVE, "Week 2 Test — Linux & shell",
        "Forty minutes, closed book, sat in Lab 1.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-28, duration=40,
        results="manual", absent=1, fail=3,
    ),
    AssessmentSpec(
        "a2-week4", HEADLINE_ACTIVE, "Week 4 Test — Docker fundamentals",
        "Images, layers, networking and volumes. Marks entered from the paper scripts.",
        AssessmentCategory.WEEKLY_TEST, AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED,
        scheduled=-14, duration=45, results="import", share=0.85, absent=2, fail=2,
    ),
    AssessmentSpec(
        "a2-quiz", HEADLINE_ACTIVE, "Week 6 Quiz — Kubernetes objects",
        "Fifteen questions on Pods, Deployments and Services. Open until Friday evening.",
        AssessmentCategory.WEEKLY_TEST, AssessmentDelivery.EXTERNAL_LINK,
        AssessmentStatus.PUBLISHED, opens=-1, closes=3, duration=20,
        external_url="https://forms.gle/grras-showcase-k8s-quiz", provider=PROVIDER_FORMS,
    ),
    AssessmentSpec(
        "a2-practical", HEADLINE_ACTIVE, "Ansible practical — configure the web tier",
        "Upload your playbook and inventory. Marked against the rubric in class.",
        AssessmentCategory.PRACTICE, AssessmentDelivery.FILE_UPLOAD, AssessmentStatus.PUBLISHED,
        opens=-7, closes=7, duration=None, results="graded", share=0.35, graded=0.6, fail=1,
    ),
    AssessmentSpec(
        "a2-mock", HEADLINE_ACTIVE, "Mock certification exam — CKA style",
        "A timed mock on the practice platform; scheduled for the week after Diwali.",
        AssessmentCategory.MOCK, AssessmentDelivery.EXTERNAL_LINK, AssessmentStatus.DRAFT,
        scheduled=12, duration=120, external_url="https://practice.grras.com/cka-mock-1",
        provider="Grras Practice Labs",
    ),
    AssessmentSpec(
        "c1-week3", HEADLINE_COMPLETED, "Week 3 Test — Storage & file systems",
        "Partitions, LVM, mounting and swap.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-140, duration=40,
        results="manual", absent=2, fail=3,
    ),
    AssessmentSpec(
        "c1-week7", HEADLINE_COMPLETED, "Week 7 Test — Networking & SELinux",
        "nmcli, firewalld and SELinux contexts.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-112, duration=40,
        results="manual", absent=1, fail=2,
    ),
    AssessmentSpec(
        "c2-week2", FAST_TRACK, "Week 2 Test — Python foundations",
        "Data structures, comprehensions and exceptions.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-266, duration=40,
        results="manual", absent=0, fail=1,
    ),
    AssessmentSpec(
        "c2-week6", FAST_TRACK, "Week 6 Test — Django ORM",
        "Models, migrations, queries and the admin.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-238, duration=45,
        results="manual", absent=1, fail=0, skip_short=True,
    ),
    AssessmentSpec(
        "pc1-week4", PUNE_COMPLETED, "Week 4 Test — CI/CD concepts",
        "Pipelines, artefacts and environments.", AssessmentCategory.WEEKLY_TEST,
        AssessmentDelivery.OFFLINE, AssessmentStatus.CLOSED, scheduled=-126, duration=40,
        results="manual", absent=1, fail=2,
    ),
    AssessmentSpec(
        "pa1-week3", "pa1", "Week 3 Test — Node & Express",
        "Middleware, routing and error handling; taken online.",
        AssessmentCategory.WEEKLY_TEST, AssessmentDelivery.EXTERNAL_LINK,
        AssessmentStatus.PUBLISHED, scheduled=2, opens=2, closes=3, duration=30,
        external_url="https://forms.gle/grras-showcase-node-week3", provider=PROVIDER_FORMS,
    ),
    AssessmentSpec(
        "pa2-week2", "pa2", "Week 2 Test — SQL joins & aggregates",
        "Sat in Lab 2 on paper.", AssessmentCategory.WEEKLY_TEST, AssessmentDelivery.OFFLINE,
        AssessmentStatus.CLOSED, scheduled=-7, duration=40, results="manual", absent=1, fail=2,
    ),
    AssessmentSpec(
        "u1-entry", "u1", "Entry assessment — Linux basics",
        "A short placement test on the first morning; no preparation needed.",
        AssessmentCategory.OTHER, AssessmentDelivery.OFFLINE, AssessmentStatus.PUBLISHED,
        scheduled=9, duration=30,
    ),
)  # fmt: skip


@dataclass(frozen=True)
class ProjectSpec:
    """One project brief and how its cohort's work is spread.

    ``work`` lists target states applied to the cohort in seeded order (the
    headline student first, the fast-track students who fall short last);
    the students left over stay ``assigned``. ``late`` is how many of the
    ``submitted`` ones handed in after the due date.
    """

    key: str
    batch: str | None
    course: str
    title: str
    description: str
    kind: str
    required: bool
    start: int
    end: int
    status: str = ProjectStatus.PUBLISHED
    repo: bool = False
    deploy: bool = False
    rubric: tuple[tuple[str, str, int], ...] = ()
    max_marks: Decimal = Decimal("100")
    work: tuple[str, ...] = ()
    late: int = 0


PROJECTS: tuple[ProjectSpec, ...] = (
    ProjectSpec(
        "c2-capstone", FAST_TRACK, "python-django-full-stack",
        "Capstone — the library management system",
        "A complete Django application: catalogue, members, loans and fines, with a REST "
        "API and a deployed demo.", ProjectKind.CAPSTONE, required=True,
        start=-224, end=-161, repo=True,
        rubric=(
            ("models", "Data model and migrations", 25),
            ("views", "Views and templates", 25),
            ("api", "REST API and authentication", 30),
            ("quality", "Tests and code quality", 20),
        ),
        work=("completed",) * 6 + ("approved",) * 2
        + ("rework_resubmitted", "approved", "submitted", "in_progress"),
        late=1,
    ),
    ProjectSpec(
        "a2-small", HEADLINE_ACTIVE, "devops-engineering",
        "Mini project — a monitored web service",
        "Package a small web service with a health endpoint, ship it with Compose and add a "
        "Prometheus scrape target.", ProjectKind.SMALL, required=False, start=-14, end=12,
        work=("in_progress", "under_review", "submitted", "rework", "in_progress"),
    ),
    ProjectSpec(
        "devops-major", None, "devops-engineering",
        "Major project — a production-style pipeline",
        "Course-wide: source to production for a two-service application — CI, image "
        "registry, Kubernetes manifests, rollback. A deployed URL is required.",
        ProjectKind.MAJOR, required=True, start=-7, end=30, deploy=True,
        work=("in_progress", "in_progress", "submitted"),
    ),
    ProjectSpec(
        "pa1-major", "pa1", "mern-full-stack",
        "Major project — the bookings platform",
        "React front end, Express API, MongoDB; authentication and a deployed demo.",
        ProjectKind.MAJOR, required=True, start=-21, end=21, repo=True, deploy=True,
        work=("submitted", "approved", "rework", "in_progress"),
    ),
    ProjectSpec(
        "u1-small", "u1", "rhcsa",
        "Small project — a hardened lab server",
        "Set up the lab VM to the checklist: users, SSH keys, firewall, a monitored service.",
        ProjectKind.SMALL, required=False, start=14, end=42,
    ),
    ProjectSpec(
        "a3-draft", "a3", "python-django-full-stack",
        "Major project — the clinic scheduler (draft)",
        "Being written; published once the ORM module is done.", ProjectKind.MAJOR,
        required=False, start=21, end=56, status=ProjectStatus.DRAFT,
    ),
)  # fmt: skip


@dataclass(frozen=True)
class ExamSpec:
    """One examination. ``attempts`` lists what happens to the cohort in
    seeded order — ``headline`` (the headline student mid-attempt),
    ``submitted`` (handed in, written answer unmarked), ``graded``,
    ``expired``; ``all_graded`` publishes the results and closes the paper,
    moving its window to ``window`` (days) once the attempts are in."""

    key: str
    batch: str
    title: str
    description: str
    opens: int
    closes: int
    duration: int
    max_attempts: int
    sections: tuple[dict[str, Any], ...]
    status: str = ExamStatus.PUBLISHED
    attempts: tuple[str, ...] = ()
    all_graded: bool = False
    window: tuple[int, int] | None = None


SECTIONS_FULL = (
    {"title": "Multiple choice", "question_count": 8, "question_type": QuestionType.MCQ},
    {"title": "True or false", "question_count": 3, "question_type": QuestionType.TRUE_FALSE},
    {"title": "Short answers", "question_count": 2, "question_type": QuestionType.SHORT_ANSWER},
    {"title": "Written answer", "question_count": 1, "question_type": QuestionType.LONG_ANSWER},
)
SECTIONS_SHORT = (
    {"title": "Multiple choice", "question_count": 6, "question_type": QuestionType.MCQ},
    {"title": "True or false", "question_count": 2, "question_type": QuestionType.TRUE_FALSE},
    {"title": "Written answer", "question_count": 1, "question_type": QuestionType.LONG_ANSWER},
)

EXAMS: tuple[ExamSpec, ...] = (
    ExamSpec(
        "a2-open", HEADLINE_ACTIVE, "Mid-course examination — Docker & Kubernetes",
        "Ninety minutes. Two attempts allowed; the better one counts.",
        opens=-1, closes=10, duration=90, max_attempts=2, sections=SECTIONS_FULL,
        attempts=("headline", "submitted", "graded", "expired", "submitted"),
    ),
    ExamSpec(
        "a2-closed", HEADLINE_ACTIVE, "Week 4 examination — Linux & containers",
        "Sixty minutes, one attempt. Results were released the following week.",
        opens=-21, closes=-18, duration=60, max_attempts=1, sections=SECTIONS_SHORT,
        status=ExamStatus.CLOSED, attempts=("graded",) * 9, all_graded=True, window=(-21, -18),
    ),
    ExamSpec(
        "a2-draft", HEADLINE_ACTIVE, "Final examination — DevOps Engineering",
        "Draft: the hard-question section still needs writing.",
        opens=60, closes=63, duration=120, max_attempts=1, status=ExamStatus.DRAFT,
        sections=(
            {"title": "Multiple choice", "question_count": 8, "question_type": QuestionType.MCQ},
            {"title": "Hard multiple choice", "question_count": 20,
             "question_type": QuestionType.MCQ, "difficulty": "hard"},
        ),
    ),
    ExamSpec(
        "pa1-ahead", "pa1", "Week 8 examination — MERN fundamentals",
        "Opens Thursday morning; sixty minutes once started.",
        opens=3, closes=6, duration=60, max_attempts=1, sections=SECTIONS_SHORT,
    ),
)  # fmt: skip

#: How each finished cohort is approved — by the rules (only those eligible,
#: leaving QUEUE_LEFT in the queue) or with override — how many are rejected,
#: and whether one certificate is reissued and one revoked.
COMPLETION_PLAN: dict[str, tuple[str, int, bool]] = {
    FAST_TRACK: ("rules", 0, False),
    HEADLINE_COMPLETED: ("override", 1, True),
    PUNE_COMPLETED: ("override", 0, False),
    ARCHIVED: ("override", 0, False),
}

# --- Text ------------------------------------------------------------------

TEXT_ANSWERS = (
    "The script tars /srv/data into /var/backups with the date in the name, deletes "
    "anything older than seven days with find -mtime +7, and writes one line to the "
    "journal through logger. Sample: 'backup: /srv/data archived, 412 MB, 7 copies kept'.",
    "Created the three accounts with useradd -G, set the shared directory to group "
    "ownership with chgrp and added the setgid bit so new files inherit the group. "
    "Verified with ls -ld and a test file created as each user.",
    "Extended the volume group with the new disk (vgextend), grew the logical volume with "
    "lvextend -r so the file system was resized online, and confirmed with df -h. No "
    "unmount was needed because XFS grows online.",
    "hostnamectl reports the static hostname lab-vm-01, the RHEL 9.4 image and the kernel "
    "5.14 build from the portal image. Chronyd is synced and the NIC is on the lab bridge.",
)
LINK_HOSTS = ("https://github.com/{local}/{slug}", "https://gitlab.com/{local}/{slug}")
FEEDBACK_PASS = (
    "Clean and correct. The health check on the API is a nice touch.",
    "Good work — the write-up explains the trade-offs clearly.",
    "Correct; a little more attention to naming next time.",
    "Well structured. Consider a smaller base image for the final stage.",
)
FEEDBACK_FAIL = (
    "The service does not start from the submitted files; the volume path is wrong.",
    "Half the tasks are missing. Look at the brief again and resubmit next week.",
    "The API returns 500 on the listing endpoint; see my comments in the file.",
)
FEEDBACK_RETURN = (
    "Returned: the Dockerfile builds but runs as root — fix the user and resubmit.",
    "Returned: the script works but never rotates the copies. Add the cleanup and hand in again.",
)
RESULT_REMARKS = ("", "", "Neat script work.", "Ran out of time on the last question.", "")
ABSENT_REMARKS = ("Absent — informed the trainer in advance.", "Absent without notice.")
PROJECT_NOTES = (
    "Repository set up; models and admin done, API in progress.",
    "Deployed to Render; the search page still needs pagination.",
    "Working on the loans workflow this week.",
)
PROJECT_FEEDBACK_REWORK = (
    "The API has no authentication — the brief asks for token auth. Add it and resubmit.",
    "The deployed URL returns 502; fix the start command and hand in again.",
)
PROJECT_FEEDBACK_APPROVED = (
    "A complete, working application. Well done.",
    "Approved. The test suite is thin, but the core flows are solid.",
    "Approved — a clear data model and a readable API.",
)
LONG_ANSWERS = (
    "First I would restate the problem in my own words, then list what I know, then try "
    "the simplest approach on a small example, and finally check the answer against the "
    "constraints before writing it up.",
    "A Deployment keeps the desired number of Pods running and rolls out changes; a "
    "Service gives them a stable address. I would use a Deployment for the API and a "
    "ClusterIP Service in front of it, with an Ingress for outside traffic.",
    "I would keep the image small with a multi-stage build, run as a non-root user, add a "
    "health check, and pin the base image tag so builds are reproducible.",
)
MARKER_FEEDBACK = (
    "Clear and complete.",
    "Covers the main points; missed the rollback step.",
    "Too brief — one line where a paragraph was asked for.",
)

PY_FILE = b'''"""Inventory report - showcase submission."""

import csv
import sys


def main(path: str) -> None:
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    low = [row for row in rows if int(row["quantity"]) < 5]
    for row in sorted(low, key=lambda r: r["sku"]):
        print(f"{row['sku']:<10} {row['quantity']:>4}")


if __name__ == "__main__":
    main(sys.argv[1])
'''
PDF_FILE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 62>>stream\nBT /F1 18 Tf 72 770 Td (Grras showcase submission) Tj ET\n"
    b"endstream\nendobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
TXT_FILE = (
    b"Lab transcript\n==============\n\n$ useradd -G developers asha\n$ chgrp developers "
    b"/srv/shared\n$ chmod 2775 /srv/shared\n$ ls -ld /srv/shared\ndrwxrwsr-x. 2 root "
    b"developers 6 /srv/shared\n"
)
FILES = (
    ("inventory_report.py", PY_FILE),
    ("lab-report.pdf", PDF_FILE),
    ("transcript.txt", TXT_FILE),
)
BRIEF_MD = (
    b"# Lab 3 brief\n\nContainerise the inventory service.\n\n1. Multi-stage Dockerfile\n"
    b"2. Non-root user\n3. Health check\n\nHand in the Dockerfile and a one-page note.\n"
)


# ---------------------------------------------------------------------------
# Scope and bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class Scope:
    """The batches by stage-4 key, their cohorts, and who does what."""

    by_spec: dict[str, Batch] = field(default_factory=dict)
    cohorts: dict[Any, list[Enrollment]] = field(default_factory=dict)
    headline: User | None = None
    #: Fast-track students who fall short of the rules, by user email.
    short: set[str] = field(default_factory=set)
    #: Every enrolment a grade or result may touch: the debounce claims.
    claimed: set[Any] = field(default_factory=set)


def _seed(*parts: Any) -> random.Random:
    """A generator for one row, from its natural key — see the module docstring."""
    return random.Random(":".join([str(RUN_SEED), STAGE, *(str(p) for p in parts)]))  # noqa: S311


def _chance(*parts: Any) -> float:
    return _seed(*parts).random()


def _draw(seq: tuple, *parts: Any):
    return seq[_seed(*parts).randrange(len(seq))]


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    if not ctx.showcase_batches:
        raise RuntimeError("No showcase batches yet: run the batches stage first.")

    scope = _timed(ctx, "scope", lambda: _scope(ctx))
    _claim_recomputes(scope)
    _timed(ctx, "course policy", lambda: _ensure_course_policy(ctx))
    _timed(ctx, "assignments", lambda: _ensure_assignments(ctx, scope))
    _timed(ctx, "assessments", lambda: _ensure_assessments(ctx, scope))
    _timed(ctx, "projects", lambda: _ensure_projects(ctx, scope))
    _timed(ctx, "exams", lambda: _ensure_exams(ctx, scope))
    template = _timed(ctx, "certificate template", lambda: _ensure_template(ctx))
    _timed(ctx, "completions", lambda: _ensure_completions(ctx, scope, template))
    _timed(ctx, "sitp completions", lambda: _ensure_sitp(ctx, template))
    _release_recomputes(ctx, scope)


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> Any:
    started = perf_counter()
    result = step()
    ctx.out(f"{STAGE}/{what}: {perf_counter() - started:.1f}s")
    return result


def _scope(ctx: Context) -> Scope:
    scope = Scope()
    names = {batch_key(spec.name): spec.key for spec in SPECS}
    for key, batch in ctx.showcase_batches.items():
        spec_key = names.get(key)
        if spec_key is not None and batch.status != BatchStatus.CANCELLED:
            scope.by_spec[spec_key] = batch
    if ctx.students.get(MAIN):
        scope.headline = ctx.students[MAIN][0].user

    fast_track = scope.by_spec.get(FAST_TRACK)
    if fast_track is not None:
        cohort = [row for row in _cohort(scope, fast_track) if row.student.user != scope.headline]
        cohort.sort(key=lambda row: _chance("short", row.student.user.email))
        scope.short = {row.student.user.email for row in cohort[:FAST_TRACK_SHORT]}
    return scope


def _cohort(scope: Scope, batch: Batch) -> list[Enrollment]:
    """The students a brief is for — the register's rule (active, suspended
    or completed), in a stable order that does not depend on the database."""
    if batch.pk not in scope.cohorts:
        rows = list(
            Enrollment.objects.filter(
                batch=batch,
                status__in=(
                    EnrollmentStatus.ACTIVE,
                    EnrollmentStatus.SUSPENDED,
                    EnrollmentStatus.COMPLETED,
                ),
            )
            .select_related("student__user", "batch__course", "batch__branch", "course")
            .order_by("student__user__email")
        )
        scope.cohorts[batch.pk] = rows
        scope.claimed.update(row.pk for row in rows)
    return scope.cohorts[batch.pk]


def _ordered(scope: Scope, cohort: list[Enrollment], *parts: Any) -> list[Enrollment]:
    """A cohort in seeded order: the headline student first, the fast-track
    students who fall short last, everybody else shuffled by the key."""
    rows = sorted(cohort, key=lambda row: _chance(*parts, row.student.user.email))
    head = [row for row in rows if row.student.user == scope.headline]
    short = [row for row in rows if row.student.user.email in scope.short]
    rest = [row for row in rows if row not in head and row not in short]
    return head + rest + short


def _grader(ctx: Context, batch: Batch) -> User:
    """Who sets and marks the work: the batch's trainer, or the centre's
    admin for a batch nobody teaches yet or whose trainer has left."""
    trainer = batch.trainer
    if trainer is not None and trainer.user_id and trainer.user.is_active:
        return trainer.user
    return ctx.actor_for(batch.branch.code)


def _course_author(ctx: Context, course: Course) -> User:
    """Course-wide work is set by the course's own trainer."""
    local = {
        "devops-engineering": "trainer",
        "rhcsa": "trainer",
        "python-django-full-stack": "neha.saxena",
    }
    return ctx.users.get(local.get(course.slug, "")) or ctx.actor_for(MAIN)


def _course(ctx: Context, slug: str) -> Course:
    try:
        return ctx.courses[slug]
    except KeyError:
        raise RuntimeError(f"Course {slug} is not loaded: run the courses stage first.") from None


def _at(ctx: Context, days: int, hour: int = 10, minute: int = 0) -> datetime:
    return ctx.at(ctx.days_ahead(days), hour, minute)


def _road(choices, target: str) -> tuple[str, ...]:
    """The status moves from draft to ``target`` along the app's transitions —
    the assignment, assessment and project lifecycles share their shape."""
    roads = {
        choices.DRAFT: (),
        choices.PUBLISHED: (choices.PUBLISHED,),
        choices.CLOSED: (choices.PUBLISHED, choices.CLOSED),
        choices.ARCHIVED: (choices.PUBLISHED, choices.ARCHIVED),
    }
    return roads[target]


# ---------------------------------------------------------------------------
# The rule this stage relaxes
# ---------------------------------------------------------------------------


def _ensure_course_policy(ctx: Context) -> None:
    course = ctx.courses.get(POLICY_COURSE)
    if course is None:
        ctx.out(f"course policy: {POLICY_COURSE} not on this database, skipped")
        return
    policy = get_or_create_policy(course=course)
    unchanged = all(getattr(policy, k) == v for k, v in POLICY_RULES.items())
    update_academic_policy(policy=policy, actor=ctx.superadmin, **POLICY_RULES)
    if unchanged:
        ctx.found_existing("academic_policy_course")
        ctx.out(f"course policy {POLICY_COURSE}: found")
    else:
        ctx.created("academic_policy_course")
        ctx.out(f"course policy {POLICY_COURSE}: configured")


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


def _ensure_assignments(ctx: Context, scope: Scope) -> None:
    for spec in ASSIGNMENTS:
        batch = scope.by_spec.get(spec.batch) if spec.batch else None
        if spec.batch and batch is None:
            ctx.out(f"assignment {spec.key}: batch not on this database, skipped")
            continue
        course = batch.course if batch is not None else _course(ctx, spec.course)
        actor = _grader(ctx, batch) if batch is not None else _course_author(ctx, course)
        assignment, created = _ensure_assignment(ctx, spec, course, batch, actor)
        if spec.status not in (AssignmentStatus.PUBLISHED, AssignmentStatus.CLOSED):
            continue
        if batch is not None:
            _ensure_submissions(ctx, scope, spec, assignment, batch, actor)
        else:
            for other in scope.by_spec.values():
                if other.course_id == course.pk and _answers_course_wide(ctx, assignment, other):
                    _ensure_submissions(ctx, scope, spec, assignment, other, _grader(ctx, other))
        if created and spec.status == AssignmentStatus.CLOSED:
            # Closed *after* the hand-ins, the way it happened: the brief was
            # open while the students answered it.
            set_assignment_status(assignment=assignment, actor=actor, status=spec.status)


def _answers_course_wide(ctx: Context, assignment: Assignment, batch: Batch) -> bool:
    """Whether a batch's students hand in a course-wide brief: one that has
    started, and a finished one only for a brief that was due before it ended."""
    if batch.start_date > ctx.today or batch.status == BatchStatus.ARCHIVED:
        return False
    if batch.status == BatchStatus.COMPLETED:
        due = assignment.due_at
        return bool(due and due.date() <= batch.end_date)
    return True


def _ensure_assignment(
    ctx: Context, spec: AssignmentSpec, course: Course, batch: Batch | None, actor: User
) -> tuple[Assignment, bool]:
    """The brief, and whether this run made it. A brief headed for *closed*
    is left published here — the caller closes it once the hand-ins are in."""
    existing = Assignment.objects.filter(course=course, batch=batch, title=spec.title).first()
    if existing is not None:
        ctx.found_existing("assignment")
        ctx.out(f"assignment {spec.key}: found")
        return existing, False

    due_at = _at(ctx, spec.due, 18, 0) if spec.due is not None else None
    assignment = create_assignment(
        actor=actor,
        course=course,
        batch=batch,
        title=spec.title,
        instructions=spec.instructions,
        submission_kind=spec.kind,
        due_at=due_at,
        allow_late=spec.allow_late,
        late_cutoff_at=_at(ctx, spec.late_cutoff, 23, 59) if spec.late_cutoff else None,
        allow_resubmission=spec.resubmission,
        max_attempts=spec.max_attempts,
        passing_marks=spec.passing,
    )
    if spec.attachment is not None:
        name, title = spec.attachment
        add_attachment(
            assignment=assignment,
            actor=actor,
            uploaded_file=ContentFile(BRIEF_MD, name=name),
            title=title,
        )
        ctx.created("assignment_attachment")
    road = _road(AssignmentStatus, spec.status)
    if spec.status == AssignmentStatus.CLOSED:
        road = road[:1]
    for status in road:
        set_assignment_status(assignment=assignment, actor=actor, status=status)

    # Set a fortnight before it is due, or three weeks ago for one with no
    # due date; never before the batch started, never after now.
    if due_at is not None:
        published = due_at - timedelta(days=14)
    else:
        published = ctx.at(ctx.days_ago(21), 9, 0)
    if batch is not None:
        published = max(published, ctx.at(batch.start_date, 9, 0))
    published = min(published, ctx.now)
    fields: dict[str, Any] = {"created_at": published}
    if assignment.published_at is not None:
        fields["published_at"] = published
    ctx.backdate(assignment, **fields)
    ctx.created("assignment")
    ctx.out(f"assignment {spec.key}: created ({spec.status})")
    return assignment, True


def _ensure_submissions(
    ctx: Context,
    scope: Scope,
    spec: AssignmentSpec,
    assignment: Assignment,
    batch: Batch,
    grader: User,
) -> None:
    """Hand-ins for one brief on one batch, each decided by its own seed."""
    if assignment.status != AssignmentStatus.PUBLISHED:
        # A closed brief on a re-run: whoever handed in is already there.
        n = AssignmentSubmission.objects.filter(assignment=assignment).count()
        ctx.found_existing("submission", n)
        return

    cohort = [row for row in _cohort(scope, batch) if row.grants_access()]
    if not cohort:
        return
    existing = set(
        AssignmentSubmission.objects.filter(assignment=assignment).values_list(
            "enrollment_id", flat=True
        )
    )
    # Who is sent back and resubmits: the first few by seed among those who
    # hand in, when the brief allows it.
    returned: set = set()
    if spec.resubmission and spec.returned:
        candidates = [
            row
            for row in _ordered(scope, cohort, "order", spec.key)
            if row.student.user != scope.headline
            and _chance("submit", spec.key, row.student.user.email) < spec.submit
        ]
        returned = {row.pk for row in candidates[: spec.returned]}

    created = found = 0
    for row in cohort:
        user = row.student.user
        if row.pk in existing:
            found += 1
            continue
        if user == scope.headline:
            if spec.headline is None:
                continue
            plan = {"late": False, "graded": spec.headline == "pass", "fail": False}
        else:
            if spec.skip_short and user.email in scope.short:
                continue
            if _chance("submit", spec.key, user.email) >= spec.submit:
                continue
            can_be_late = spec.due is not None and spec.due < 0 and spec.allow_late
            plan = {
                "late": can_be_late and _chance("late", spec.key, user.email) < spec.late,
                "graded": _chance("graded", spec.key, user.email) < spec.graded,
                "fail": _chance("fail", spec.key, user.email) < spec.fail,
            }
        _hand_in(ctx, spec.key, assignment, row, grader, plan, returned=row.pk in returned)
        created += 1
    ctx.created("submission", created)
    ctx.found_existing("submission", found)
    if created:
        ctx.out(f"submissions {spec.key} @ {batch.code}: {created} created, {found} found")


def _hand_in(
    ctx: Context,
    key: str,
    assignment: Assignment,
    row: Enrollment,
    grader: User,
    plan: dict[str, bool],
    *,
    returned: bool,
) -> None:
    """One student's hand-in: the attempt(s), the grade or return, the dates."""
    user = row.student.user
    email = user.email
    submissions: list[AssignmentSubmission] = []

    first = submit_assignment(
        assignment=assignment,
        enrollment=row,
        actor=user,
        **_content(key, assignment, email, attempt=1),
    )
    submissions.append(first)
    last = first
    if returned:
        return_submission(
            submission=first, actor=grader, feedback=_draw(FEEDBACK_RETURN, "return", email)
        )
        ctx.created("submission_return")
        second = submit_assignment(
            assignment=assignment,
            enrollment=row,
            actor=user,
            **_content(key, assignment, email, attempt=2),
        )
        submissions.append(second)
        last = second
        plan = {**plan, "graded": True, "fail": False}

    if plan["graded"]:
        maximum = assignment.max_marks
        passing = _pass_mark(assignment)
        draw = _seed("marks", key, email)
        if plan["fail"]:
            marks = passing * Decimal(draw.randint(35, 85)) / Decimal(100)
        else:
            span = int(maximum - passing)
            marks = passing + Decimal(draw.randint(max(1, span // 5), max(1, span)))
        marks = min(marks.quantize(Decimal("1")), maximum)
        feedback = _draw(FEEDBACK_FAIL if plan["fail"] else FEEDBACK_PASS, "feedback", email)
        grade_submission(submission=last, actor=grader, marks=marks, feedback=feedback)
        ctx.created("submission_grade")

    # Make it historical — after the last service call on each row. On time
    # means a few hours to four days before the due date (or before now, for
    # a brief still open); late means one to two and a half days after it.
    due = assignment.due_at
    anchor = min(due, ctx.now) if due else (assignment.published_at or ctx.now) + timedelta(days=3)
    draw = _seed("when", key, email)
    previous: datetime | None = None
    for submission in submissions:
        if plan["late"] and not returned:
            when = due + timedelta(hours=draw.randint(24, 60))
            late = True
        else:
            when = anchor - timedelta(hours=draw.randint(2, 96))
            if previous is not None:
                when = previous + timedelta(days=3)
            late = bool(due and when > due)
        when = min(when, ctx.now - timedelta(minutes=5))
        if assignment.published_at is not None:
            when = max(when, assignment.published_at)
        previous = when
        fields: dict[str, Any] = {"submitted_at": when, "created_at": when, "is_late": late}
        if submission.graded_at is not None:
            fields["graded_at"] = min(when + timedelta(hours=draw.randint(12, 72)), ctx.now)
        ctx.backdate(submission, **fields)


def _content(key: str, assignment: Assignment, email: str, *, attempt: int) -> dict:
    """What the student hands in, matching the brief's submission kind."""
    local = email.split("@", 1)[0].replace(".", "-")
    slug = assignment.title.lower().split("—")[-1].strip().replace(" ", "-")[:30] or "work"
    kind = assignment.submission_kind
    which = _seed("content", key, email, attempt).randrange(3)
    if kind == SubmissionKind.ANY:
        kind = (SubmissionKind.FILE, SubmissionKind.TEXT, SubmissionKind.LINK)[which]
    if kind == SubmissionKind.FILE:
        name, body = FILES[which]
        return {"files": [ContentFile(body, name=name)]}
    if kind == SubmissionKind.LINK:
        return {"link_url": LINK_HOSTS[which % 2].format(local=local, slug=slug)}
    return {"text_answer": TEXT_ANSWERS[which % len(TEXT_ANSWERS)]}


def _pass_mark(assignment: Assignment) -> Decimal:
    from apps.academics.policies import passing_mark_for_assignment

    return passing_mark_for_assignment(assignment)


# ---------------------------------------------------------------------------
# Assessments and results
# ---------------------------------------------------------------------------


def _ensure_assessments(ctx: Context, scope: Scope) -> None:
    for spec in ASSESSMENTS:
        batch = scope.by_spec.get(spec.batch)
        if batch is None:
            ctx.out(f"assessment {spec.key}: batch not on this database, skipped")
            continue
        actor = _grader(ctx, batch)
        assessment = _ensure_assessment(ctx, spec, batch, actor)
        if spec.results == "manual":
            _ensure_results(ctx, scope, spec, assessment, batch, actor)
        elif spec.results == "import":
            _ensure_import(ctx, scope, spec, assessment, batch, actor)
        elif spec.results == "graded":
            _ensure_upload_grading(ctx, scope, spec, assessment, batch, actor)


def _ensure_assessment(ctx: Context, spec: AssessmentSpec, batch: Batch, actor: User) -> Assessment:
    existing = Assessment.objects.filter(batch=batch, title=spec.title).first()
    if existing is not None:
        ctx.found_existing("assessment")
        ctx.out(f"assessment {spec.key}: found")
        return existing

    fields: dict[str, Any] = {
        "title": spec.title,
        "description": spec.description,
        "category": spec.category,
        "delivery": spec.delivery,
        "external_url": spec.external_url,
        "external_provider": spec.provider,
        "scheduled_for": _at(ctx, spec.scheduled, 11, 0) if spec.scheduled is not None else None,
        "opens_at": _at(ctx, spec.opens, 9, 0) if spec.opens is not None else None,
        "closes_at": _at(ctx, spec.closes, 18, 0) if spec.closes is not None else None,
        "max_marks": spec.max_marks,
    }
    if spec.duration is not None:
        fields["duration_minutes"] = spec.duration
    assessment = create_assessment(actor=actor, batch=batch, **fields)
    for status in _road(AssessmentStatus, spec.status):
        set_assessment_status(assessment=assessment, actor=actor, status=status)

    anchor = assessment.scheduled_for or assessment.opens_at or ctx.now
    created_at = max(anchor - timedelta(days=7), ctx.at(batch.start_date, 9, 0) - timedelta(days=3))
    created_at = min(created_at, ctx.now)
    fields = {"created_at": created_at}
    if assessment.published_at is not None:
        fields["published_at"] = min(created_at + timedelta(hours=2), ctx.now)
    ctx.backdate(assessment, **fields)
    if assessment.backing_assignment_id:
        ctx.backdate(assessment.backing_assignment, **fields)
    ctx.created("assessment")
    ctx.out(f"assessment {spec.key}: created ({spec.status}, {spec.delivery})")
    return assessment


def _result_plan(
    scope: Scope, spec: AssessmentSpec, cohort: list[Enrollment]
) -> dict[Any, tuple[str, Decimal | None]]:
    """Who gets what on a paper test: ``(outcome, marks)`` per enrolment —
    ``absent``, ``fail`` or ``pass`` — from seeds; the headline student
    always sits and passes, and on the fast track the misses land on the
    students who fall short, so nobody else's average dips below the rule."""
    ordered = [
        row
        for row in _ordered(scope, cohort, "result-order", spec.key)
        if row.student.user != scope.headline
    ]
    if spec.batch == FAST_TRACK and not spec.skip_short:
        ordered = [r for r in ordered if r.student.user.email in scope.short] + [
            r for r in ordered if r.student.user.email not in scope.short
        ]
    absent = {row.pk for row in ordered[: spec.absent]}
    failed = {row.pk for row in ordered[spec.absent : spec.absent + spec.fail]}
    plan: dict[Any, tuple[str, Decimal | None]] = {}
    maximum = spec.max_marks or Decimal("100")
    for row in cohort:
        email = row.student.user.email
        if spec.skip_short and email in scope.short:
            continue
        if row.student.user != scope.headline and _chance("sit", spec.key, email) >= spec.share:
            continue
        draw = _seed("marks", spec.key, email)
        if row.pk in absent:
            plan[row.pk] = ("absent", None)
        elif row.pk in failed:
            plan[row.pk] = ("fail", _percent_of(maximum, draw.randint(12, 34)))
        else:
            plan[row.pk] = ("pass", _percent_of(maximum, draw.randint(46, 96)))
    return plan


def _percent_of(maximum: Decimal, percent: int) -> Decimal:
    """``percent`` of ``maximum``, as a whole mark."""
    return (maximum * percent / 100).quantize(Decimal("1"))


def _ensure_results(
    ctx: Context,
    scope: Scope,
    spec: AssessmentSpec,
    assessment: Assessment,
    batch: Batch,
    actor: User,
) -> None:
    cohort = _cohort(scope, batch)
    existing = set(assessment.results.values_list("enrollment_id", flat=True))
    plan = _result_plan(scope, spec, cohort)
    recorded_at = min((assessment.scheduled_for or ctx.now) + timedelta(hours=6), ctx.now)
    created = found = 0
    for row in cohort:
        if row.pk not in plan:
            continue
        if row.pk in existing:
            found += 1
            continue
        outcome, marks = plan[row.pk]
        email = row.student.user.email
        remarks = ABSENT_REMARKS if outcome == "absent" else RESULT_REMARKS
        result, _ = record_result(
            assessment=assessment,
            enrollment=row,
            actor=actor,
            marks=marks,
            is_absent=outcome == "absent",
            remarks=_draw(remarks, "remark", email),
        )
        ctx.backdate(result, recorded_at=recorded_at, created_at=recorded_at)
        created += 1
    ctx.created("assessment_result", created)
    ctx.found_existing("assessment_result", found)
    if created:
        ctx.out(f"results {spec.key}: {created} recorded, {found} found")


def _ensure_import(
    ctx: Context,
    scope: Scope,
    spec: AssessmentSpec,
    assessment: Assessment,
    batch: Batch,
    actor: User,
) -> None:
    """A result sheet imported through preview → confirm, and a second sheet
    with bad rows left at the preview step with its error report."""
    cohort = _cohort(scope, batch)
    plan = _result_plan(scope, spec, cohort)
    by_pk = {row.pk: row for row in cohort}
    lines = ["student_id,marks,absent,remarks"]
    for pk, (outcome, marks) in sorted(plan.items(), key=lambda i: by_pk[i[0]].student.student_id):
        student_id = by_pk[pk].student.student_id
        if outcome == "absent":
            lines.append(f"{student_id},,yes,{ABSENT_REMARKS[1]}")
        else:
            lines.append(f"{student_id},{marks},no,")
    clean = ("\n".join(lines) + "\n").encode()
    # The bad rows: somebody outside the batch, a mark over the maximum on a
    # student the sheet missed, a duplicate, and a formula where an id goes.
    in_sheet = [by_pk[pk].student.student_id for pk in plan]
    missed = [row.student.student_id for row in cohort if row.pk not in plan]
    over = missed[0] if missed else "GRS-S-00002"
    duplicate = in_sheet[0] if in_sheet else "GRS-S-00001"
    with_errors = (
        "\n".join(
            [
                *lines,
                "GRS-S-99999,72,no,Not on this batch",
                f"{over},150,no,Over the maximum",
                f"{duplicate},64,no,Duplicate of an earlier line",
                "=SUM(A1:A9),50,no,A formula in the id column",
            ]
        )
        + "\n"
    ).encode()

    confirmed = ResultImport.objects.filter(
        assessment=assessment, status=ImportStatus.CONFIRMED
    ).exists()
    # The files are put back whenever the storage lacks them (a fresh
    # MEDIA_ROOT), but they count as created only with the import they
    # belong to — otherwise a re-run under a per-process media directory
    # would report rows it did not make.
    for path, body in ((IMPORT_CLEAN, clean), (IMPORT_WITH_ERRORS, with_errors)):
        if not default_storage.exists(path):
            default_storage.save(path, ContentFile(body))
            ctx.out(f"import fixture {path}: written")
        if confirmed:
            ctx.found_existing("import_fixture")
        else:
            ctx.created("import_fixture")
    if not confirmed and plan:
        run = preview_import(
            assessment=assessment,
            actor=actor,
            uploaded_file=ContentFile(clean, name=IMPORT_CLEAN.rsplit("/", 1)[-1]),
        )
        run = confirm_import(run=run, actor=actor)
        when = min((assessment.scheduled_for or ctx.now) + timedelta(days=1), ctx.now)
        for result in assessment.results.all():
            ctx.backdate(result, recorded_at=when, created_at=when)
        ctx.backdate(run, created_at=when - timedelta(minutes=10), confirmed_at=when)
        ctx.created("result_import")
        ctx.created("assessment_result", run.created_count)
        ctx.out(f"result import {spec.key}: {run.created_count} results confirmed")
    else:
        ctx.found_existing("result_import")
        ctx.found_existing("assessment_result", assessment.results.count())

    name = IMPORT_WITH_ERRORS.rsplit("/", 1)[-1]
    if ResultImport.objects.filter(assessment=assessment, original_filename=name).exists():
        ctx.found_existing("result_import_preview")
    elif plan:
        run = preview_import(
            assessment=assessment, actor=actor, uploaded_file=ContentFile(with_errors, name=name)
        )
        ctx.backdate(run, created_at=ctx.now - timedelta(days=1))
        ctx.created("result_import_preview")
        ctx.out(f"result import {spec.key}: preview with {run.error_count} errors kept")


def _ensure_upload_grading(
    ctx: Context,
    scope: Scope,
    spec: AssessmentSpec,
    assessment: Assessment,
    batch: Batch,
    actor: User,
) -> None:
    """A file-upload test: students hand in on the backing assignment and the
    grade mirrors into the results table (``source=graded``)."""
    backing = assessment.backing_assignment
    if backing is None or backing.status != AssignmentStatus.PUBLISHED:
        n = AssignmentSubmission.objects.filter(assignment=backing).count() if backing else 0
        ctx.found_existing("submission", n)
        return
    cohort = [row for row in _cohort(scope, batch) if row.grants_access()]
    sitting = [
        row
        for row in _ordered(scope, cohort, "upload-order", spec.key)
        if row.student.user != scope.headline
    ][: max(1, round(len(cohort) * spec.share))]
    existing = set(
        AssignmentSubmission.objects.filter(assignment=backing).values_list(
            "enrollment_id", flat=True
        )
    )
    failed = {row.pk for row in sitting[: spec.fail]}
    created = found = 0
    for index, row in enumerate(sitting):
        if row.pk in existing:
            found += 1
            continue
        graded = index < round(len(sitting) * spec.graded)
        plan = {"late": False, "graded": graded, "fail": row.pk in failed}
        _hand_in(ctx, spec.key, backing, row, actor, plan, returned=False)
        created += 1
        # The mirrored result was stamped now by `record_result`; make it
        # agree with the grading date.
        result = assessment.results.filter(enrollment=row).first()
        if result is not None:
            submission = AssignmentSubmission.objects.get(assignment=backing, enrollment=row)
            when = submission.graded_at or submission.submitted_at
            ctx.backdate(result, recorded_at=when, created_at=when)
            ctx.created("assessment_result")
    ctx.created("submission", created)
    ctx.found_existing("submission", found)
    if created:
        ctx.out(f"upload test {spec.key}: {created} handed in, {found} found")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _ensure_projects(ctx: Context, scope: Scope) -> None:
    for spec in PROJECTS:
        batch = scope.by_spec.get(spec.batch) if spec.batch else None
        if spec.batch and batch is None:
            ctx.out(f"project {spec.key}: batch not on this database, skipped")
            continue
        course = batch.course if batch is not None else _course(ctx, spec.course)
        actor = _grader(ctx, batch) if batch is not None else _course_author(ctx, course)
        project = _ensure_project(ctx, spec, course, batch, actor)
        if project.status != ProjectStatus.PUBLISHED:
            continue
        outcome = assign_project(project=project, actor=actor)
        ctx.created("student_project", outcome["assigned"])
        ctx.found_existing("student_project", outcome["already_had"])
        if batch is not None:
            targets = [batch] if batch.start_date <= ctx.today else []
        else:
            # Course-wide work is done on the batches running right now.
            targets = [
                b
                for b in scope.by_spec.values()
                if b.course_id == course.pk and b.status == BatchStatus.ACTIVE
            ]
        for target in targets:
            _ensure_project_work(ctx, scope, spec, project, target)


def _ensure_project(
    ctx: Context, spec: ProjectSpec, course: Course, batch: Batch | None, actor: User
) -> Project:
    existing = Project.objects.filter(course=course, batch=batch, title=spec.title).first()
    if existing is not None:
        ctx.found_existing("project")
        ctx.out(f"project {spec.key}: found")
        return existing

    trainer = batch.trainer if batch is not None else None
    reviewer = trainer if trainer is not None and trainer.user.is_active else None
    project = create_project(
        actor=actor,
        course=course,
        batch=batch,
        title=spec.title,
        description=spec.description,
        instructions="Work in your own repository; commit as you go. Ask in the batch "
        "discussion if the brief is unclear.",
        deliverables="Source repository, a README, and a short demo recording or deployed URL.",
        kind=spec.kind,
        is_required=spec.required,
        start_date=ctx.days_ahead(spec.start),
        end_date=ctx.days_ahead(spec.end),
        requires_repository_url=spec.repo,
        requires_deployment_url=spec.deploy,
        max_marks=spec.max_marks,
        rubric=[{"key": k, "label": label, "max_marks": m} for k, label, m in spec.rubric],
        reviewer=reviewer,
    )
    for status in _road(ProjectStatus, spec.status):
        set_project_status(project=project, actor=actor, status=status)
    created_at = min(ctx.at(ctx.days_ahead(spec.start), 9, 0) - timedelta(days=5), ctx.now)
    fields: dict[str, Any] = {"created_at": created_at}
    if project.published_at is not None:
        fields["published_at"] = min(created_at + timedelta(days=1), ctx.now)
    ctx.backdate(project, **fields)
    ctx.created("project")
    ctx.out(f"project {spec.key}: created ({spec.status}, {spec.kind})")
    return project


def _ensure_project_work(
    ctx: Context, scope: Scope, spec: ProjectSpec, project: Project, batch: Batch
) -> None:
    cohort = [row for row in _cohort(scope, batch) if row.grants_access()]
    rows = {
        work.enrollment_id: work
        for work in StudentProject.objects.filter(project=project, enrollment__in=cohort)
    }
    ordered = _ordered(scope, cohort, "work-order", spec.key)
    reviewer = _grader(ctx, batch)
    late: set = set()
    for row, target in zip(ordered, spec.work, strict=False):
        if target == "submitted" and len(late) < spec.late:
            late.add(row.pk)

    created = found = 0
    for row, target in zip(ordered, spec.work, strict=False):
        work = rows.get(row.pk)
        if work is None:
            continue
        if work.status != WorkStatus.ASSIGNED or work.submission_count or work.notes:
            found += 1
            continue
        _walk_work(ctx, spec, project, work, row, reviewer, target, late=row.pk in late)
        created += 1
    ctx.created("project_work", created)
    ctx.found_existing("project_work", found)
    if created:
        ctx.out(f"project work {spec.key} @ {batch.code}: {created} walked, {found} found")


def _walk_work(
    ctx: Context,
    spec: ProjectSpec,
    project: Project,
    work: StudentProject,
    row: Enrollment,
    reviewer: User,
    target: str,
    *,
    late: bool,
) -> None:
    """Move one student's project to ``target`` through the student's and the
    reviewer's own moves, then date it."""
    user = row.student.user
    email = user.email
    local = email.split("@", 1)[0].replace(".", "-")
    slug = spec.key.replace("-", "")
    urls = {
        "repository_url": f"https://github.com/{local}/{slug}",
        "deployment_url": f"https://{local}-{slug}.onrender.com",
    }
    notes = _draw(PROJECT_NOTES, "notes", spec.key, email)
    draw = _seed("project-marks", spec.key, email)

    def submit() -> None:
        submit_project(work=work, actor=user, notes=notes, **urls)

    def rework() -> None:
        review_project(
            work=work,
            actor=reviewer,
            outcome=WorkStatus.REWORK,
            feedback=_draw(PROJECT_FEEDBACK_REWORK, "rework", email),
        )

    def approve() -> None:
        feedback = _draw(PROJECT_FEEDBACK_APPROVED, "approved", email)
        if project.rubric:
            scores = {
                item["key"]: int(item["max_marks"]) * draw.randint(55, 100) // 100
                for item in project.rubric
            }
            review_project(
                work=work,
                actor=reviewer,
                outcome=WorkStatus.APPROVED,
                rubric_scores=scores,
                feedback=feedback,
            )
        else:
            marks = (project.max_marks * draw.randint(55, 98) / 100).quantize(Decimal("1"))
            review_project(
                work=work,
                actor=reviewer,
                outcome=WorkStatus.APPROVED,
                marks=marks,
                feedback=feedback,
            )

    if target == "in_progress":
        save_progress(work=work, actor=user, notes=notes, repository_url=urls["repository_url"])
    elif target == "submitted":
        submit()
    elif target == "under_review":
        submit()
        review_project(work=work, actor=reviewer, outcome=WorkStatus.UNDER_REVIEW)
    elif target == "rework":
        submit()
        rework()
    elif target == "rework_resubmitted":
        submit()
        rework()
        submit()
        approve()
    elif target == "approved":
        submit()
        approve()
    elif target == "completed":
        submit()
        approve()
        review_project(work=work, actor=reviewer, outcome=WorkStatus.COMPLETED)
    ctx.created(f"project_{target}")

    # Dates: handed in a few days before the due date (or after it, when
    # late), reviewed a few days on; never ahead of the clock.
    work.refresh_from_db()
    if work.submitted_at is None:
        return
    due = ctx.at(project.end_date, 18, 0)
    if late:
        when = due + timedelta(days=draw.randint(1, 4))
    else:
        when = due - timedelta(days=draw.randint(1, 12), hours=draw.randint(0, 9))
    start = ctx.at(project.start_date, 9, 0) if project.start_date else when
    when = max(min(when, ctx.now - timedelta(hours=1)), start)
    fields: dict[str, Any] = {"submitted_at": when, "is_late": late}
    if work.reviewed_at is not None:
        fields["reviewed_at"] = min(when + timedelta(days=draw.randint(1, 3)), ctx.now)
    ctx.backdate(work, **fields)


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------


def _ensure_exams(ctx: Context, scope: Scope) -> None:
    for spec in EXAMS:
        batch = scope.by_spec.get(spec.batch)
        if batch is None:
            ctx.out(f"exam {spec.key}: batch not on this database, skipped")
            continue
        actor = _grader(ctx, batch)
        exam, created = _ensure_exam(ctx, spec, batch, actor)
        if spec.attempts:
            _ensure_attempts(ctx, scope, spec, exam, batch, actor, created)


def _ensure_exam(ctx: Context, spec: ExamSpec, batch: Batch, actor: User) -> tuple[Exam, bool]:
    existing = Exam.objects.filter(batch=batch, title=spec.title).first()
    if existing is not None:
        ctx.found_existing("exam")
        ctx.out(f"exam {spec.key}: found")
        return existing, False

    # A closed exam is created with a window that is open — the attempts need
    # one they can start in — and moved into the past through `update_exam`
    # once they are in (`_ensure_attempts`).
    opens = _at(ctx, spec.opens, 9, 0)
    closes = _at(ctx, spec.closes, 18, 0)
    if spec.status == ExamStatus.CLOSED:
        closes = ctx.now + timedelta(hours=3)
    exam = create_exam(
        actor=actor,
        batch=batch,
        title=spec.title,
        description=spec.description,
        instructions="Answer every question. Unanswered questions score zero; there is no "
        "negative marking. Your answers are saved as you go.",
        opens_at=opens,
        closes_at=closes,
        duration_minutes=spec.duration,
        max_attempts=spec.max_attempts,
        sections=[dict(section) for section in spec.sections],
    )
    if spec.status == ExamStatus.DRAFT:
        readiness = check_readiness(exam)
        ctx.out(
            f"exam {spec.key}: draft, ready={readiness['ready']}: "
            + "; ".join(readiness["problems"])
        )
    else:
        set_exam_status(exam=exam, actor=actor, status=ExamStatus.PUBLISHED)
    fields: dict[str, Any] = {"created_at": min(opens - timedelta(days=5), ctx.now)}
    if exam.published_at is not None:
        fields["published_at"] = min(opens - timedelta(days=2), ctx.now)
    ctx.backdate(exam, **fields)
    ctx.created("exam")
    ctx.out(f"exam {spec.key}: created ({spec.status})")
    return exam, True


def _ensure_attempts(
    ctx: Context,
    scope: Scope,
    spec: ExamSpec,
    exam: Exam,
    batch: Batch,
    actor: User,
    fresh: bool,
) -> None:
    cohort = [row for row in _cohort(scope, batch) if row.status != EnrollmentStatus.SUSPENDED]
    ordered = _ordered(scope, cohort, "sit-order", spec.key)
    headline = [row for row in ordered if row.student.user == scope.headline]
    others = [row for row in ordered if row.student.user != scope.headline]
    plan: list[tuple[Enrollment, str]] = []
    for target in spec.attempts:
        if target == "headline":
            if headline:
                plan.append((headline[0], target))
        elif others:
            plan.append((others.pop(0), target))

    created = found = 0
    for row, target in plan:
        sat = ExamAttempt.objects.filter(exam=exam, enrollment=row)
        latest = sat.order_by("-attempt_number").first()
        if latest is not None:
            live = latest.status == AttemptStatus.IN_PROGRESS and not latest.has_expired
            if target != "headline" or live or sat.count() >= exam.max_attempts or not exam.is_open:
                found += 1
                continue
            # The headline attempt went stale on a later day: start a new one,
            # so "mid-attempt" stays true — see the module docstring.
        if not exam.is_open:
            continue
        _sit(ctx, spec, exam, row, actor, target)
        created += 1
    ctx.created("exam_attempt", created)
    ctx.found_existing("exam_attempt", found)
    if created:
        ctx.out(f"attempts {spec.key}: {created} sat, {found} found")

    if fresh and spec.all_graded:
        publish_results(exam=exam, actor=actor)
        ctx.created("exam_results_published")
        set_exam_status(exam=exam, actor=actor, status=ExamStatus.CLOSED)
        if spec.window:
            opens, closes = _at(ctx, spec.window[0], 9, 0), _at(ctx, spec.window[1], 18, 0)
            update_exam(exam=exam, actor=actor, opens_at=opens, closes_at=closes)
            ctx.backdate(
                exam,
                created_at=opens - timedelta(days=5),
                published_at=opens - timedelta(days=2),
                results_published_at=closes + timedelta(days=2),
            )
            for attempt in exam.attempts.select_related("enrollment__student__user"):
                draw = _seed("sat-at", spec.key, attempt.enrollment.student.user.email)
                started = opens + timedelta(hours=draw.randint(1, 60))
                started = min(started, closes - timedelta(minutes=exam.duration_minutes))
                finished = started + timedelta(minutes=draw.randint(25, exam.duration_minutes - 1))
                ctx.backdate(
                    attempt,
                    created_at=started,
                    started_at=started,
                    expires_at=started + timedelta(minutes=exam.duration_minutes),
                    submitted_at=finished,
                    graded_at=closes + timedelta(days=1, hours=draw.randint(0, 8)),
                )


def _sit(
    ctx: Context, spec: ExamSpec, exam: Exam, row: Enrollment, marker: User, target: str
) -> None:
    """One candidate's sitting, to the state asked for."""
    user = row.student.user
    email = user.email
    attempt = start_attempt(exam=exam, enrollment=row, actor=user)
    questions = list(
        attempt.questions.select_related("question")
        .prefetch_related("question__options")
        .order_by("position")
    )
    accuracy = 0.45 + _chance("accuracy", email) * 0.5
    draw = _seed("answers", spec.key, email)
    answered = questions
    if target == "headline":
        answered = questions[: max(1, len(questions) // 2)]
    elif target == "expired":
        answered = questions[: max(1, len(questions) // 3)]

    for attempt_question in answered:
        question = attempt_question.question
        kind = question.question_type
        options = list(question.options.all())
        correct = draw.random() < accuracy
        answer: dict[str, Any] = {}
        if kind in (QuestionType.MCQ, QuestionType.TRUE_FALSE):
            pool = [o for o in options if o.is_correct == correct] or options
            answer["selected_options"] = [str(draw.choice(pool).pk)]
        elif kind == QuestionType.MULTIPLE:
            right = [str(o.pk) for o in options if o.is_correct]
            wrong = [str(o.pk) for o in options if not o.is_correct]
            answer["selected_options"] = right if correct or not wrong else right[:-1] + wrong[:1]
        elif kind == QuestionType.SHORT_ANSWER:
            keys = list(question.answer_key or [])
            answer["text_answer"] = keys[0] if (correct and keys) else "not sure"
        else:
            answer["text_answer"] = _draw(LONG_ANSWERS, "long", spec.key, email)
        save_answer(attempt=attempt, attempt_question=attempt_question, actor=user, **answer)

    if target == "headline":
        return
    if target == "expired":
        started = ctx.at(ctx.days_ago(1), 10, 0)
        ctx.backdate(
            attempt,
            created_at=started,
            started_at=started,
            expires_at=started + timedelta(minutes=exam.duration_minutes),
        )
        return

    attempt = submit_attempt(attempt=attempt, actor=user)
    if target == "graded" and attempt.status == AttemptStatus.SUBMITTED:
        pending = AttemptAnswer.objects.filter(
            attempt_question__attempt=attempt, needs_manual_marking=True, awarded__isnull=True
        ).select_related("attempt_question")
        for answer_row in pending:
            worth = answer_row.attempt_question.marks
            share = Decimal(draw.choice((100, 80, 60, 40, 20))) / 100
            mark_written_answer(
                answer=answer_row,
                actor=marker,
                awarded=(worth * share).quantize(Decimal("0.5")),
                feedback=_draw(MARKER_FEEDBACK, "marker", spec.key, email),
            )
            ctx.created("exam_answer_marked")
    if spec.status == ExamStatus.CLOSED:
        return  # dated in bulk once the window has moved
    # On the open exam the sitting happened earlier today or yesterday.
    started = ctx.now - timedelta(hours=draw.randint(3, 30))
    started = max(started, exam.opens_at or started)
    finished = started + timedelta(minutes=draw.randint(20, exam.duration_minutes - 1))
    attempt.refresh_from_db()
    fields: dict[str, Any] = {
        "created_at": started,
        "started_at": started,
        "expires_at": started + timedelta(minutes=exam.duration_minutes),
        "submitted_at": finished,
    }
    if attempt.graded_at is not None:
        fields["graded_at"] = min(finished + timedelta(hours=draw.randint(2, 20)), ctx.now)
    ctx.backdate(attempt, **fields)


# ---------------------------------------------------------------------------
# Completions and certificates — the showcase cohorts
# ---------------------------------------------------------------------------


def _ensure_template(ctx: Context) -> CertificateTemplate:
    existing = CertificateTemplate.objects.filter(name=TEMPLATE_NAME).first()
    if existing is not None:
        ctx.found_existing("certificate_template")
        ctx.out("certificate template: found")
        return existing
    template = save_template(
        actor=ctx.superadmin,
        name=TEMPLATE_NAME,
        is_default=True,
        institution_name="Grras Solutions",
        title="Certificate of Completion",
        body=(
            "This is to certify that {student_name} has successfully completed the course "
            "{course_title} (batch {batch_code}) at {institution_name} on {completion_date}. "
            "Certificate number {certificate_number}."
        ),
        signatory_name="Rajesh Sharma",
        signatory_title="Director, Grras Solutions",
        footer="Verify this certificate at grras.com/verify with the code on the QR.",
    )
    ctx.backdate(template, created_at=ctx.at(ctx.weeks_ago(52), 10, 0))
    ctx.created("certificate_template")
    ctx.out("certificate template: created")
    return template


def _ensure_completions(ctx: Context, scope: Scope, template: CertificateTemplate) -> None:
    # Every showcase cohort enrolment gets its eligibility computed, so the
    # completions screen has an in_progress row per student.
    refreshed = found = 0
    for batch in scope.by_spec.values():
        admin = ctx.actor_for(batch.branch.code)
        for row in _cohort(scope, batch):
            existed = CourseCompletion.objects.filter(enrollment=row).exists()
            refresh_completion(enrollment=row, actor=admin)
            if existed:
                found += 1
            else:
                refreshed += 1
    ctx.created("completion", refreshed)
    ctx.found_existing("completion", found)
    ctx.out(f"completions refreshed: {refreshed} new, {found} found")

    for spec_key, (mode, rejects, reissue) in COMPLETION_PLAN.items():
        batch = scope.by_spec.get(spec_key)
        if batch is None:
            continue
        _decide_cohort(ctx, scope, batch, template, mode=mode, rejects=rejects, reissue=reissue)


def _decide_cohort(
    ctx: Context,
    scope: Scope,
    batch: Batch,
    template: CertificateTemplate,
    *,
    mode: str,
    rejects: int,
    reissue: bool,
) -> None:
    """Approve (and certify) one finished cohort, reject a few, leave the
    rest where the rules put them."""
    admin = ctx.actor_for(batch.branch.code)
    cohort = _cohort(scope, batch)
    completions = {
        c.enrollment_id: c for c in CourseCompletion.objects.filter(enrollment__in=cohort)
    }
    ordered = _ordered(scope, cohort, "decide", batch.name)
    others = [row for row in ordered if row.student.user != scope.headline]

    reject_set = {row.pk for row in others[:rejects]}
    queue: set = set()
    if mode == "rules":
        # Those the rules let through — still eligible, or approved on an
        # earlier run — in seeded order; the last few stay in the queue, and
        # a re-run picks the same few because approvals do not change the
        # membership of this list.
        through = [
            row
            for row in others
            if completions[row.pk].status in (CompletionStatus.ELIGIBLE, CompletionStatus.APPROVED)
        ]
        if len(through) > QUEUE_LEFT:
            queue = {row.pk for row in through[-QUEUE_LEFT:]}

    end = ctx.at(batch.end_date, 17, 0)
    approved: list[CourseCompletion] = []
    created = found = 0
    for row in ordered:
        completion = completions[row.pk]
        if completion.is_decided:
            found += 1
            if completion.status == CompletionStatus.APPROVED:
                approved.append(completion)
            continue
        if row.pk in reject_set:
            completion = reject_completion(
                enrollment=row,
                actor=admin,
                note=ctx.note(
                    "Attendance below the 80% the RHCSA track requires; to re-sit the labs "
                    "with the next cohort."
                ),
            )
            ctx.created("completion_rejected")
            ctx.backdate(completion, decided_at=end + timedelta(days=4, hours=2))
            created += 1
            continue
        if row.pk in queue:
            continue
        if mode == "rules" and completion.status != CompletionStatus.ELIGIBLE:
            continue
        completion = approve_completion(
            enrollment=row,
            actor=admin,
            completed_on=batch.end_date,
            note=ctx.note("Approved at the end-of-batch review."),
            override=mode == "override",
        )
        ctx.created("completion_approved")
        fields: dict[str, Any] = {"decided_at": end + timedelta(days=3, hours=2)}
        if completion.became_eligible_at is not None:
            fields["became_eligible_at"] = end + timedelta(days=1)
        ctx.backdate(completion, **fields)
        approved.append(completion)
        created += 1
    ctx.out(
        f"completions {batch.code}: {created} decided, {found} found "
        f"({len(queue)} left in the queue)"
    )
    _ensure_certificates(
        ctx, batch, approved, admin, template, reissue=int(reissue), revoke=int(reissue)
    )


def _ensure_certificates(
    ctx: Context,
    batch: Batch,
    approved: list[CourseCompletion],
    admin: User,
    template: CertificateTemplate,
    *,
    reissue: int,
    revoke: int,
    share: float = 1.0,
) -> None:
    """Issue for the approved completions (or a share of them), then reissue
    and revoke a few — the headline student's is never the one revoked."""
    end = ctx.at(batch.end_date, 11, 0)
    ordered = sorted(approved, key=lambda c: _chance("cert", batch.name, c.enrollment_id))
    if share < 1.0:
        ordered = ordered[: max(1, round(len(ordered) * share))]
    issued: list[Certificate] = []
    created = found = 0
    for completion in ordered:
        live = completion.certificates.filter(status=CertificateStatus.ISSUED).first()
        if live is not None or completion.certificates.exists():
            found += 1
            if live is not None:
                issued.append(live)
            continue
        certificate = issue_certificate(completion=completion, actor=admin, template=template)
        when = end + timedelta(days=5, hours=created % 6)
        ctx.backdate(certificate, issued_at=when, created_at=when)
        issued.append(certificate)
        created += 1
    ctx.created("certificate", created)
    ctx.found_existing("certificate", found)
    if created:
        ctx.out(f"certificates {batch.code}: {created} issued, {found} found")

    # Reissue the first few (a corrected name), revoke the next few — keyed
    # by state on the cohort: a revoked certificate is no longer live, so
    # `issued` would not list it on a re-run, and picking "the next live one"
    # again would revoke a second student's. Once the cohort holds one
    # superseded (revoked) certificate, that is the reissue (revocation).
    cohort = Certificate.objects.filter(completion__in=approved)
    reissued = revoked = 0
    if reissue:
        if cohort.filter(status=CertificateStatus.SUPERSEDED).exists():
            ctx.found_existing("certificate_reissued")
        else:
            for certificate in issued[:reissue]:
                replacement = reissue_certificate(
                    certificate=certificate,
                    actor=admin,
                    reason=ctx.note("Name corrected to match the student's ID document."),
                )
                when = end + timedelta(days=9)
                ctx.backdate(replacement, issued_at=when, created_at=when)
                ctx.created("certificate_reissued")
                reissued += 1
    if revoke:
        if cohort.filter(status=CertificateStatus.REVOKED).exists():
            ctx.found_existing("certificate_revoked")
        else:
            candidates = [
                c
                for c in issued[reissue:]
                if c.completion.enrollment.student.user.email != f"student@{DOMAIN}"
            ]
            for certificate in candidates[:revoke]:
                revoke_certificate(
                    certificate=certificate,
                    actor=admin,
                    reason=ctx.note(
                        "Issued against the wrong batch; a corrected certificate follows."
                    ),
                )
                ctx.backdate(certificate, revoked_at=end + timedelta(days=12))
                ctx.created("certificate_revoked")
                revoked += 1
    if reissued or revoked:
        ctx.out(f"certificates {batch.code}: {reissued} reissued, {revoked} revoked")


# ---------------------------------------------------------------------------
# The SITP part: the twelve finished summer batches
# ---------------------------------------------------------------------------


def _ensure_sitp(ctx: Context, template: CertificateTemplate) -> None:
    if not ctx.imported_batches:
        ctx.out("imported batches: none on this database")
        return
    finished = sorted(
        (b for b in ctx.imported_batches.values() if b.status == BatchStatus.COMPLETED),
        key=lambda b: b.name,
    )
    if not finished:
        ctx.out("imported batches: none completed")
        return

    started = perf_counter()
    refreshed = found = 0
    cohorts: dict[Any, list[Enrollment]] = {}
    for batch in finished:
        # `ctx.live_enrolments` is for the running batches (pending/active/
        # suspended); a finished batch's students are its completed rows.
        rows = list(
            Enrollment.objects.filter(batch=batch, status=EnrollmentStatus.COMPLETED)
            .select_related("student__user", "batch__course", "batch__branch", "course")
            .order_by("student__user__email")
        )
        cohorts[batch.pk] = rows
        admin = ctx.actor_for(batch.branch.code)
        end = ctx.at(batch.end_date, 17, 0)
        for row in rows:
            existed = CourseCompletion.objects.filter(enrollment=row).exists()
            completion = refresh_completion(enrollment=row, actor=admin)
            if existed:
                found += 1
                continue
            refreshed += 1
            fields: dict[str, Any] = {"created_at": end + timedelta(days=1)}
            if completion.became_eligible_at is not None:
                fields["became_eligible_at"] = end + timedelta(days=1)
            ctx.backdate(completion, **fields)
    ctx.created("sitp_completion", refreshed)
    ctx.found_existing("sitp_completion", found)
    ctx.out(
        f"{STAGE}/sitp refresh: {refreshed} new, {found} found across {len(finished)} batches, "
        f"{perf_counter() - started:.1f}s"
    )

    for index, batch in enumerate(finished):
        rows = cohorts[batch.pk]
        if not rows:
            continue
        admin = ctx.actor_for(batch.branch.code)
        end = ctx.at(batch.end_date, 17, 0)
        completions = {
            c.enrollment_id: c for c in CourseCompletion.objects.filter(enrollment__in=rows)
        }
        ordered = sorted(rows, key=lambda row: _chance("sitp", batch.name, row.student.user.email))
        n_approve = max(1, round(len(ordered) * SITP_APPROVE_SHARE))
        to_approve = ordered[:n_approve]
        to_reject = ordered[n_approve : n_approve + 1] if index < SITP_REJECTS else []

        approved: list[CourseCompletion] = []
        created = decided_found = 0
        for row in to_approve:
            completion = completions[row.pk]
            if completion.is_decided:
                decided_found += 1
                if completion.status == CompletionStatus.APPROVED:
                    approved.append(completion)
                continue
            completion = approve_completion(
                enrollment=row,
                actor=admin,
                completed_on=batch.end_date,
                note=ctx.note("Approved at the SITP closing review."),
                override=True,
            )
            ctx.backdate(completion, decided_at=end + timedelta(days=3, hours=2))
            approved.append(completion)
            created += 1
        for row in to_reject:
            completion = completions[row.pk]
            if completion.is_decided:
                decided_found += 1
                continue
            completion = reject_completion(
                enrollment=row,
                actor=admin,
                note=ctx.note("Final project not submitted by the closing date."),
            )
            ctx.backdate(completion, decided_at=end + timedelta(days=4))
            ctx.created("sitp_completion_rejected")
        ctx.created("sitp_completion_approved", created)
        ctx.found_existing("sitp_completion_approved", decided_found)
        _ensure_certificates(
            ctx,
            batch,
            approved,
            admin,
            template,
            reissue=1 if index < SITP_REISSUES else 0,
            revoke=1 if SITP_REISSUES <= index < SITP_REISSUES + SITP_REVOKES else 0,
            share=SITP_CERTIFICATE_SHARE,
        )
    ctx.out(f"{STAGE}/sitp decisions: {perf_counter() - started:.1f}s in all")


# ---------------------------------------------------------------------------
# One risk recompute per student, not one per mark
# ---------------------------------------------------------------------------


def _claim_recomputes(scope: Scope) -> None:
    """Hold the debounce key for every student a grade or result may touch,
    so the services' own on-commit callbacks find a recompute "already
    pending" and stand down."""
    for enrollment_id in scope.claimed:
        cache.add(_pending_key(enrollment_id), True, CLAIM_SECONDS)


def _release_recomputes(ctx: Context, scope: Scope) -> None:
    """Registered last, so it runs after every service's own callback: let go
    of each claim and schedule the one recompute the claim promised."""
    ids = sorted(scope.claimed, key=str)

    def _release() -> None:
        started = perf_counter()
        for enrollment_id in ids:
            cache.delete(_pending_key(enrollment_id))
            risk_tasks.schedule_recompute(enrollment_id)
        ctx.out(f"{STAGE}/risk recomputes: {len(ids)} scheduled, {perf_counter() - started:.1f}s")

    transaction.on_commit(_release)


def _pending_key(enrollment_id: Any) -> str:
    # The task module's key format is the contract the debounce is built on;
    # naming it here rather than copying the string keeps the two in step.
    return risk_tasks._PENDING_KEY.format(enrollment_id=enrollment_id)


__all__ = ["ASSESSMENTS", "ASSIGNMENTS", "COMPLETION_PLAN", "EXAMS", "PROJECTS", "run"]
