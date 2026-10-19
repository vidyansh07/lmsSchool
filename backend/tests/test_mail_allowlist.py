"""`EMAIL_RECIPIENT_ALLOWLIST`: a staging environment emails only who it lists.

What is pinned:

- empty (production), everybody may be emailed;
- set, a whole address or an `@domain` entry lets a recipient through, case
  apart, and anything else is not mailed;
- a refused notification is abandoned, not retried, and says why;
- a refused account email (an invitation) is recorded as not sent with the
  same reason, so the account page explains it.
"""

from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts import services
from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.common.mail_policy import NOT_ON_LIST, recipient_allowed
from apps.notifications.channels import send_email_message
from apps.notifications.models import EmailMessage, EmailStatus


def test_an_empty_list_lets_everybody_through(settings):
    settings.EMAIL_RECIPIENT_ALLOWLIST = []
    assert recipient_allowed("anyone@grras.com")


def test_addresses_and_domains(settings):
    settings.EMAIL_RECIPIENT_ALLOWLIST = ["@gmail.com", "Ritesh@GrrasSolutions.in"]
    assert recipient_allowed("Someone@Gmail.com")
    assert recipient_allowed("ritesh@grrassolutions.in")
    assert not recipient_allowed("deepratan@grrassolutions.in")
    assert not recipient_allowed("manager@grras.com")
    assert not recipient_allowed("trainer@sitp.grras.invalid")
    assert not recipient_allowed("")


@pytest.mark.django_db
def test_a_notification_to_someone_off_the_list_is_abandoned_not_retried(settings):
    settings.EMAIL_RECIPIENT_ALLOWLIST = ["@gmail.com"]
    message = EmailMessage.objects.create(
        to_email="manager@grras.com", subject="Report due", body="x"
    )
    mail.outbox.clear()
    assert send_email_message(message) is False
    message.refresh_from_db()
    assert message.status == EmailStatus.ABANDONED
    assert message.last_error == NOT_ON_LIST
    assert mail.outbox == []

    allowed = EmailMessage.objects.create(to_email="real.person@gmail.com", subject="Hi", body="x")
    assert send_email_message(allowed) is True
    assert [m.to for m in mail.outbox] == [["real.person@gmail.com"]]


@pytest.mark.django_db
def test_an_invitation_off_the_list_is_recorded_with_the_reason(
    settings, admin_user, branch, django_capture_on_commit_callbacks
):
    settings.EMAIL_RECIPIENT_ALLOWLIST = ["@gmail.com"]
    user = User.objects.create_user(
        email="seeded.person@grras.com",
        password=None,
        first_name="Seed",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )
    mail.outbox.clear()
    # A failure's audit row is written once the transaction ends.
    with django_capture_on_commit_callbacks(execute=True):
        reason = services.resend_invitation(user=user, actor=admin_user)
    assert reason is not None and "recipient list" in reason
    assert mail.outbox == []
    row = AuditLog.objects.get(action=AuditAction.CREDENTIAL_EMAIL_FAILED, resource_id=str(user.pk))
    assert row.context["error"] == NOT_ON_LIST
