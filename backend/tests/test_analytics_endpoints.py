"""The two analytics aggregates that are not reports.

Fee collections and the admissions funnel both live outside
`apps/reporting` on purpose: the scoping that matters for them is
`visible_enrollments`/`visible_students` and the capabilities are
`fee.view_any` and `student.create`, which is what the fees and dashboards
apps already established. Both views declare `required_capability`, so
`tests/test_authorization_matrix.py` sweeps them automatically -- the
per-role tests here are about *scope*, which that sweep does not check.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone


@pytest.fixture(autouse=True)
def _forget_policy_memo():
    from apps.common.request_context import clear_scope

    clear_scope()
    yield
    clear_scope()


@pytest.fixture
def paid_enrollment(admin_user, enrollment):
    """A fee plan with one live receipt against it."""
    from apps.fees.services import record_payment, set_fee_plan

    plan = set_fee_plan(
        enrollment=enrollment,
        actor=admin_user,
        agreed_amount=Decimal("10000.00"),
    )
    record_payment(
        plan=plan,
        actor=admin_user,
        amount=Decimal("2500.00"),
        paid_on=timezone.localdate(),
    )
    return plan


# ---------------------------------------------------------------------------
# Fee collections trend
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counsellor_reads_the_collections_trend(
    api_client_no_csrf, counsellor_user, paid_enrollment
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get("/api/v1/fees/collections-trend/")
    assert response.status_code == 200
    body = response.json()
    assert body
    assert set(body[0]) == {"week", "amount", "receipts"}
    assert Decimal(body[0]["amount"]) == Decimal("2500.00")
    assert body[0]["receipts"] == 1


@pytest.mark.django_db
def test_a_student_cannot_read_the_collections_trend(
    api_client_no_csrf, student_profile, enrollment
):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/fees/collections-trend/").status_code == 403


@pytest.mark.django_db
def test_a_trainer_cannot_read_the_collections_trend(api_client_no_csrf, trainer_profile):
    """A trainer holds no fee capability -- fees are not their business."""
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get("/api/v1/fees/collections-trend/").status_code == 403


@pytest.mark.django_db
def test_a_voided_receipt_is_not_money(api_client_no_csrf, admin_user, paid_enrollment):
    """A cancelled receipt was never a collection, and a chart that counted
    it would disagree with the ledger it came from."""
    from apps.fees.models import FeePayment
    from apps.fees.services import void_payment

    payment = FeePayment.objects.get(plan=paid_enrollment)
    void_payment(payment=payment, actor=admin_user, reason="Entered twice")

    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/fees/collections-trend/").json()
    assert sum(Decimal(row["amount"]) for row in body) == Decimal("0")


@pytest.mark.django_db
def test_the_collections_trend_counts_only_the_callers_own_centre(
    api_client_no_csrf, manager_user, paid_enrollment, other_branch_enrollment, unbounded_superadmin
):
    from apps.fees.services import record_payment, set_fee_plan

    other_plan = set_fee_plan(
        enrollment=other_branch_enrollment,
        actor=unbounded_superadmin,
        agreed_amount=Decimal("8000.00"),
    )
    record_payment(
        plan=other_plan,
        actor=unbounded_superadmin,
        amount=Decimal("4000.00"),
        paid_on=timezone.localdate(),
    )

    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get("/api/v1/fees/collections-trend/").json()
    # Their own centre took 2,500. The other centre's 4,000 must not be in it.
    assert sum(Decimal(row["amount"]) for row in body) == Decimal("2500.00")


@pytest.mark.django_db
def test_the_collections_window_is_clamped(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get("/api/v1/fees/collections-trend/?weeks=9999").status_code == 200
    assert api_client_no_csrf.get("/api/v1/fees/collections-trend/?weeks=0").status_code == 200


# ---------------------------------------------------------------------------
# Admissions pipeline
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_pipeline_stages_nest(api_client_no_csrf, counsellor_user, paid_enrollment):
    """Every stage is a subset of the one above it. If a later stage ever
    exceeded an earlier one, a conversion would read over 100% and the
    aggregate would be wrong rather than the chart."""
    api_client_no_csrf.force_login(counsellor_user)
    body = api_client_no_csrf.get("/api/v1/dashboards/counsellor/pipeline/").json()

    counts = [stage["count"] for stage in body["stages"]]
    assert counts == sorted(counts, reverse=True)
    assert [stage["key"] for stage in body["stages"]] == [
        "registered",
        "enrolled",
        "active",
        "with_plan",
        "paying",
    ]
    assert counts[0] >= 1


@pytest.mark.django_db
def test_the_pipeline_carries_a_weekly_shape(api_client_no_csrf, counsellor_user, enrollment):
    api_client_no_csrf.force_login(counsellor_user)
    body = api_client_no_csrf.get("/api/v1/dashboards/counsellor/pipeline/").json()
    assert body["weekly"]
    assert set(body["weekly"][0]) == {"week", "registered", "enrolled"}


@pytest.mark.django_db
def test_a_student_cannot_read_the_pipeline(api_client_no_csrf, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/dashboards/counsellor/pipeline/").status_code == 403


@pytest.mark.django_db
def test_a_trainer_cannot_read_the_pipeline(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get("/api/v1/dashboards/counsellor/pipeline/").status_code == 403


@pytest.mark.django_db
def test_the_pipeline_counts_only_the_callers_own_centre(
    api_client_no_csrf, counsellor_user, student_profile, other_branch_student, enrollment
):
    api_client_no_csrf.force_login(counsellor_user)
    body = api_client_no_csrf.get("/api/v1/dashboards/counsellor/pipeline/?weeks=52").json()
    registered = next(s["count"] for s in body["stages"] if s["key"] == "registered")
    # Their own centre has the one student; the other centre's must not be
    # added to it.
    assert registered == 1


@pytest.mark.django_db
def test_the_pipeline_is_two_queries_regardless_of_stage_count(
    counsellor_user, paid_enrollment, django_assert_max_num_queries
):
    """Five stages from one queryset, not five queries.

    Asserted against the aggregate rather than the request, deliberately: a
    round trip through the view also pays for the session, the user and the
    capability resolution, so an end-to-end budget here would be measuring
    the auth stack and would drift every time that changed. The thing worth
    pinning is that adding a sixth stage costs no extra query.

    Six: four to resolve what this counsellor may see (`visible_students`
    walks the role and scope tables) and two aggregates -- the five stages in
    one grouped query, the weekly shape in another. Five independent stage
    counts would have been nine.
    """
    from apps.dashboards.views import _counsellor_pipeline

    with django_assert_max_num_queries(6):
        _counsellor_pipeline(counsellor_user, weeks=12)
