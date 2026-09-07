"""A centre is a wall, and these tests push on every brick of it.

The property under defence is one sentence: **no query issued on behalf of a
branch-scoped caller may return a row belonging to another centre.** The failure
this guards against is not a crash. It is a manager in Jaipur opening the
student list and seeing Pune's admissions — a screen that looks entirely normal
and is a data breach, discovered months later by whoever notices the totals do
not match.

`apps.organisation.scoping` is one small module that sixteen access modules
call, so the same mistake made once is made everywhere. That is a virtue for
correctness and a hazard for testing: a suite that proves the seam and stops
would pass with the seam wired into nothing. So this module asserts the seam
*through* each access function it is supposed to have been wired into, one test
per function, named after the function. Delete a `scope_to_branch` call anywhere
and a test named for that call fails.

Four questions are asked of every function, because three of them pass on a
broken system:

1. a bounded caller sees their own centre's rows — a filter that returns nothing
   is not a scoped filter, it is a broken one;
2. a bounded caller does **not** see the other centre's rows;
3. a platform operator sees both, so the rule has not simply been "deny";
4. a caller carrying **no** centre sees nothing — the fail-closed rule, and the
   one a null column reads as "everything" if anybody ever collapses
   `is_unbounded` and `actor_branch_id` back into a single question.

Anonymous and inactive callers get their own banner. They reach these helpers
because `scope_to_branch` is called on the capability-holder branch, *above* the
authenticated guard by convention — so `AttributeError` on `AnonymousUser` is a
live failure mode, not a hypothetical one.

The endpoint half of this — 404s on ids from the other centre, exports,
downloads, the recycle bin, dashboards, filters and pagination — is
`tests/test_branch_scoping_api.py`.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.accounts.models import User, UserRole

TEST_PASSWORD = "correct-horse-battery-staple"


# ---------------------------------------------------------------------------
# Fixtures — two centres, each complete enough to be leaked
# ---------------------------------------------------------------------------
#
# Centre A is the default fixture set from `conftest.py` (branch MAIN): its
# manager, counsellor, admin, trainer, student, batch and enrolment. Centre B is
# the `other_branch_*` set (branch PUNE). Everything below fills in the people
# and academic records those two sets do not already carry, on both sides, so
# that "sees A, not B" is a claim about two populated worlds rather than about
# one world and an empty space.


@pytest.fixture
def counsellor_b(other_branch) -> User:
    """A counsellor at the second centre."""
    return User.objects.create_user(
        email="counsellor@pune.example.test",
        password=TEST_PASSWORD,
        first_name="Chandni",
        last_name="Pune",
        role=UserRole.COUNSELLOR,
        branch=other_branch,
    )


@pytest.fixture
def admin_b(other_branch) -> User:
    """An administrator at the second centre — bounded, per D-127."""
    return User.objects.create_user(
        email="admin@pune.example.test",
        password=TEST_PASSWORD,
        first_name="Anil",
        last_name="Pune",
        role=UserRole.ADMIN,
        branch=other_branch,
        is_staff=True,
    )


@pytest.fixture
def branchless_manager(db) -> User:
    """A manager stamped with no centre at all.

    The account the Django admin's add form, a fixture load, or a half-finished
    migration produces. Under the fail-closed rule they see nothing; under the
    bug this whole module exists to prevent, they would see everything.
    """
    return User.objects.create_user(
        email="nobranch.manager@example.test",
        password=TEST_PASSWORD,
        first_name="Nadia",
        last_name="Nowhere",
        role=UserRole.MANAGER,
        branch=None,
    )


@pytest.fixture
def branchless_admin(db) -> User:
    """An administrator with no centre. Not a superadmin, so not unbounded."""
    return User.objects.create_user(
        email="nobranch.admin@example.test",
        password=TEST_PASSWORD,
        first_name="Nilesh",
        last_name="Nowhere",
        role=UserRole.ADMIN,
        branch=None,
        is_staff=True,
    )


@pytest.fixture
def inactive_manager(branch) -> User:
    """A manager at centre A whose account has been switched off."""
    return User.objects.create_user(
        email="former.manager@example.test",
        password=TEST_PASSWORD,
        first_name="Farah",
        last_name="Former",
        role=UserRole.MANAGER,
        branch=branch,
        is_active=False,
    )


@pytest.fixture
def session_a(admin_user, batch):
    """A finished class at centre A, so there is something to report on."""
    from apps.sessions.services import create_session

    return create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Filesystem basics",
    )


@pytest.fixture
def session_b(unbounded_superadmin, other_branch_batch):
    """The same class, at centre B."""
    from apps.sessions.services import create_session

    return create_session(
        batch=other_branch_batch,
        actor=unbounded_superadmin,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Cabling",
    )


@pytest.fixture
def dsr_a(admin_user, session_a):
    from apps.dsr.services import start_dsr

    return start_dsr(session=session_a, actor=admin_user)


@pytest.fixture
def dsr_b(unbounded_superadmin, session_b):
    from apps.dsr.services import start_dsr

    return start_dsr(session=session_b, actor=unbounded_superadmin)


@pytest.fixture
def assessment_a(admin_user, batch):
    from apps.assessments.models import AssessmentDelivery
    from apps.assessments.services import create_assessment

    return create_assessment(
        actor=admin_user,
        batch=batch,
        title="Week 1 — Jaipur",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )


@pytest.fixture
def assessment_b(unbounded_superadmin, other_branch_batch):
    from apps.assessments.models import AssessmentDelivery
    from apps.assessments.services import create_assessment

    return create_assessment(
        actor=unbounded_superadmin,
        batch=other_branch_batch,
        title="Week 1 — Pune",
        delivery=AssessmentDelivery.OFFLINE,
        max_marks=Decimal("20.00"),
    )


@pytest.fixture
def result_a(assessment_a, enrollment):
    """A mark, written straight to the model.

    `record_result` would do the same thing through three more layers; what is
    under test here is which marks a queryset returns, not how a mark is
    recorded.
    """
    from apps.assessments.models import AssessmentResult

    return AssessmentResult.objects.create(
        assessment=assessment_a,
        enrollment=enrollment,
        marks_obtained=Decimal("15.00"),
        recorded_at=timezone.now(),
    )


@pytest.fixture
def result_b(assessment_b, other_branch_enrollment):
    from apps.assessments.models import AssessmentResult

    return AssessmentResult.objects.create(
        assessment=assessment_b,
        enrollment=other_branch_enrollment,
        marks_obtained=Decimal("18.00"),
        recorded_at=timezone.now(),
    )


@pytest.fixture
def assignment_a(admin_user, published_course, batch):
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Jaipur exercise",
        instructions="Write a script.",
    )


@pytest.fixture
def assignment_b(unbounded_superadmin, published_course, other_branch_batch):
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=unbounded_superadmin,
        course=published_course,
        batch=other_branch_batch,
        title="Pune exercise",
        instructions="Write a script.",
    )


@pytest.fixture
def course_wide_assignment(admin_user, published_course):
    """An assignment set for the course rather than for one class.

    `batch` is null, which is what makes it everybody's — and what a plain
    `filter(batch__branch_id=...)` would silently drop, because a join through
    a nullable foreign key is an INNER JOIN. This fixture is the one that turns
    that into a failing test rather than a quiet disappearance.
    """
    from apps.assignments.services import create_assignment

    return create_assignment(
        actor=admin_user,
        course=published_course,
        title="Set for every class on the course",
        instructions="Read chapter one.",
    )


@pytest.fixture
def submission_a(assignment_a, enrollment):
    from apps.assignments.models import AssignmentSubmission

    return AssignmentSubmission.objects.create(
        assignment=assignment_a, enrollment=enrollment, text_answer="Jaipur answer"
    )


@pytest.fixture
def submission_b(assignment_b, other_branch_enrollment):
    from apps.assignments.models import AssignmentSubmission

    return AssignmentSubmission.objects.create(
        assignment=assignment_b, enrollment=other_branch_enrollment, text_answer="Pune answer"
    )


@pytest.fixture
def exam_a(admin_user, batch):
    from apps.exams.services import create_exam

    return create_exam(actor=admin_user, batch=batch, title="Jaipur final")


@pytest.fixture
def exam_b(unbounded_superadmin, other_branch_batch):
    from apps.exams.services import create_exam

    return create_exam(actor=unbounded_superadmin, batch=other_branch_batch, title="Pune final")


@pytest.fixture
def attempt_a(exam_a, enrollment):
    from apps.exams.models import ExamAttempt

    return ExamAttempt.objects.create(
        exam=exam_a, enrollment=enrollment, expires_at=timezone.now() + timedelta(hours=1)
    )


@pytest.fixture
def attempt_b(exam_b, other_branch_enrollment):
    from apps.exams.models import ExamAttempt

    return ExamAttempt.objects.create(
        exam=exam_b,
        enrollment=other_branch_enrollment,
        expires_at=timezone.now() + timedelta(hours=1),
    )


@pytest.fixture
def project_a(admin_user, published_course, batch):
    from apps.projects.services import create_project

    return create_project(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Jaipur project",
        description="A tool.",
        instructions="Build it.",
        deliverables="Source.",
    )


@pytest.fixture
def project_b(unbounded_superadmin, published_course, other_branch_batch):
    from apps.projects.services import create_project

    return create_project(
        actor=unbounded_superadmin,
        course=published_course,
        batch=other_branch_batch,
        title="Pune project",
        description="A tool.",
        instructions="Build it.",
        deliverables="Source.",
    )


@pytest.fixture
def course_wide_project(admin_user, published_course):
    """A project set for the course, belonging to no class. See
    `course_wide_assignment` for why this fixture earns its place."""
    from apps.projects.services import create_project

    return create_project(
        actor=admin_user,
        course=published_course,
        title="Set for every class on the course",
        description="A tool.",
        instructions="Build it.",
        deliverables="Source.",
    )


@pytest.fixture
def student_project_a(project_a, enrollment):
    from apps.projects.models import StudentProject

    return StudentProject.objects.create(project=project_a, enrollment=enrollment)


@pytest.fixture
def student_project_b(project_b, other_branch_enrollment):
    from apps.projects.models import StudentProject

    return StudentProject.objects.create(project=project_b, enrollment=other_branch_enrollment)


@pytest.fixture
def announcement_a(admin_user, batch):
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=admin_user,
        title="Jaipur lab closed",
        body="The lab is closed on Friday.",
        audience=Audience.BATCH,
        batch=batch,
        course=batch.course,
    )
    return publish(announcement=created, actor=admin_user)


@pytest.fixture
def announcement_b(unbounded_superadmin, other_branch_batch):
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=unbounded_superadmin,
        title="Pune lab closed",
        body="The lab is closed on Friday.",
        audience=Audience.BATCH,
        batch=other_branch_batch,
        course=other_branch_batch.course,
    )
    return publish(announcement=created, actor=unbounded_superadmin)


@pytest.fixture
def private_announcement_b(other_branch_manager, other_branch_student):
    """A notice the second centre addressed to named people.

    `audience='selected'` carries no batch — the model's own
    `announcement_audience_matches_target` constraint requires that — so this is
    the row that a nullable-batch reading classifies as institution-wide. The
    two `announcement_*` fixtures above are both batch notices, which is exactly
    why nothing here noticed.
    """
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=other_branch_manager,
        title="Pune: fee default follow-up",
        body="Ring these two families about arrears before Friday.",
        audience=Audience.SELECTED,
        recipients=[other_branch_student.user],
    )
    return publish(announcement=created, actor=other_branch_manager)


@pytest.fixture
def course_announcement_b(other_branch_manager, published_course):
    """A notice the second centre set for a whole course. Also batch-less."""
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=other_branch_manager,
        title="Pune: Linux intake rescheduled",
        body="The Pune sitting moves to the 14th.",
        audience=Audience.COURSE,
        course=published_course,
    )
    return publish(announcement=created, actor=other_branch_manager)


@pytest.fixture
def orphaned_announcement_b(other_branch_manager, published_course):
    """A batch-less notice from the other centre whose author has since gone.

    `created_by` is SET_NULL, so this row's centre is unknowable. It belongs to
    nobody, not to everybody — the same reading an orphaned export job gets.
    """
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=other_branch_manager,
        title="Pune: author has left",
        body="Nobody owns this any more.",
        audience=Audience.COURSE,
        course=published_course,
    )
    published = publish(announcement=created, actor=other_branch_manager)
    other_branch_manager.delete()
    published.refresh_from_db()
    return published


@pytest.fixture
def institution_wide_announcement(admin_user):
    """Addressed to everyone, so it belongs to no batch and no centre."""
    from apps.announcements.models import Audience
    from apps.announcements.services import create_announcement, publish

    created = create_announcement(
        actor=admin_user,
        title="Holiday on Monday",
        body="Every centre is closed.",
        audience=Audience.EVERYONE,
    )
    return publish(announcement=created, actor=admin_user)


@pytest.fixture
def review_a(unbounded_superadmin, student_profile):
    """A performance review about a student at centre A."""
    from apps.performance.services import create_review

    today = timezone.localdate()
    return create_review(
        actor=unbounded_superadmin,
        student=student_profile,
        period_start=today - timedelta(days=30),
        period_end=today,
        rating=4,
        summary="Doing well.",
    )


@pytest.fixture
def review_b(unbounded_superadmin, other_branch_student):
    """The same, about a student at centre B."""
    from apps.performance.services import create_review

    today = timezone.localdate()
    return create_review(
        actor=unbounded_superadmin,
        student=other_branch_student,
        period_start=today - timedelta(days=30),
        period_end=today,
        rating=3,
        summary="Doing well.",
    )


@pytest.fixture
def trainer_review_b(unbounded_superadmin, other_branch_trainer):
    """A review about a *trainer* at centre B.

    The trainer subject is the other half of `scope_by_subject`'s `OR`, and a
    rule written only against `student__branch_id` would pass every test above
    while leaking this one.
    """
    from apps.performance.services import create_review

    today = timezone.localdate()
    return create_review(
        actor=unbounded_superadmin,
        trainer=other_branch_trainer,
        period_start=today - timedelta(days=30),
        period_end=today,
        rating=4,
        summary="Reliable.",
    )


@pytest.fixture
def feedback_a(unbounded_superadmin, student_profile, batch):
    from apps.performance.services import create_feedback

    return create_feedback(
        actor=unbounded_superadmin,
        student=student_profile,
        batch=batch,
        body="Asked a good question in class.",
    )


@pytest.fixture
def feedback_b(unbounded_superadmin, other_branch_student, other_branch_batch):
    from apps.performance.services import create_feedback

    return create_feedback(
        actor=unbounded_superadmin,
        student=other_branch_student,
        batch=other_branch_batch,
        body="Asked a good question in class.",
    )


@pytest.fixture
def trainer_feedback_b(unbounded_superadmin, other_branch_trainer):
    from apps.performance.services import create_feedback

    return create_feedback(
        actor=unbounded_superadmin,
        trainer=other_branch_trainer,
        body="Handled a difficult class well.",
    )


@pytest.fixture
def bulk_import_a(manager_user):
    """A pending admissions spreadsheet at centre A."""
    from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind

    return BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=manager_user,
        original_filename="jaipur-intake.csv",
        status=BulkImportStatus.PREVIEW,
        report={"rows": [], "errors": [], "summary": {"read": 0, "valid": 0, "errors": 0}},
    )


@pytest.fixture
def bulk_import_b(other_branch_manager):
    """The same at centre B. Its `report` is the parsed file — names, addresses
    and phone numbers of people who are not students anywhere yet."""
    from apps.reporting.models import BulkImport, BulkImportStatus, ImportKind

    return BulkImport.objects.create(
        kind=ImportKind.STUDENTS,
        uploaded_by=other_branch_manager,
        original_filename="pune-intake.csv",
        status=BulkImportStatus.PREVIEW,
        report={
            "rows": [{"line": 2, "email": "pune.prospect@example.test", "phone": "9999900000"}],
            "errors": [],
            "summary": {"read": 1, "valid": 1, "errors": 0},
        },
    )


def _ids(queryset) -> set[str]:
    """The primary keys a queryset returns, as strings, for set comparison."""
    return {str(pk) for pk in queryset.values_list("pk", flat=True)}


# ---------------------------------------------------------------------------
# The seam against real SQL
# ---------------------------------------------------------------------------
#
# `apps/organisation/tests/test_scoping.py` proves the logic on hand-built
# objects. These prove the two things only a database can: that the filter
# expressions are valid ORM paths, and that the nullable-foreign-key join
# behaves the way the docstring claims it does.


@pytest.mark.django_db
def test_scope_to_branch_narrows_a_real_queryset_to_the_callers_centre(
    manager_user, batch, other_branch_batch
):
    from apps.batches.models import Batch
    from apps.organisation.scoping import scope_to_branch

    scoped = scope_to_branch(Batch.objects.all(), manager_user, path="branch")
    assert _ids(scoped) == {str(batch.pk)}


@pytest.mark.django_db
def test_scope_to_branch_follows_a_multi_segment_path(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.enrollments.models import Enrollment
    from apps.organisation.scoping import scope_to_branch

    scoped = scope_to_branch(Enrollment.objects.all(), manager_user, path="batch__branch")
    assert _ids(scoped) == {str(enrollment.pk)}


@pytest.mark.django_db
def test_scope_to_branch_or_shared_keeps_the_rows_whose_batch_is_null(
    manager_user, assignment_a, assignment_b, course_wide_assignment
):
    """The INNER JOIN trap, stated as SQL.

    `filter(batch__branch_id=X)` on a nullable `batch` drops every row where
    `batch IS NULL` — which would hide every course-wide assignment from every
    branch-scoped manager, with nothing in the logs to say so.
    """
    from apps.assignments.models import Assignment
    from apps.organisation.scoping import scope_to_branch_or_shared

    scoped = scope_to_branch_or_shared(Assignment.objects.all(), manager_user, path="batch__branch")
    assert _ids(scoped) == {str(assignment_a.pk), str(course_wide_assignment.pk)}


@pytest.mark.django_db
def test_a_plain_branch_filter_would_have_dropped_the_shared_rows(
    manager_user, assignment_a, course_wide_assignment
):
    """The negative control for the test above.

    Without this, `scope_to_branch_or_shared` could be quietly replaced by
    `scope_to_branch` and its own test would have to be read very carefully to
    notice. This asserts the wrong implementation really is wrong.
    """
    from apps.assignments.models import Assignment
    from apps.organisation.scoping import scope_to_branch

    naive = scope_to_branch(Assignment.objects.all(), manager_user, path="batch__branch")
    assert str(course_wide_assignment.pk) not in _ids(naive)
    assert str(assignment_a.pk) in _ids(naive)


@pytest.mark.django_db
def test_scope_to_branch_or_shared_returns_everything_for_a_platform_operator(
    unbounded_superadmin, assignment_a, assignment_b, course_wide_assignment
):
    from apps.assignments.models import Assignment
    from apps.organisation.scoping import scope_to_branch_or_shared

    scoped = scope_to_branch_or_shared(
        Assignment.objects.all(), unbounded_superadmin, path="batch__branch"
    )
    assert _ids(scoped) == {
        str(assignment_a.pk),
        str(assignment_b.pk),
        str(course_wide_assignment.pk),
    }


# ---------------------------------------------------------------------------
# apps.organisation.access — the centres themselves
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_branches_shows_a_manager_their_own_centre_and_no_other(
    manager_user, branch, other_branch
):
    from apps.organisation.access import visible_branches

    assert _ids(visible_branches(manager_user)) == {str(branch.pk)}


@pytest.mark.django_db
def test_visible_branches_shows_a_counsellor_their_own_centre_and_no_other(
    counsellor_user, branch, other_branch
):
    from apps.organisation.access import visible_branches

    assert _ids(visible_branches(counsellor_user)) == {str(branch.pk)}


@pytest.mark.django_db
def test_visible_branches_shows_a_platform_operator_every_centre(
    unbounded_superadmin, branch, other_branch
):
    from apps.organisation.access import visible_branches

    assert _ids(visible_branches(unbounded_superadmin)) == {str(branch.pk), str(other_branch.pk)}


@pytest.mark.django_db
def test_visible_branches_shows_a_manager_with_no_centre_nothing(
    branchless_manager, branch, other_branch
):
    from apps.organisation.access import visible_branches

    assert _ids(visible_branches(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_branches_shows_a_student_nothing(student, branch, other_branch):
    """A student holds no `organisation.view_any`, so the list is not theirs."""
    from apps.organisation.access import visible_branches

    assert _ids(visible_branches(student)) == set()


# ---------------------------------------------------------------------------
# apps.batches.access — the hub eight other modules derive from
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_batches_shows_a_manager_their_own_centres_classes(
    manager_user, batch, other_branch_batch
):
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(manager_user)) == {str(batch.pk)}


@pytest.mark.django_db
def test_visible_batches_shows_a_counsellor_their_own_centres_classes(
    counsellor_user, batch, other_branch_batch
):
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(counsellor_user)) == {str(batch.pk)}


@pytest.mark.django_db
def test_visible_batches_shows_the_other_centres_manager_the_other_centres_classes(
    other_branch_manager, batch, other_branch_batch
):
    """The mirror image, so "sees only A" cannot be passing because B is empty."""
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(other_branch_manager)) == {str(other_branch_batch.pk)}


@pytest.mark.django_db
def test_visible_batches_shows_a_platform_operator_both_centres(
    unbounded_superadmin, batch, other_branch_batch
):
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(unbounded_superadmin)) == {
        str(batch.pk),
        str(other_branch_batch.pk),
    }


@pytest.mark.django_db
def test_visible_batches_shows_a_manager_with_no_centre_nothing(
    branchless_manager, batch, other_branch_batch
):
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_batches_shows_an_administrator_with_no_centre_nothing(
    branchless_admin, batch, other_branch_batch
):
    """An admin is bounded exactly like a manager (D-127); a null branch on one
    is a mis-filed account, never a licence."""
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(branchless_admin)) == set()


@pytest.mark.django_db
def test_visible_enrollments_shows_a_manager_their_own_centres_enrolments(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.batches.access import visible_enrollments

    assert _ids(visible_enrollments(manager_user)) == {str(enrollment.pk)}


@pytest.mark.django_db
def test_visible_enrollments_shows_a_counsellor_their_own_centres_enrolments(
    counsellor_user, enrollment, other_branch_enrollment
):
    from apps.batches.access import visible_enrollments

    assert _ids(visible_enrollments(counsellor_user)) == {str(enrollment.pk)}


@pytest.mark.django_db
def test_visible_enrollments_shows_a_platform_operator_both_centres(
    unbounded_superadmin, enrollment, other_branch_enrollment
):
    from apps.batches.access import visible_enrollments

    assert _ids(visible_enrollments(unbounded_superadmin)) == {
        str(enrollment.pk),
        str(other_branch_enrollment.pk),
    }


@pytest.mark.django_db
def test_visible_enrollments_shows_a_manager_with_no_centre_nothing(
    branchless_manager, enrollment, other_branch_enrollment
):
    from apps.batches.access import visible_enrollments

    assert _ids(visible_enrollments(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.students.access and apps.trainers.access — the people
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_students_shows_a_manager_their_own_centres_students(
    manager_user, student_profile, other_branch_student
):
    from apps.students.access import visible_students

    reached = _ids(visible_students(manager_user))
    assert str(student_profile.pk) in reached
    assert str(other_branch_student.pk) not in reached


@pytest.mark.django_db
def test_visible_students_shows_a_counsellor_their_own_centres_students(
    counsellor_user, student_profile, other_branch_student
):
    """Admissions is the counsellor's whole job, so this is the list that would
    hurt most: another city's applicants, names and all."""
    from apps.students.access import visible_students

    reached = _ids(visible_students(counsellor_user))
    assert str(student_profile.pk) in reached
    assert str(other_branch_student.pk) not in reached


@pytest.mark.django_db
def test_visible_students_shows_a_platform_operator_both_centres(
    unbounded_superadmin, student_profile, other_branch_student
):
    from apps.students.access import visible_students

    reached = _ids(visible_students(unbounded_superadmin))
    assert {str(student_profile.pk), str(other_branch_student.pk)} <= reached


@pytest.mark.django_db
def test_visible_students_shows_a_manager_with_no_centre_nothing(
    branchless_manager, student_profile, other_branch_student
):
    from apps.students.access import visible_students

    assert _ids(visible_students(branchless_manager)) == set()


@pytest.mark.django_db
def test_reachable_students_is_narrowed_to_the_centre_even_though_it_ignores_audience(
    manager_user, student_profile, other_branch_student
):
    """`reachable_students` deliberately answers only the branch question — but
    it must still answer it, or the detail route 403s on another centre's id
    instead of 404ing and confirms the person exists."""
    from apps.students.access import reachable_students

    reached = _ids(reachable_students(manager_user))
    assert str(student_profile.pk) in reached
    assert str(other_branch_student.pk) not in reached


@pytest.mark.django_db
def test_reachable_students_is_empty_for_a_caller_with_no_centre(
    branchless_manager, student_profile, other_branch_student
):
    from apps.students.access import reachable_students

    assert _ids(reachable_students(branchless_manager)) == set()


@pytest.mark.django_db
def test_can_view_student_refuses_a_student_at_another_centre(
    manager_user, student_profile, other_branch_student
):
    from apps.students.access import can_view_student

    assert can_view_student(manager_user, student_profile) is True
    assert can_view_student(manager_user, other_branch_student) is False


@pytest.mark.django_db
def test_visible_trainers_shows_a_manager_their_own_centres_trainers(
    manager_user, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import visible_trainers

    reached = _ids(visible_trainers(manager_user))
    assert str(trainer_profile.pk) in reached
    assert str(other_branch_trainer.pk) not in reached


@pytest.mark.django_db
def test_visible_trainers_shows_a_counsellor_their_own_centres_trainers(
    counsellor_user, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import visible_trainers

    reached = _ids(visible_trainers(counsellor_user))
    assert str(trainer_profile.pk) in reached
    assert str(other_branch_trainer.pk) not in reached


@pytest.mark.django_db
def test_visible_trainers_shows_a_platform_operator_both_centres(
    unbounded_superadmin, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import visible_trainers

    reached = _ids(visible_trainers(unbounded_superadmin))
    assert {str(trainer_profile.pk), str(other_branch_trainer.pk)} <= reached


@pytest.mark.django_db
def test_visible_trainers_shows_a_manager_with_no_centre_nothing(
    branchless_manager, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import visible_trainers

    assert _ids(visible_trainers(branchless_manager)) == set()


@pytest.mark.django_db
def test_reachable_trainers_is_narrowed_to_the_centre(
    manager_user, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import reachable_trainers

    reached = _ids(reachable_trainers(manager_user))
    assert str(trainer_profile.pk) in reached
    assert str(other_branch_trainer.pk) not in reached


@pytest.mark.django_db
def test_can_view_trainer_refuses_a_trainer_at_another_centre(
    manager_user, trainer_profile, other_branch_trainer
):
    from apps.trainers.access import can_view_trainer

    assert can_view_trainer(manager_user, trainer_profile) is True
    assert can_view_trainer(manager_user, other_branch_trainer) is False


@pytest.mark.django_db
def test_a_trainer_still_reaches_their_own_record_without_holding_the_capability(
    trainer_profile, other_branch_trainer
):
    """The positive half. A rule that only refuses passes on a system where
    nothing works."""
    from apps.trainers.access import visible_trainers

    assert _ids(visible_trainers(trainer_profile.user)) == {str(trainer_profile.pk)}


# ---------------------------------------------------------------------------
# apps.sessions.access — classes on the timetable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_sessions_shows_a_manager_their_own_centres_classes(
    manager_user, session_a, session_b
):
    """Inherited from `visible_batches` rather than restated — which is exactly
    why it needs a test: nothing in `sessions/access.py` mentions a branch."""
    from apps.sessions.access import visible_sessions

    assert _ids(visible_sessions(manager_user)) == {str(session_a.pk)}


@pytest.mark.django_db
def test_manageable_sessions_shows_a_manager_their_own_centres_classes(
    manager_user, session_a, session_b
):
    """`manageable_sessions` builds its own base queryset, so the rule had to be
    written twice. A manager must not be able to reschedule Pune's class."""
    from apps.sessions.access import manageable_sessions

    assert _ids(manageable_sessions(manager_user)) == {str(session_a.pk)}


@pytest.mark.django_db
def test_manageable_sessions_shows_a_platform_operator_both_centres(
    unbounded_superadmin, session_a, session_b
):
    from apps.sessions.access import manageable_sessions

    assert _ids(manageable_sessions(unbounded_superadmin)) == {
        str(session_a.pk),
        str(session_b.pk),
    }


@pytest.mark.django_db
def test_manageable_sessions_shows_a_manager_with_no_centre_nothing(
    branchless_manager, session_a, session_b
):
    from apps.sessions.access import manageable_sessions

    assert _ids(manageable_sessions(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.dsr.access — daily status reports
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_dsrs_shows_a_manager_their_own_centres_reports(manager_user, dsr_a, dsr_b):
    from apps.dsr.access import visible_dsrs

    assert _ids(visible_dsrs(manager_user)) == {str(dsr_a.pk)}


@pytest.mark.django_db
def test_visible_dsrs_shows_a_platform_operator_both_centres(unbounded_superadmin, dsr_a, dsr_b):
    from apps.dsr.access import visible_dsrs

    assert _ids(visible_dsrs(unbounded_superadmin)) == {str(dsr_a.pk), str(dsr_b.pk)}


@pytest.mark.django_db
def test_visible_dsrs_shows_a_manager_with_no_centre_nothing(branchless_manager, dsr_a, dsr_b):
    from apps.dsr.access import visible_dsrs

    assert _ids(visible_dsrs(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.assessments.access — tests and their marks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_assessments_shows_a_manager_their_own_centres_tests(
    manager_user, assessment_a, assessment_b
):
    from apps.assessments.access import visible_assessments

    assert _ids(visible_assessments(manager_user)) == {str(assessment_a.pk)}


@pytest.mark.django_db
def test_manageable_assessments_shows_a_manager_their_own_centres_tests(
    manager_user, assessment_a, assessment_b
):
    from apps.assessments.access import manageable_assessments

    assert _ids(manageable_assessments(manager_user)) == {str(assessment_a.pk)}


@pytest.mark.django_db
def test_visible_results_shows_a_manager_their_own_centres_marks(manager_user, result_a, result_b):
    """Marks are the record most obviously nobody else's business."""
    from apps.assessments.access import visible_results

    assert _ids(visible_results(manager_user)) == {str(result_a.pk)}


@pytest.mark.django_db
def test_visible_results_shows_a_platform_operator_both_centres(
    unbounded_superadmin, result_a, result_b
):
    from apps.assessments.access import visible_results

    assert _ids(visible_results(unbounded_superadmin)) == {str(result_a.pk), str(result_b.pk)}


@pytest.mark.django_db
def test_visible_results_shows_a_manager_with_no_centre_nothing(
    branchless_manager, result_a, result_b
):
    from apps.assessments.access import visible_results

    assert _ids(visible_results(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.assignments.access — briefs and submissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_assignments_shows_a_manager_their_own_centres_briefs_and_the_shared_ones(
    manager_user, assignment_a, assignment_b, course_wide_assignment
):
    from apps.assignments.access import visible_assignments

    assert _ids(visible_assignments(manager_user)) == {
        str(assignment_a.pk),
        str(course_wide_assignment.pk),
    }


@pytest.mark.django_db
def test_manageable_assignments_shows_a_manager_their_own_centres_briefs_and_the_shared_ones(
    manager_user, assignment_a, assignment_b, course_wide_assignment
):
    from apps.assignments.access import manageable_assignments

    assert _ids(manageable_assignments(manager_user)) == {
        str(assignment_a.pk),
        str(course_wide_assignment.pk),
    }


@pytest.mark.django_db
def test_visible_submissions_shows_a_manager_their_own_centres_submitted_work(
    manager_user, submission_a, submission_b
):
    from apps.assignments.access import visible_submissions

    assert _ids(visible_submissions(manager_user)) == {str(submission_a.pk)}


@pytest.mark.django_db
def test_visible_submissions_shows_a_platform_operator_both_centres(
    unbounded_superadmin, submission_a, submission_b
):
    from apps.assignments.access import visible_submissions

    assert _ids(visible_submissions(unbounded_superadmin)) == {
        str(submission_a.pk),
        str(submission_b.pk),
    }


@pytest.mark.django_db
def test_visible_assignments_shows_a_manager_with_no_centre_nothing(
    branchless_manager, assignment_a, assignment_b, course_wide_assignment
):
    """`course_wide_assignment` is the point of this test, and the reason it is
    written out rather than left to the sweep. `scope_to_branch_or_shared` used
    to hand a branchless caller the batch-less rows on the grounds that they
    belong to no centre — which made "bounded to nothing" mean two different
    things in two helpers, and let a manager created through the Django admin
    read every course-wide brief in the institution."""
    from apps.assignments.access import manageable_assignments, visible_assignments

    assert _ids(visible_assignments(branchless_manager)) == set()
    assert _ids(manageable_assignments(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_projects_shows_a_manager_with_no_centre_nothing(
    branchless_manager, project_a, project_b, course_wide_project
):
    from apps.projects.access import manageable_projects, visible_projects

    assert _ids(visible_projects(branchless_manager)) == set()
    assert _ids(manageable_projects(branchless_manager)) == set()


@pytest.mark.django_db
def test_a_manager_with_no_centre_keeps_only_what_is_addressed_to_everyone(
    branchless_manager, announcement_a, announcement_b, institution_wide_announcement
):
    """The one deliberate exception, stated so it cannot be mistaken for the bug.

    A notice addressed to everyone is addressed to *this person too* — every
    signed-in caller reads those, capability or not — so withholding it from a
    mis-filed manager would be a rule about their branch column rather than
    about the audience. What they must not reach is a notice belonging to a
    centre, and neither centre's is here.
    """
    from apps.announcements.access import manageable_announcements, visible_announcements

    assert _ids(visible_announcements(branchless_manager)) == {
        str(institution_wide_announcement.pk)
    }
    # Managing, though, is a claim on somebody's board. They have none.
    assert _ids(manageable_announcements(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_bulk_imports_shows_a_manager_their_own_centres_runs(
    manager_user, bulk_import_a, bulk_import_b
):
    from apps.reporting.access import visible_bulk_imports

    assert _ids(visible_bulk_imports(manager_user)) == {str(bulk_import_a.pk)}


@pytest.mark.django_db
def test_visible_bulk_imports_shows_a_platform_operator_both_centres(
    unbounded_superadmin, bulk_import_a, bulk_import_b
):
    from apps.reporting.access import visible_bulk_imports

    assert _ids(visible_bulk_imports(unbounded_superadmin)) == {
        str(bulk_import_a.pk),
        str(bulk_import_b.pk),
    }


@pytest.mark.django_db
def test_visible_bulk_imports_shows_a_manager_with_no_centre_nothing(
    branchless_manager, bulk_import_a, bulk_import_b
):
    from apps.reporting.access import visible_bulk_imports

    assert _ids(visible_bulk_imports(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_submissions_shows_a_manager_with_no_centre_nothing(
    branchless_manager, submission_a, submission_b
):
    from apps.assignments.access import visible_submissions

    assert _ids(visible_submissions(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.exams.access — examinations and attempts
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_exams_shows_a_manager_their_own_centres_examinations(manager_user, exam_a, exam_b):
    from apps.exams.access import visible_exams

    assert _ids(visible_exams(manager_user)) == {str(exam_a.pk)}


@pytest.mark.django_db
def test_manageable_exams_shows_a_manager_their_own_centres_examinations(
    manager_user, exam_a, exam_b
):
    from apps.exams.access import manageable_exams

    assert _ids(manageable_exams(manager_user)) == {str(exam_a.pk)}


@pytest.mark.django_db
def test_visible_attempts_shows_a_manager_their_own_centres_attempts(
    manager_user, attempt_a, attempt_b
):
    from apps.exams.access import visible_attempts

    assert _ids(visible_attempts(manager_user)) == {str(attempt_a.pk)}


@pytest.mark.django_db
def test_visible_attempts_shows_a_platform_operator_both_centres(
    unbounded_superadmin, attempt_a, attempt_b
):
    from apps.exams.access import visible_attempts

    assert _ids(visible_attempts(unbounded_superadmin)) == {str(attempt_a.pk), str(attempt_b.pk)}


@pytest.mark.django_db
def test_visible_attempts_shows_a_manager_with_no_centre_nothing(
    branchless_manager, attempt_a, attempt_b
):
    from apps.exams.access import visible_attempts

    assert _ids(visible_attempts(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.projects.access — projects and student work
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_projects_shows_a_manager_their_own_centres_projects_and_the_shared_ones(
    manager_user, project_a, project_b, course_wide_project
):
    from apps.projects.access import visible_projects

    assert _ids(visible_projects(manager_user)) == {
        str(project_a.pk),
        str(course_wide_project.pk),
    }


@pytest.mark.django_db
def test_manageable_projects_shows_a_manager_their_own_centres_projects_and_the_shared_ones(
    manager_user, project_a, project_b, course_wide_project
):
    from apps.projects.access import manageable_projects

    assert _ids(manageable_projects(manager_user)) == {
        str(project_a.pk),
        str(course_wide_project.pk),
    }


@pytest.mark.django_db
def test_visible_student_projects_shows_a_manager_their_own_centres_work(
    manager_user, student_project_a, student_project_b
):
    from apps.projects.access import visible_student_projects

    assert _ids(visible_student_projects(manager_user)) == {str(student_project_a.pk)}


@pytest.mark.django_db
def test_visible_student_projects_shows_a_platform_operator_both_centres(
    unbounded_superadmin, student_project_a, student_project_b
):
    from apps.projects.access import visible_student_projects

    assert _ids(visible_student_projects(unbounded_superadmin)) == {
        str(student_project_a.pk),
        str(student_project_b.pk),
    }


@pytest.mark.django_db
def test_visible_student_projects_shows_a_manager_with_no_centre_nothing(
    branchless_manager, student_project_a, student_project_b
):
    from apps.projects.access import visible_student_projects

    assert _ids(visible_student_projects(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# apps.announcements.access — the noticeboard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_announcements_shows_a_manager_their_own_centres_notices_and_the_shared_ones(
    manager_user, announcement_a, announcement_b, institution_wide_announcement
):
    from apps.announcements.access import visible_announcements

    assert _ids(visible_announcements(manager_user)) == {
        str(announcement_a.pk),
        str(institution_wide_announcement.pk),
    }


@pytest.mark.django_db
def test_manageable_announcements_shows_a_manager_their_own_centres_notices(
    manager_user, announcement_a, announcement_b, institution_wide_announcement
):
    from apps.announcements.access import manageable_announcements

    reached = _ids(manageable_announcements(manager_user))
    assert str(announcement_a.pk) in reached
    assert str(announcement_b.pk) not in reached


@pytest.mark.django_db
def test_manageable_announcements_shows_a_platform_operator_both_centres(
    unbounded_superadmin, announcement_a, announcement_b
):
    from apps.announcements.access import manageable_announcements

    reached = _ids(manageable_announcements(unbounded_superadmin))
    assert {str(announcement_a.pk), str(announcement_b.pk)} <= reached


@pytest.mark.django_db
def test_can_manage_refuses_a_manager_a_notice_from_another_centre(
    manager_user, announcement_a, announcement_b
):
    """`can_manage` short-circuits on the capability before consulting the
    queryset, so it needs its own assertion rather than inheriting one."""
    from apps.announcements.access import can_manage

    assert can_manage(manager_user, announcement_a) is True
    assert can_manage(manager_user, announcement_b) is False


@pytest.mark.django_db
def test_visible_announcements_hides_a_notice_another_centre_sent_to_named_people(
    manager_user, private_announcement_b
):
    """The negative control the suite was missing.

    `scope_to_branch_or_shared` reads `batch IS NULL` as "set for every batch
    running the course", which is true of an assignment and false of an
    announcement: the audience constraint requires a null batch for `selected`,
    `course` and `everyone` alike. So a notice naming two families in Pune was
    being classified as institution-wide and served, with its title and body, to
    every other centre's manager.
    """
    from apps.announcements.access import visible_announcements

    assert str(private_announcement_b.pk) not in _ids(visible_announcements(manager_user))


@pytest.mark.django_db
def test_manageable_announcements_hides_a_notice_another_centre_sent_to_named_people(
    manager_user, private_announcement_b
):
    """The same expression backs the manage queryset, so the read leak was also
    an edit-and-archive leak: a manager in one city taking a notice off another
    city's board, audited in their own name."""
    from apps.announcements.access import can_manage, manageable_announcements

    assert str(private_announcement_b.pk) not in _ids(manageable_announcements(manager_user))
    assert can_manage(manager_user, private_announcement_b) is False


@pytest.mark.django_db
def test_visible_announcements_hides_a_course_notice_from_another_centre(
    manager_user, course_announcement_b
):
    """The course catalogue is institution-wide; a notice about one centre's
    sitting of it is not."""
    from apps.announcements.access import visible_announcements

    assert str(course_announcement_b.pk) not in _ids(visible_announcements(manager_user))


@pytest.mark.django_db
def test_a_notice_addressed_to_everyone_stays_readable_at_every_centre(
    other_branch_manager, institution_wide_announcement
):
    """The positive half, and the reason the rule keys on the audience rather
    than on the null batch: `everyone` really does mean everyone."""
    from apps.announcements.access import visible_announcements

    reached = _ids(visible_announcements(other_branch_manager))
    assert str(institution_wide_announcement.pk) in reached


@pytest.mark.django_db
def test_a_notice_addressed_to_everyone_is_still_managed_only_by_its_own_centre(
    other_branch_manager, institution_wide_announcement
):
    """Readable everywhere is not editable everywhere. An institution-wide
    notice is still somebody's notice, and archiving another centre's is the
    same cross-centre write as any other."""
    from apps.announcements.access import can_manage, manageable_announcements

    reached = _ids(manageable_announcements(other_branch_manager))
    assert str(institution_wide_announcement.pk) not in reached
    assert can_manage(other_branch_manager, institution_wide_announcement) is False


@pytest.mark.django_db
def test_a_manager_still_manages_their_own_centres_institution_wide_notice(
    manager_user, institution_wide_announcement
):
    """...and the centre that wrote it keeps it, which is what stops the rule
    above from simply being "nobody may edit an `everyone` notice"."""
    from apps.announcements.access import can_manage

    assert can_manage(manager_user, institution_wide_announcement) is True


@pytest.mark.django_db
def test_a_notice_whose_author_is_gone_belongs_to_no_centre(manager_user, orphaned_announcement_b):
    from apps.announcements.access import can_manage, visible_announcements

    assert str(orphaned_announcement_b.pk) not in _ids(visible_announcements(manager_user))
    assert can_manage(manager_user, orphaned_announcement_b) is False


@pytest.mark.django_db
def test_visible_announcements_shows_a_platform_operator_every_centres_private_notices(
    unbounded_superadmin, private_announcement_b, course_announcement_b
):
    """A 404 for everybody would satisfy every assertion above."""
    from apps.announcements.access import visible_announcements

    reached = _ids(visible_announcements(unbounded_superadmin))
    assert {str(private_announcement_b.pk), str(course_announcement_b.pk)} <= reached


# ---------------------------------------------------------------------------
# apps.performance.access — reviews and feedback, scoped through the subject
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_visible_reviews_shows_a_manager_their_own_centres_reviews(
    manager_user, review_a, review_b
):
    from apps.performance.access import visible_reviews

    assert _ids(visible_reviews(manager_user)) == {str(review_a.pk)}


@pytest.mark.django_db
def test_visible_reviews_hides_a_review_about_a_trainer_at_another_centre(
    manager_user, review_a, trainer_review_b
):
    """The trainer half of `scope_by_subject`'s `OR`. A rule written only
    against `student__branch_id` passes every student test and leaks this."""
    from apps.performance.access import visible_reviews

    assert _ids(visible_reviews(manager_user)) == {str(review_a.pk)}


@pytest.mark.django_db
def test_visible_reviews_shows_a_platform_operator_both_centres(
    unbounded_superadmin, review_a, review_b, trainer_review_b
):
    from apps.performance.access import visible_reviews

    assert _ids(visible_reviews(unbounded_superadmin)) == {
        str(review_a.pk),
        str(review_b.pk),
        str(trainer_review_b.pk),
    }


@pytest.mark.django_db
def test_can_view_review_refuses_a_manager_a_review_from_another_centre(
    manager_user, review_a, review_b
):
    """Every boolean in this module answers through its own queryset.

    While `visible_reviews` returned the institution to a capability holder,
    `if can_view_any_performance(user): return True` was an exact restatement of
    it. Once the queryset narrowed to a centre the short-circuit did not, and
    the two halves of one rule disagreed — invisibly, because every caller
    happened to resolve the review out of `visible_reviews` first. The next one
    would not have.
    """
    from apps.performance.access import can_view_review

    assert can_view_review(manager_user, review_a) is True
    assert can_view_review(manager_user, review_b) is False


@pytest.mark.django_db
def test_can_view_batch_performance_refuses_a_manager_another_centres_class(
    manager_user, batch, other_branch_batch
):
    from apps.performance.access import can_view_batch_performance

    assert can_view_batch_performance(manager_user, batch) is True
    assert can_view_batch_performance(manager_user, other_branch_batch) is False


@pytest.mark.django_db
def test_can_view_student_performance_refuses_a_manager_another_centres_enrolment(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.performance.access import can_view_student_performance

    assert can_view_student_performance(manager_user, enrollment) is True
    assert can_view_student_performance(manager_user, other_branch_enrollment) is False


@pytest.mark.django_db
def test_can_view_trainer_performance_refuses_a_manager_another_centres_trainer(
    manager_user, trainer_profile, other_branch_trainer
):
    from apps.performance.access import can_view_trainer_performance

    assert can_view_trainer_performance(manager_user, trainer_profile) is True
    assert can_view_trainer_performance(manager_user, other_branch_trainer) is False


@pytest.mark.django_db
def test_a_moderator_may_not_moderate_another_centres_discussion(
    manager_user, batch, other_branch_batch
):
    """`discussions.access` had the same capability short-circuit, and it is the
    same rule: a moderator moderates the discussions they can already see."""
    from apps.discussions.access import can_moderate, can_post_in

    assert can_moderate(manager_user, batch) is True
    assert can_moderate(manager_user, other_branch_batch) is False
    assert can_post_in(manager_user, batch) is True
    assert can_post_in(manager_user, other_branch_batch) is False


@pytest.mark.django_db
def test_visible_reviews_shows_a_manager_with_no_centre_nothing(
    branchless_manager, review_a, review_b
):
    from apps.performance.access import visible_reviews

    assert _ids(visible_reviews(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_feedback_shows_a_manager_their_own_centres_feedback(
    manager_user, feedback_a, feedback_b
):
    from apps.performance.access import visible_feedback

    assert _ids(visible_feedback(manager_user)) == {str(feedback_a.pk)}


@pytest.mark.django_db
def test_visible_feedback_hides_feedback_about_a_trainer_at_another_centre(
    manager_user, feedback_a, trainer_feedback_b
):
    from apps.performance.access import visible_feedback

    assert _ids(visible_feedback(manager_user)) == {str(feedback_a.pk)}


@pytest.mark.django_db
def test_visible_feedback_shows_a_manager_with_no_centre_nothing(
    branchless_manager, feedback_a, feedback_b
):
    from apps.performance.access import visible_feedback

    assert _ids(visible_feedback(branchless_manager)) == set()


@pytest.mark.django_db
def test_visible_enrollments_for_performance_shows_a_manager_their_own_centre(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.performance.access import visible_enrollments_for_performance

    assert _ids(visible_enrollments_for_performance(manager_user)) == {str(enrollment.pk)}


@pytest.mark.django_db
def test_scope_by_subject_matches_a_row_once_and_needs_no_distinct(
    manager_user, review_a, review_b
):
    """The `OR` is over two mutually exclusive columns, so a row cannot join
    twice — asserted rather than assumed, because a duplicate here would show up
    as an inflated count on a dashboard long before anybody suspected the join.
    """
    from apps.performance.access import scope_by_subject
    from apps.performance.models import PerformanceReview

    rows = list(scope_by_subject(PerformanceReview.objects.all(), manager_user))
    assert [row.pk for row in rows] == [review_a.pk]


# ---------------------------------------------------------------------------
# apps.reporting.access — the aggregates
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scope_for_restricts_a_branch_scoped_manager_to_their_own_batches(
    manager_user, batch, other_branch_batch
):
    """A manager holds `report.view_any`, so before branches arrived this
    returned an unrestricted scope — every metric, dashboard figure and export
    running institution-wide for exactly the role branches exist to bound.
    """
    from apps.reporting.access import scope_for

    scope = scope_for(manager_user)
    assert "restrict_to_batches" in scope
    assert {str(pk) for pk in scope["restrict_to_batches"]} == {str(batch.pk)}


@pytest.mark.django_db
def test_scope_for_leaves_a_platform_operator_unrestricted(
    unbounded_superadmin, batch, other_branch_batch
):
    from apps.reporting.access import scope_for

    assert "restrict_to_batches" not in scope_for(unbounded_superadmin)


@pytest.mark.django_db
def test_scope_for_restricts_a_manager_with_no_centre_to_nothing(
    branchless_manager, batch, other_branch_batch
):
    from apps.reporting.access import scope_for

    assert scope_for(branchless_manager)["restrict_to_batches"] == []


@pytest.mark.django_db
def test_reporting_visible_trainers_agrees_with_the_trainer_list(
    manager_user, trainer_profile, other_branch_trainer
):
    """Two screens, one set of people. The hub's rollup and the trainer list
    disagreeing about who exists is the §11.4 failure: nobody knows which to
    believe."""
    from apps.reporting.access import visible_trainers as hub_trainers
    from apps.trainers.access import visible_trainers as list_trainers

    assert _ids(hub_trainers(manager_user)) == _ids(list_trainers(manager_user))
    assert str(other_branch_trainer.pk) not in _ids(hub_trainers(manager_user))


@pytest.mark.django_db
def test_reporting_visible_trainers_shows_a_manager_with_no_centre_nothing(
    branchless_manager, trainer_profile, other_branch_trainer
):
    from apps.reporting.access import visible_trainers

    assert _ids(visible_trainers(branchless_manager)) == set()


# ---------------------------------------------------------------------------
# Derived modules — scoped by inheritance, and therefore easiest to forget
# ---------------------------------------------------------------------------
#
# None of these modules mentions a branch. They are scoped only because they
# derive from `batches.access`, which is a property nothing in their own source
# records. If somebody ever gives one of them its own base queryset, these are
# the tests that notice.


@pytest.mark.django_db
def test_progress_visible_enrollments_is_scoped_through_the_batch_hub(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.progress.access import visible_enrollments

    assert _ids(visible_enrollments(manager_user)) == {str(enrollment.pk)}


@pytest.mark.django_db
def test_visible_completions_is_scoped_through_the_batch_hub(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.progress.access import visible_completions
    from apps.progress.models import CourseCompletion

    mine = CourseCompletion.objects.create(enrollment=enrollment)
    theirs = CourseCompletion.objects.create(enrollment=other_branch_enrollment)

    reached = _ids(visible_completions(manager_user))
    assert str(mine.pk) in reached
    assert str(theirs.pk) not in reached


@pytest.mark.django_db
def test_visible_threads_is_scoped_through_the_batch_hub(
    manager_user, admin_user, unbounded_superadmin, batch, other_branch_batch
):
    from apps.discussions.access import visible_threads
    from apps.discussions.services import create_thread

    mine = create_thread(batch=batch, actor=admin_user, title="Jaipur", body="Question.")
    theirs = create_thread(
        batch=other_branch_batch, actor=unbounded_superadmin, title="Pune", body="Question."
    )

    reached = _ids(visible_threads(manager_user))
    assert str(mine.pk) in reached
    assert str(theirs.pk) not in reached


@pytest.mark.django_db
def test_visible_certificates_is_scoped_through_the_batch_hub(
    manager_user, enrollment, other_branch_enrollment
):
    from apps.certificates.views import visible_certificates
    from apps.progress.models import CourseCompletion

    mine = _certificate_for(CourseCompletion.objects.create(enrollment=enrollment))
    theirs = _certificate_for(CourseCompletion.objects.create(enrollment=other_branch_enrollment))

    reached = _ids(visible_certificates(manager_user))
    assert str(mine.pk) in reached
    assert str(theirs.pk) not in reached


def _certificate_for(completion):
    """A certificate row, built directly — issuing one needs an approved
    completion and a template, none of which changes which rows a queryset
    returns."""
    from apps.certificates.models import Certificate

    enrollment = completion.enrollment
    return Certificate.objects.create(
        completion=completion,
        number=f"CERT-{str(completion.pk)[:8]}",
        student_name=enrollment.student.user.get_full_name(),
        student_code=enrollment.student.student_id,
        course_title=enrollment.batch.course.title,
        batch_code=enrollment.batch.code,
        completion_date=timezone.localdate(),
        verification_code=str(completion.pk)[:12],
    )


# ---------------------------------------------------------------------------
# Anonymous and inactive callers — the helpers are reached above the guard
# ---------------------------------------------------------------------------
#
# `scope_to_branch` is called on the capability-holder branch of an access
# function, which by convention sits *above* the is_authenticated / is_active
# guard. So every one of these functions really is invoked with an
# `AnonymousUser` in production, and an `AttributeError` here would be a 500 on
# an unauthenticated request rather than a 401.

_ACCESS_FUNCTIONS = [
    ("apps.organisation.access", "visible_branches"),
    ("apps.batches.access", "visible_batches"),
    ("apps.batches.access", "visible_enrollments"),
    ("apps.students.access", "visible_students"),
    ("apps.students.access", "reachable_students"),
    ("apps.trainers.access", "visible_trainers"),
    ("apps.trainers.access", "reachable_trainers"),
    ("apps.sessions.access", "visible_sessions"),
    ("apps.sessions.access", "manageable_sessions"),
    ("apps.dsr.access", "visible_dsrs"),
    ("apps.assessments.access", "visible_assessments"),
    ("apps.assessments.access", "manageable_assessments"),
    ("apps.assessments.access", "visible_results"),
    ("apps.assignments.access", "visible_assignments"),
    ("apps.assignments.access", "manageable_assignments"),
    ("apps.assignments.access", "visible_submissions"),
    ("apps.exams.access", "visible_exams"),
    ("apps.exams.access", "manageable_exams"),
    ("apps.exams.access", "visible_attempts"),
    ("apps.projects.access", "visible_projects"),
    ("apps.projects.access", "manageable_projects"),
    ("apps.projects.access", "visible_student_projects"),
    ("apps.announcements.access", "visible_announcements"),
    ("apps.announcements.access", "manageable_announcements"),
    ("apps.performance.access", "visible_reviews"),
    ("apps.performance.access", "visible_feedback"),
    ("apps.performance.access", "visible_enrollments_for_performance"),
    ("apps.progress.access", "visible_enrollments"),
    ("apps.progress.access", "visible_completions"),
    ("apps.reporting.access", "visible_bulk_imports"),
    ("apps.reporting.access", "visible_batches"),
    ("apps.reporting.access", "visible_enrollments"),
    ("apps.reporting.access", "visible_trainers"),
]


def test_the_access_function_sweep_found_something():
    """Vacuity guard: a sweep over an empty list passes silently."""
    assert len(_ACCESS_FUNCTIONS) >= 33


def _resolve(module_name: str, function_name: str):
    from importlib import import_module

    return getattr(import_module(module_name), function_name)


@pytest.mark.django_db
@pytest.mark.parametrize(("module_name", "function_name"), _ACCESS_FUNCTIONS)
def test_every_access_function_returns_an_empty_queryset_for_an_anonymous_caller(
    module_name,
    function_name,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
    course_wide_assignment,
    course_wide_project,
    institution_wide_announcement,
):
    where = f"{module_name}.{function_name}"
    result = _resolve(module_name, function_name)(AnonymousUser())
    assert result is not None, where
    assert result.count() == 0, where


@pytest.mark.django_db
@pytest.mark.parametrize(("module_name", "function_name"), _ACCESS_FUNCTIONS)
def test_every_access_function_returns_an_empty_queryset_for_no_caller_at_all(
    module_name,
    function_name,
    batch,
    other_branch_batch,
    course_wide_assignment,
    course_wide_project,
    institution_wide_announcement,
):
    """`None` reaches these through a service called outside a request."""
    where = f"{module_name}.{function_name}"
    result = _resolve(module_name, function_name)(None)
    assert result is not None, where
    assert result.count() == 0, where


@pytest.mark.django_db
@pytest.mark.parametrize(("module_name", "function_name"), _ACCESS_FUNCTIONS)
def test_every_access_function_returns_an_empty_queryset_for_a_deactivated_manager(
    module_name,
    function_name,
    inactive_manager,
    batch,
    other_branch_batch,
    enrollment,
    other_branch_enrollment,
    course_wide_assignment,
    course_wide_project,
    institution_wide_announcement,
):
    """A manager whose account was switched off keeps their branch column. If
    the guard read the column rather than asking `is_unbounded`, this is the
    caller who would still see their old centre."""
    where = f"{module_name}.{function_name}"
    result = _resolve(module_name, function_name)(inactive_manager)
    assert result is not None, where
    assert result.count() == 0, where


@pytest.mark.django_db
@pytest.mark.parametrize(("module_name", "function_name"), _ACCESS_FUNCTIONS)
def test_no_access_function_returns_a_list_where_a_queryset_is_expected(
    module_name, function_name, manager_user, batch, other_branch_batch
):
    """Views chain `.filter()` onto these. A list would work in the test that
    only counts rows and fail in the endpoint that pages them."""
    from django.db.models import QuerySet

    where = f"{module_name}.{function_name}"
    result = _resolve(module_name, function_name)(manager_user)
    assert isinstance(result, QuerySet), where


# ---------------------------------------------------------------------------
# The write side — a centre is forced, never chosen
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_bounded_actor_cannot_plant_a_student_in_another_centre(
    manager_user, other_branch, branch
):
    """A supplied branch id is *ignored* rather than validated: forcing the
    actor's own centre means the worst a wrong id can do is be silently right.
    """
    from apps.students.services import create_student

    profile = create_student(
        email="planted@example.test",
        first_name="Planted",
        last_name="Learner",
        actor=manager_user,
        branch=other_branch,
        send_invitation=False,
    )
    assert profile.branch_id == branch.pk
    assert profile.user.branch_id == branch.pk


@pytest.mark.django_db
def test_a_bounded_actor_cannot_plant_a_batch_in_another_centre(
    manager_user, published_course, trainer_profile, other_branch, branch
):
    from apps.batches.services import create_batch

    created = create_batch(
        actor=manager_user,
        branch=other_branch,
        name="Planted class",
        course=published_course,
        trainer=trainer_profile,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=30),
        capacity=2,
    )
    assert created.branch_id == branch.pk


@pytest.mark.django_db
def test_a_platform_operator_must_name_the_centre_for_a_new_record(unbounded_superadmin):
    """An unbounded actor has no centre to inherit, and a branchless record is
    one that, under the fail-closed rule, nobody can see."""
    from apps.common.exceptions import ApplicationError
    from apps.students.services import create_student

    with pytest.raises(ApplicationError) as excinfo:
        create_student(
            email="homeless@example.test",
            first_name="No",
            last_name="Centre",
            actor=unbounded_superadmin,
            send_invitation=False,
        )
    assert "branch" in excinfo.value.detail


@pytest.mark.django_db
def test_an_account_and_its_profile_are_always_stamped_with_the_same_centre(
    unbounded_superadmin, other_branch
):
    from apps.trainers.services import create_trainer

    profile = create_trainer(
        email="paired@pune.example.test",
        first_name="Paired",
        last_name="Trainer",
        actor=unbounded_superadmin,
        branch=other_branch,
        send_invitation=False,
    )
    assert profile.branch_id == other_branch.pk == profile.user.branch_id


@pytest.mark.django_db
def test_a_class_cannot_be_staffed_from_another_centre(
    unbounded_superadmin, batch, other_branch_trainer
):
    """Refused where the pairing is *made*, which is why `visible_batches` can
    leave the trainer branch alone and a transferred trainer keeps their history.
    """
    from apps.batches.services import assign_trainer
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError) as excinfo:
        assign_trainer(batch=batch, trainer=other_branch_trainer, actor=unbounded_superadmin)
    assert "trainer" in excinfo.value.detail


@pytest.mark.django_db
def test_a_student_cannot_be_enrolled_onto_a_class_at_another_centre(
    unbounded_superadmin, student_profile, other_branch_batch
):
    from apps.common.exceptions import ApplicationError
    from apps.enrollments.services import enrol_student

    with pytest.raises(ApplicationError) as excinfo:
        enrol_student(student=student_profile, batch=other_branch_batch, actor=unbounded_superadmin)
    assert "batch" in excinfo.value.detail


@pytest.mark.django_db
def test_a_student_cannot_be_transferred_to_a_class_at_another_centre(
    unbounded_superadmin, enrollment, other_branch_batch
):
    from apps.common.exceptions import ApplicationError
    from apps.enrollments.services import transfer_student

    with pytest.raises(ApplicationError) as excinfo:
        transfer_student(
            enrollment=enrollment,
            target_batch=other_branch_batch,
            actor=unbounded_superadmin,
            reason="Moved city.",
        )
    assert "batch" in excinfo.value.detail


@pytest.mark.django_db
def test_a_bounded_administrator_has_no_authority_over_an_account_at_another_centre(
    admin_user, other_branch_manager
):
    """Authority and reach are different questions: an administrator in Jaipur
    is neither senior nor junior to one in Pune, they are not in each other's
    world at all."""
    from apps.accounts.services import AuthorityError, update_user

    with pytest.raises(AuthorityError):
        update_user(user=other_branch_manager, actor=admin_user, first_name="Renamed")

    other_branch_manager.refresh_from_db()
    assert other_branch_manager.first_name == "Priya"


@pytest.mark.django_db
def test_an_administrator_with_no_centre_has_authority_over_nobody(branchless_admin, manager_user):
    """The Django-admin-created account. Reading its null branch as "no branch
    check applies" would have made it the most powerful account in the system.
    """
    from apps.accounts.services import AuthorityError, update_user

    with pytest.raises(AuthorityError):
        update_user(user=manager_user, actor=branchless_admin, first_name="Renamed")


@pytest.mark.django_db
def test_a_bounded_administrator_may_still_administer_their_own_centre(admin_user, manager_user):
    """The positive half, so the branch guard cannot be satisfied by refusing
    everybody."""
    from apps.accounts.services import update_user

    updated = update_user(user=manager_user, actor=admin_user, first_name="Renamed")
    assert updated.first_name == "Renamed"


@pytest.mark.django_db
def test_a_centre_cannot_be_changed_as_a_side_effect_of_editing_an_account(
    admin_user, manager_user, other_branch
):
    from apps.accounts.services import update_user
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError) as excinfo:
        update_user(user=manager_user, actor=admin_user, branch=other_branch)
    assert "branch" in excinfo.value.detail

    manager_user.refresh_from_db()
    assert manager_user.branch_id != other_branch.pk


@pytest.mark.django_db
def test_moving_an_account_between_centres_is_audited_as_its_own_action(
    unbounded_superadmin, manager_user, other_branch, branch
):
    from apps.accounts.services import move_user_to_branch
    from apps.audit.models import AuditAction, AuditLog

    move_user_to_branch(
        user=manager_user, branch=other_branch, actor=unbounded_superadmin, reason="Relocated."
    )

    manager_user.refresh_from_db()
    assert manager_user.branch_id == other_branch.pk

    entry = AuditLog.objects.filter(action=AuditAction.USER_BRANCH_CHANGED).latest("created_at")
    assert entry.context["from"] == branch.code
    assert entry.context["to"] == other_branch.code
    assert entry.context["reason"] == "Relocated."


@pytest.mark.django_db
def test_moving_an_account_changes_what_it_can_see(
    unbounded_superadmin, manager_user, other_branch, batch, other_branch_batch
):
    """The point of the whole feature, asserted end to end at the queryset."""
    from apps.accounts.services import move_user_to_branch
    from apps.batches.access import visible_batches

    assert _ids(visible_batches(manager_user)) == {str(batch.pk)}
    move_user_to_branch(user=manager_user, branch=other_branch, actor=unbounded_superadmin)
    manager_user.refresh_from_db()
    assert _ids(visible_batches(manager_user)) == {str(other_branch_batch.pk)}
