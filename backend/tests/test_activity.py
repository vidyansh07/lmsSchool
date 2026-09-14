"""The administrator's activity review.

- the feed is the audit log without sign-ins, listings, downloads and
  refusals, each row with a sentence and a link;
- filters narrow by person, role, kind and date without widening anything;
- scorecards count each staff member's work for the period and add the fees
  they collected; the counsellor's card leads with registrations and money,
  the manager's with reviews;
- only an administrator (`audit.view`) reads either.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog

FEED_URL = "/api/v1/activity/feed/"
CARDS_URL = "/api/v1/activity/scorecards/"


@pytest.fixture
def a_days_work(counsellor_user, manager_user, enrollment, admin_user):
    from apps.fees import services as fees

    plan = fees.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="12000")
    fees.record_payment(plan=plan, actor=counsellor_user, amount="5000", method="upi")
    # Noise that must not appear.
    AuditLog.objects.create(
        action=AuditAction.LOGIN_SUCCEEDED, actor=counsellor_user, actor_label=counsellor_user.email
    )
    AuditLog.objects.create(
        action=AuditAction.PERMISSION_DENIED,
        actor=manager_user,
        actor_label=manager_user.email,
        result="denied",
    )
    return plan


@pytest.mark.django_db
def test_the_feed_reads_as_sentences_and_leaves_the_noise_out(
    api_client_no_csrf, admin_user, counsellor_user, a_days_work
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(FEED_URL)
    assert response.status_code == 200, response.data
    rows = response.json()["results"]
    actions = {row["action"] for row in rows}
    assert AuditAction.FEE_PAYMENT_RECORDED in actions
    assert AuditAction.LOGIN_SUCCEEDED not in actions
    assert AuditAction.PERMISSION_DENIED not in actions
    payment = next(row for row in rows if row["action"] == AuditAction.FEE_PAYMENT_RECORDED)
    assert payment["summary"].startswith("Received ₹5,000 by upi")
    assert payment["actor_label"] == counsellor_user.email
    assert payment["actor_role"] == "counsellor"
    assert payment["kind"] == "fees"
    assert payment["href"].startswith("/admissions/")


@pytest.mark.django_db
def test_the_feed_filters_by_person_kind_and_date(
    api_client_no_csrf, admin_user, counsellor_user, manager_user, a_days_work
):
    api_client_no_csrf.force_login(admin_user)
    mine = api_client_no_csrf.get(FEED_URL, {"actor": str(counsellor_user.pk)}).json()["results"]
    assert mine and all(row["actor_id"] == str(counsellor_user.pk) for row in mine)
    fees_only = api_client_no_csrf.get(FEED_URL, {"kind": "fees"}).json()["results"]
    assert fees_only and all(row["kind"] == "fees" for row in fees_only)
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    nothing = api_client_no_csrf.get(FEED_URL, {"since": tomorrow}).json()["results"]
    assert nothing == []
    backwards = api_client_no_csrf.get(FEED_URL, {"since": tomorrow, "until": "2020-01-01"})
    assert backwards.status_code == 400


@pytest.mark.django_db
def test_scorecards_count_the_work_and_the_money(
    api_client_no_csrf, admin_user, counsellor_user, a_days_work
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(CARDS_URL, {"period": "today"})
    assert response.status_code == 200, response.data
    body = response.json()
    assert body["since"] == body["until"] == timezone.localdate().isoformat()
    card = next(card for card in body["cards"] if card["user_id"] == str(counsellor_user.pk))
    assert card["role"] == "counsellor"
    assert card["fees_collected"] == "5000.00"
    figures = {figure["key"]: figure["value"] for figure in card["figures"]}
    assert figures["payments_recorded"] == 1
    # The counsellor's card leads with the admissions figures, in order.
    assert [figure["key"] for figure in card["figures"]][:2] == [
        "students_registered",
        "enrolments",
    ]
    assert card["last_active_at"] is not None
    # Noise did not count.
    assert card["total_actions"] == 3  # plan set, payment, and the derived fee status


@pytest.mark.django_db
def test_a_custom_period_needs_both_dates_in_order(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(CARDS_URL, {"period": "custom"}).status_code == 400
    assert (
        api_client_no_csrf.get(
            CARDS_URL, {"period": "custom", "since": "2026-09-10", "until": "2026-09-01"}
        ).status_code
        == 400
    )
    ok = api_client_no_csrf.get(
        CARDS_URL, {"period": "custom", "since": "2026-09-01", "until": "2026-09-10"}
    )
    assert ok.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["manager_user", "counsellor_user", "trainer", "student"])
def test_only_an_administrator_reads_the_review(request, api_client_no_csrf, fixture):
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))
    assert api_client_no_csrf.get(FEED_URL).status_code == 403
    assert api_client_no_csrf.get(CARDS_URL).status_code == 403
