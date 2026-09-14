"""Shared pytest fixtures.

Test database strategy: pytest-django creates ``test_<name>`` on the same
PostgreSQL server the app uses, runs every test inside a transaction that is
rolled back afterwards, and destroys the database at the end. Tests therefore
exercise real PostgreSQL behaviour (constraints, JSON and array fields, the
case-insensitive unique index, the ID sequences) rather than a SQLite
approximation, while staying isolated.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.students.services import create_student
from apps.trainers.services import create_trainer

TEST_PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "an-entirely-different-passphrase"


@pytest.fixture(autouse=True)
def _reset_request_scope():
    """Clear the per-request context between tests.

    Failure audits are queued in a `contextvars` queue and written by middleware
    after the request transaction ends. A test that triggers one without a real
    request leaves it in the queue — and the next test to flush the queue writes
    it, pointing at a user whose transaction has since been rolled back. The
    symptom is a foreign-key error in a test that did nothing wrong, which is a
    miserable thing to debug.
    """
    from apps.common.request_context import reset

    reset()
    yield
    reset()


@pytest.fixture(autouse=True)
def _reset_rate_limit_counters():
    """Clear throttle state between tests.

    Throttle counters live in the Django cache, which is process-wide. Without
    this, a test that exercises the login endpoint would push unrelated later
    tests over the auth rate limit, and the suite would fail differently
    depending on execution order.
    """
    from django.core.cache import cache

    from apps.common.throttling import AuthEndpointThrottle, BurstThrottle

    # The rate *table* is cached on the throttle classes, and the tests that
    # exercise a limit have to lower it there. Snapshot and restore, or the
    # tightened rate leaks into every test that runs afterwards.
    rates = [(cls, cls.THROTTLE_RATES) for cls in (AuthEndpointThrottle, BurstThrottle)]

    cache.clear()
    yield
    cache.clear()
    for cls, original in rates:
        cls.THROTTLE_RATES = original


@pytest.fixture
def api_client() -> APIClient:
    """Client that enforces CSRF, matching how a browser really behaves."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def api_client_no_csrf() -> APIClient:
    return APIClient()


@pytest.fixture
def branch(db):
    """The centre everything in the default fixture set belongs to.

    One branch for the whole default set on purpose: the existing suite keeps
    passing unchanged, and scoping is proved only by tests that deliberately opt
    into `other_branch`. A shared fixture that quietly put two branches in play
    would make every unrelated test a scoping test.

    `get_or_create`, not `create`: `organisation.0002_default_branch` already
    put a MAIN row in the test database, so this fixture adopts the same centre
    a real deployment has after the backfill rather than colliding with it.
    """
    from apps.organisation.models import Branch

    return Branch.objects.get_or_create(
        code="MAIN", defaults={"name": "Main centre", "city": "Jaipur"}
    )[0]


@pytest.fixture
def other_branch(db):
    """A second centre, so a scoping test has something to be refused.

    The sibling of `rival` in `tests/test_authorization_matrix.py`: the same
    job, one level up. A test that only proves a manager sees their own branch
    passes on a system with one branch.
    """
    from apps.organisation.models import Branch

    return Branch.objects.create(code="PUNE", name="Pune centre", city="Pune")


@pytest.fixture
def student(branch) -> User:
    return User.objects.create_user(
        email="student@example.test",
        password=TEST_PASSWORD,
        first_name="Sam",
        last_name="Student",
        role=UserRole.STUDENT,
        branch=branch,
    )


@pytest.fixture
def trainer(branch) -> User:
    return User.objects.create_user(
        email="trainer@example.test",
        password=TEST_PASSWORD,
        first_name="Tina",
        last_name="Trainer",
        role=UserRole.TRAINER,
        branch=branch,
    )


@pytest.fixture
def admin_user(branch) -> User:
    return User.objects.create_user(
        email="admin@example.test",
        password=TEST_PASSWORD,
        first_name="Amy",
        last_name="Admin",
        role=UserRole.ADMIN,
        branch=branch,
        is_staff=True,
    )


@pytest.fixture
def manager_user(branch) -> User:
    """Runs academic operations; cannot change who anybody *is*."""
    return User.objects.create_user(
        email="manager@example.test",
        password=TEST_PASSWORD,
        first_name="Mira",
        last_name="Manager",
        role=UserRole.MANAGER,
        branch=branch,
    )


@pytest.fixture
def counsellor_user(branch) -> User:
    """Brings students in: registers, enrols, staffs the batch, then hands over.

    Holds nothing academic and nothing about accounts, so this fixture is also
    the one to reach for when a test needs "signed in, trusted with admissions,
    and refused everything else".
    """
    return User.objects.create_user(
        email="counsellor@example.test",
        password=TEST_PASSWORD,
        first_name="Kiran",
        last_name="Counsellor",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )


@pytest.fixture
def student_profile(admin_user):
    """A student created through the service, so it has a profile and an ID."""
    return create_student(
        email="enrolled@example.test",
        first_name="Enrolled",
        last_name="Learner",
        actor=admin_user,
        password=TEST_PASSWORD,
        send_invitation=False,
        profile_fields={"city": "Jaipur", "state": "Rajasthan"},
    )


@pytest.fixture
def other_student_profile(admin_user):
    """A second student, used for cross-tenant access tests."""
    return create_student(
        email="other@example.test",
        first_name="Other",
        last_name="Learner",
        actor=admin_user,
        password=TEST_PASSWORD,
        send_invitation=False,
    )


@pytest.fixture
def trainer_profile(admin_user):
    return create_trainer(
        email="staff.trainer@example.test",
        first_name="Staff",
        last_name="Trainer",
        actor=admin_user,
        password=TEST_PASSWORD,
        send_invitation=False,
        profile_fields={"professional_title": "Senior Linux Trainer", "skills": ["Linux"]},
    )


@pytest.fixture
def png_bytes() -> bytes:
    """Smallest valid PNG, generated rather than checked in as a binary blob."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (64, 64), color=(20, 120, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Course fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def category(db):
    from apps.courses.models import Category

    return Category.objects.create(name="Linux", slug="linux", description="Linux courses")


@pytest.fixture
def draft_course(admin_user, category):
    """A course that has never been published."""
    from apps.courses.services import create_course

    return create_course(
        actor=admin_user,
        title="Draft Linux Administration",
        category=category,
        short_description="Not published yet.",
    )


@pytest.fixture
def published_course(admin_user, category):
    """A published course with one published module and two published lessons.

    Built through the services so it exercises the same code the API does,
    including position allocation and the publishing checklist.
    """
    from apps.courses import services
    from apps.courses.models import LessonContentType, PublishStatus

    course = services.create_course(
        actor=admin_user,
        title="Linux Essentials",
        category=category,
        short_description="A published course.",
        description="Full description of the published course.",
        learning_objectives=["Use the shell", "Manage packages"],
    )
    module = services.create_module(
        course=course, actor=admin_user, title="Getting started", status=PublishStatus.PUBLISHED
    )
    services.create_lesson(
        module=module,
        actor=admin_user,
        title="Welcome",
        content_type=LessonContentType.TEXT,
        text_content="Welcome to the course.",
        status=PublishStatus.PUBLISHED,
        is_preview=True,
    )
    services.create_lesson(
        module=module,
        actor=admin_user,
        title="The shell",
        content_type=LessonContentType.TEXT,
        text_content="Secret paid content.",
        status=PublishStatus.PUBLISHED,
    )
    services.set_course_status(
        course=course, target=PublishStatus.PUBLISHED, actor=admin_user, may_publish=True
    )
    course.refresh_from_db()
    return course


@pytest.fixture
def published_module(published_course):
    return published_course.modules.first()


@pytest.fixture
def preview_lesson(published_module):
    return published_module.lessons.get(is_preview=True)


@pytest.fixture
def paid_lesson(published_module):
    return published_module.lessons.get(is_preview=False)


@pytest.fixture
def assigned_trainer(trainer, draft_course, admin_user):
    """A trainer with editor rights on ``draft_course`` and nothing else."""
    from apps.courses.models import CourseAuthorRole
    from apps.courses.services import assign_author

    assign_author(course=draft_course, user=trainer, role=CourseAuthorRole.EDITOR, actor=admin_user)
    return trainer


@pytest.fixture
def owning_trainer(trainer, draft_course, admin_user):
    """A trainer with owner rights on ``draft_course``."""
    from apps.courses.models import CourseAuthorRole
    from apps.courses.services import assign_author

    assign_author(course=draft_course, user=trainer, role=CourseAuthorRole.OWNER, actor=admin_user)
    return trainer


@pytest.fixture
def pdf_bytes() -> bytes:
    """A minimal but structurally valid PDF, generated rather than committed."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )


# ---------------------------------------------------------------------------
# Batch, schedule and enrolment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trainer_profile_two(admin_user):
    """A second trainer, for conflict and cross-tenant tests."""
    from apps.trainers.services import create_trainer

    return create_trainer(
        email="second.trainer@example.test",
        first_name="Sunil",
        last_name="Second",
        actor=admin_user,
        password=TEST_PASSWORD,
        send_invitation=False,
        profile_fields={"professional_title": "Python Trainer", "skills": ["Python"]},
    )


@pytest.fixture
def batch(admin_user, published_course, trainer_profile):
    """An active batch on the published course, with a seat or two spare."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.batches.models import BatchStatus
    from apps.batches.services import create_batch, set_batch_status

    today = timezone.localdate()
    created = create_batch(
        actor=admin_user,
        name="Linux Essentials — Morning",
        course=published_course,
        trainer=trainer_profile,
        start_date=today - timedelta(days=7),
        end_date=today + timedelta(days=60),
        capacity=3,
    )
    return set_batch_status(batch=created, target=BatchStatus.ACTIVE, actor=admin_user)


@pytest.fixture
def upcoming_batch(admin_user, published_course, trainer_profile_two):
    """A second batch on the same course, taught by a different trainer."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.batches.services import create_batch

    today = timezone.localdate()
    return create_batch(
        actor=admin_user,
        name="Linux Essentials — Evening",
        course=published_course,
        trainer=trainer_profile_two,
        start_date=today + timedelta(days=14),
        end_date=today + timedelta(days=90),
        capacity=2,
    )


@pytest.fixture
def unbounded_superadmin(db) -> User:
    """A platform operator, bounded to no centre at all.

    `branch=None` here is the only place in the fixture set where a null branch
    is correct — for everybody else it means "sees nothing", which is what makes
    the fail-closed rule real rather than decorative.
    """
    return User.objects.create_user(
        email="superadmin@example.test",
        password=TEST_PASSWORD,
        first_name="Sona",
        last_name="Super",
        role=UserRole.SUPERADMIN,
        branch=None,
    )


@pytest.fixture
def other_branch_manager(other_branch) -> User:
    """A manager at the second centre. The person who must see nothing of the first."""
    return User.objects.create_user(
        email="manager@pune.example.test",
        password=TEST_PASSWORD,
        first_name="Priya",
        last_name="Pune",
        role=UserRole.MANAGER,
        branch=other_branch,
    )


@pytest.fixture
def other_branch_trainer(other_branch, unbounded_superadmin):
    """A trainer at the second centre.

    Created by the superadmin because only an unbounded actor may name a centre
    other than their own — which is itself the rule under test elsewhere.
    """
    return create_trainer(
        email="trainer@pune.example.test",
        first_name="Prakash",
        last_name="Pune",
        actor=unbounded_superadmin,
        branch=other_branch,
        password=TEST_PASSWORD,
        send_invitation=False,
        profile_fields={"professional_title": "Networking Trainer", "skills": ["Networking"]},
    )


@pytest.fixture
def other_branch_student(other_branch, unbounded_superadmin):
    """A student at the second centre."""
    return create_student(
        email="student@pune.example.test",
        first_name="Pooja",
        last_name="Pune",
        actor=unbounded_superadmin,
        branch=other_branch,
        password=TEST_PASSWORD,
        send_invitation=False,
    )


@pytest.fixture
def other_branch_batch(other_branch, unbounded_superadmin, published_course, other_branch_trainer):
    """An active batch at the second centre, on the same shared course."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.batches.models import BatchStatus
    from apps.batches.services import create_batch, set_batch_status

    today = timezone.localdate()
    created = create_batch(
        actor=unbounded_superadmin,
        branch=other_branch,
        name="Linux Essentials — Pune",
        course=published_course,
        trainer=other_branch_trainer,
        start_date=today - timedelta(days=7),
        end_date=today + timedelta(days=60),
        capacity=3,
    )
    return set_batch_status(batch=created, target=BatchStatus.ACTIVE, actor=unbounded_superadmin)


@pytest.fixture
def other_branch_enrollment(unbounded_superadmin, other_branch_student, other_branch_batch):
    """An enrolment entirely inside the second centre."""
    from apps.enrollments.services import enrol_student

    return enrol_student(
        student=other_branch_student, batch=other_branch_batch, actor=unbounded_superadmin
    )


@pytest.fixture
def schedule(admin_user, batch):
    """A Monday-morning class on ``batch``."""
    from datetime import time

    from apps.batches.models import Weekday
    from apps.batches.services import create_schedule

    return create_schedule(
        batch=batch,
        actor=admin_user,
        weekday=Weekday.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        timezone_name="Asia/Kolkata",
        location="Lab 1",
    )


@pytest.fixture
def enrollment(admin_user, student_profile, batch):
    """An active enrolment: the student can open the course."""
    from apps.enrollments.services import enrol_student

    return enrol_student(student=student_profile, batch=batch, actor=admin_user)


@pytest.fixture
def other_enrollment(admin_user, other_student_profile, batch):
    """A second student on the same batch, for cross-student access tests."""
    from apps.enrollments.services import enrol_student

    return enrol_student(student=other_student_profile, batch=batch, actor=admin_user)
