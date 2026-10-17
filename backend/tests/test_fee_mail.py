"""Fee mails: a receipt for every payment, a statement when the fee is agreed.

What is pinned:

- recording a payment mails the student the receipt PDF, once the
  transaction commits — never for a payment that rolled back;
- agreeing a fee mails a statement; a second change while the first is still
  waiting in the outbox does not mail twice;
- the institution's switches stop the automatic mails, and the demo seed's
  `suppressed()` block does too;
- a counsellor can send either again by hand, a trainer cannot, and a student
  without an address gets a reason rather than a silent nothing;
- a mail problem never loses the payment;
- the institution's published `fee.receipt` template replaces the wording;
- the statement PDF is the student's and staff's, nobody else's.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.core import mail as django_mail

from apps.configuration.models import SystemSetting
from apps.configuration.settings_resolver import forget_resolved_settings
from apps.fees import mail, services
from apps.fees.models import FeePayment
from apps.notifications.models import EmailMessage, EmailStatus


def fee(enrollment, actor, **extra):
    return services.set_fee_plan(
        enrollment=enrollment, actor=actor, agreed_amount="20000", installments=[], **extra
    )


def pay(enrollment, actor, amount="5000", method="cash"):
    from apps.fees.models import FeePlan

    plan = FeePlan.objects.get(enrollment=enrollment)
    return services.record_payment(plan=plan, actor=actor, amount=amount, method=method)


def settings(**fields):
    row = SystemSetting.objects.first() or SystemSetting.objects.create()
    for name, value in fields.items():
        setattr(row, name, value)
    row.save()
    forget_resolved_settings()


@pytest.mark.django_db
def test_a_payment_mails_the_receipt_pdf_once_it_commits(
    counsellor_user, enrollment, django_capture_on_commit_callbacks
):
    fee(enrollment, counsellor_user)
    django_mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        payment = pay(enrollment, counsellor_user, method="upi")

    receipts = [m for m in django_mail.outbox if "Receipt" in m.subject]
    assert len(receipts) == 1
    sent = receipts[0]
    assert sent.to == [enrollment.student.user.email]
    assert payment.receipt_number in sent.subject
    assert "₹5,000.00" in sent.body and "Balance: ₹15,000.00" in sent.body
    (filename, content, mimetype) = sent.attachments[0]
    assert filename == f"receipt-{payment.receipt_number}.pdf"
    assert mimetype == "application/pdf"
    assert content.startswith(b"%PDF")
    row = EmailMessage.objects.get(template=mail.RECEIPT_KIND)
    assert row.status == EmailStatus.SENT


@pytest.mark.django_db
def test_a_payment_that_rolls_back_mails_nothing(
    counsellor_user, enrollment, django_capture_on_commit_callbacks
):
    from django.db import transaction

    fee(enrollment, counsellor_user)
    django_mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        try:
            with transaction.atomic():
                pay(enrollment, counsellor_user, method="cash")
                raise RuntimeError("the request failed after the payment")
        except RuntimeError:
            pass
    assert not FeePayment.objects.exists()
    assert not EmailMessage.objects.filter(template=mail.RECEIPT_KIND).exists()
    assert not [m for m in django_mail.outbox if "Receipt" in m.subject]
    assert callbacks == []


@pytest.mark.django_db
def test_agreeing_a_fee_mails_one_statement_even_if_the_schedule_follows(
    counsellor_user, enrollment, django_capture_on_commit_callbacks
):
    from datetime import timedelta

    from django.utils import timezone

    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="20000",
        discount_percent="10",
        discount_reason="Early bird",
        installments=[],
    )
    # Still waiting in the outbox: the follow-up change reuses it.
    services.set_installments(
        plan=plan,
        actor=counsellor_user,
        items=[
            {"amount": "9000", "due_on": timezone.localdate()},
            {"amount": "9000", "due_on": timezone.localdate() + timedelta(days=30)},
        ],
    )
    rows = EmailMessage.objects.filter(template=mail.STATEMENT_KIND)
    assert rows.count() == 1
    assert "Discount: ₹2,000.00 (10%)" in rows.get().body

    django_mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        mail.email_statement(plan, automatic=False)
    sent = django_mail.outbox[-1]
    filename, content, _ = sent.attachments[0]
    assert filename == f"fee-statement-{enrollment.code}.pdf"
    assert content.startswith(b"%PDF")


@pytest.mark.django_db
@pytest.mark.parametrize("switch", ["fee_receipt_email_enabled", "notification_email_enabled"])
def test_the_institution_can_turn_receipt_mail_off(counsellor_user, enrollment, switch):
    fee(enrollment, counsellor_user)
    settings(**{switch: False})
    pay(enrollment, counsellor_user, method="cash")
    assert not EmailMessage.objects.filter(template=mail.RECEIPT_KIND).exists()


@pytest.mark.django_db
def test_the_statement_switch_is_separate(counsellor_user, enrollment):
    settings(fee_statement_email_enabled=False)
    fee(enrollment, counsellor_user)
    pay(enrollment, counsellor_user, method="cash")
    assert not EmailMessage.objects.filter(template=mail.STATEMENT_KIND).exists()
    assert EmailMessage.objects.filter(template=mail.RECEIPT_KIND).count() == 1


@pytest.mark.django_db
def test_seeding_and_imports_send_no_fee_mail(counsellor_user, enrollment):
    with mail.suppressed():
        fee(enrollment, counsellor_user)
        pay(enrollment, counsellor_user, method="cash")
    assert not EmailMessage.objects.filter(
        template__in=[mail.RECEIPT_KIND, mail.STATEMENT_KIND]
    ).exists()


@pytest.mark.django_db
def test_a_mail_problem_never_loses_the_payment(counsellor_user, enrollment):
    fee(enrollment, counsellor_user)
    with mock.patch.object(mail, "_receipt_text", side_effect=RuntimeError("template bug")):
        payment = pay(enrollment, counsellor_user, method="cash")
    assert FeePayment.objects.filter(pk=payment.pk).exists()
    assert not EmailMessage.objects.filter(template=mail.RECEIPT_KIND).exists()


@pytest.mark.django_db
def test_counsellor_resends_a_receipt_and_sees_the_mail_log(
    api_client_no_csrf, counsellor_user, enrollment, django_capture_on_commit_callbacks
):
    fee(enrollment, counsellor_user)
    payment = pay(enrollment, counsellor_user, method="cash")
    api_client_no_csrf.force_login(counsellor_user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client_no_csrf.post(f"/api/v1/fees/payments/{payment.pk}/email-receipt/")
    assert response.status_code == 202, response.json()
    assert response.json()["to_email"] == enrollment.student.user.email

    log = api_client_no_csrf.get(f"/api/v1/fees/enrollments/{enrollment.pk}/emails/")
    assert log.status_code == 200
    kinds = [row["kind"] for row in log.json()]
    assert kinds.count("fee_receipt") == 2
    assert "fee_statement" in kinds
    resent = log.json()[0]
    assert resent["kind"] == "fee_receipt"
    assert resent["receipt_number"] == payment.receipt_number
    assert resent["status"] == "sent"


@pytest.mark.django_db
def test_a_trainer_cannot_send_fee_mail(api_client_no_csrf, counsellor_user, trainer, enrollment):
    fee(enrollment, counsellor_user)
    payment = pay(enrollment, counsellor_user, method="cash")
    api_client_no_csrf.force_login(trainer)
    assert (
        api_client_no_csrf.post(f"/api/v1/fees/payments/{payment.pk}/email-receipt/").status_code
        == 403
    )
    assert (
        api_client_no_csrf.post(
            f"/api/v1/fees/enrollments/{enrollment.pk}/email-statement/"
        ).status_code
        == 403
    )
    assert (
        api_client_no_csrf.get(f"/api/v1/fees/enrollments/{enrollment.pk}/emails/").status_code
        == 403
    )


@pytest.mark.django_db
def test_sending_by_hand_says_why_it_cannot(api_client_no_csrf, counsellor_user, enrollment):
    fee(enrollment, counsellor_user)
    user = enrollment.student.user
    user.is_active = False
    user.save(update_fields=["is_active"])
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(f"/api/v1/fees/enrollments/{enrollment.pk}/email-statement/")
    assert response.status_code == 400
    assert "no active email address" in str(response.json())


@pytest.mark.django_db
def test_the_published_template_replaces_the_wording(counsellor_user, enrollment, admin_user):
    from apps.communication import services as communication

    template = communication.create_template(
        actor=admin_user,
        key=mail.RECEIPT_TEMPLATE_KEY,
        name="Fee receipt",
        channel="email",
        kind="fee.receipt",
    )
    version = template.current_version or template.versions.get(number=1)
    version = communication.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Payment {{payment.receipt_number}} for {{student.first_name}}",
        body_text="We got {{payment.amount}}. Left: {{fee.balance}}.",
        body_html="<p>We got {{payment.amount}}.</p>",
        variables=list(mail.RECEIPT_VARIABLES),
    )
    version = communication.approve_version(actor=admin_user, version=version)
    communication.publish_version(actor=admin_user, version=version)

    fee(enrollment, counsellor_user)
    payment = pay(enrollment, counsellor_user, method="cash")
    row = EmailMessage.objects.get(template=mail.RECEIPT_KIND)
    assert row.subject == (
        f"Payment {payment.receipt_number} for {enrollment.student.user.first_name}"
    )
    assert row.body == "We got ₹5,000.00. Left: ₹15,000.00."


@pytest.mark.django_db
def test_the_statement_pdf_is_for_the_student_and_staff_only(
    api_client_no_csrf, counsellor_user, enrollment, other_student_profile
):
    fee(enrollment, counsellor_user)
    url = f"/api/v1/fees/enrollments/{enrollment.pk}/statement/"

    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

    api_client_no_csrf.force_login(enrollment.student.user)
    assert api_client_no_csrf.get(url).status_code == 200

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get(url).status_code == 404
