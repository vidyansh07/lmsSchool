"""The institution's own settings: resolving them, writing them, and what reads them.

A settings row nothing consumes is configuration that lies to the operator who
sets it, so most of this module is about the *consumers* — the email footer, the
outbound-mail switch, the export retention window, the upload ceiling — rather
than about the CRUD around the row.

Four failures are cheap to catch here and expensive to meet in production, and
each has a test named after it:

* A key in ``DEFAULT_SETTINGS`` with no field on ``EffectiveSettings`` makes
  ``EffectiveSettings(**resolved)`` raise ``TypeError`` on the *first*
  resolution anywhere — which is every test in the suite failing at once, with a
  message naming a keyword rather than the cause.
* A truthiness test instead of a membership test in the resolver would make
  ``notification_email_enabled=False`` un-turn-off-able: the operator's answer
  would be silently replaced by the default they were trying to change.
* Forgetting to drop the memo after a write means a serializer later in the same
  response renders the pre-write value, so the screen that just saved shows the
  old number.
* An operator's support phone number is personal data, and the audit context is
  scrubbed by key name rather than by content — so a before-and-after context of
  the kind `update_policy` writes would persist it verbatim for the life of the
  trail.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.accounts.roles import ROLE_CAPABILITIES, Capability, UserRole
from apps.audit.models import AuditAction, AuditLog
from apps.configuration.models import DEFAULT_SETTINGS, SETTING_FIELDS, SystemSetting
from apps.configuration.serializers import PublicSettingsSerializer
from apps.configuration.services import get_or_create_settings, update_settings
from apps.configuration.settings_resolver import (
    EffectiveSettings,
    effective_settings,
    export_retention,
    resource_upload_limit_bytes,
)
from apps.notifications.models import EmailMessage, Notification, NotificationKind


def _settings_url() -> str:
    return "/api/v1/settings/"


def _public_settings_url() -> str:
    return "/api/v1/settings/public/"


def _last_audit(action) -> AuditLog:
    return AuditLog.objects.filter(action=action).latest("created_at")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_row(db) -> SystemSetting:
    """The stored row, as an operator's first visit to the screen creates it."""
    return get_or_create_settings()


@pytest.fixture
def delivered(django_capture_on_commit_callbacks):
    """Run a block and flush its on-commit callbacks, so delivery is observable.

    Notifications are delivered on commit and pytest-django rolls every test
    back, so the callbacks have to be drained by hand.
    """

    def run(action):
        with django_capture_on_commit_callbacks(execute=True):
            return action()

    return run


# ---------------------------------------------------------------------------
# The registry: the three lists that must agree with each other
# ---------------------------------------------------------------------------


def test_every_default_setting_has_a_field_on_the_dataclass():
    """The cheap guard for the worst hazard in this feature.

    A key with no dataclass field raises `TypeError` on the first resolution
    anywhere, which is the whole suite failing with a message about a keyword
    argument rather than about a missing field.
    """
    assert SETTING_FIELDS, "the setting registry is empty — this test would be vacuous"
    assert set(SETTING_FIELDS) == set(EffectiveSettings.__dataclass_fields__)


def test_a_field_default_is_either_unset_or_the_resolved_default():
    """A freshly created row and the resolver must not answer differently.

    There are exactly two legal shapes for a column default. A text field
    defaults to the empty string, which is how the model says "nobody has set
    this" and is what makes the resolver supply the fallback; anything else
    must carry the same default the resolver would. A text column that defaulted
    to a *value* would mean a row created by the admin site disagreed with a row
    created by `get_or_create_settings`, and nothing else in the codebase would
    notice.
    """
    for field in SETTING_FIELDS:
        default = SystemSetting._meta.get_field(field).default
        assert default == "" or default == DEFAULT_SETTINGS[field], field


def test_settings_manage_is_an_administrator_capability_and_platform_configure_is_not():
    """The two must not be conflated.

    `platform.configure` is superadmin-only because it is the rung
    `can_grant_role` exists to withhold; changing the institution's address is
    an administrator's job.
    """
    assert Capability.SETTINGS_MANAGE in ROLE_CAPABILITIES[UserRole.ADMIN]
    assert Capability.PLATFORM_CONFIGURE not in ROLE_CAPABILITIES[UserRole.ADMIN]
    assert Capability.SETTINGS_MANAGE not in ROLE_CAPABILITIES[UserRole.MANAGER]


# ---------------------------------------------------------------------------
# Resolution and the fallback order
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_settings_resolve_to_their_defaults_before_anybody_writes_one():
    resolved = effective_settings()

    assert resolved.institution_name == DEFAULT_SETTINGS["institution_name"]
    assert resolved.export_retention_days == DEFAULT_SETTINGS["export_retention_days"]
    assert resolved.resource_upload_max_mb == DEFAULT_SETTINGS["resource_upload_max_mb"]


@pytest.mark.django_db
def test_an_empty_string_falls_back_to_the_default(settings_row):
    """An empty string is how the model says "not set"; NULL is not a second way."""
    settings_row.institution_name = ""
    settings_row.save(update_fields=["institution_name", "updated_at"])

    assert effective_settings().institution_name == DEFAULT_SETTINGS["institution_name"]


@pytest.mark.django_db
def test_a_false_boolean_is_not_mistaken_for_an_unset_value(settings_row):
    """Guards the one line where truthiness would make the switch un-turn-off-able."""
    settings_row.notification_email_enabled = False
    settings_row.save(update_fields=["notification_email_enabled", "updated_at"])

    assert effective_settings().notification_email_enabled is False


@pytest.mark.django_db
def test_a_zero_is_not_mistaken_for_an_unset_value(settings_row):
    """The same property for an integer, asserted below the API.

    Written through the model rather than the endpoint so it holds for a
    management command and a data migration too, neither of which passes
    through the serializer's range check.
    """
    settings_row.export_retention_days = 0
    settings_row.save(update_fields=["export_retention_days", "updated_at"])

    assert effective_settings().export_retention_days == 0


@pytest.mark.django_db
def test_the_settings_are_resolved_once_per_request(django_assert_num_queries, settings_row):
    with django_assert_num_queries(1):
        effective_settings()
        effective_settings()


@pytest.mark.django_db
def test_writing_a_setting_drops_the_memo_in_the_same_request(admin_user, settings_row):
    """Otherwise a serializer later in the same response renders the old value."""
    assert effective_settings().institution_name == "Grras Solutions"

    update_settings(settings_row=settings_row, actor=admin_user, institution_name="Sunrise Academy")

    assert effective_settings().institution_name == "Sunrise Academy"


@pytest.mark.django_db
def test_dropping_the_settings_memo_does_not_drop_the_policy_memo(
    django_assert_num_queries, admin_user, settings_row
):
    """Pins `clear_scope("system-settings")` rather than the bare `clear_scope()`.

    `forget_resolved_policies` clears everything only because it predates any
    second consumer of the request scope. Copying it here would make a settings
    write throw away the academic policy this request already paid to resolve.
    """
    from apps.academics.policies import policy_for

    policy_for()
    update_settings(settings_row=settings_row, actor=admin_user, support_phone="+91 141 000 0000")

    with django_assert_num_queries(0):
        policy_for()


# ---------------------------------------------------------------------------
# One row, created on demand
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_one_settings_row_can_exist(settings_row):
    """The database enforces it, not a convention somebody eventually breaks."""
    with pytest.raises(IntegrityError), transaction.atomic():
        SystemSetting.objects.create()


@pytest.mark.django_db
def test_the_row_is_created_on_first_use_and_not_by_a_migration():
    """A migration that creates a row must be reversed, and races a second worker."""
    assert SystemSetting.objects.count() == 0

    first = get_or_create_settings()
    second = get_or_create_settings()

    assert SystemSetting.objects.count() == 1
    assert first.pk == second.pk


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("value", [0, 400])
def test_an_export_retention_outside_the_range_is_refused(
    api_client_no_csrf, admin_user, settings_row, value
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _settings_url(), {"export_retention_days": value}, format="json"
    )

    assert response.status_code == 400, response.data
    assert "export_retention_days" in response.json()["error"]["details"], value
    settings_row.refresh_from_db()
    assert settings_row.export_retention_days == 14, value


@pytest.mark.django_db
@pytest.mark.parametrize("value", [0, 500])
def test_an_upload_ceiling_outside_the_range_is_refused(
    api_client_no_csrf, admin_user, settings_row, value
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _settings_url(), {"resource_upload_max_mb": value}, format="json"
    )

    assert response.status_code == 400, response.data
    assert "resource_upload_max_mb" in response.json()["error"]["details"], value
    settings_row.refresh_from_db()
    assert settings_row.resource_upload_max_mb == 25, value


@pytest.mark.django_db
def test_a_control_character_in_the_institution_name_is_refused(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _settings_url(), {"institution_name": "Sunrise\x07Academy"}, format="json"
    )

    assert response.status_code == 400, response.data
    assert "institution_name" in response.json()["error"]["details"]
    assert not SystemSetting.objects.filter(institution_name__contains="Sunrise").exists()


@pytest.mark.django_db
def test_a_malformed_support_email_is_refused(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _settings_url(), {"support_email": "not-an-address"}, format="json"
    )

    assert response.status_code == 400, response.data
    assert "support_email" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_an_unknown_field_is_refused(api_client_no_csrf, admin_user):
    """`StrictSerializer` names the field rather than ignoring it."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(_settings_url(), {"secret_key": "hunter2"}, format="json")

    assert response.status_code == 400, response.data
    assert response.json()["error"]["code"] == "validation_error"
    assert "secret_key" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_the_service_refuses_a_field_that_is_not_a_setting(admin_user, settings_row):
    """The same refusal one layer down: the API is one door of several."""
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        update_settings(settings_row=settings_row, actor=admin_user, secret_key="hunter2")


# ---------------------------------------------------------------------------
# Who may read and who may write
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_can_read_the_settings(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(_settings_url())

    assert response.status_code == 200, response.data
    assert set(SETTING_FIELDS) <= set(response.json())


@pytest.mark.django_db
def test_the_settings_screen_shows_the_values_actually_in_force(api_client_no_csrf, admin_user):
    """A fresh install must not show the administrator a different name from everybody else.

    The stored row's `institution_name` defaults to the empty string, which is
    how the model says "not set" — while the email footer, the public endpoint
    and the profile card all render `DEFAULT_SETTINGS["institution_name"]`.
    Serving the row rather than the resolved values put those two on screen at
    the same time, and nothing on either screen explained the difference.
    """
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(_settings_url()).json()

    assert body["institution_name"] == DEFAULT_SETTINGS["institution_name"]
    assert body["updated_by_name"] is None
    assert body["updated_at"] is None


@pytest.mark.django_db
def test_reading_the_settings_creates_no_row(api_client_no_csrf, admin_user):
    """A read is a read.

    Creating the row on GET meant two administrators opening the screen in the
    same second raced the `systemsetting_one_row` constraint, and one of them
    got a 500 from a page they had only looked at.
    """
    api_client_no_csrf.force_login(admin_user)

    assert api_client_no_csrf.get(_settings_url()).status_code == 200
    assert SystemSetting.objects.count() == 0


@pytest.mark.django_db
def test_the_settings_screen_says_who_changed_them_last(api_client_no_csrf, admin_user):
    """The positive half of the two assertions above."""
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        _settings_url(), {"institution_name": "Sunrise Academy"}, format="json"
    )

    body = api_client_no_csrf.get(_settings_url()).json()

    assert body["institution_name"] == "Sunrise Academy"
    assert body["updated_by_name"] == admin_user.full_name
    assert body["updated_at"] is not None


@pytest.mark.django_db
def test_an_administrator_can_change_the_settings(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.patch(
        _settings_url(), {"institution_name": "Sunrise Academy"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.json()["institution_name"] == "Sunrise Academy"
    assert SystemSetting.objects.get().institution_name == "Sunrise Academy"


@pytest.mark.django_db
def test_a_superadmin_can_change_the_settings(api_client_no_csrf, db):
    from apps.accounts.models import User

    superadmin = User.objects.create_user(
        email="root@demo.grras.invalid",
        password="correct-horse-battery-staple",
        first_name="Root",
        last_name="Admin",
        role=UserRole.SUPERADMIN,
    )
    api_client_no_csrf.force_login(superadmin)
    response = api_client_no_csrf.patch(
        _settings_url(), {"support_phone": "+91 141 000 0000"}, format="json"
    )

    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_a_manager_is_refused_the_settings(api_client_no_csrf, manager_user):
    api_client_no_csrf.force_login(manager_user)

    assert api_client_no_csrf.get(_settings_url()).status_code == 403
    assert (
        api_client_no_csrf.patch(
            _settings_url(), {"institution_name": "Sneaked"}, format="json"
        ).status_code
        == 403
    )
    assert not SystemSetting.objects.filter(institution_name="Sneaked").exists()


@pytest.mark.django_db
def test_a_counsellor_is_refused_the_settings(api_client_no_csrf, counsellor_user):
    api_client_no_csrf.force_login(counsellor_user)

    assert api_client_no_csrf.get(_settings_url()).status_code == 403
    assert (
        api_client_no_csrf.patch(
            _settings_url(), {"institution_name": "Sneaked"}, format="json"
        ).status_code
        == 403
    )
    assert not SystemSetting.objects.filter(institution_name="Sneaked").exists()


@pytest.mark.django_db
def test_a_trainer_is_refused_the_settings(api_client_no_csrf, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)

    assert api_client_no_csrf.get(_settings_url()).status_code == 403
    assert (
        api_client_no_csrf.patch(
            _settings_url(), {"institution_name": "Sneaked"}, format="json"
        ).status_code
        == 403
    )
    assert not SystemSetting.objects.filter(institution_name="Sneaked").exists()


@pytest.mark.django_db
def test_a_student_is_refused_the_settings(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    assert api_client_no_csrf.get(_settings_url()).status_code == 403
    assert (
        api_client_no_csrf.patch(
            _settings_url(), {"institution_name": "Sneaked"}, format="json"
        ).status_code
        == 403
    )
    assert not SystemSetting.objects.filter(institution_name="Sneaked").exists()


@pytest.mark.django_db
def test_an_anonymous_caller_is_refused_the_settings(api_client_no_csrf):
    assert api_client_no_csrf.get(_settings_url()).status_code in (401, 403)


@pytest.mark.django_db
def test_reading_the_settings_costs_one_query(
    django_assert_max_num_queries, api_client_no_csrf, admin_user, settings_row
):
    """Eight, of which exactly one is this endpoint's.

    The other seven are what every authenticated GET in this suite pays: the
    savepoints `ATOMIC_REQUESTS` opens and releases, the session read, the user
    read, and the session-expiry touch. What this pins is the difference — the
    settings row and its `updated_by` are fetched together, and resolving the
    values in force reuses that row rather than reading the table a second
    time. Either of those regressing takes it to nine.
    """
    api_client_no_csrf.force_login(admin_user)
    # The first request after a cache clear also resolves the caller's role
    # from its rows (ADR-01) and caches the set for ten minutes; that cost is
    # the roles cache's, not this endpoint's, so it is paid once before the
    # measurement.
    assert api_client_no_csrf.get(_settings_url()).status_code == 200
    with django_assert_max_num_queries(8):
        assert api_client_no_csrf.get(_settings_url()).status_code == 200


# ---------------------------------------------------------------------------
# The public three
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role", [UserRole.STUDENT, UserRole.TRAINER, UserRole.COUNSELLOR, UserRole.MANAGER, "admin"]
)
def test_anyone_signed_in_can_read_the_public_settings(api_client_no_csrf, db, role):
    from apps.accounts.models import User

    user = User.objects.create_user(
        email=f"public-{role}@demo.grras.invalid",
        password="correct-horse-battery-staple",
        first_name="Public",
        last_name=str(role).title(),
        role=role,
    )
    api_client_no_csrf.force_login(user)

    assert api_client_no_csrf.get(_public_settings_url()).status_code == 200, role


@pytest.mark.django_db
def test_the_public_settings_carry_nothing_administrative(
    api_client_no_csrf, student_profile, admin_user, settings_row
):
    """The test that stops a later setting leaking onto a student's screen.

    The key set is pinned exactly, so a field added to the model cannot arrive
    here by being added to one list and forgotten in another.
    """
    update_settings(
        settings_row=settings_row,
        actor=admin_user,
        institution_name="Sunrise Academy",
        support_email="help@sunrise.grras.invalid",
        support_phone="+91 141 000 0000",
        export_retention_days=3,
        resource_upload_max_mb=7,
        notification_email_enabled=False,
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(_public_settings_url())
    body = response.json()

    public = set(PublicSettingsSerializer().fields)
    assert response.status_code == 200, response.data
    # The vacuity guard: derived from the serializer, so widening that class
    # widens this test too — but only ever to a strict subset of the settings,
    # so it can never quietly become "the public shape is everything".
    assert public < set(SETTING_FIELDS)
    assert set(body) == public


@pytest.mark.django_db
def test_the_public_settings_are_refused_to_an_anonymous_caller(api_client_no_csrf):
    """Deliberately not `AllowAnyPublic`: nothing needs this before sign-in."""
    assert api_client_no_csrf.get(_public_settings_url()).status_code in (401, 403)


@pytest.mark.django_db
def test_the_public_settings_answer_before_any_row_exists(api_client_no_csrf, student_profile):
    """A fresh install must not 404 or 500 on the screen that renders this."""
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(_public_settings_url())

    assert response.status_code == 200, response.data
    assert response.json()["institution_name"] == DEFAULT_SETTINGS["institution_name"]
    assert SystemSetting.objects.count() == 0


# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_changing_a_setting_writes_an_audit_entry(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        _settings_url(), {"institution_name": "Sunrise Academy"}, format="json"
    )

    entry = _last_audit(AuditAction.SYSTEM_SETTINGS_UPDATED)
    assert entry.context["fields"] == ["institution_name"]
    assert entry.resource_type == "system_setting"
    assert entry.actor_id == admin_user.pk


@pytest.mark.django_db
def test_a_change_that_changes_nothing_writes_no_audit_entry(
    api_client_no_csrf, admin_user, settings_row
):
    api_client_no_csrf.force_login(admin_user)
    before = AuditLog.objects.filter(action=AuditAction.SYSTEM_SETTINGS_UPDATED).count()

    response = api_client_no_csrf.patch(
        _settings_url(),
        {"institution_name": settings_row.institution_name, "export_retention_days": 14},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert AuditLog.objects.filter(action=AuditAction.SYSTEM_SETTINGS_UPDATED).count() == before


@pytest.mark.django_db
def test_the_audit_entry_does_not_record_the_new_value(api_client_no_csrf, admin_user):
    """An operator's contact details are personal data.

    `apps.common.logging.scrub` redacts by key name, not by content, so a
    `{"from": …, "to": …}` context of the kind `update_policy` writes would
    persist a phone number and an address verbatim for the life of the trail.
    The field names on their own answer who changed what, when.
    """
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.patch(
        _settings_url(),
        {"support_phone": "+91 141 555 0199", "support_email": "help@sunrise.grras.invalid"},
        format="json",
    )

    entry = _last_audit(AuditAction.SYSTEM_SETTINGS_UPDATED)
    assert entry.context["fields"] == ["support_email", "support_phone"]
    assert "555 0199" not in str(entry.context)
    assert "help@sunrise.grras.invalid" not in str(entry.context)


# ---------------------------------------------------------------------------
# Consumer: the outbound email footer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_outbound_email_signs_off_with_the_configured_institution(
    admin_user, student_profile, settings_row, delivered
):
    from apps.notifications.services import notify

    update_settings(settings_row=settings_row, actor=admin_user, institution_name="Sunrise Academy")

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
        )
    )

    body = EmailMessage.objects.get().body
    assert "Sunrise Academy" in body
    assert "Grras Solutions" not in body


@pytest.mark.django_db
def test_the_outbound_email_carries_the_support_contact_when_one_is_set(
    admin_user, student_profile, settings_row, delivered
):
    from apps.notifications.services import notify

    update_settings(
        settings_row=settings_row,
        actor=admin_user,
        support_email="help@sunrise.grras.invalid",
    )

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
        )
    )

    assert "help@sunrise.grras.invalid" in EmailMessage.objects.get().body


@pytest.mark.django_db
def test_the_outbound_email_carries_no_contact_line_when_neither_is_set(student_profile, delivered):
    """A default install must not mail an empty "Need help?" line."""
    from apps.notifications.services import notify

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
        )
    )

    assert "Need help?" not in EmailMessage.objects.get().body


# ---------------------------------------------------------------------------
# Consumer: the outbound-mail switch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_turning_notification_email_off_still_writes_the_notification(
    admin_user, student_profile, settings_row, delivered
):
    """What makes the switch safe rather than a way to lose a notification."""
    from apps.notifications.services import notify

    update_settings(settings_row=settings_row, actor=admin_user, notification_email_enabled=False)

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
        )
    )

    assert Notification.objects.count() == 1
    assert EmailMessage.objects.count() == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_notification_email_is_delivered_when_the_setting_is_on(student_profile, delivered):
    """The positive half: the refusal above cannot pass on a broken system."""
    from apps.notifications.services import notify

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
        )
    )

    assert Notification.objects.count() == 1
    assert EmailMessage.objects.count() == 1


# ---------------------------------------------------------------------------
# Consumer: the export retention window
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_export_retention_window_comes_from_the_settings(
    api_client_no_csrf, admin_user, enrollment, settings_row
):
    from apps.reporting.models import ExportFormat, ExportJob

    update_settings(settings_row=settings_row, actor=admin_user, export_retention_days=3)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/reports/exports/",
        {"report_key": "student_progress", "format": ExportFormat.CSV},
    )
    job = ExportJob.objects.get(pk=response.json()["id"])

    assert job.expires_at - job.finished_at == timedelta(days=3)


@pytest.mark.django_db
def test_the_export_retention_window_defaults_to_the_code_constant(
    api_client_no_csrf, admin_user, enrollment
):
    """So the mirror between `EXPORT_RETENTION` and the default is real."""
    from apps.reporting.models import EXPORT_RETENTION, ExportFormat, ExportJob

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/reports/exports/",
        {"report_key": "student_progress", "format": ExportFormat.CSV},
    )
    job = ExportJob.objects.get(pk=response.json()["id"])

    assert job.expires_at - job.finished_at == EXPORT_RETENTION
    assert export_retention() == EXPORT_RETENTION


@pytest.mark.django_db
def test_a_retention_change_takes_effect_on_the_next_export_in_the_same_worker(
    api_client_no_csrf, admin_user, enrollment, settings_row, monkeypatch
):
    """The memo is per *request*, and a Celery worker never has one.

    `RequestContextMiddleware` is the only thing that calls
    `request_context.reset()`, and it does not run in a worker — so without a
    deliberate drop at the top of the task, the first job a worker process
    handled would pin the retention window for the life of that process, and an
    operator who shortened "keep exports for" would see no change until the
    next deploy.

    Both jobs are run directly rather than through the API, because an HTTP
    request between them would reset the scope and the test would pass whether
    or not the task drops the memo itself.
    """
    from apps.reporting import tasks
    from apps.reporting.models import EXPORT_RETENTION, ExportFormat, ExportJob

    monkeypatch.setattr(tasks.run_export, "delay", lambda *a, **k: None)

    def queue() -> ExportJob:
        api_client_no_csrf.force_login(admin_user)
        response = api_client_no_csrf.post(
            "/api/v1/reports/exports/",
            {"report_key": "student_progress", "format": ExportFormat.CSV},
        )
        assert response.status_code == 202, response.data
        return ExportJob.objects.get(pk=response.json()["id"])

    first, second = queue(), queue()

    tasks.run_export(str(first.pk))

    # Written through the queryset rather than through `update_settings`: this
    # stands in for the operator changing the setting in the *web* process,
    # whose `forget_resolved_settings()` cannot reach into a worker.
    SystemSetting.objects.filter(pk=settings_row.pk).update(export_retention_days=3)

    tasks.run_export(str(second.pk))

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.expires_at - first.finished_at == EXPORT_RETENTION
    assert second.expires_at - second.finished_at == timedelta(days=3)


# ---------------------------------------------------------------------------
# Consumer: the upload ceiling
# ---------------------------------------------------------------------------


def _upload_resource(client, lesson_id, content: bytes):
    return client.post(
        f"/api/v1/lessons/{lesson_id}/resources/",
        {
            "title": "Course handout",
            "file": SimpleUploadedFile("handout.pdf", content, content_type="application/pdf"),
        },
        format="multipart",
    )


@pytest.mark.django_db
def test_a_resource_larger_than_the_configured_ceiling_is_refused(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes, settings_row
):
    """And the message names the configured number, not the code default."""
    from apps.courses.models import LessonResource

    update_settings(settings_row=settings_row, actor=admin_user, resource_upload_max_mb=1)

    api_client_no_csrf.force_login(admin_user)
    response = _upload_resource(
        api_client_no_csrf, preview_lesson.id, pdf_bytes + b"0" * (2 * 1024 * 1024)
    )

    assert response.status_code == 400, response.data
    assert "1 MB or smaller" in str(response.json())
    assert LessonResource.objects.count() == 0


@pytest.mark.django_db
def test_the_same_resource_is_accepted_once_the_ceiling_is_raised(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes, settings_row
):
    from apps.courses.models import LessonResource

    update_settings(settings_row=settings_row, actor=admin_user, resource_upload_max_mb=5)

    api_client_no_csrf.force_login(admin_user)
    response = _upload_resource(
        api_client_no_csrf, preview_lesson.id, pdf_bytes + b"0" * (2 * 1024 * 1024)
    )

    assert response.status_code == 201, response.data
    assert LessonResource.objects.count() == 1


@pytest.mark.django_db
def test_the_default_upload_ceiling_mirrors_the_code_constant():
    """`MAX_RESOURCE_BYTES` and the default must not drift apart silently.

    The same guard the retention pair already has. Without it, changing the
    constant in `apps.common.uploads` would leave an unconfigured institution
    on the old ceiling, and the only symptom would be a file refused at a size
    the code says is allowed.
    """
    from apps.common.uploads import MAX_RESOURCE_BYTES

    assert resource_upload_limit_bytes() == MAX_RESOURCE_BYTES


@pytest.mark.django_db
def test_the_upload_limit_in_bytes_follows_the_setting(admin_user, settings_row):
    """The arithmetic lives in one place, so no consumer can get it wrong alone."""
    assert resource_upload_limit_bytes() == 25 * 1024 * 1024

    update_settings(settings_row=settings_row, actor=admin_user, resource_upload_max_mb=10)

    assert resource_upload_limit_bytes() == 10 * 1024 * 1024
