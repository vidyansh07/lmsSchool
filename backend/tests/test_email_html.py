"""HTML email: what the composer shows is what the recipient gets.

Two gaps this closes, both of which made the block composer a lie.

The outgoing mail was **plain text only** — `send_mail(message=…)`, no HTML
alternative — so a template with a laid-out body reached the recipient as
either the text version or a wall of markup, while its author was looking at
a preview of columns and a button.

And the body was sanitised with `apps.forms.validation.sanitise_richtext`,
whose allowlist is right for a form answer and silently drops every heading,
rule, image and table an email is made of. `sanitise_email_html` is the
second allowlist for the second job: more tags, still no `style`, still only
`https://` for `href` and `src`, and every attribute that is not named per
tag dropped rather than filtered — so no `on*` handler can survive.
"""

from __future__ import annotations

import pytest
from django.core import mail

from apps.communication import services
from apps.communication.models import Delivery, DeliveryState, MessageChannel
from apps.communication.rendering import sanitise_email_html
from apps.notifications.channels import send_email_message
from apps.notifications.models import EmailMessage

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# The sanitiser
# ---------------------------------------------------------------------------


def test_the_blocks_an_email_is_made_of_survive():
    body = (
        "<h2>Welcome</h2><hr /><p>Hello</p>"
        '<table width="100%" role="presentation"><tr><td valign="top">Left</td></tr></table>'
        '<img src="https://grras.example/logo.png" alt="GRRAS" />'
        '<p><a href="https://grras.example/portal">Open the portal</a></p>'
    )
    kept = sanitise_email_html(body)

    for fragment in [
        "<h2>",
        "<hr/>",
        "<table",
        "<td",
        "<img",
        'href="https://grras.example/portal"',
    ]:
        assert fragment in kept, f"{fragment} was dropped: {kept}"


def test_a_script_goes_with_its_content_and_a_handler_cannot_survive():
    nasty = (
        "<script>alert(1)</script>"
        '<p onclick="alert(2)">Click</p>'
        '<a href="javascript:alert(3)">Nope</a>'
        '<img src="http://tracker.example/pixel.gif" alt="" />'
    )
    kept = sanitise_email_html(nasty)

    assert "alert(1)" not in kept
    assert "onclick" not in kept
    # The tag stays, the dangerous attribute does not.
    assert "<p>Click</p>" in kept
    assert "javascript:" not in kept
    # http:// is dropped with the attribute: no cleartext tracking pixel.
    assert "tracker.example" not in kept


def test_inline_style_is_refused_everywhere():
    """Marketing email is normally built with inline CSS, and inline CSS is
    also how content hides and how `background:url(javascript:…)` arrives.
    The composer emits presentational attributes instead."""
    kept = sanitise_email_html('<div style="position:fixed;top:0">Hidden</div>')
    assert "style" not in kept
    assert "Hidden" in kept


def test_an_unknown_tag_loses_its_markup_not_its_words():
    assert sanitise_email_html("<marquee>Fees due</marquee>") == "Fees due"


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def test_an_html_body_is_sent_as_an_alternative_to_the_text():
    message = EmailMessage.objects.create(
        to_email="student@gmail.com",
        subject="Your batch starts Monday",
        body="Your batch starts Monday.",
        body_html="<h2>Your batch starts Monday</h2>",
    )

    assert send_email_message(message) is True
    sent = mail.outbox[-1]
    assert sent.body == "Your batch starts Monday."
    assert sent.alternatives == [("<h2>Your batch starts Monday</h2>", "text/html")]


def test_a_text_only_message_is_still_a_plain_email():
    message = EmailMessage.objects.create(
        to_email="student@gmail.com", subject="Fee received", body="We received 5,000."
    )

    assert send_email_message(message) is True
    sent = mail.outbox[-1]
    assert getattr(sent, "alternatives", []) == []


def test_a_delivery_carries_the_rendered_html_to_the_outbox(admin_user):
    template = services.create_template(
        actor=admin_user,
        key="email.batch.welcome",
        name="Batch welcome",
        channel=MessageChannel.EMAIL,
        kind="batch.welcome",
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Welcome",
        body_html="<h2>Welcome</h2><p>See you Monday.</p>",
        body_text="Welcome. See you Monday.",
        variables=[],
    )
    version = services.approve_version(actor=admin_user, version=version)
    version = services.publish_version(actor=admin_user, version=version)

    delivery = Delivery.objects.create(
        channel=MessageChannel.EMAIL,
        address="student@gmail.com",
        template_version=version,
        state=DeliveryState.QUEUED,
    )
    services.dispatch_delivery(delivery)

    delivery.refresh_from_db()
    assert delivery.state == DeliveryState.SENT, delivery.error
    assert delivery.email_message is not None
    # The heading reaches the recipient rather than being unwrapped on the
    # way out, and the text alternative is the author's own words.
    assert "<h2>Welcome</h2>" in delivery.email_message.body_html
    assert delivery.email_message.body == "Welcome. See you Monday."


def test_a_template_with_no_text_body_gets_one_from_its_html(admin_user):
    """A composed email is laid out in blocks and often has no separate text
    version. Sending the markup as the plain-text part would put tags in
    front of a text-only client, so the tags are stripped for it."""
    template = services.create_template(
        actor=admin_user,
        key="email.blocks.only",
        name="Blocks only",
        channel=MessageChannel.EMAIL,
        kind="batch.welcome",
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Welcome",
        body_html="<h2>Welcome</h2><p>See you Monday.</p>",
        body_text="",
        variables=[],
    )
    version = services.approve_version(actor=admin_user, version=version)
    version = services.publish_version(actor=admin_user, version=version)

    delivery = Delivery.objects.create(
        channel=MessageChannel.EMAIL,
        address="student@gmail.com",
        template_version=version,
        state=DeliveryState.QUEUED,
    )
    services.dispatch_delivery(delivery)

    delivery.refresh_from_db()
    body = delivery.email_message.body
    assert "<h2>" not in body
    assert "Welcome" in body and "See you Monday." in body


def test_a_button_keeps_its_colour_without_inline_css():
    """The old "bulletproof button": a cell with `bgcolor` and a link inside.
    Only a hex colour is kept, so `bgcolor="url(...)"` cannot ride in on it."""
    kept = sanitise_email_html(
        '<table role="presentation"><tr>'
        '<td bgcolor="#EF7220" align="center"><a href="https://grras.example">Open</a></td>'
        "</tr></table>"
    )
    assert 'bgcolor="#EF7220"' in kept

    refused = sanitise_email_html('<td bgcolor="url(javascript:alert(1))">x</td>')
    assert "bgcolor" not in refused
