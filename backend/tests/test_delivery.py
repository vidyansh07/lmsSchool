"""The delivery log and manual send (ERP Phase 19, ADR-12).

Per the phase's plan row:
- retry only from `failed`, cancel only from `queued`;
- `GET /deliveries/` never includes an OTP delivery's variables/body (there
  is no such row to begin with — see `apps.communication.services`'s module
  docstring; this file asserts the structural guarantee directly);
- the manual-send `confirm_count` mismatch is refused with a freshly
  recomputed count, never the client's own stale number.
"""

from __future__ import annotations

import pytest

from apps.common.exceptions import ApplicationError, ConflictError
from apps.communication import services
from apps.communication.models import Delivery, DeliveryState, MessageChannel

pytestmark = pytest.mark.django_db

DELIVERIES_URL = "/api/v1/deliveries/"


def _published_email_template(actor, key="test.delivery.template"):
    template = services.create_template(
        actor=actor,
        key=key,
        name="Delivery test template",
        channel=MessageChannel.EMAIL,
        kind="activity.assigned",
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=actor,
        version=version,
        subject="Hello {{recipient.name}}",
        body_text="Hi {{recipient.name}}",
        variables=["recipient.name"],
    )
    version = services.approve_version(actor=actor, version=version)
    return services.publish_version(actor=actor, version=version)


def _delivery(**overrides) -> Delivery:
    defaults = {
        "channel": MessageChannel.EMAIL,
        "address": "someone@example.test",
        "state": DeliveryState.QUEUED,
    }
    defaults.update(overrides)
    return Delivery.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Retry only from failed, cancel only from queued
# ---------------------------------------------------------------------------


class TestRetryAndCancelStateGuards:
    @pytest.mark.parametrize(
        "state", [DeliveryState.QUEUED, DeliveryState.SENT, DeliveryState.CANCELLED]
    )
    def test_retry_refused_unless_failed(self, admin_user, state):
        delivery = _delivery(state=state)
        with pytest.raises(ConflictError):
            services.retry_delivery(actor=admin_user, delivery=delivery)

    def test_retry_succeeds_from_failed_and_requeues(self, admin_user):
        delivery = _delivery(state=DeliveryState.FAILED, error="boom", attempts=1)
        result = services.retry_delivery(actor=admin_user, delivery=delivery)
        assert result.state == DeliveryState.QUEUED
        assert result.next_attempt_at is None

    @pytest.mark.parametrize(
        "state",
        [
            DeliveryState.FAILED,
            DeliveryState.SENT,
            DeliveryState.PROCESSING,
            DeliveryState.CANCELLED,
        ],
    )
    def test_cancel_refused_unless_queued(self, admin_user, state):
        delivery = _delivery(state=state)
        with pytest.raises(ConflictError):
            services.cancel_delivery(actor=admin_user, delivery=delivery)

    def test_cancel_succeeds_from_queued(self, admin_user):
        delivery = _delivery(state=DeliveryState.QUEUED)
        result = services.cancel_delivery(actor=admin_user, delivery=delivery)
        assert result.state == DeliveryState.CANCELLED

    def test_retry_and_cancel_require_communication_send(self, manager_user):
        # manager_user *does* hold communication.send per the catalog, so
        # prove the guard the other way: a role that does not.
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole

        trainer = User.objects.create_user(
            email="trainer.delivery@example.test",
            password="whatever-not-used",
            first_name="T",
            last_name="Trainer",
            role=UserRole.TRAINER,
            branch=manager_user.branch,
        )
        from apps.common.exceptions import AuthorityError

        queued = _delivery(state=DeliveryState.QUEUED)
        with pytest.raises(AuthorityError):
            services.cancel_delivery(actor=trainer, delivery=queued)

        failed = _delivery(state=DeliveryState.FAILED)
        with pytest.raises(AuthorityError):
            services.retry_delivery(actor=trainer, delivery=failed)

    def test_api_retry_and_cancel_respect_state_guards(self, admin_user, api_client_no_csrf):
        api_client_no_csrf.force_login(admin_user)
        queued = _delivery(state=DeliveryState.QUEUED)
        failed = _delivery(state=DeliveryState.FAILED)

        # Wrong state, wrong endpoint.
        assert (
            api_client_no_csrf.post(
                f"{DELIVERIES_URL}{queued.pk}/retry/", {}, format="json"
            ).status_code
            == 409
        )
        assert (
            api_client_no_csrf.post(
                f"{DELIVERIES_URL}{failed.pk}/cancel/", {}, format="json"
            ).status_code
            == 409
        )
        # Right state, right endpoint.
        assert (
            api_client_no_csrf.post(
                f"{DELIVERIES_URL}{queued.pk}/cancel/", {}, format="json"
            ).status_code
            == 200
        )
        assert (
            api_client_no_csrf.post(
                f"{DELIVERIES_URL}{failed.pk}/retry/", {}, format="json"
            ).status_code
            == 200
        )


# ---------------------------------------------------------------------------
# GET /deliveries/ never carries an OTP send
# ---------------------------------------------------------------------------


class TestDeliveryLogExcludesOtp:
    def test_no_module_reachable_from_accounts_ever_imports_communication(self):
        """The structural half of the guarantee: an OTP send goes through
        `apps.accounts.otp`/`.emails` directly (`send_mail`, no `EmailMessage`
        row, no `Delivery` row) and never touches this app at all, so there
        is no code path by which an OTP send could ever create a `Delivery`
        row for `GET /deliveries/` to leak."""
        import apps.accounts.emails as emails_module
        import apps.accounts.otp as otp_module

        for module in (otp_module, emails_module):
            source = module.__file__
            with open(source, encoding="utf-8") as handle:
                contents = handle.read()
            assert "apps.communication" not in contents
            assert "from .communication" not in contents

    def test_deliveries_list_view_requires_capability_and_is_branch_scoped(
        self, admin_user, manager_user, other_branch_manager, api_client_no_csrf
    ):
        _delivery(state=DeliveryState.SENT, recipient=manager_user)
        _delivery(state=DeliveryState.SENT, recipient=other_branch_manager)

        api_client_no_csrf.force_login(manager_user)
        response = api_client_no_csrf.get(DELIVERIES_URL)
        assert response.status_code == 200
        recipients = {row["recipient"] for row in response.json()["results"]}
        assert str(manager_user.pk) in recipients
        assert str(other_branch_manager.pk) not in recipients

    def test_deliveries_list_denied_without_capability(self, student, api_client_no_csrf):
        api_client_no_csrf.force_login(student)
        assert api_client_no_csrf.get(DELIVERIES_URL).status_code == 403


# ---------------------------------------------------------------------------
# Manual send: confirm_count is always recomputed server-side
# ---------------------------------------------------------------------------


class TestManualSendConfirmCount:
    def test_stale_confirm_count_is_refused_with_409_and_the_fresh_count(
        self, admin_user, student_profile
    ):
        _published_email_template(admin_user, key="manual.send.count")
        # There is exactly one eligible student; the caller claims two.
        with pytest.raises(ConflictError) as excinfo:
            services.manual_send(
                actor=admin_user,
                channel=MessageChannel.EMAIL,
                template_key="manual.send.count",
                recipients_spec={"role": "student"},
                variables={},
                confirm_count=2,
            )
        message = str(excinfo.value.detail)
        assert "1" in message

    def test_correct_confirm_count_succeeds_and_queues_one_delivery_per_recipient(
        self, admin_user, student_profile, other_student_profile
    ):
        _published_email_template(admin_user, key="manual.send.count.ok")
        result = services.manual_send(
            actor=admin_user,
            channel=MessageChannel.EMAIL,
            template_key="manual.send.count.ok",
            recipients_spec={"role": "student"},
            variables={},
            confirm_count=2,
        )
        assert result["count"] == 2
        assert Delivery.objects.filter(pk__in=result["delivery_ids"]).count() == 2

    def test_a_client_cannot_shrink_the_recipient_set_by_lying_about_the_count(
        self, admin_user, student_profile, other_student_profile
    ):
        """Even a plausible-looking, too-small count is refused — the
        service recomputes and compares, it never trusts the client's
        number as a ceiling either."""
        _published_email_template(admin_user, key="manual.send.count.small")
        with pytest.raises(ConflictError):
            services.manual_send(
                actor=admin_user,
                channel=MessageChannel.EMAIL,
                template_key="manual.send.count.small",
                recipients_spec={"role": "student"},
                variables={},
                confirm_count=1,
            )

    def test_manual_send_requires_exactly_one_recipient_spec_key(self, admin_user):
        _published_email_template(admin_user, key="manual.send.badspec")
        with pytest.raises(ApplicationError):
            services.manual_send(
                actor=admin_user,
                channel=MessageChannel.EMAIL,
                template_key="manual.send.badspec",
                recipients_spec={},
                variables={},
                confirm_count=0,
            )

    def test_manual_send_audits_counts_only_never_recipient_pii(self, admin_user, student_profile):
        from apps.audit.models import AuditLog

        _published_email_template(admin_user, key="manual.send.audit")
        services.manual_send(
            actor=admin_user,
            channel=MessageChannel.EMAIL,
            template_key="manual.send.audit",
            recipients_spec={"role": "student"},
            variables={},
            confirm_count=1,
        )
        entry = AuditLog.objects.filter(action="communication.sent").latest("created_at")
        assert entry.context.get("count") == 1
        assert str(student_profile.user_id) not in str(entry.context)
        assert student_profile.user.email not in str(entry.context)
