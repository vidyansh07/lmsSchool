"""Who hears about what, and how.

The matrix the settings screen draws: an event, a recipient, a channel, on or
off. Three things this suite fixes in place:

1. **A missing row means off.** A product that starts texting parents the day
   it is deployed has made a decision nobody took.
2. The seeded defaults are the institute's *current* practice — the student
   hears about their own money — and guardians and owners start silent.
3. Changing the matrix is `platform.configure`. Whether a parent gets a text
   about their child's fees is a policy decision, not an operational one, and
   it is not a counsellor's to make from a screen they happened to open.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.notifications import messaging
from apps.notifications.models import MessageRule

pytestmark = pytest.mark.django_db

URL = "/api/v1/notifications/message-settings/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def test_a_cell_with_no_row_is_off(db):
    """Not "unset", not "inherit" — off. Anything else is a message somebody
    receives because nobody wrote the row that would have stopped it."""
    assert messaging.channels_for("payment.made", "guardian") == set()


def test_the_seeded_defaults_tell_the_student_and_nobody_else(db):
    assert messaging.channels_for("payment.made", "student") == {"sms", "push"}
    assert messaging.channels_for("payment.made", "guardian") == set()
    assert messaging.channels_for("payment.made", "owner") == set()


def test_a_bounced_cheque_reaches_the_student_every_way(db):
    """The one the desk cannot afford to be quiet about."""
    assert messaging.channels_for("payment.cheque_bounced", "student") == {
        "sms",
        "email",
        "push",
    }


def test_the_screen_is_sent_its_own_shape(api_client_no_csrf, admin_user):
    """A screen that hardcodes the events drifts the moment one is added, and
    the first anybody knows is a message nobody can turn off."""
    body = _client(admin_user).get(URL).json()

    titles = [tab["title"] for tab in body["tabs"]]
    assert titles == ["Student", "Admission", "Payment"]
    payment = next(tab for tab in body["tabs"] if tab["title"] == "Payment")
    assert [event["label"] for event in payment["events"]][:3] == [
        "Payment made",
        "Cheque clearance",
        "Cheque bounced",
    ]
    assert [row["key"] for row in body["recipients"]] == ["student", "guardian", "owner"]
    assert [row["key"] for row in body["channels"]] == ["sms", "email", "push"]


def test_turning_a_cell_on_and_off(api_client_no_csrf, admin_user):
    client = _client(admin_user)
    saved = client.put(
        URL,
        {
            "rules": [
                {
                    "event": "payment.made",
                    "recipient": "guardian",
                    "channel": "sms",
                    "is_enabled": True,
                }
            ]
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert messaging.channels_for("payment.made", "guardian") == {"sms"}

    client.put(
        URL,
        {
            "rules": [
                {
                    "event": "payment.made",
                    "recipient": "guardian",
                    "channel": "sms",
                    "is_enabled": False,
                }
            ]
        },
        format="json",
    )
    assert messaging.channels_for("payment.made", "guardian") == set()
    # The row stays, turned off — so the screen shows the institute's actual
    # answer rather than a blank that reads as "never considered".
    assert MessageRule.objects.filter(
        event="payment.made", recipient="guardian", channel="sms"
    ).exists()


def test_a_cell_nobody_can_see_is_refused_not_stored(api_client_no_csrf, admin_user):
    """An event the screen does not draw is an event nobody could turn off
    again."""
    response = _client(admin_user).put(
        URL,
        {
            "rules": [
                {
                    "event": "something.invented",
                    "recipient": "student",
                    "channel": "sms",
                    "is_enabled": True,
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 400
    assert not MessageRule.objects.filter(event="something.invented").exists()


def test_changing_the_matrix_is_an_administrators_decision(
    api_client_no_csrf, manager_user, counsellor_user, student_profile
):
    payload = {
        "rules": [
            {
                "event": "payment.made",
                "recipient": "guardian",
                "channel": "sms",
                "is_enabled": True,
            }
        ]
    }
    for user in (manager_user, counsellor_user, student_profile.user):
        client = _client(user)
        assert client.get(URL).status_code == 403
        assert client.put(URL, payload, format="json").status_code == 403
    assert messaging.channels_for("payment.made", "guardian") == set()


def test_the_matrix_reads_in_one_query(django_assert_num_queries, db):
    """Drawing the table cell by cell would be a query per cell, which only
    shows up once the table has rows in it."""
    with django_assert_num_queries(1):
        messaging.matrix()


# ---------------------------------------------------------------------------
# What actually gets sent
# ---------------------------------------------------------------------------


def test_a_payment_reaches_the_student_in_app(admin_user, enrollment, student_profile):
    """The seeded matrix says a payment reaches the student by SMS and
    in-app. The in-app half is real; see the SMS test below for the half
    that is not."""
    from apps.fees import services as fee_services
    from apps.notifications.models import Notification

    plan = fee_services.set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")
    fee_services.record_payment(plan=plan, actor=admin_user, amount="5000")

    written = Notification.objects.filter(recipient=student_profile.user)
    assert written.exists()
    assert "5000" in written.first().title


def test_sms_is_counted_and_not_sent_because_there_is_no_provider(admin_user, student_profile):
    """The one honest gap. The rule is stored, the audience is resolved, and
    the count says one — and nothing is sent, because no SMS provider is
    wired. Reporting it is what stops this becoming a feature everybody
    believes is working."""
    sent = messaging.deliver_for_event(
        "payment.made",
        student=student_profile,
        kind="fee.payment",
        title="Payment received",
    )
    assert sent["sms"] == 1
    assert sent["push"] == 1


def test_a_guardian_cell_sends_nothing_in_app_because_they_have_no_account(
    admin_user, student_profile
):
    """A guardian is a name, a number and an address — not an account. The
    cell can be turned on; what it cannot do is quietly fail."""
    from apps.students import services as student_services

    student_services.set_guardians(
        actor=admin_user, student=student_profile, guardians=[{"name": "Ramesh"}]
    )
    messaging.set_cell(event="payment.made", recipient="guardian", channel="push", enabled=True)

    sent = messaging.deliver_for_event(
        "payment.made", student=student_profile, kind="fee.payment", title="Payment"
    )
    # The student still got theirs; the guardian's in-app count did not move.
    assert sent["push"] == 1


def test_turning_the_student_off_stops_the_notification(admin_user, enrollment, student_profile):
    from apps.fees import services as fee_services
    from apps.notifications.models import Notification

    for channel in ("sms", "push"):
        messaging.set_cell(
            event="payment.made", recipient="student", channel=channel, enabled=False
        )

    plan = fee_services.set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")
    fee_services.record_payment(plan=plan, actor=admin_user, amount="5000")

    assert not Notification.objects.filter(
        recipient=student_profile.user, kind="fee.payment"
    ).exists()


def test_a_bounced_cheque_tells_the_student(admin_user, enrollment, student_profile):
    from apps.fees import services as fee_services
    from apps.notifications.models import Notification

    plan = fee_services.set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")
    payment = fee_services.record_payment(
        plan=plan, actor=admin_user, amount="5000", method="cheque"
    )
    Notification.objects.all().delete()

    fee_services.mark_payment_bounced(
        payment=payment, actor=admin_user, reason="Insufficient funds."
    )

    titles = list(
        Notification.objects.filter(recipient=student_profile.user).values_list("title", flat=True)
    )
    assert any("did not clear" in title for title in titles)
