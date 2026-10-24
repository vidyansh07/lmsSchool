"""The institution's own short lists: academic years, banks, payment
categories and tax groups.

All four were readable and none was writable — the settings screens had
nothing to call. Three rules hold across them, and they are why this is a
service rather than four generic viewsets:

* exactly one year is current, and at most one of everything else is the
  default: setting one unsets the other in the same transaction;
* nothing is deleted, because a bank or a category is referenced by records
  that outlive the institute's interest in it — `is_active` takes it out of
  the pickers and leaves history legible;
* every change is audited, because these lists quietly change the meaning of
  money.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditAction, AuditLog
from apps.fees.models import PaymentCategory, TaxGroup
from apps.organisation.models import AcademicYear, Bank

pytestmark = pytest.mark.django_db

YEARS = "/api/v1/academic-years/"
BANKS = "/api/v1/banks/"
CATEGORIES = "/api/v1/fees/payment-categories/"
TAXES = "/api/v1/fees/tax-groups/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# Academic years
# ---------------------------------------------------------------------------


def test_an_administrator_adds_a_year_and_makes_it_current(api_client_no_csrf, admin_user):
    client = _client(admin_user)
    AcademicYear.objects.create(name="2025-26", is_current=True)

    created = client.post(
        YEARS,
        {"name": "2026-27", "starts_on": "2026-04-01", "ends_on": "2027-03-31"},
        format="json",
    )
    assert created.status_code == 201, created.content
    year_id = created.json()["id"]
    assert created.json()["is_current"] is False

    moved = client.patch(f"{YEARS}{year_id}/", {"is_current": True}, format="json")
    assert moved.status_code == 200, moved.content
    # One current year, always.
    assert list(AcademicYear.objects.filter(is_current=True).values_list("name", flat=True)) == [
        "2026-27"
    ]


def test_a_year_cannot_be_un_currented_leaving_none(api_client_no_csrf, admin_user):
    year = AcademicYear.objects.create(name="2026-27", is_current=True)
    refused = _client(admin_user).patch(f"{YEARS}{year.pk}/", {"is_current": False}, format="json")
    assert refused.status_code == 400
    assert "another year current" in str(refused.json())
    year.refresh_from_db()
    assert year.is_current is True


def test_a_year_cannot_end_before_it_starts(api_client_no_csrf, admin_user):
    refused = _client(admin_user).post(
        YEARS,
        {"name": "2026-27", "starts_on": "2026-04-01", "ends_on": "2026-03-31"},
        format="json",
    )
    assert refused.status_code == 400
    assert "end before it starts" in str(refused.json())


def test_two_years_cannot_share_a_name(api_client_no_csrf, admin_user):
    AcademicYear.objects.create(name="2026-27")
    refused = _client(admin_user).post(YEARS, {"name": "2026-27"}, format="json")
    assert refused.status_code == 409


def test_a_counsellor_reads_the_years_but_changes_none(
    api_client_no_csrf, admin_user, counsellor_user
):
    year = AcademicYear.objects.create(name="2026-27")
    client = _client(counsellor_user)

    assert client.get(YEARS).status_code == 200
    assert client.post(YEARS, {"name": "2027-28"}, format="json").status_code == 403
    assert client.patch(f"{YEARS}{year.pk}/", {"name": "Nope"}, format="json").status_code == 403


# ---------------------------------------------------------------------------
# Banks
# ---------------------------------------------------------------------------


def test_a_bank_is_added_and_retired_rather_than_deleted(api_client_no_csrf, admin_user):
    client = _client(admin_user)
    created = client.post(BANKS, {"name": "HDFC Bank"}, format="json")
    assert created.status_code == 201, created.content
    bank_id = created.json()["id"]

    retired = client.patch(f"{BANKS}{bank_id}/", {"is_active": False}, format="json")
    assert retired.status_code == 200
    assert Bank.objects.get(pk=bank_id).is_active is False
    # Still listed for whoever manages the list, or it could never come back.
    names = [row["name"] for row in client.get(BANKS).json()]
    assert "HDFC Bank" in names


def test_the_payment_dialog_sees_only_the_active_banks(
    api_client_no_csrf, admin_user, counsellor_user
):
    Bank.objects.create(name="Old Bank", is_active=False)
    Bank.objects.create(name="HDFC Bank")

    listed = [row["name"] for row in _client(counsellor_user).get(BANKS).json()]
    assert listed == ["HDFC Bank"]


def test_two_banks_cannot_share_a_name_whatever_the_casing(api_client_no_csrf, admin_user):
    """ "HDFC", "HDFC Bank" and "hdfc bank" are one bank and three rows, and
    three rows is the problem the list exists to solve."""
    client = _client(admin_user)
    client.post(BANKS, {"name": "HDFC Bank"}, format="json")
    assert client.post(BANKS, {"name": "hdfc bank"}, format="json").status_code == 409


# ---------------------------------------------------------------------------
# Payment categories and tax groups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "model"),
    [(CATEGORIES, PaymentCategory), (TAXES, TaxGroup)],
)
def test_only_one_row_is_the_default(api_client_no_csrf, admin_user, url, model):
    client = _client(admin_user)
    first = client.post(url, {"name": "Hostel deposit", "is_default": True}, format="json")
    assert first.status_code == 201, first.content
    second = client.post(url, {"name": "Lab fee", "is_default": True}, format="json")
    assert second.status_code == 201, second.content

    defaults = list(model.objects.filter(is_default=True).values_list("name", flat=True))
    assert defaults == ["Lab fee"]


@pytest.mark.parametrize("url", [CATEGORIES, TAXES])
def test_changing_a_row_is_audited_with_what_changed(api_client_no_csrf, admin_user, url):
    client = _client(admin_user)
    created = client.post(url, {"name": "Exam fee"}, format="json")
    row_id = created.json()["id"]
    client.patch(f"{url}{row_id}/", {"name": "Examination fee"}, format="json")

    entries = AuditLog.objects.filter(action=AuditAction.SETTINGS_LIST_CHANGED).order_by(
        "created_at"
    )
    assert [entry.context["changed"] for entry in entries][-1] == ["name"]
    assert entries.last().context["name"] == "Examination fee"


@pytest.mark.parametrize("url", [CATEGORIES, TAXES])
def test_a_counsellor_reads_the_list_but_changes_none(
    api_client_no_csrf, counsellor_user, admin_user, url
):
    _client(admin_user).post(url, {"name": "Hostel deposit"}, format="json")
    client = _client(counsellor_user)

    assert client.get(url).status_code == 200
    assert client.post(url, {"name": "Sneaky"}, format="json").status_code == 403


@pytest.mark.parametrize("url", [CATEGORIES, TAXES])
def test_a_student_sees_neither_list(api_client_no_csrf, student_profile, url):
    assert _client(student_profile.user).get(url).status_code == 403
