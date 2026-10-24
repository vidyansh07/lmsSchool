"""SMS, and what kind of message a template is.

Two gaps the communication centre had against the reference product's
template screen.

**SMS** is now a channel: it has templates, a category and a row in the
message matrix. It has no gateway — GRRAS has no DLT-registered sender wired
up here — so a delivery on it *fails*, saying exactly that, rather than
sitting in `queued` looking like it is on its way. "Nothing was sent" is the
one thing a delivery log must never be vague about.

**Category** says whether a message is transactional or promotional, which is
what the telecom regulator and WhatsApp both mean by the word: a promotional
message needs consent, a receipt or a cancellation does not.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.communication import services
from apps.communication.models import (
    UNWIRED_CHANNELS,
    Delivery,
    DeliveryState,
    MessageChannel,
    MessageTemplate,
    TemplateCategory,
)

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def test_an_sms_delivery_fails_with_the_reason_rather_than_looking_sent(admin_user):
    delivery = Delivery.objects.create(
        channel=MessageChannel.SMS,
        address="+919876543210",
        state=DeliveryState.QUEUED,
    )

    services.dispatch_delivery(delivery)

    delivery.refresh_from_db()
    assert delivery.state == DeliveryState.FAILED
    assert "No SMS gateway is configured" in delivery.error
    # And it is retryable the day one exists, which is what `failed` means
    # here rather than "give up".
    assert delivery.attempts == 1


def test_sms_is_named_as_unwired_in_one_place(admin_user):
    """The screens read this rather than each deciding for themselves which
    channels are real."""
    assert MessageChannel.SMS in UNWIRED_CHANNELS
    assert MessageChannel.EMAIL not in UNWIRED_CHANNELS
    assert MessageChannel.WHATSAPP not in UNWIRED_CHANNELS


def test_an_sms_template_can_be_made_and_says_what_kind_it_is(api_client_no_csrf, admin_user):
    created = _client(admin_user).post(
        "/api/v1/templates/",
        {
            "key": "sms.fee.reminder",
            "name": "Fee reminder (SMS)",
            "channel": "sms",
            "kind": "fee.reminder",
            "category": "promotional",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    assert created.json()["channel"] == "sms"
    assert created.json()["category"] == "promotional"


def test_a_template_is_transactional_unless_it_says_otherwise(admin_user):
    """The safe default: a transactional message is the one that may always
    go, so calling a promotional one transactional by accident is the
    mistake worth preventing — which is why it is a choice on the form rather
    than a blank."""
    template = services.create_template(
        actor=admin_user,
        key="email.receipt",
        name="Receipt",
        channel=MessageChannel.EMAIL,
        kind="fee.receipt",
    )
    assert template.category == TemplateCategory.TRANSACTIONAL


def test_the_category_comes_back_on_the_list(api_client_no_csrf, admin_user):
    services.create_template(
        actor=admin_user,
        key="whatsapp.class.reminder",
        name="Class reminder",
        channel=MessageChannel.WHATSAPP,
        kind="class.reminder",
        category=TemplateCategory.PROMOTIONAL,
    )
    rows = _client(admin_user).get("/api/v1/templates/").json()["results"]
    row = next(item for item in rows if item["key"] == "whatsapp.class.reminder")
    assert row["category"] == "promotional"
    assert MessageTemplate.objects.get(key="whatsapp.class.reminder").category == "promotional"
