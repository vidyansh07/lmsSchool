"""The account flow, end to end: invited, accepted, reset, and told the truth.

What is pinned:

- a new account gets an *invitation* — a set-your-password link that lasts
  `AUTH_TOKEN_INVITATION_TTL_DAYS`, not the one-hour reset — and the email says
  how long it lasts;
- accepting it (or any password link) sets the password *and* verifies the
  email it was opened from, so nobody is asked to verify straight after;
- "accepted" means a password of their own; "Resend invitation" sends a new
  set-password link that supersedes the old one, never a verify-email link;
- "Forgot password" for somebody who never set one sends them the invitation;
- when the mail service refuses a message, the person who asked is told in
  words, the account's page shows it, and the provider's raw text (which
  carries account identifiers) is never shown; an unsent one-time code does
  not count against the cooldown;
- an administrator who created a fellow administrator can resend that
  person's invitation until it is accepted, and not after;
- the account page shows the invitation, the last account email, and what the
  person can do.
"""

from __future__ import annotations

import smtplib
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import AccountToken, TokenPurpose, User, UserRole
from apps.audit.models import AuditAction, AuditLog
from tests.conftest import NEW_PASSWORD

USERS_URL = "/api/v1/users/"
CONFIRM_URL = "/api/v1/auth/password/reset/confirm/"
RESET_URL = "/api/v1/auth/password/reset/"
REQUEST_CODE = "/api/v1/auth/step-up/request-code/"

REFUSED = smtplib.SMTPDataError(
    554,
    b"Access denied: User 'arn:aws:iam::123456789012:user/x' is not authorized to perform "
    b"'ses:SendRawEmail'",
)


def _token_from(message) -> str:
    from urllib.parse import parse_qs, urlparse

    link = next(word for word in message.body.split() if "token=" in word)
    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.django_db
def test_a_new_account_is_invited_for_days_and_accepting_verifies_the_email(
    api_client_no_csrf, admin_user, branch, django_capture_on_commit_callbacks, settings
):
    settings.AUTH_TOKEN_INVITATION_TTL_DAYS = 7
    api_client_no_csrf.force_login(admin_user)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        created = api_client_no_csrf.post(
            USERS_URL,
            {
                "email": "new.counsellor@example.test",
                "first_name": "Nita",
                "role": "counsellor",
                "branch": str(branch.pk),
            },
            format="json",
        )
    assert created.status_code == 201, created.json()
    user = User.objects.get(email="new.counsellor@example.test")
    token = AccountToken.objects.get(user=user, purpose=TokenPurpose.INVITATION)
    assert token.expires_at - timezone.now() > timedelta(days=6)

    (invitation,) = [m for m in mail.outbox if m.to == [user.email]]
    assert "expires in 7 day(s)" in invitation.body
    assert "invite=1" in invitation.body

    record = api_client_no_csrf.get(f"{USERS_URL}{user.pk}/").json()
    assert record["invitation_accepted"] is False
    assert record["invitation"]["expired"] is False
    assert record["last_account_email"]["kind"] == "invitation"
    assert record["last_account_email"]["sent"] is True

    accepted = api_client_no_csrf.post(
        CONFIRM_URL, {"token": _token_from(invitation), "new_password": NEW_PASSWORD}
    )
    assert accepted.status_code == 200, accepted.json()
    user.refresh_from_db()
    assert user.has_usable_password()
    assert user.is_email_verified and user.email_verified_at is not None
    assert AuditLog.objects.filter(
        action=AuditAction.INVITATION_ACCEPTED, resource_id=str(user.pk)
    ).exists()


@pytest.mark.django_db
def test_resend_sends_a_set_password_link_that_replaces_the_old_one(admin_user, branch):
    user = services.create_user(
        email="pending@example.test",
        first_name="Pen",
        role=UserRole.COUNSELLOR,
        actor=admin_user,
        branch=branch,
    )
    first = AccountToken.objects.get(user=user, purpose=TokenPurpose.INVITATION)
    mail.outbox.clear()

    assert services.resend_invitation(user=user, actor=admin_user) is None
    (message,) = mail.outbox
    assert "Set your password" in message.body
    assert "Verify your email" not in message.body
    first.refresh_from_db()
    assert first.used_at is not None  # the old link no longer works

    user.set_password(NEW_PASSWORD)
    user.save(update_fields=["password"])
    reason = services.resend_invitation(user=user, actor=admin_user)
    assert "already set their password" in reason


@pytest.mark.django_db
def test_forgot_password_without_a_password_sends_the_invitation(api_client_no_csrf, branch):
    user = User.objects.create_user(
        email="imported@example.test",
        password=None,
        first_name="Imran",
        role=UserRole.STUDENT,
        branch=branch,
    )
    mail.outbox.clear()
    response = api_client_no_csrf.post(RESET_URL, {"email": user.email})
    assert response.status_code in (200, 202)
    (message,) = mail.outbox
    assert "An account has been created for you" in message.body
    assert AccountToken.objects.filter(user=user, purpose=TokenPurpose.INVITATION).exists()
    assert not AccountToken.objects.filter(user=user, purpose=TokenPurpose.PASSWORD_RESET).exists()


@pytest.mark.django_db
def test_a_refused_send_is_reported_in_words_and_shown_on_the_account(
    api_client_no_csrf, admin_user, branch
):
    user = User.objects.create_user(
        email="trainer.new@example.test",
        password=None,
        first_name="Tara",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )
    api_client_no_csrf.force_login(admin_user)
    with mock.patch("apps.accounts.emails.send_mail", side_effect=REFUSED):
        response = api_client_no_csrf.post(
            f"{USERS_URL}{user.pk}/credential-link/", {"action": "password_reset"}, format="json"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is False
    assert "not allowed to email this address" in body["detail"]
    assert "arn:aws" not in body["detail"]

    record = api_client_no_csrf.get(f"{USERS_URL}{user.pk}/").json()
    assert record["last_account_email"]["sent"] is False
    assert record["last_account_email"]["kind"] == "invitation"
    assert "arn:aws" not in str(record)
    assert AuditLog.objects.filter(
        action=AuditAction.CREDENTIAL_EMAIL_FAILED, resource_id=str(user.pk)
    ).exists()


@pytest.mark.django_db
def test_a_refused_bulk_resend_is_a_skip_with_the_reason(api_client_no_csrf, admin_user, branch):
    user = User.objects.create_user(
        email="bulk.pending@example.test",
        password=None,
        first_name="Bina",
        role=UserRole.COUNSELLOR,
        branch=branch,
    )
    api_client_no_csrf.force_login(admin_user)
    with mock.patch("apps.accounts.emails.send_mail", side_effect=REFUSED):
        response = api_client_no_csrf.post(
            f"{USERS_URL}bulk/",
            {"action": "resend_invitation", "ids": [str(user.pk)]},
            format="json",
        )
    body = response.json()
    assert body["done"] == 0
    assert "could not be sent" in body["skipped"][0]["reason"]


@pytest.mark.django_db
def test_an_unsent_code_does_not_count_against_the_cooldown(api_client_no_csrf, student):
    from apps.accounts.models import OneTimeCode

    api_client_no_csrf.force_login(student)
    with mock.patch("apps.accounts.emails.send_mail", side_effect=REFUSED):
        refused = api_client_no_csrf.post(REQUEST_CODE, format="json")
    assert refused.status_code == 400
    assert "could not email your code" in str(refused.json())
    assert not OneTimeCode.objects.filter(user=student).exists()

    mail.outbox.clear()
    retried = api_client_no_csrf.post(REQUEST_CODE, format="json")
    assert retried.status_code == 202, retried.json()
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_an_administrator_can_resend_a_peer_admins_invitation_until_it_is_accepted(admin_user):
    peer = User.objects.create_user(
        email="peer.admin@example.test",
        password=None,
        first_name="Pia",
        role=UserRole.ADMIN,
        branch=admin_user.branch,
    )
    assert services.may_send_invitation(admin_user, peer)
    assert services.resend_invitation(user=peer, actor=admin_user) is None

    peer.set_password(NEW_PASSWORD)
    peer.save(update_fields=["password"])
    assert not services.may_send_invitation(admin_user, peer)


@pytest.mark.django_db
def test_the_account_page_says_what_the_person_can_do(api_client_no_csrf, admin_user, trainer):
    api_client_no_csrf.force_login(admin_user)
    record = api_client_no_csrf.get(f"{USERS_URL}{trainer.pk}/").json()
    codes = {row["code"] for row in record["capabilities"]}
    assert "profile.view_own" in codes
    assert all(row["label"] for row in record["capabilities"])
    assert record["invitation_accepted"] is True
    assert record["invitation"] is None
    assert "mfa_enabled" in record
