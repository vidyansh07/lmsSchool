"""§14.2 — every role against every route, derived rather than listed.

Two sweeps.

The **route sweep** walks the real URL resolver, so it covers endpoints that did
not exist when it was written. For each one it reads the capability the view
itself declares and asks: does a caller without that capability get refused? A
hand-maintained list of endpoints is out of date the day somebody adds one; this
is not, which is the whole reason it is built this way.

The **object sweep** is written by hand, because the interesting failures are
not "can a student open the admin list" — they are "can a student open *another
student's* record by changing an id". That question needs two real objects and a
real relationship between them, and it is exactly what §14.2's examples ask for.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.roles import ROLE_CAPABILITIES, Capability, UserRole, has_capability

# ---------------------------------------------------------------------------
# Route discovery
# ---------------------------------------------------------------------------


def _routes() -> list[tuple[str, object]]:
    """Every API route with no URL parameters, paired with its view class.

    Parameterless because this sweep is about reachability, not about a specific
    record: an endpoint that needs an id is covered by the object sweep below,
    where the id can be somebody else's on purpose.
    """
    found: list[tuple[str, object]] = []

    def walk(patterns, prefix: str) -> None:
        for entry in patterns:
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns, prefix + str(entry.pattern))
            elif isinstance(entry, URLPattern):
                route = prefix + str(entry.pattern)
                if "<" in route or not route.startswith("api/v1/"):
                    continue
                view = getattr(entry.callback, "cls", None) or getattr(
                    entry.callback, "view_class", None
                )
                if view is not None:
                    found.append(("/" + route, view))

    walk(get_resolver().url_patterns, "")
    return sorted(set(found), key=lambda row: row[0])


def _declared_capabilities(view) -> tuple[str, ...]:
    """The capabilities a view requires for a GET, as the view itself states them.

    A view with a ``capability_map`` that says nothing about GET is not guarding
    GET, and neither is one that overrides ``get_permissions`` to apply the
    capability to writes only — the category list is exactly that, readable by
    anyone signed in and writable by a manager.
    """
    by_method = getattr(view, "capability_map", None)
    if by_method is not None:
        required = by_method.get("GET")
        if required is None:
            return ()
        return (required,) if isinstance(required, str) else tuple(required)
    if "get_permissions" in vars(view):
        return ()
    single = getattr(view, "required_capability", None)
    if single:
        return (single,)
    return tuple(getattr(view, "required_capabilities", ()))


ROUTES = _routes()
GUARDED = [(path, view) for path, view in ROUTES if _declared_capabilities(view)]


def test_the_sweep_actually_found_the_api():
    """A resolver change that silently emptied this file would make it vacuous."""
    assert len(ROUTES) > 30, f"only found {len(ROUTES)} routes"
    assert GUARDED, "no route declares a capability — the sweep found nothing to check"


# ---------------------------------------------------------------------------
# The route sweep
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "view"), GUARDED, ids=[path for path, _ in GUARDED])
def test_a_role_without_the_capability_is_refused(api_client_no_csrf, db, path, view):
    """For every guarded route, every role that lacks its capability is refused."""
    from apps.accounts.models import User

    required = _declared_capabilities(view)

    for role in UserRole.values:
        if all(capability in ROLE_CAPABILITIES[role] for capability in required):
            continue
        user = User.objects.create_user(
            email=f"matrix-{role}@demo.grras.invalid",
            password="Str0ng-Passphrase!42",
            first_name="Matrix",
            last_name=role.title(),
            role=role,
        )
        api_client_no_csrf.force_login(user)
        response = api_client_no_csrf.get(path)
        assert response.status_code in (403, 404), (
            f"{role} reached {path} ({response.status_code}) without {required}"
        )
        api_client_no_csrf.logout()
        user.delete()


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "view"), ROUTES, ids=[path for path, _ in ROUTES])
def test_no_route_is_reachable_anonymously_unless_it_says_so(api_client_no_csrf, path, view):
    """Deny by default, checked against the resolver rather than a list."""
    from apps.common.permissions import AllowAnyPublic

    permission_classes = getattr(view, "permission_classes", ())
    if any(issubclass(cls, AllowAnyPublic) for cls in permission_classes):
        # A deliberately public endpoint. There are a handful — certificate
        # verification, the login and CSRF routes — and each one names itself.
        return

    response = api_client_no_csrf.get(path)
    assert response.status_code in (401, 403, 405), f"{path} answered {response.status_code}"


#: The parameterless routes a *student* is meant to reach. Everything else must
#: refuse them. Written out rather than derived because "what may a student
#: see?" is a product decision, and a decision belongs in a list somebody can
#: read in a review — the derived half is the sweep that checks it holds.
STUDENT_REACHABLE = frozenset(
    {
        # Credentials and the caller's own account.
        "/api/v1/auth/csrf/",
        "/api/v1/auth/login/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/logout-all/",
        "/api/v1/auth/me/",
        "/api/v1/auth/me/email/",
        "/api/v1/auth/me/profile-image/",
        "/api/v1/auth/password/change/",
        "/api/v1/auth/password/reset/",
        "/api/v1/auth/password/reset/confirm/",
        "/api/v1/auth/email/verify/",
        "/api/v1/auth/email/verify/confirm/",
        "/api/v1/students/me/",
        # The catalogue and what they are enrolled on.
        "/api/v1/categories/",
        "/api/v1/courses/",
        "/api/v1/courses/mine/",
        "/api/v1/batches/",
        "/api/v1/enrollments/",
        "/api/v1/enrollments/mine/",
        # Academic work. The list endpoints are scoped by queryset, so a student
        # sees their own rows and nobody else's — asserted below.
        "/api/v1/assignments/",
        "/api/v1/assignments/mine/",
        "/api/v1/submissions/mine/",
        "/api/v1/assessments/",
        "/api/v1/assessments/mine/",
        "/api/v1/results/mine/",
        "/api/v1/projects/",
        "/api/v1/projects/mine/",
        "/api/v1/projects/mine/required/",
        "/api/v1/exams/",
        "/api/v1/exams/mine/",
        "/api/v1/attempts/mine/",
        "/api/v1/questions/",
        "/api/v1/completions/",
        "/api/v1/certificates/",
        "/api/v1/certificates/mine/",
        "/api/v1/progress/mine/",
        # Attendance and the timetable.
        "/api/v1/attendance/mine/",
        "/api/v1/sessions/",
        "/api/v1/sessions/today/",
        "/api/v1/calendar/",
        "/api/v1/academics/calendar/",
        "/api/v1/academics/policy/effective/",
        # Communication.
        "/api/v1/notifications/",
        "/api/v1/notifications/unread/",
        "/api/v1/notifications/preferences/",
        "/api/v1/announcements/",
        "/api/v1/discussions/",
        "/api/v1/learning/home/",
        "/api/v1/learning/upcoming/",
        "/api/v1/learning/bookmarks/",
        "/api/v1/learning/notes/",
        # Their own dashboard, and the trainer one which answers "you are not a
        # trainer" rather than refusing — see the test below.
        "/api/v1/dashboard/student/",
        "/api/v1/dashboard/trainer/",
    }
)


#: Endpoints a student may call that hold staff data, and which therefore must
#: come back empty rather than merely permitted. The distinction matters: these
#: return 200 because authorization is a queryset, and a queryset that stopped
#: filtering would still return 200.
EMPTY_FOR_A_STUDENT = (
    "/api/v1/questions/",
    "/api/v1/completions/",
    "/api/v1/certificates/",
)


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "view"), ROUTES, ids=[path for path, _ in ROUTES])
def test_a_student_reaches_only_what_a_student_should(
    api_client_no_csrf, student_profile, path, view
):
    """The broad sweep: an admin endpoint added without a check fails here.

    Most views enforce authorization inside the handler through their own
    ``access`` module rather than by declaring a capability, so the derived
    check above only covers the few that declare one. This covers the rest, from
    the other direction: whatever the mechanism, a student must not get an
    answer from a staff endpoint.
    """
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(path)

    if path in STUDENT_REACHABLE:
        assert response.status_code in (200, 201, 204, 400, 405), (
            f"{path} refused a student with {response.status_code}"
        )
    else:
        assert response.status_code in (403, 404, 405), (
            f"a student reached {path} ({response.status_code})"
        )


@pytest.mark.django_db
def test_the_endpoints_a_student_may_call_hold_nothing_of_theirs(
    api_client_no_csrf, student_profile, rival, admin_user
):
    """A 200 is not a pass mark; an empty 200 is.

    The question bank in particular holds exam answers. It returns 200 to a
    student because the rule is expressed as a queryset — so this asserts the
    queryset is still doing its job, with somebody else's records in the
    database to be leaked.
    """
    from apps.questions.models import Question, QuestionType

    Question.objects.create(
        text="What is the answer?",
        question_type=QuestionType.SHORT_ANSWER,
        marks=5,
        course=rival["batch"].course,
        created_by=admin_user,
    )

    api_client_no_csrf.force_login(student_profile.user)
    for path in EMPTY_FOR_A_STUDENT:
        body = api_client_no_csrf.get(path).json()
        assert body["count"] == 0, f"{path} returned {body['count']} rows to a student"


@pytest.mark.django_db
def test_the_trainer_dashboard_tells_a_student_they_are_not_a_trainer(
    api_client_no_csrf, student_profile, rival
):
    """It answers rather than refusing, so it must answer with nothing."""
    api_client_no_csrf.force_login(student_profile.user)
    body = api_client_no_csrf.get("/api/v1/dashboard/trainer/").json()

    assert body["is_trainer"] is False
    assert body["batches"] == []
    assert body["today_classes"] == []
    assert body["student_count"] == 0


def test_the_student_allow_list_names_only_real_routes():
    """A stale entry would quietly stop asserting anything."""
    known = {path for path, _ in ROUTES}
    assert STUDENT_REACHABLE <= known, f"gone: {sorted(STUDENT_REACHABLE - known)}"


def test_every_capability_is_held_by_somebody():
    """A capability no role holds is a permission nobody can ever exercise."""
    granted = set().union(*ROLE_CAPABILITIES.values())
    orphans = set(Capability.values) - granted
    assert not orphans, f"capabilities nobody holds: {sorted(orphans)}"


def test_the_two_teaching_roles_hold_no_administrative_capability():
    """§14.2: a trainer cannot change their own role, and neither can a student."""
    for role in (UserRole.TRAINER, UserRole.STUDENT):
        held = ROLE_CAPABILITIES[role]
        assert Capability.USER_CHANGE_ROLE not in held
        assert Capability.USER_CREATE not in held
        assert Capability.PLATFORM_CONFIGURE not in held


# ---------------------------------------------------------------------------
# The object sweep — Phases 5 to 8
# ---------------------------------------------------------------------------


@pytest.fixture
def rival(db, admin_user, published_course, trainer_profile_two):
    """A second batch, with a second trainer and a second student in it.

    Everything below asks the same question in a different place: can somebody
    reach this object by naming it, when it belongs to the other side?
    """
    from apps.accounts.models import User
    from apps.batches.models import Batch, BatchStatus
    from apps.common.identifiers import next_enrolment_code, next_student_id
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.students.models import StudentProfile

    batch = Batch.objects.create(
        code="RIVAL-001",
        name="Somebody else's batch",
        course=published_course,
        trainer=trainer_profile_two,
        start_date=date.today() - timedelta(days=20),
        end_date=date.today() + timedelta(days=40),
        capacity=30,
        status=BatchStatus.ACTIVE,
        created_by=admin_user,
    )
    user = User.objects.create_user(
        email="rival-student@demo.grras.invalid",
        password="Str0ng-Passphrase!42",
        first_name="Rival",
        last_name="Student",
        role=UserRole.STUDENT,
    )
    profile = StudentProfile.objects.create(user=user, student_id=next_student_id())
    enrollment = Enrollment.objects.create(
        code=next_enrolment_code(),
        student=profile,
        batch=batch,
        course=published_course,
        status=EnrollmentStatus.ACTIVE,
        start_date=date.today() - timedelta(days=15),
        created_by=admin_user,
    )
    return {"batch": batch, "trainer": trainer_profile_two, "enrollment": enrollment}


@pytest.mark.django_db
def test_a_student_cannot_read_another_students_progress(
    api_client_no_csrf, student_profile, rival
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/progress/{rival['enrollment'].id}/")
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_a_trainer_cannot_read_a_batch_they_do_not_teach(
    api_client_no_csrf, trainer_profile, rival
):
    """§14.2: "trainer cannot access another trainer's private batch"."""
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/batches/{rival['batch'].id}/roster/")
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_a_trainer_cannot_mark_attendance_on_a_class_they_do_not_teach(
    api_client_no_csrf, trainer_profile, rival, admin_user
):
    """§14.2: "trainer cannot modify unrelated attendance"."""
    from apps.sessions.models import ClassSession, SessionStatus

    session = ClassSession.objects.create(
        batch=rival["batch"],
        session_date=date.today(),
        start_time="10:00",
        end_time="12:00",
        topic="Somebody else's class",
        status=SessionStatus.IN_PROGRESS,
        created_by=admin_user,
    )
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/sessions/{session.id}/register/",
        {"entries": [{"enrollment_id": str(rival["enrollment"].id), "status": "present"}]},
        format="json",
    )
    assert response.status_code in (403, 404)
    # And the register must not even be readable by them.
    assert api_client_no_csrf.get(f"/api/v1/sessions/{session.id}/register/").status_code in (
        403,
        404,
    )


@pytest.mark.django_db
def test_a_student_cannot_record_their_own_test_result(
    api_client_no_csrf, student_profile, enrollment, admin_user, batch
):
    """§14.2: "student cannot change grades"."""
    from apps.assessments.models import (
        Assessment,
        AssessmentCategory,
        AssessmentDelivery,
        AssessmentStatus,
    )

    assessment = Assessment.objects.create(
        batch=batch,
        course=batch.course,
        title="Weekly Test 1",
        category=AssessmentCategory.WEEKLY_TEST,
        delivery=AssessmentDelivery.OFFLINE,
        status=AssessmentStatus.PUBLISHED,
        max_marks=50,
        passing_marks=20,
        created_by=admin_user,
    )
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assessments/{assessment.id}/results/",
        {"results": [{"enrollment_id": str(enrollment.id), "marks_obtained": "50"}]},
        format="json",
    )
    assert response.status_code in (403, 404, 405)


@pytest.mark.django_db
def test_a_student_cannot_download_another_students_submission(
    api_client_no_csrf, student_profile, rival, admin_user, batch, enrollment
):
    """§14.2: "student cannot access private files by changing IDs"."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.assignments.models import (
        Assignment,
        AssignmentStatus,
        AssignmentSubmission,
        SubmissionFile,
        SubmissionStatus,
    )

    assignment = Assignment.objects.create(
        course=batch.course,
        title="Private work",
        instructions="Hand it in.",
        status=AssignmentStatus.PUBLISHED,
        max_marks=100,
        created_by=admin_user,
    )
    submission = AssignmentSubmission.objects.create(
        assignment=assignment,
        enrollment=rival["enrollment"],
        status=SubmissionStatus.SUBMITTED,
        attempt=1,
    )
    stored = SubmissionFile.objects.create(
        submission=submission,
        file=SimpleUploadedFile("private.txt", b"somebody else's answer"),
        original_filename="private.txt",
        extension=".txt",
        size_bytes=22,
        checksum="0" * 64,
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/submissions/files/{stored.id}/download/")
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_a_manager_cannot_reach_what_only_an_administrator_may(api_client_no_csrf, db):
    """§14.2: "manager cannot access functions outside their permissions"."""
    from apps.accounts.models import User

    manager = User.objects.create_user(
        email="matrix-manager@demo.grras.invalid",
        password="Str0ng-Passphrase!42",
        first_name="Matrix",
        last_name="Manager",
        role=UserRole.MANAGER,
    )
    api_client_no_csrf.force_login(manager)

    assert not has_capability(manager, Capability.USER_CREATE)
    response = api_client_no_csrf.post(
        "/api/v1/users/",
        {
            "email": "new-admin@demo.grras.invalid",
            "first_name": "New",
            "last_name": "Admin",
            "role": "admin",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_student_cannot_reach_the_audit_log(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    for path in ("/api/v1/reports/", "/api/v1/dashboards/admin/"):
        assert api_client_no_csrf.get(path).status_code in (403, 404), path
    # POST, because the import endpoints only accept one.
    assert api_client_no_csrf.post("/api/v1/imports/students/", {}, format="json").status_code in (
        403,
        404,
    )


#: What a trainer must never reach. Short and specific: these are the endpoints
#: that administer people, configure the institution, or move data in bulk —
#: teaching authority is not institutional authority.
TRAINER_DENIED = (
    "/api/v1/users/",
    "/api/v1/students/",
    "/api/v1/trainers/",
    "/api/v1/dashboards/admin/",
    "/api/v1/academics/policy/",
    "/api/v1/certificates/templates/",
)


@pytest.mark.django_db
@pytest.mark.parametrize("path", TRAINER_DENIED)
def test_a_trainer_holds_teaching_authority_and_no_more(api_client_no_csrf, trainer_profile, path):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(path).status_code in (403, 404), path


@pytest.mark.django_db
def test_a_trainer_cannot_import_or_export_in_bulk(api_client_no_csrf, trainer_profile):
    """§8.5 gave exporting its own capability; §14.2 checks a trainer lacks it."""
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.post("/api/v1/imports/students/", {}, format="json").status_code in (
        403,
        404,
    )
    assert api_client_no_csrf.get("/api/v1/reports/student_progress/export/").status_code in (
        403,
        404,
    )


@pytest.mark.django_db
def test_a_trainers_report_contains_only_their_own_batches(
    api_client_no_csrf, trainer_profile, enrollment, rival
):
    """Phase 8 lets a trainer read reports. §14.2 checks what is in them.

    Reading is allowed and *scoped*: the catalogue opens, and the rows are the
    trainer's own cohort. A report that quietly widened to the institution would
    still answer 200, which is why this asserts on the rows.
    """
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.get("/api/v1/reports/").status_code == 200
    body = api_client_no_csrf.get("/api/v1/reports/student_progress/").json()

    codes = {row["batch_code"] for row in body["rows"]}
    assert rival["batch"].code not in codes
    assert codes <= {enrollment.batch.code}


# ---------------------------------------------------------------------------
# §11.3 — a superadmin is refused by nothing
# ---------------------------------------------------------------------------


#: Endpoints that answer "about me" rather than "about the institution". A
#: superadmin holds every capability and still has no student profile, because
#: they are not a student — that is a missing record, not a withheld permission,
#: and it is the one honest exception to "nothing refuses a superadmin".
SELF_SERVICE_ROUTES = frozenset({"/api/v1/students/me/", "/api/v1/trainers/me/"})


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "view"), ROUTES, ids=[path for path, _ in ROUTES])
def test_no_route_refuses_a_superadmin(api_client_no_csrf, db, path, view):
    """ "Superadmin holds every power" has to be true of the running system.

    A capability table can say so while a screen still refuses them, because
    authorization is expressed in several ways here — a declared capability, an
    `access` module, a queryset. This walks the resolver and checks the claim
    against all three at once.

    A 404 is allowed: it means the route wanted a record and this caller has no
    such record, which is not a refusal. A 403 is not.
    """
    if path in SELF_SERVICE_ROUTES:
        pytest.skip("answers about the caller, and a superadmin is neither a student nor a trainer")

    from apps.accounts.models import User

    superadmin = User.objects.create_user(
        email="sweep-superadmin@demo.grras.invalid",
        password="Str0ng-Passphrase!42",
        first_name="Sweep",
        last_name="Superadmin",
        role=UserRole.SUPERADMIN,
    )
    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.get(path)
    assert response.status_code != 403, f"a superadmin was refused {path}"


def test_the_superadmin_set_contains_every_other_role():
    """Strictly: every other role's capabilities are a subset, and superadmin
    holds at least one thing no other role does."""
    superadmin = ROLE_CAPABILITIES[UserRole.SUPERADMIN]

    for role, held in ROLE_CAPABILITIES.items():
        assert held <= superadmin, (
            f"{role} holds something a superadmin does not: {held - superadmin}"
        )

    others = set().union(
        *(held for role, held in ROLE_CAPABILITIES.items() if role != UserRole.SUPERADMIN)
    )
    assert superadmin - others, "superadmin holds nothing that sets it apart"


def test_the_capability_ladder_has_no_ties():
    """Each step down the ladder holds strictly less than the one above.

    This is what `can_administer` reads: if two roles ever held the same set,
    neither could administer the other and the hierarchy would quietly have a
    flat spot in it.
    """
    from itertools import pairwise

    ladder = [UserRole.SUPERADMIN, UserRole.ADMIN, UserRole.MANAGER]
    for higher, lower in pairwise(ladder):
        assert ROLE_CAPABILITIES[lower] < ROLE_CAPABILITIES[higher], (
            f"{lower} does not hold strictly less than {higher}"
        )
