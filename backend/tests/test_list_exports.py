"""Everything exportable: the list screens as reports, in Excel, PDF and CSV.

- the six list-screen reports run through the same scoped querysets the
  screens use, with the extra filters (student, since/until, actor, kind);
- `?format=xlsx|pdf` renders inline up to the limit and refuses past it with a
  409 that says to queue a background export;
- a queued export carries the extra filters and tells the requester when it
  is ready;
- a payment has a receipt PDF, for staff who can see the enrolment and the
  student it belongs to, and nobody else.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.fees import services as fees

EXPORTS_URL = "/api/v1/reports/exports/"


def _url(key: str, **params) -> str:
    from urllib.parse import urlencode

    return f"/api/v1/reports/{key}/export/" + (f"?{urlencode(params)}" if params else "")


@pytest.fixture
def ledger(counsellor_user, enrollment, other_enrollment):
    plan = fees.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="10000")
    payment = fees.record_payment(plan=plan, actor=counsellor_user, amount="2500", method="upi")
    other = fees.set_fee_plan(
        enrollment=other_enrollment, actor=counsellor_user, agreed_amount="8000"
    )
    fees.record_payment(plan=other, actor=counsellor_user, amount="1000", method="cash")
    return payment


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key", ["students", "enrollments", "fee_payments", "daily_reports", "batches", "activity"]
)
def test_every_list_report_runs_and_exports_in_every_format(
    api_client_no_csrf, admin_user, ledger, key
):
    api_client_no_csrf.force_login(admin_user)
    page = api_client_no_csrf.get(f"/api/v1/reports/{key}/")
    assert page.status_code == 200, (key, page.data)
    assert page.json()["columns"]

    csv = api_client_no_csrf.get(_url(key))
    assert csv.status_code == 200
    assert csv["Content-Type"].startswith("text/csv")

    xlsx = api_client_no_csrf.get(_url(key, **{"as": "xlsx"}))
    assert xlsx.status_code == 200, key
    assert xlsx["Content-Type"].startswith("application/vnd.openxmlformats")
    assert xlsx.content[:2] == b"PK"

    pdf = api_client_no_csrf.get(_url(key, **{"as": "pdf"}))
    assert pdf.status_code == 200, key
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_the_ledger_export_carries_the_figures(api_client_no_csrf, admin_user, ledger, enrollment):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get("/api/v1/reports/fee_payments/").json()
    rows = body["rows"]
    mine = next(row for row in rows if row["receipt_number"] == ledger.receipt_number)
    assert mine["amount"] == "2,500.00"
    assert mine["method"] == "UPI"
    assert mine["student_code"] == enrollment.student.student_id

    students = api_client_no_csrf.get("/api/v1/reports/students/").json()["rows"]
    me = next(row for row in students if row["student_code"] == enrollment.student.student_id)
    assert me["fee_paid"] == "2,500.00"
    assert me["fee_balance"] == "7,500.00"


@pytest.mark.django_db
def test_a_student_filter_narrows_the_ledger_to_one_person(
    api_client_no_csrf, admin_user, ledger, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    narrowed = api_client_no_csrf.get(
        f"/api/v1/reports/fee_payments/?student={enrollment.student_id}"
    ).json()["rows"]
    assert len(narrowed) == 1
    assert narrowed[0]["student_code"] == enrollment.student.student_id
    # An id the caller cannot see narrows to nothing rather than to everything.
    import uuid

    nothing = api_client_no_csrf.get(f"/api/v1/reports/fee_payments/?student={uuid.uuid4()}")
    assert nothing.json()["rows"] == []


@pytest.mark.django_db
def test_an_inline_excel_export_refuses_past_the_limit(
    api_client_no_csrf, admin_user, ledger, monkeypatch
):
    from apps.reporting import views

    monkeypatch.setattr(views, "SYNC_ROW_LIMIT", 1)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_url("fee_payments", **{"as": "xlsx"}))
    assert response.status_code == 409
    assert "Queue a background export" in str(response.json()["error"]["details"])
    # CSV still streams whatever the size.
    assert api_client_no_csrf.get(_url("fee_payments")).status_code == 200


@pytest.mark.django_db
def test_a_queued_export_keeps_its_filters_and_tells_the_requester(
    api_client_no_csrf, admin_user, ledger, enrollment
):
    from apps.notifications.models import Notification, NotificationKind
    from apps.reporting.models import ExportJob, ExportStatus

    api_client_no_csrf.force_login(admin_user)
    since = (timezone.localdate() - timedelta(days=1)).isoformat()
    response = api_client_no_csrf.post(
        EXPORTS_URL,
        {
            "report_key": "activity",
            "format": "xlsx",
            "since": since,
            "until": timezone.localdate().isoformat(),
            "kind": "fees",
        },
        format="json",
    )
    assert response.status_code == 202, response.data
    job = ExportJob.objects.get(pk=response.json()["id"])
    assert job.filters["kind"] == "fees"
    assert job.filters["since"] == since
    # Eager in tests: the job has already run.
    assert job.status == ExportStatus.COMPLETED, job.error
    assert job.row_count >= 2
    note = Notification.objects.get(recipient=admin_user, kind=NotificationKind.EXPORT_READY)
    assert "Activity record" in note.title
    assert note.link_path == "/admin/reports#exports"


@pytest.mark.django_db
def test_the_activity_export_needs_the_audit_right(api_client_no_csrf, manager_user, ledger):
    api_client_no_csrf.force_login(manager_user)
    body = api_client_no_csrf.get("/api/v1/reports/activity/").json()
    assert body["rows"] == []


@pytest.mark.django_db
def test_a_receipt_pdf_for_staff_and_the_student(
    api_client_no_csrf, counsellor_user, other_branch_manager, ledger, enrollment
):
    url = f"/api/v1/fees/payments/{ledger.pk}/receipt/"
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert ledger.receipt_number in response["Content-Disposition"]

    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(url).status_code == 200

    api_client_no_csrf.force_login(other_branch_manager)
    assert api_client_no_csrf.get(url).status_code == 404


@pytest.mark.django_db
def test_a_voided_receipt_still_renders(api_client_no_csrf, counsellor_user, manager_user, ledger):
    fees.void_payment(payment=ledger, actor=manager_user, reason="Entered twice")
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get(f"/api/v1/fees/payments/{ledger.pk}/receipt/")
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"
