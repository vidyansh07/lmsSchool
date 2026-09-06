"""The counsellor role, checked from both sides.

A role is defined as much by what it cannot reach as by what it can, and a test
file that only proves refusals will pass happily on a system where the role can
do nothing at all. So both halves are here: the admissions work a counsellor
must be able to do, and the academic and account work they must not.

The route-level sweep in ``test_authorization_matrix.py`` already checks every
capability-guarded endpoint against every role, including this one, without
anybody listing them. What this file adds is the part a sweep cannot derive:
whether the *product decision* is right. "A counsellor may open a batch but not
mark its register" is a judgement, and a judgement belongs somewhere a reviewer
can read it.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import User, UserRole
from apps.accounts.roles import (
    BASE_CAPABILITIES,
    ROLE_CAPABILITIES,
    Capability,
    can_administer,
    can_grant_role,
    has_capability,
)

PASSWORD = "Str0ng-Passphrase!42"


# ---------------------------------------------------------------------------
# The capability set itself
# ---------------------------------------------------------------------------


def test_a_counsellor_holds_strictly_less_than_a_manager():
    """The property `can_administer` depends on, stated where it is decided.

    If these two sets ever became incomparable — a counsellor holding one thing
    a manager does not — the hierarchy would have a flat spot: neither role able
    to administer the other, for no reason anybody could explain from the
    product.
    """
    counsellor = ROLE_CAPABILITIES[UserRole.COUNSELLOR]
    manager = ROLE_CAPABILITIES[UserRole.MANAGER]

    assert counsellor < manager, (
        f"a counsellor holds something a manager does not: {sorted(counsellor - manager)}"
    )
    assert BASE_CAPABILITIES < counsellor


@pytest.mark.parametrize(
    "capability",
    [
        Capability.STUDENT_CREATE,
        Capability.STUDENT_VIEW_ANY,
        Capability.STUDENT_UPDATE_ANY,
        Capability.COURSE_VIEW_ANY,
        Capability.TRAINER_VIEW_ANY,
        Capability.BATCH_CREATE,
        Capability.BATCH_UPDATE_ANY,
        Capability.BATCH_MANAGE_SCHEDULE,
        Capability.ENROLMENT_CREATE,
        Capability.ENROLMENT_UPDATE_ANY,
        Capability.DATA_IMPORT,
        Capability.DATA_EXPORT,
    ],
)
def test_the_admissions_workflow_is_held(counsellor_user, capability):
    """Every step of registration to enrolment, one capability at a time."""
    assert has_capability(counsellor_user, capability)


@pytest.mark.parametrize(
    "capability",
    [
        # Accounts. A counsellor creates students through the student service,
        # which is a different act from administering an account.
        Capability.USER_VIEW_ANY,
        Capability.USER_CREATE,
        Capability.USER_UPDATE_ANY,
        Capability.USER_SET_ACTIVE,
        Capability.USER_CHANGE_ROLE,
        # Staff records.
        Capability.TRAINER_CREATE,
        Capability.TRAINER_UPDATE_ANY,
        # Running the training, as opposed to setting it up.
        Capability.SESSION_MANAGE_ANY,
        Capability.ATTENDANCE_CORRECT_ANY,
        Capability.ATTENDANCE_VIEW_ANY,
        Capability.DSR_VIEW_ANY,
        Capability.DSR_MANAGE_ANY,
        Capability.DSR_REVIEW,
        Capability.ASSIGNMENT_MANAGE_ANY,
        Capability.ASSESSMENT_MANAGE_ANY,
        Capability.RESULT_MANAGE_ANY,
        Capability.PROJECT_MANAGE_ANY,
        Capability.EXAM_MANAGE_ANY,
        Capability.QUESTION_VIEW_ANY,
        # Judging people.
        Capability.PERFORMANCE_VIEW_ANY,
        Capability.REVIEW_MANAGE_ANY,
        Capability.COMPLETION_APPROVE,
        Capability.CERTIFICATE_MANAGE,
        # The institution's own levers.
        Capability.ACADEMIC_CONFIGURE,
        Capability.PLATFORM_CONFIGURE,
        Capability.AUDIT_VIEW,
        Capability.COURSE_CREATE,
        Capability.COURSE_PUBLISH_ANY,
        Capability.CATEGORY_MANAGE,
        Capability.ANNOUNCEMENT_MANAGE_ANY,
        # Reading the institution in aggregate, and reading other people's
        # extractions of it.
        Capability.REPORT_VIEW_ANY,
        Capability.EXPORT_VIEW_ANY,
    ],
)
def test_the_rest_of_the_institution_is_not(counsellor_user, capability):
    assert not has_capability(counsellor_user, capability)


# ---------------------------------------------------------------------------
# The workflow, through the API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counsellor_can_register_a_student(api_client_no_csrf, counsellor_user):
    """The first step of the job, end to end through the endpoint.

    Creating a student creates a user account underneath, which means it passes
    through `can_grant_role`. A counsellor holds more than a student does, so
    the grant is allowed — and that is the only role they can hand out this way,
    because the endpoint hard-codes it.
    """
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        "/api/v1/students/",
        {
            "email": "walk.in@admissions.grras.invalid",
            "first_name": "Walk",
            "last_name": "In",
            "profile": {"city": "Jaipur", "state": "Rajasthan"},
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    created = User.objects.get(email="walk.in@admissions.grras.invalid")
    assert created.role == UserRole.STUDENT


@pytest.mark.django_db
def test_a_counsellor_can_open_a_batch_and_staff_it(
    api_client_no_csrf, counsellor_user, published_course, trainer_profile
):
    """Batch creation and trainer assignment, the two steps in the middle."""
    from datetime import timedelta

    from django.utils import timezone

    api_client_no_csrf.force_login(counsellor_user)
    today = timezone.localdate()

    created = api_client_no_csrf.post(
        "/api/v1/batches/",
        {
            "name": "Linux Essentials — Admissions intake",
            "course": str(published_course.pk),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=60)).isoformat(),
            "capacity": 20,
        },
        format="json",
    )
    assert created.status_code == 201, created.data

    staffed = api_client_no_csrf.post(
        f"/api/v1/batches/{created.data['id']}/trainer/",
        {"trainer_id": str(trainer_profile.pk)},
        format="json",
    )
    assert staffed.status_code == 200, staffed.data


@pytest.mark.django_db
def test_a_counsellor_can_enrol_a_student(
    api_client_no_csrf, counsellor_user, student_profile, batch
):
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        "/api/v1/enrollments/",
        {"student_id": str(student_profile.pk), "batch_id": str(batch.pk)},
        format="json",
    )

    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_a_counsellor_sees_the_lists_the_job_needs(
    api_client_no_csrf, counsellor_user, student_profile, trainer_profile, batch
):
    api_client_no_csrf.force_login(counsellor_user)

    for path in (
        "/api/v1/students/",
        "/api/v1/trainers/",
        "/api/v1/batches/",
        "/api/v1/enrollments/",
        "/api/v1/courses/",
    ):
        assert api_client_no_csrf.get(path).status_code == 200, path


# ---------------------------------------------------------------------------
# And the doors that stay shut
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users/",
        "/api/v1/academics/policy/",
        "/api/v1/reports/",
        "/api/v1/dashboards/admin/",
    ],
)
def test_a_counsellor_is_refused_the_institution(api_client_no_csrf, counsellor_user, path):
    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(path).status_code in (403, 404), path


@pytest.mark.django_db
def test_a_counsellor_cannot_create_a_trainer(api_client_no_csrf, counsellor_user):
    """Staffing a batch with an existing trainer is admissions work.

    Creating the trainer is not, and the capability that separates them is
    `trainer.create` rather than anything about the batch.
    """
    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        "/api/v1/trainers/",
        {
            "email": "sneaked.in@admissions.grras.invalid",
            "first_name": "Sneaked",
            "last_name": "In",
        },
        format="json",
    )

    assert response.status_code == 403
    assert not User.objects.filter(email="sneaked.in@admissions.grras.invalid").exists()


@pytest.mark.django_db
def test_a_counsellor_cannot_mint_a_colleague(api_client_no_csrf, counsellor_user):
    """The escalation worth checking explicitly.

    A counsellor creates student accounts all day, so "can they create an
    account?" already has a yes buried in it. The answer that matters is that
    the general user endpoint refuses them, whatever role they name.
    """
    api_client_no_csrf.force_login(counsellor_user)

    for role in (UserRole.COUNSELLOR, UserRole.MANAGER, UserRole.ADMIN, UserRole.SUPERADMIN):
        response = api_client_no_csrf.post(
            "/api/v1/users/",
            {
                "email": f"minted-{role}@admissions.grras.invalid",
                "first_name": "Minted",
                "last_name": "Colleague",
                "role": role,
            },
            format="json",
        )
        assert response.status_code == 403, role
        assert not User.objects.filter(email=f"minted-{role}@admissions.grras.invalid").exists()


@pytest.mark.django_db
def test_a_counsellor_cannot_touch_an_account_even_where_the_ladder_allows_it(
    api_client_no_csrf, counsellor_user, student_profile
):
    """The two gates, and why the first one alone is not the answer.

    `can_administer` says a counsellor outranks a student, because it compares
    capability sets and a counsellor holds strictly more. That is a true
    statement about the ladder and a misleading one about the product, because
    every administration endpoint also demands a `user.*` capability that a
    counsellor does not hold. Both halves are asserted together here so nobody
    reads the first without the second.
    """
    assert can_administer(counsellor_user, student_profile.user) is True
    assert not has_capability(counsellor_user, Capability.USER_UPDATE_ANY)

    api_client_no_csrf.force_login(counsellor_user)
    user_id = student_profile.user.pk

    assert (
        api_client_no_csrf.patch(
            f"/api/v1/users/{user_id}/", {"first_name": "Renamed"}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"/api/v1/users/{user_id}/set-active/", {"is_active": False}, format="json"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"/api/v1/users/{user_id}/credential-link/",
            {"action": "password_reset"},
            format="json",
        ).status_code
        == 403
    )

    student_profile.user.refresh_from_db()
    assert student_profile.user.first_name != "Renamed"
    assert student_profile.user.is_active is True


@pytest.mark.django_db
def test_a_counsellor_cannot_mark_or_correct_a_register(
    api_client_no_csrf, counsellor_user, enrollment, batch
):
    """Admissions ends where teaching begins.

    A counsellor can see the batch — they opened it — and that visibility must
    not turn into authority over what happens inside it.
    """
    from apps.sessions.models import ClassSession, SessionStatus

    session = ClassSession.objects.create(
        batch=batch,
        session_date=batch.start_date,
        start_time="09:00",
        end_time="11:00",
        status=SessionStatus.COMPLETED,
    )

    api_client_no_csrf.force_login(counsellor_user)

    response = api_client_no_csrf.post(
        f"/api/v1/sessions/{session.pk}/register/",
        {"entries": [{"enrollment_id": str(enrollment.pk), "status": "present"}]},
        format="json",
    )
    assert response.status_code in (403, 404)
    assert not enrollment.attendance.exists()


# ---------------------------------------------------------------------------
# Exporting: the gap this role opened, and the fix
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counsellor_cannot_export_an_institution_report(api_client_no_csrf, counsellor_user):
    """A file is not a weaker way to read something.

    The export endpoint used to check only `data.export`. A counsellor holds
    that capability — admissions arrive and leave as spreadsheets — and did not
    hold `report.view_any`, which would have let them stream a report they
    cannot open on screen. The export now applies the same read rule as the
    on-screen view.
    """
    api_client_no_csrf.force_login(counsellor_user)

    assert has_capability(counsellor_user, Capability.DATA_EXPORT)
    assert not has_capability(counsellor_user, Capability.REPORT_VIEW_ANY)

    response = api_client_no_csrf.get("/api/v1/reports/student_progress/export/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_manager_can_still_export(api_client_no_csrf, manager_user, enrollment):
    """The other half of the change: nothing that worked stopped working."""
    api_client_no_csrf.force_login(manager_user)

    response = api_client_no_csrf.get("/api/v1/reports/student_progress/export/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_a_trainer_still_cannot_export(api_client_no_csrf, trainer_profile):
    """A trainer may read reports about their own batches and export nothing."""
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.get("/api/v1/reports/student_progress/export/").status_code == 403


# ---------------------------------------------------------------------------
# Granting the role
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_may_appoint_a_counsellor(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        "/api/v1/users/",
        {
            "email": "new.counsellor@admissions.grras.invalid",
            "first_name": "New",
            "last_name": "Counsellor",
            "role": UserRole.COUNSELLOR,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert User.objects.get(email="new.counsellor@admissions.grras.invalid").role == (
        UserRole.COUNSELLOR
    )


@pytest.mark.django_db
def test_a_manager_may_not_appoint_one(manager_user):
    """A manager holds every capability a counsellor does, so the *containment*
    rule would allow the grant. What stops it is `user.create`, which a manager
    does not hold — running the school and staffing it are separate."""
    assert can_grant_role(manager_user, UserRole.COUNSELLOR) is True
    assert not has_capability(manager_user, Capability.USER_CREATE)


@pytest.mark.django_db
def test_a_counsellor_may_not_appoint_anyone_above_a_student(counsellor_user):
    assert can_grant_role(counsellor_user, UserRole.STUDENT) is True
    assert can_grant_role(counsellor_user, UserRole.MANAGER) is False
    assert can_grant_role(counsellor_user, UserRole.ADMIN) is False
    assert can_grant_role(counsellor_user, UserRole.SUPERADMIN) is False
