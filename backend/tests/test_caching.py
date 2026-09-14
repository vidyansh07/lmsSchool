"""Application caching (20a): dashboards and overviews for a minute per person,
branding and public settings until changed. Never across people, never past a
write that would make the value a lie.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache

from apps.common import caching


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def test_remember_computes_once_and_forget_moves_on():
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    assert caching.remember("t", ("a",), 60, compute) == {"n": 1}
    assert caching.remember("t", ("a",), 60, compute) == {"n": 1}
    assert caching.remember("t", ("b",), 60, compute) == {"n": 2}
    caching.forget("t")
    assert caching.remember("t", ("a",), 60, compute) == {"n": 3}


@pytest.mark.django_db
def test_the_admin_dashboard_is_held_for_a_minute_per_person(
    api_client_no_csrf, admin_user, unbounded_superadmin, batch
):
    api_client_no_csrf.force_login(admin_user)
    first = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    from apps.batches.models import BatchStatus
    from apps.batches.services import set_batch_status

    set_batch_status(batch=batch, target=BatchStatus.CANCELLED, actor=admin_user)
    again = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    assert again["active_batches"] == first["active_batches"]
    # A different person is never served this person's figures.
    api_client_no_csrf.force_login(unbounded_superadmin)
    theirs = api_client_no_csrf.get("/api/v1/dashboards/admin/").json()
    assert theirs["active_batches"] == first["active_batches"] - 1


@pytest.mark.django_db
def test_the_fees_overview_forgets_on_every_ledger_write(
    api_client_no_csrf, counsellor_user, enrollment
):
    from apps.fees import services as fees

    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get("/api/v1/fees/overview/").json()["outstanding_total"] == "0.00"
    fees.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="5000")
    assert api_client_no_csrf.get("/api/v1/fees/overview/").json()["outstanding_total"] == "5000.00"


@pytest.mark.django_db
def test_branding_and_public_settings_are_held_until_changed(
    api_client_no_csrf, unbounded_superadmin, admin_user
):
    api_client_no_csrf.force_login(unbounded_superadmin)
    before = api_client_no_csrf.get("/api/v1/branding/").json()
    api_client_no_csrf.patch("/api/v1/branding/", {"brand_color": "#123456"}, format="json")
    after = api_client_no_csrf.get("/api/v1/branding/").json()
    assert after != before

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.get("/api/v1/settings/public/")
    changed = api_client_no_csrf.patch(
        "/api/v1/settings/", {"institution_name": "Grras Pune"}, format="json"
    )
    assert changed.status_code == 200, changed.data
    assert (
        api_client_no_csrf.get("/api/v1/settings/public/").json()["institution_name"]
        == "Grras Pune"
    )
