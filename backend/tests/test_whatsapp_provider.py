"""The WhatsApp channel (ERP Phase 19, ADR-12).

Per the phase's plan row: the Null provider always skips cleanly, and a
recipient without ``whatsapp_opt_in`` is refused/skipped regardless of the
configured provider. The webhook's own signature/token verification (the
phase's other named security concern) gets its own tests here too.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.test import override_settings

from apps.communication import services
from apps.communication.models import Delivery, DeliveryState, MessageChannel
from apps.communication.providers import (
    MetaCloudWhatsAppProvider,
    NullWhatsAppProvider,
    WhatsAppSendResult,
    get_provider,
)
from apps.communication.webhooks import WhatsAppWebhookView, _verify_signature

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/communication/whatsapp/webhook/"


def _published_whatsapp_template(actor, key="test.wa.template"):
    template = services.create_template(
        actor=actor, key=key, name="WA test", channel=MessageChannel.WHATSAPP, kind="wa.notice"
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=actor,
        version=version,
        body_text="Hi {{recipient.name}}",
        variables=["recipient.name"],
    )
    version = services.approve_version(actor=actor, version=version)
    return services.publish_version(actor=actor, version=version)


# ---------------------------------------------------------------------------
# get_provider: Null by default, never crashes unconfigured
# ---------------------------------------------------------------------------


class TestProviderSelection:
    def test_get_provider_returns_null_when_unconfigured(self):
        with override_settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID=""):
            assert isinstance(get_provider(), NullWhatsAppProvider)

    def test_get_provider_returns_meta_cloud_once_both_settings_are_present(self):
        with override_settings(
            WHATSAPP_ACCESS_TOKEN="token-123", WHATSAPP_PHONE_NUMBER_ID="55500011122"
        ):
            assert isinstance(get_provider(), MetaCloudWhatsAppProvider)

    def test_partial_configuration_still_falls_back_to_null(self):
        with override_settings(WHATSAPP_ACCESS_TOKEN="token-only", WHATSAPP_PHONE_NUMBER_ID=""):
            assert isinstance(get_provider(), NullWhatsAppProvider)


class TestNullProviderAlwaysSkipsCleanly:
    def test_send_never_raises_and_reports_not_configured(self):
        provider = NullWhatsAppProvider()
        result = provider.send(to="+919876543210", template_version=None, variables={}, rendered={})
        assert isinstance(result, WhatsAppSendResult)
        assert result.ok is False
        assert "not configured" in result.error.lower()

    def test_dispatch_through_the_null_provider_marks_the_delivery_failed_not_stuck(
        self, admin_user
    ):
        """A `Delivery` created against an unconfigured provider must reach a
        real terminal state (`failed`, with a legible reason) rather than
        hang — the Null provider is the deliberate scope boundary, not a
        silent success."""
        version = _published_whatsapp_template(admin_user)
        delivery = Delivery.objects.create(
            channel=MessageChannel.WHATSAPP,
            address="+919876543210",
            template_version=version,
            variables={"recipient": {"name": "Sam"}},
        )
        with override_settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID=""):
            services.dispatch_delivery(delivery)
        delivery.refresh_from_db()
        assert delivery.state == DeliveryState.FAILED
        assert delivery.error


# ---------------------------------------------------------------------------
# Opt-in is required regardless of provider
# ---------------------------------------------------------------------------


class TestOptInIsRequiredRegardlessOfProvider:
    def test_a_user_without_opt_in_is_never_returned_as_an_eligible_whatsapp_recipient(
        self, admin_user, branch
    ):
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole

        not_opted_in = User.objects.create_user(
            email="no.optin@example.test",
            password="whatever-not-used",
            first_name="No",
            last_name="Optin",
            role=UserRole.STUDENT,
            branch=branch,
            phone="+919876500001",
            whatsapp_opt_in=False,
        )
        opted_in = User.objects.create_user(
            email="optin@example.test",
            password="whatever-not-used",
            first_name="Opted",
            last_name="In",
            role=UserRole.STUDENT,
            branch=branch,
            phone="+919876500002",
            whatsapp_opt_in=True,
        )
        eligible = services.resolve_recipients(
            actor=admin_user, channel=MessageChannel.WHATSAPP, spec={"role": "student"}
        )
        assert opted_in in eligible
        assert not_opted_in not in eligible

    def test_create_deliveries_skips_a_recipient_with_no_whatsapp_address(self, admin_user, branch):
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole

        not_opted_in = User.objects.create_user(
            email="skip.optin@example.test",
            password="whatever-not-used",
            first_name="Skip",
            last_name="Optin",
            role=UserRole.STUDENT,
            branch=branch,
            phone="+919876500003",
            whatsapp_opt_in=False,
        )
        version = _published_whatsapp_template(admin_user, key="test.wa.skip")
        deliveries = services.create_deliveries(
            channel=MessageChannel.WHATSAPP, template_version=version, recipients=[not_opted_in]
        )
        assert deliveries == []
        assert not Delivery.objects.filter(recipient=not_opted_in).exists()

    def test_dispatch_refuses_defense_in_depth_if_opt_in_is_withdrawn_after_queueing(
        self, admin_user, branch
    ):
        """Consent can be withdrawn between queue time and send time; the
        dispatcher itself must re-check, not only the resolver that first
        created the row."""
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole

        recipient = User.objects.create_user(
            email="withdraw.optin@example.test",
            password="whatever-not-used",
            first_name="With",
            last_name="Draw",
            role=UserRole.STUDENT,
            branch=branch,
            phone="+919876500004",
            whatsapp_opt_in=True,
        )
        version = _published_whatsapp_template(admin_user, key="test.wa.withdraw")
        delivery = Delivery.objects.create(
            channel=MessageChannel.WHATSAPP,
            address=recipient.phone,
            recipient=recipient,
            template_version=version,
            variables={"recipient": {"name": "With"}},
        )
        recipient.whatsapp_opt_in = False
        recipient.save(update_fields=["whatsapp_opt_in"])

        services.dispatch_delivery(delivery)
        delivery.refresh_from_db()
        assert delivery.state == DeliveryState.FAILED
        assert "opt" in delivery.error.lower()

    def test_test_send_of_a_whatsapp_template_requires_the_callers_own_opt_in(self, admin_user):
        from apps.common.exceptions import ApplicationError

        version = _published_whatsapp_template(admin_user, key="test.wa.selftest")
        admin_user.whatsapp_opt_in = False
        admin_user.save(update_fields=["whatsapp_opt_in"])
        with pytest.raises(ApplicationError):
            services.test_send(actor=admin_user, version=version)


# ---------------------------------------------------------------------------
# MetaCloudWhatsAppProvider: never calls a non-https base url
# ---------------------------------------------------------------------------


class TestMetaCloudProviderGuardsAgainstInsecureConfiguration:
    def test_refuses_a_non_https_base_url_before_ever_opening_a_socket(self, admin_user):
        version = _published_whatsapp_template(admin_user, key="test.wa.insecure")
        provider = MetaCloudWhatsAppProvider(
            access_token="tok", phone_number_id="123", api_base_url="http://not-secure.test"
        )
        result = provider.send(
            to="+919876543210", template_version=version, variables={}, rendered={}
        )
        assert result.ok is False
        assert "misconfigured" in result.error.lower()


# ---------------------------------------------------------------------------
# The webhook: signature/token verification before anything is trusted
# ---------------------------------------------------------------------------


class TestWebhookAuthentication:
    def test_view_carries_no_session_authentication_at_all(self):
        assert WhatsAppWebhookView.authentication_classes == ()

    def test_signature_check_fails_closed_when_secret_is_unconfigured(self):
        with override_settings(WHATSAPP_APP_SECRET=""):
            assert _verify_signature(b'{"a": 1}', "sha256=anything") is False

    def test_signature_check_rejects_a_wrong_signature(self):
        with override_settings(WHATSAPP_APP_SECRET="s3cret"):
            assert _verify_signature(b'{"a": 1}', "sha256=" + "0" * 64) is False

    def test_signature_check_accepts_a_correctly_signed_body(self):
        body = b'{"a": 1}'
        with override_settings(WHATSAPP_APP_SECRET="s3cret"):
            digest = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
            assert _verify_signature(body, f"sha256={digest}") is True

    def test_post_without_a_valid_signature_is_refused_before_touching_any_delivery(
        self, admin_user, api_client_no_csrf
    ):
        version = _published_whatsapp_template(admin_user, key="test.wa.webhook1")
        delivery = Delivery.objects.create(
            channel=MessageChannel.WHATSAPP,
            address="+919876543210",
            template_version=version,
            provider_message_id="wamid.unsigned",
            state=DeliveryState.SENT,
        )
        payload = {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": "wamid.unsigned", "status": "delivered"}]}}
                    ]
                }
            ]
        }
        with override_settings(WHATSAPP_APP_SECRET="real-secret"):
            response = api_client_no_csrf.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256="sha256=" + "0" * 64,
            )
        assert response.status_code == 403
        delivery.refresh_from_db()
        assert delivery.state == DeliveryState.SENT  # untouched

    def test_post_with_a_valid_signature_updates_the_matching_delivery(
        self, admin_user, api_client_no_csrf
    ):
        version = _published_whatsapp_template(admin_user, key="test.wa.webhook2")
        delivery = Delivery.objects.create(
            channel=MessageChannel.WHATSAPP,
            address="+919876543210",
            template_version=version,
            provider_message_id="wamid.signed",
            state=DeliveryState.SENT,
        )
        payload = {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": "wamid.signed", "status": "delivered"}]}}
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        with override_settings(WHATSAPP_APP_SECRET="real-secret"):
            digest = hmac.new(b"real-secret", body, hashlib.sha256).hexdigest()
            response = api_client_no_csrf.post(
                WEBHOOK_URL,
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=f"sha256={digest}",
            )
        assert response.status_code == 200
        delivery.refresh_from_db()
        assert delivery.state == DeliveryState.DELIVERED

    def test_a_valid_session_cookie_never_substitutes_for_a_missing_signature(
        self, admin_user, api_client_no_csrf
    ):
        """The webhook must never be treated as authenticated by session
        under any circumstance — signing in as an administrator must not
        make an unsigned payload acceptable."""
        api_client_no_csrf.force_login(admin_user)
        payload = {"entry": []}
        with override_settings(WHATSAPP_APP_SECRET="real-secret"):
            response = api_client_no_csrf.post(
                WEBHOOK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        assert response.status_code == 403

    def test_get_handshake_requires_matching_verify_token(self, api_client_no_csrf):
        with override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="right-token"):
            wrong = api_client_no_csrf.get(
                WEBHOOK_URL,
                {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "echo-me"},
            )
            assert wrong.status_code == 403

            right = api_client_no_csrf.get(
                WEBHOOK_URL,
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": "right-token",
                    "hub.challenge": "echo-me",
                },
            )
            assert right.status_code == 200
            assert right.content.decode() == "echo-me"

    def test_get_handshake_fails_closed_when_no_verify_token_is_configured(
        self, api_client_no_csrf
    ):
        with override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=""):
            response = api_client_no_csrf.get(
                WEBHOOK_URL,
                {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "echo-me"},
            )
            assert response.status_code == 403

    def test_a_cancelled_delivery_is_never_resurrected_by_a_stray_callback(self, admin_user):
        version = _published_whatsapp_template(admin_user, key="test.wa.cancelled")
        delivery = Delivery.objects.create(
            channel=MessageChannel.WHATSAPP,
            address="+919876543210",
            template_version=version,
            provider_message_id="wamid.cancelled",
            state=DeliveryState.CANCELLED,
        )
        result = services.apply_whatsapp_status_update(
            provider_message_id="wamid.cancelled", status="delivered"
        )
        assert result is None
        delivery.refresh_from_db()
        assert delivery.state == DeliveryState.CANCELLED
