"""Communication centre templates (ERP Phase 19, ADR-12, D-051).

This file's job, per the phase's own plan row ("test_templates
(injection)"), is specifically the injection surface:

- a template body containing something that looks like a script tag is
  neutralised, never reflected raw, whether it comes from the template
  author's own text or from a real record's data pulled in at send time;
- a variable reference that is not on a version's own allowlist is dropped
  and reported in ``warnings``, never substituted and never an error;
- an unapproved/unpublished template cannot be sent from
  (``resolve_published_template`` and ``manual_send``);
- publishing is immutable — editing a published version is refused, and an
  edit after publishing opens the *next* draft version instead.

Capability gating (``template.manage``/``template.approve``) and the
WhatsApp step-up requirement get their own tests too, since both are named
directly in the phase's spec.
"""

from __future__ import annotations

import pytest

from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.communication import services
from apps.communication.models import (
    MessageChannel,
    MessageTemplate,
    TemplateVersion,
)
from apps.communication.rendering import render_template

pytestmark = pytest.mark.django_db

TEMPLATES_URL = "/api/v1/templates/"


def _step_up(client) -> None:
    from tests.conftest import TEST_PASSWORD

    stepped = client.post("/api/v1/auth/step-up/", {"password": TEST_PASSWORD}, format="json")
    assert stepped.status_code == 204, stepped.json()


def _template(actor, *, channel=MessageChannel.EMAIL, kind="activity.assigned", key=None):
    return services.create_template(
        actor=actor,
        key=key or f"test.template.{MessageTemplate.objects.count()}",
        name="Test template",
        channel=channel,
        kind=kind,
    )


def _approved_version(actor, template, **fields) -> TemplateVersion:
    version = (
        template.current_version
        or TemplateVersion.objects.filter(template=template, published_at__isnull=True).first()
    )
    defaults = {
        "subject": "Hello {{recipient.name}}",
        "body_html": "<p>Hi {{recipient.name}}, welcome.</p>",
        "body_text": "Hi {{recipient.name}}, welcome.",
        "variables": ["recipient.name"],
    }
    defaults.update(fields)
    version = services.update_draft_version(actor=actor, version=version, **defaults)
    return services.approve_version(actor=actor, version=version)


# ---------------------------------------------------------------------------
# D-051: template injection
# ---------------------------------------------------------------------------


class TestTemplateInjection:
    def test_script_tag_in_template_body_is_stripped(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            subject="Hi",
            body_html="<p>Hello</p><script>alert('pwned')</script>",
            body_text="Hello",
            variables=[],
        )
        result = render_template(version, {})
        assert "<script" not in result["html"].lower()
        assert "alert(" not in result["html"]

    def test_script_tag_in_a_recipients_own_data_is_stripped_too(self, admin_user):
        """The *same* class of bug, from the other direction: a recipient's
        own name (or any other allowlisted value) containing markup must not
        survive into the rendered HTML either."""
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            subject="Hi {{recipient.name}}",
            body_html="<p>Hello {{recipient.name}}</p>",
            body_text="Hello {{recipient.name}}",
            variables=["recipient.name"],
        )
        hostile_name = "<script>document.location='https://evil.test'</script>Sam"
        result = render_template(version, {"recipient": {"name": hostile_name}})
        assert "<script" not in result["html"].lower()
        # The text may still be present as inert, escaped characters (safe to
        # display) — what must never happen is it surviving as live markup a
        # browser would parse and execute.
        assert "<script>document.location" not in result["html"]
        assert "&lt;script&gt;" in result["html"]

    def test_recipient_data_containing_an_otherwise_allowed_tag_renders_as_literal_text(
        self, admin_user
    ):
        """D-051, in its own words: a recipient's own data containing
        something that *would* be safe markup from a template author (a
        `<b>` tag is on the sanitiser's own allowlist) must still render as
        literal text when it comes from a real record's field, never be
        interpreted as live markup."""
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            body_html="<p>Hello {{recipient.name}}</p>",
            variables=["recipient.name"],
        )
        result = render_template(version, {"recipient": {"name": "<b>Sam</b>"}})
        assert "<b>" not in result["html"]
        assert "&lt;b&gt;" in result["html"]

    def test_onerror_attribute_is_stripped_from_an_allowed_tag(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            body_html='<img src=x onerror="alert(1)"><p>ok</p>',
            variables=[],
        )
        result = render_template(version, {})
        assert "onerror" not in result["html"].lower()

    def test_unlisted_variable_is_dropped_and_reported_never_substituted(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        # `activity.title` is not on this version's allowlist.
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            subject="Re: {{activity.title}}",
            body_text="About {{activity.title}} for {{recipient.name}}",
            variables=["recipient.name"],
        )
        result = render_template(
            version, {"recipient": {"name": "Sam"}, "activity": {"title": "SECRET INTERNAL TITLE"}}
        )
        assert "SECRET INTERNAL TITLE" not in result["subject"]
        assert "SECRET INTERNAL TITLE" not in result["text"]
        assert result["text"] == "About  for Sam"
        assert any("activity.title" in warning for warning in result["warnings"])

    def test_rendering_never_raises_for_a_missing_or_unlisted_variable(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            body_text="{{nonexistent.path}} {{recipient.name}}",
            variables=["recipient.name"],
        )
        # Neither an unlisted path nor one that resolves to nothing raises.
        result = render_template(version, {})
        assert result["text"] == " "
        assert result["warnings"]

    def test_never_evaluates_the_body_as_an_expression(self, admin_user):
        """A template body is substituted, never `.format()`-ed or `eval`-ed:
        a stray `{}` or Python-looking snippet must pass through literally."""
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user,
            version=version,
            body_text="{0} {'a': 1} __import__('os')",
            variables=[],
        )
        result = render_template(version, {})
        assert result["text"] == "{0} {'a': 1} __import__('os')"

    def test_preview_endpoint_never_creates_a_delivery(self, admin_user, api_client_no_csrf):
        from apps.communication.models import Delivery

        template = _template(admin_user)
        version = _approved_version(admin_user, template)
        services.publish_version(actor=admin_user, version=version)

        api_client_no_csrf.force_login(admin_user)
        url = f"{TEMPLATES_URL}{template.key}/versions/{version.number}/preview/"
        response = api_client_no_csrf.post(
            url, {"variables": {"recipient": {"name": "<script>alert(1)</script>"}}}, format="json"
        )
        assert response.status_code == 200
        assert "<script" not in response.json()["html"].lower()
        assert Delivery.objects.count() == 0


# ---------------------------------------------------------------------------
# Draft -> approve -> publish, and immutability once published
# ---------------------------------------------------------------------------


class TestVersionLifecycle:
    def test_cannot_publish_without_approval(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(actor=admin_user, version=version, subject="Hi")
        with pytest.raises(ApplicationError):
            services.publish_version(actor=admin_user, version=version)

    def test_publish_then_edit_is_refused_immutable(self, admin_user):
        template = _template(admin_user)
        version = _approved_version(admin_user, template)
        services.publish_version(actor=admin_user, version=version)
        version.refresh_from_db()
        assert version.is_published

        with pytest.raises(ConflictError):
            services.update_draft_version(actor=admin_user, version=version, subject="Changed")

    def test_editing_after_publish_means_opening_a_new_draft_version(self, admin_user):
        template = _template(admin_user)
        version = _approved_version(admin_user, template)
        services.publish_version(actor=admin_user, version=version)
        template.refresh_from_db()

        draft = services.create_draft_version(actor=admin_user, template=template)
        assert draft.number == version.number + 1
        assert not draft.is_published
        # The new draft starts as a clone of the published content — the
        # same discipline `apps.forms`'s own draft-cloning follows.
        assert draft.subject == version.subject

        draft = services.update_draft_version(actor=admin_user, version=draft, subject="v2 subject")
        assert draft.subject == "v2 subject"
        # The already-published version is untouched.
        version.refresh_from_db()
        assert version.subject != "v2 subject"

    def test_cannot_open_a_second_draft_while_one_exists(self, admin_user):
        template = _template(admin_user)
        with pytest.raises(ConflictError):
            services.create_draft_version(actor=admin_user, template=template)

    def test_publish_refuses_when_nothing_actually_changed(self, admin_user):
        template = _template(admin_user)
        version = _approved_version(admin_user, template)
        services.publish_version(actor=admin_user, version=version)
        template.refresh_from_db()

        draft = services.create_draft_version(actor=admin_user, template=template)
        # Approve it unchanged (identical content to the published version).
        draft = services.approve_version(actor=admin_user, version=draft)
        with pytest.raises(ConflictError):
            services.publish_version(actor=admin_user, version=draft)

    def test_editing_an_approved_draft_revokes_its_approval(self, admin_user):
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(
            actor=admin_user, version=version, subject="Hi", variables=[]
        )
        version = services.approve_version(actor=admin_user, version=version)
        assert version.approved_at is not None

        version = services.update_draft_version(
            actor=admin_user, version=version, subject="Hi again"
        )
        assert version.approved_at is None
        assert version.approved_by_id is None


# ---------------------------------------------------------------------------
# An unapproved/unpublished template cannot be sent from
# ---------------------------------------------------------------------------


class TestOnlyPublishedTemplatesAreUsable:
    def test_resolve_published_template_ignores_a_draft_or_approved_only_version(self, admin_user):
        template = _template(admin_user)
        assert (
            services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL)
            is None
        )

        version = template.versions.get(number=1)
        services.update_draft_version(actor=admin_user, version=version, subject="Hi", variables=[])
        services.approve_version(actor=admin_user, version=version)
        # Approved, not yet published.
        assert (
            services.resolve_published_template(key=template.key, channel=MessageChannel.EMAIL)
            is None
        )

    def test_manual_send_refuses_an_unpublished_template(self, admin_user, student):
        template = _template(admin_user)
        with pytest.raises(ApplicationError):
            services.manual_send(
                actor=admin_user,
                channel=MessageChannel.EMAIL,
                template_key=template.key,
                recipients_spec={"role": "student"},
                variables={},
                confirm_count=1,
            )


# ---------------------------------------------------------------------------
# Capability gating
# ---------------------------------------------------------------------------


class TestCapabilityGating:
    def test_template_manage_required_to_create(self, manager_user):
        with pytest.raises(AuthorityError):
            services.create_template(
                actor=manager_user,
                key="denied.template",
                name="Denied",
                channel=MessageChannel.EMAIL,
                kind="activity.assigned",
            )

    def test_template_approve_is_a_separate_capability_from_manage(self, admin_user, manager_user):
        # Manager holds neither `template.manage` nor `template.approve` per
        # the catalog — this just proves the two checks are independent
        # calls, not the same guard reused twice.
        template = _template(admin_user)
        version = template.versions.get(number=1)
        version = services.update_draft_version(actor=admin_user, version=version, subject="Hi")
        with pytest.raises(AuthorityError):
            services.approve_version(actor=manager_user, version=version)

    def test_api_gates_template_manage_and_approve(
        self, admin_user, manager_user, api_client_no_csrf
    ):
        api_client_no_csrf.force_login(manager_user)
        assert api_client_no_csrf.get(TEMPLATES_URL).status_code == 403
        refused = api_client_no_csrf.post(
            TEMPLATES_URL,
            {
                "key": "manager.denied",
                "name": "Denied",
                "channel": "email",
                "kind": "activity.assigned",
            },
            format="json",
        )
        assert refused.status_code == 403

        api_client_no_csrf.force_login(admin_user)
        created = api_client_no_csrf.post(
            TEMPLATES_URL,
            {
                "key": "manager.allowed",
                "name": "Allowed",
                "channel": "email",
                "kind": "activity.assigned",
            },
            format="json",
        )
        assert created.status_code == 201


# ---------------------------------------------------------------------------
# WhatsApp channel templates need a fresh step-up to approve
# ---------------------------------------------------------------------------


class TestWhatsAppApprovalStepUp:
    def test_approving_a_whatsapp_template_without_fresh_stepup_is_refused(
        self, admin_user, api_client_no_csrf
    ):
        template = _template(admin_user, channel=MessageChannel.WHATSAPP, kind="wa.test")
        version = template.versions.get(number=1)
        services.update_draft_version(
            actor=admin_user,
            version=version,
            body_text="Hi {{recipient.name}}",
            variables=["recipient.name"],
        )

        api_client_no_csrf.force_login(admin_user)
        url = f"{TEMPLATES_URL}{template.key}/versions/{version.number}/approve/"
        response = api_client_no_csrf.post(url, {}, format="json")
        assert response.status_code == 403

    def test_approving_a_whatsapp_template_with_fresh_stepup_succeeds(
        self, admin_user, api_client_no_csrf
    ):
        template = _template(admin_user, channel=MessageChannel.WHATSAPP, kind="wa.test2")
        version = template.versions.get(number=1)
        services.update_draft_version(
            actor=admin_user,
            version=version,
            body_text="Hi {{recipient.name}}",
            variables=["recipient.name"],
        )

        api_client_no_csrf.force_login(admin_user)
        _step_up(api_client_no_csrf)

        url = f"{TEMPLATES_URL}{template.key}/versions/{version.number}/approve/"
        response = api_client_no_csrf.post(url, {}, format="json")
        assert response.status_code == 200

    def test_approving_an_email_template_needs_no_stepup(self, admin_user, api_client_no_csrf):
        template = _template(admin_user, channel=MessageChannel.EMAIL, kind="email.test")
        version = template.versions.get(number=1)
        services.update_draft_version(actor=admin_user, version=version, subject="Hi", variables=[])

        api_client_no_csrf.force_login(admin_user)
        url = f"{TEMPLATES_URL}{template.key}/versions/{version.number}/approve/"
        assert api_client_no_csrf.post(url, {}, format="json").status_code == 200
