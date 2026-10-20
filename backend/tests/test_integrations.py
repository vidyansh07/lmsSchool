"""Integrations: API keys and the lead endpoint, webhooks and `send_webhook`.

What is pinned:

- a key is shown once, stored as a hash, and works until it is revoked;
- a lead posted with a key becomes an enquiry at the key's centre, with no
  owner, and a second post with the same mobile or Meritto lead id updates
  that enquiry instead of duplicating it; a bad lead is a 400 with reasons and
  a logged intake, never a 500;
- a Meritto key understands Meritto's field names, and a key's own field map
  points a custom field anywhere;
- only `integration.manage` reaches the screens; a counsellor does not;
- a webhook refuses private addresses and plain http, keeps its secrets
  encrypted, signs every body, and logs every delivery; it is generic JSON —
  nothing is ever sent back to Meritto (owner's decision, 17 October 2026);
- an automation rule's `send_webhook` posts the rule's context, and fails the
  run when the receiver says no.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
from unittest import mock

import pytest

from apps.common.exceptions import ApplicationError, AuthorityError
from apps.enquiries.models import Enquiry
from apps.integrations import crypto, services
from apps.integrations.models import ApiKey, IntakeStatus, LeadIntake, Webhook, WebhookDelivery

LEADS = "/api/v1/integrations/leads/"


@pytest.fixture
def public_dns():
    """Every host resolves to a public address (no real DNS in tests)."""
    with mock.patch(
        "apps.integrations.security.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    ):
        yield


def _key(admin_user, **extra):
    return services.create_api_key(actor=admin_user, name="Website", **extra)


def _post(client, key, body):
    return client.post(LEADS, body, format="json", HTTP_AUTHORIZATION=f"Bearer {key}")


# ---------------------------------------------------------------------------
# Keys and the lead endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_key_is_shown_once_and_stored_as_a_hash(admin_user):
    key, plaintext = _key(admin_user)
    assert plaintext.startswith(f"grk_{key.prefix}_")
    assert key.key_hash == hashlib.sha256(plaintext.encode()).hexdigest()
    assert plaintext not in json.dumps(list(ApiKey.objects.values()), default=str), (
        "the key itself is never stored"
    )
    assert services.authenticate(f"Bearer {plaintext}") == key
    assert services.authenticate(f"Bearer {plaintext}x") is None
    assert services.authenticate("Bearer grk_nothing_here") is None


@pytest.mark.django_db
def test_a_posted_lead_becomes_an_enquiry_at_the_keys_centre(api_client, admin_user, branch):
    key, plaintext = _key(admin_user, branch=branch, default_source="website")
    response = _post(
        api_client,
        plaintext,
        {
            "name": "Riya Sharma",
            "phone": "+91 98290 11111",
            "email": "riya@example.test",
            "course": "DevOps",
            "utm_campaign": "diwali",
            "source": "Instagram ad",
        },
    )
    assert response.status_code == 201, response.json()
    enquiry = Enquiry.objects.get(pk=response.json()["enquiry_id"])
    assert enquiry.full_name == "Riya Sharma"
    assert enquiry.branch == branch
    assert enquiry.owner is None
    assert enquiry.stage == "new"
    assert enquiry.source == "website"  # an unknown source falls back, and is noted
    assert "Source given: Instagram ad" in enquiry.remarks
    assert enquiry.utm_campaign == "diwali"
    intake = LeadIntake.objects.get()
    assert intake.status == IntakeStatus.CREATED
    key.refresh_from_db()
    assert key.last_used_at is not None

    # The same mobile again updates the open enquiry.
    again = _post(
        api_client, plaintext, {"name": "Riya S", "mobile": "9829011111", "city": "Jaipur"}
    )
    assert again.status_code == 200
    assert again.json()["status"] == "updated"
    assert Enquiry.objects.count() == 1
    assert Enquiry.objects.get().city == "Jaipur"


@pytest.mark.django_db
def test_a_meritto_key_reads_meritto_names_and_dedupes_by_lead_id(api_client, admin_user, branch):
    _key_row, plaintext = _key(
        admin_user, preset="meritto", branch=branch, field_map={"cf_batch_pref": "batch_timing"}
    )
    body = {
        "lead_id": "MER-1001",
        "student_name": "Aman Verma",
        "mobile_number": "9876500001",
        "email_id": "aman@example.test",
        "course_name": "Python Full Stack",
        "lead_source": "google",
        "cf_batch_pref": "evening",
    }
    first = _post(api_client, plaintext, body)
    assert first.status_code == 201, first.json()
    enquiry = Enquiry.objects.get()
    assert (enquiry.external_system, enquiry.external_id) == ("meritto", "MER-1001")
    assert enquiry.course == "Python Full Stack"
    assert enquiry.source == "google"
    assert enquiry.batch_timing == "evening"

    # Meritto sends the lead again with a new number: still the same enquiry.
    second = _post(api_client, plaintext, {**body, "mobile_number": "9876500002"})
    assert second.json()["status"] == "updated"
    assert Enquiry.objects.count() == 1
    assert Enquiry.objects.get().mobile == "9876500002"


@pytest.mark.django_db
def test_a_bad_lead_is_refused_with_reasons_and_logged(api_client, admin_user):
    _key_row, plaintext = _key(admin_user)
    response = _post(api_client, plaintext, {"email": "nobody@example.test"})
    assert response.status_code == 400
    assert response.json()["status"] == "rejected"
    assert "name and a mobile" in str(response.json()["errors"])
    assert LeadIntake.objects.get().status == IntakeStatus.REJECTED

    listed = _post(api_client, plaintext, [{"name": "A", "mobile": "1"}])
    assert listed.status_code == 400
    assert not Enquiry.objects.exists()


@pytest.mark.django_db
def test_no_key_or_a_revoked_key_gets_401(api_client, admin_user):
    key, plaintext = _key(admin_user)
    assert (
        api_client.post(LEADS, {"name": "A", "mobile": "9999999999"}, format="json").status_code
        == 401
    )
    services.revoke_api_key(actor=admin_user, key=key)
    assert _post(api_client, plaintext, {"name": "A", "mobile": "9999999999"}).status_code == 401
    assert not Enquiry.objects.exists()


@pytest.mark.django_db
def test_a_lead_never_sets_its_own_stage(api_client, admin_user):
    _key_row, plaintext = _key(admin_user)
    _post(api_client, plaintext, {"name": "A", "mobile": "9999999999", "stage": "registered"})
    assert Enquiry.objects.get().stage == "new"


@pytest.mark.django_db
def test_only_an_administrator_reaches_the_screens(api_client_no_csrf, admin_user, counsellor_user):
    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get("/api/v1/integrations/api-keys/").status_code == 403
    assert (
        api_client_no_csrf.post(
            "/api/v1/integrations/api-keys/", {"name": "x"}, format="json"
        ).status_code
        == 403
    )
    with pytest.raises(AuthorityError):
        services.create_api_key(actor=counsellor_user, name="sneaky")

    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(
        "/api/v1/integrations/api-keys/", {"name": "Meritto", "preset": "meritto"}, format="json"
    )
    assert created.status_code == 201, created.json()
    assert created.json()["key"].startswith("grk_")
    listed = api_client_no_csrf.get("/api/v1/integrations/api-keys/").json()
    assert listed[0]["display"].endswith("_…")
    assert "key" not in listed[0]


@pytest.mark.django_db
def test_a_field_map_may_only_point_at_enquiry_fields(admin_user):
    with pytest.raises(ApplicationError):
        _key(admin_user, field_map={"x": "password"})


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url, resolved",
    [
        ("http://hooks.example.test/in", "93.184.216.34"),
        ("https://hooks.example.test/in", "10.0.0.5"),
        ("https://hooks.example.test/in", "127.0.0.1"),
        ("https://hooks.example.test/in", "169.254.169.254"),
        ("https://user:pass@hooks.example.test/in", "93.184.216.34"),
    ],
)
def test_a_webhook_refuses_anywhere_it_should_not_reach(admin_user, url, resolved):
    with mock.patch(
        "apps.integrations.security.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, 443))],
    ):
        with pytest.raises(ApplicationError):
            services.save_webhook(actor=admin_user, name="Bad", url=url)
    assert not Webhook.objects.exists()


@pytest.mark.django_db
def test_a_webhook_keeps_its_secrets_encrypted(admin_user, public_dns):
    _webhook, secret = services.save_webhook(
        actor=admin_user,
        name="Accounts",
        url="https://accounts.example.test/in",
        headers={"access-key": "AK-123", "secret-key": "SK-456"},
    )
    assert secret
    row = Webhook.objects.get()
    assert "SK-456" not in row.headers_encrypted and secret not in row.secret_encrypted
    assert crypto.decrypt(row.secret_encrypted) == secret
    assert crypto.decrypt_json(row.headers_encrypted) == {
        "access-key": "AK-123",
        "secret-key": "SK-456",
    }
    assert row.header_names == ["access-key", "secret-key"]
    with pytest.raises(ApplicationError):
        services.save_webhook(actor=admin_user, webhook=row, headers={"Host": "evil"})


class _Response:
    def __init__(self, status=200, body=b'{"ok":true}'):
        self.status = status
        self._body = body

    def read(self, limit=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.django_db
def test_every_delivery_is_signed_and_logged(admin_user, public_dns):
    webhook, secret = services.save_webhook(
        actor=admin_user, name="Accounts", url="https://hooks.example.test/in"
    )
    sent = {}

    def fake_urlopen(request, timeout):
        sent["body"] = request.data
        sent["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _Response()

    with mock.patch("apps.integrations.services.urllib_request.urlopen", side_effect=fake_urlopen):
        delivery = services.send_test(actor=admin_user, webhook=webhook)
    assert delivery.ok and delivery.status_code == 200
    expected = "sha256=" + hmac.new(secret.encode(), sent["body"], hashlib.sha256).hexdigest()
    assert sent["headers"]["x-grras-signature"] == expected
    assert json.loads(sent["body"])["event"] == "test"


@pytest.mark.django_db
def test_a_refused_delivery_is_logged_not_raised(admin_user, public_dns):
    from urllib.error import HTTPError

    webhook, _secret = services.save_webhook(
        actor=admin_user, name="Accounts", url="https://hooks.example.test/in"
    )
    error = HTTPError(webhook.url, 422, "Unprocessable", {}, None)
    error.read = lambda limit=-1: b"missing mobile"
    with mock.patch("apps.integrations.services.urllib_request.urlopen", side_effect=error):
        delivery = services.send_test(actor=admin_user, webhook=webhook)
    assert not delivery.ok
    assert delivery.status_code == 422
    assert delivery.response_excerpt == "missing mobile"
    assert WebhookDelivery.objects.count() == 1


@pytest.mark.django_db
def test_nothing_is_sent_back_to_meritto(admin_user, public_dns):
    with pytest.raises(ApplicationError):
        services.save_webhook(
            actor=admin_user,
            name="Meritto",
            preset="meritto",
            url="https://api.meritto.example.test/leads",
        )
    assert not Webhook.objects.exists()


@pytest.mark.django_db
def test_a_rule_posts_its_context_to_a_webhook(admin_user, public_dns, branch):
    from apps.automation import services as automation
    from apps.automation.models import AutomationRun, AutomationRunStatus, AutomationTrigger
    from apps.enquiries import services as enquiries

    webhook, _secret = services.save_webhook(
        actor=admin_user,
        name="Accounts",
        url="https://accounts.example.test/in",
        headers={"x-token": "AK"},
    )
    rule = automation.create_rule(
        actor=admin_user,
        name="Tell accounts about walk-ins",
        trigger="ENQUIRY_CREATED",
        conditions=[],
        actions=[{"type": "send_webhook", "params": {"webhook": str(webhook.pk)}}],
        status="active",
    )
    enquiry, _created = enquiries.capture(
        actor=admin_user, values={"full_name": "Neha", "mobile": "9000000001"}, branch=branch
    )
    sent = {}

    def fake_urlopen(request, timeout):
        sent["body"] = json.loads(request.data)
        sent["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _Response()

    with mock.patch("apps.integrations.services.urllib_request.urlopen", side_effect=fake_urlopen):
        automation.dispatch(AutomationTrigger.ENQUIRY_CREATED, enquiry)
    run = AutomationRun.objects.get(rule=rule)
    assert run.status == AutomationRunStatus.RAN, run.result
    assert sent["body"]["event"] == "ENQUIRY_CREATED"
    assert sent["body"]["rule"] == "Tell accounts about walk-ins"
    assert sent["body"]["data"]["enquiry"]["full_name"] == "Neha"
    assert sent["headers"]["x-token"] == "AK"

    # The receiver saying no fails the run.
    from urllib.error import HTTPError

    second, _ = enquiries.capture(
        actor=admin_user, values={"full_name": "Om", "mobile": "9000000002"}, branch=branch
    )
    error = HTTPError(webhook.url, 500, "Down", {}, None)
    error.read = lambda limit=-1: b""
    with mock.patch("apps.integrations.services.urllib_request.urlopen", side_effect=error):
        automation.dispatch(AutomationTrigger.ENQUIRY_CREATED, second)
    failed = AutomationRun.objects.filter(rule=rule).exclude(pk=run.pk).get()
    assert failed.status == AutomationRunStatus.FAILED


@pytest.mark.django_db
def test_only_an_integration_manager_may_point_a_rule_at_a_webhook(
    admin_user, manager_user, public_dns
):
    from apps.automation import services as automation

    webhook, _secret = services.save_webhook(
        actor=admin_user, name="Out", url="https://hooks.example.test/in"
    )
    with pytest.raises((AuthorityError, ApplicationError)):
        automation.create_rule(
            actor=manager_user,
            name="Sneaky",
            trigger="ENQUIRY_CREATED",
            conditions=[],
            actions=[{"type": "send_webhook", "params": {"webhook": str(webhook.pk)}}],
            status="draft",
        )
    with pytest.raises(ApplicationError):
        automation.create_rule(
            actor=admin_user,
            name="Nowhere",
            trigger="ENQUIRY_CREATED",
            conditions=[],
            actions=[{"type": "send_webhook", "params": {"webhook": "not-a-uuid"}}],
            status="draft",
        )
