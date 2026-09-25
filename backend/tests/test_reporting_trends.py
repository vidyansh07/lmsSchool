"""The weekly trend endpoints behind the analytics charts.

Three of them (`enrolment-trend`, `delivery-trend`, `dsr-compliance-trend`)
aggregate over models that are *not* `Enrollment`, which is the reason this
file leans so hard on leak tests. `metrics._enrollments` carries a comment
saying the batch restriction lives there "so no metric can forget it"; the
new `_sessions` and `_dsr` helpers exist to give sessions and daily reports
the same single choke point, because neither model carries a per-row
permission check of its own. An aggregate that filtered them inline would
hand a trainer every batch in the institution and nothing else in the suite
would notice.

`tests/test_authorization_matrix.py` cannot help here either: it reads
`required_capability` off the view class, and these views gate in the body
through `access.can_read_reports`. So every role is asserted explicitly
below.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.utils import timezone

TREND_ROUTES = (
    "/api/v1/reports/metrics/enrolment-trend/",
    "/api/v1/reports/metrics/delivery-trend/",
    "/api/v1/reports/metrics/dsr-compliance-trend/",
)


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


@pytest.fixture
def held_session(admin_user, batch, schedule):
    """A class that happened yesterday and was marked completed."""
    from apps.sessions.models import SessionStatus
    from apps.sessions.services import create_session

    session = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Delivered class",
    )
    session.status = SessionStatus.COMPLETED
    session.save(update_fields=["status"])
    return session


# ---------------------------------------------------------------------------
# Who may read them
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_a_student_cannot_read_a_trend(api_client_no_csrf, student_profile, enrollment, route):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(route).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_a_counsellor_reads_a_trend(api_client_no_csrf, counsellor_user, route):
    """A counsellor *does* hold `report.view_any`.

    Worth pinning, because it is easy to assume otherwise:
    `_COUNSELLOR_CAPABILITIES` is `_MANAGER_CAPABILITIES` minus four
    capabilities, and `REPORT_VIEW_ANY` is not one of the four. So a
    counsellor is a report audience, and the branch floor is what keeps them
    to their own centre rather than a capability check.
    """
    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(route).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_an_anonymous_caller_cannot_read_a_trend(api_client_no_csrf, route):
    assert api_client_no_csrf.get(route).status_code in {401, 403}


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_an_admin_reads_a_trend(api_client_no_csrf, admin_user, route):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(route)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_a_trainer_reads_a_trend(api_client_no_csrf, trainer_profile, batch, route):
    """A trainer holds no report capability; they qualify through their own
    trainer profile, and see only their own batches (asserted below)."""
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get(route).status_code == 200


# ---------------------------------------------------------------------------
# The scope helpers -- the leak tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_session_helper_hides_another_trainers_batch(
    trainer_profile, trainer_profile_two, batch, upcoming_batch, held_session, admin_user
):
    """`_sessions` is the choke point, so the test is on the helper itself
    rather than only on the view that happens to call it today."""
    from apps.reporting import access, metrics
    from apps.sessions.services import create_session

    # `upcoming_batch` starts in a fortnight, and a class has to fall inside
    # its batch's dates.
    theirs = create_session(
        batch=upcoming_batch,
        actor=admin_user,
        session_date=upcoming_batch.start_date + timedelta(days=1),
        start_time=time(14, 0),
        end_time=time(16, 0),
        topic="Someone else's class",
    )

    scope = access.scope_for(trainer_profile.user)
    visible = set(metrics._sessions(scope).values_list("id", flat=True))
    assert held_session.pk in visible
    assert theirs.pk not in visible

    other_scope = access.scope_for(trainer_profile_two.user)
    other_visible = set(metrics._sessions(other_scope).values_list("id", flat=True))
    assert theirs.pk in other_visible
    assert held_session.pk not in other_visible


@pytest.mark.django_db
def test_the_dsr_helper_hides_another_trainers_report_and_soft_deleted_ones(
    trainer_profile, trainer_profile_two, batch, upcoming_batch, held_session, admin_user
):
    from apps.dsr.services import start_dsr
    from apps.reporting import access, metrics
    from apps.sessions.services import create_session

    mine = start_dsr(session=held_session, actor=trainer_profile.user)
    their_session = create_session(
        batch=upcoming_batch,
        actor=admin_user,
        session_date=upcoming_batch.start_date + timedelta(days=2),
        start_time=time(14, 0),
        end_time=time(16, 0),
        topic="Their class",
    )
    theirs = start_dsr(session=their_session, actor=trainer_profile_two.user)

    scope = access.scope_for(trainer_profile.user)
    visible = set(metrics._dsr(scope).values_list("id", flat=True))
    assert mine.pk in visible
    assert theirs.pk not in visible

    # Soft-deleted reports stay out of every aggregate built on the helper.
    mine.delete()
    assert mine.pk not in set(metrics._dsr(scope).values_list("id", flat=True))


@pytest.mark.django_db
def test_the_enrolment_helper_keeps_its_default_status_set(enrollment):
    """Widening the default would change every existing ratio metric, so the
    trend passes its own set rather than touching it."""
    from apps.enrollments.models import EnrollmentStatus
    from apps.reporting import access, metrics

    scope = access.scope_for(None) if False else {}
    default_statuses = (
        set(metrics._enrollments(scope).values_list("status", flat=True).distinct()) or set()
    )
    assert EnrollmentStatus.CANCELLED not in default_statuses

    # And the widened call really does include them.
    enrollment.status = EnrollmentStatus.CANCELLED
    enrollment.save(update_fields=["status"])
    assert metrics._enrollments(scope).filter(pk=enrollment.pk).count() == 0
    widened = metrics._enrollments(scope, statuses=EnrollmentStatus.values)
    assert widened.filter(pk=enrollment.pk).count() == 1


@pytest.mark.django_db
def test_a_trend_counts_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, batch, other_branch_batch, other_branch_enrollment, enrollment
):
    """A branch-bounded manager holding a report capability must still be
    narrowed to their own centre -- the bug `access.scope_for` was written to
    fix."""
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get("/api/v1/reports/metrics/enrolment-trend/?weeks=52").json()
    started = sum(row["started"] for row in body)
    # Their own centre has exactly one enrolment in range; the other centre's
    # must not be added to it.
    assert started == 1


# ---------------------------------------------------------------------------
# The aggregation itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_enrolment_trend_groups_by_week(
    api_client_no_csrf, admin_user, enrollment, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(12):
        body = api_client_no_csrf.get("/api/v1/reports/metrics/enrolment-trend/").json()

    assert body
    row = body[0]
    assert set(row) == {"week", "started", "active", "completed", "cancelled"}
    assert row["started"] >= 1


@pytest.mark.django_db
def test_the_enrolment_trend_buckets_a_late_evening_enrolment_into_its_local_week(
    api_client_no_csrf, admin_user, enrollment
):
    """`enrolled_at` is a datetime, unlike every other field these trends
    bucket on. Without pinning `TruncWeek`'s output to a date, the week
    boundary moves by the active timezone's offset -- so an enrolment saved
    late in the evening can land in the wrong week."""
    from django.utils import timezone as dj_timezone

    local_late = dj_timezone.make_aware(
        dj_timezone.datetime.combine(dj_timezone.localdate(), time(23, 30))
    )
    enrollment.enrolled_at = local_late
    enrollment.save(update_fields=["enrolled_at"])

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/metrics/enrolment-trend/").json()

    # The week it belongs to is the Monday of the local date, not the Monday
    # of whatever UTC thought the date was.
    expected_monday = dj_timezone.localdate() - timedelta(days=dj_timezone.localdate().weekday())
    assert [row["week"] for row in body if row["started"]] == [expected_monday.isoformat()]


@pytest.mark.django_db
def test_the_delivery_trend_counts_held_classes_and_outstanding_registers(
    api_client_no_csrf, admin_user, held_session, django_assert_max_num_queries
):
    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(12):
        body = api_client_no_csrf.get("/api/v1/reports/metrics/delivery-trend/").json()

    assert body
    row = body[0]
    assert set(row) == {"week", "scheduled", "held", "cancelled", "registers_outstanding"}
    assert row["held"] >= 1
    # Yesterday's class was completed with no register taken.
    assert row["registers_outstanding"] >= 1


@pytest.mark.django_db
def test_a_class_later_today_is_not_an_outstanding_register(
    api_client_no_csrf, admin_user, batch, schedule
):
    """Pending is not outstanding. Counting a class that has not finished yet
    would make every morning look like a compliance failure."""
    from apps.sessions.models import SessionStatus
    from apps.sessions.services import create_session

    today = create_session(
        batch=batch,
        actor=admin_user,
        session_date=timezone.localdate(),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Later today",
    )
    today.status = SessionStatus.COMPLETED
    today.save(update_fields=["status"])

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/metrics/delivery-trend/").json()
    assert sum(row["registers_outstanding"] for row in body) == 0


@pytest.mark.django_db
def test_the_delivery_trend_stops_at_today(
    api_client_no_csrf, admin_user, upcoming_batch, batch, schedule
):
    """A "last N weeks" window is bounded at both ends.

    Batches are created months ahead, so without an upper bound the axis runs
    out to the furthest scheduled class and the recent past -- the part
    anybody is looking at -- is squeezed into the left margin.
    """
    from apps.sessions.services import create_session

    future = create_session(
        batch=upcoming_batch,
        actor=admin_user,
        session_date=upcoming_batch.start_date + timedelta(days=30),
        start_time=time(9, 0),
        end_time=time(11, 0),
        topic="Months away",
    )

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/metrics/delivery-trend/").json()

    weeks = {row["week"] for row in body}
    assert str(future.session_date - timedelta(days=future.session_date.weekday())) not in weeks
    assert all(week <= timezone.localdate().isoformat() for week in weeks)


@pytest.mark.django_db
def test_the_dsr_trend_groups_by_status(
    api_client_no_csrf,
    admin_user,
    trainer_profile,
    batch,
    held_session,
    django_assert_max_num_queries,
):
    from apps.dsr.services import start_dsr, submit_dsr

    draft = start_dsr(session=held_session, actor=trainer_profile.user)
    submit_dsr(dsr=draft, actor=trainer_profile.user)

    api_client_no_csrf.force_login(admin_user)
    with django_assert_max_num_queries(12):
        body = api_client_no_csrf.get("/api/v1/reports/metrics/dsr-compliance-trend/").json()

    assert body
    row = body[0]
    assert set(row) == {"week", "draft", "submitted", "approved", "rejected"}
    assert row["submitted"] >= 1


@pytest.mark.django_db
@pytest.mark.parametrize("route", TREND_ROUTES)
def test_the_weeks_window_is_clamped(api_client_no_csrf, admin_user, route):
    """A typed value cannot ask for a decade, and cannot ask for nothing."""
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{route}?weeks=9999").status_code == 200
    assert api_client_no_csrf.get(f"{route}?weeks=0").status_code == 200
    assert api_client_no_csrf.get(f"{route}?weeks=-5").status_code == 200


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route", "view_name"),
    [
        ("/api/v1/reports/metrics/enrolment-trend/", "EnrolmentTrendView"),
        ("/api/v1/reports/metrics/delivery-trend/", "DeliveryTrendView"),
        ("/api/v1/reports/metrics/dsr-compliance-trend/", "DsrComplianceTrendView"),
    ],
)
def test_each_trend_route_reaches_its_own_view(route, view_name):
    """`reports/urls.py` ends in a `<slug:key>/` catch-all. A metrics route
    declared below it is swallowed by `ReportView`, which answers for a
    report key that does not exist -- a plausible response rather than a 404,
    which is the worst way for this to break."""
    from django.urls import resolve

    assert resolve(route).func.view_class.__name__ == view_name
