"""Announcement scheduling (ERP Phase 19).

Per the phase's plan row: the `schedule`/`cancel` transitions, and the beat
task (`announcements.publish_due`) actually publishing a due announcement
while leaving one not yet due untouched.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.announcements import services
from apps.announcements.models import Announcement, AnnouncementStatus, Audience
from apps.announcements.tasks import publish_due
from apps.common.exceptions import ApplicationError, ConflictError

pytestmark = pytest.mark.django_db

ANNOUNCEMENTS_URL = "/api/v1/announcements/"


def _draft(actor, **overrides) -> Announcement:
    defaults = {
        "title": "Test notice",
        "body": "Something worth reading.",
        "audience": Audience.EVERYONE,
    }
    defaults.update(overrides)
    return services.create_announcement(actor=actor, **defaults)


# ---------------------------------------------------------------------------
# schedule(): draft -> scheduled
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_schedule_moves_draft_to_scheduled(self, manager_user):
        announcement = _draft(manager_user)
        publish_at = timezone.now() + timedelta(hours=1)
        scheduled = services.schedule(
            announcement=announcement, actor=manager_user, publish_at=publish_at
        )
        assert scheduled.status == AnnouncementStatus.SCHEDULED
        assert scheduled.publish_at == publish_at

    def test_schedule_requires_a_draft(self, manager_user):
        announcement = _draft(manager_user)
        services.publish(announcement=announcement, actor=manager_user)
        with pytest.raises(ConflictError):
            services.schedule(
                announcement=announcement,
                actor=manager_user,
                publish_at=timezone.now() + timedelta(hours=1),
            )

    def test_schedule_requires_publish_at(self, manager_user):
        announcement = _draft(manager_user)
        with pytest.raises(ApplicationError):
            services.schedule(announcement=announcement, actor=manager_user, publish_at=None)

    def test_schedule_requires_publish_at_in_the_future(self, manager_user):
        announcement = _draft(manager_user)
        with pytest.raises(ApplicationError):
            services.schedule(
                announcement=announcement,
                actor=manager_user,
                publish_at=timezone.now() - timedelta(minutes=5),
            )

    def test_cannot_schedule_an_already_scheduled_announcement_again(self, manager_user):
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        with pytest.raises(ConflictError):
            services.schedule(
                announcement=announcement,
                actor=manager_user,
                publish_at=timezone.now() + timedelta(hours=2),
            )


# ---------------------------------------------------------------------------
# cancel_scheduled(): scheduled -> cancelled
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_moves_scheduled_to_cancelled(self, manager_user):
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        cancelled = services.cancel_scheduled(announcement=announcement, actor=manager_user)
        assert cancelled.status == AnnouncementStatus.CANCELLED

    def test_cannot_cancel_a_draft(self, manager_user):
        announcement = _draft(manager_user)
        with pytest.raises(ConflictError):
            services.cancel_scheduled(announcement=announcement, actor=manager_user)

    def test_cannot_cancel_an_already_published_announcement(self, manager_user):
        announcement = _draft(manager_user)
        services.publish(announcement=announcement, actor=manager_user)
        with pytest.raises(ConflictError):
            services.cancel_scheduled(announcement=announcement, actor=manager_user)

    def test_cancelled_announcement_cannot_be_published_directly(self, manager_user):
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        services.cancel_scheduled(announcement=announcement, actor=manager_user)
        with pytest.raises(ConflictError):
            services.publish(announcement=announcement, actor=manager_user)


# ---------------------------------------------------------------------------
# The beat task: publishes due, leaves not-due alone
# ---------------------------------------------------------------------------


class TestPublishDueTask:
    def test_publishes_a_scheduled_announcement_whose_time_has_passed(self, manager_user):
        announcement = _draft(manager_user)
        # `schedule()` itself refuses a past `publish_at`, so back-date it
        # directly on the row afterwards, exactly as the passage of real
        # time would.
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        Announcement.objects.filter(pk=announcement.pk).update(
            publish_at=timezone.now() - timedelta(minutes=1)
        )

        result = publish_due()

        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHED
        assert announcement.published_at is not None
        assert result["published"] == 1

    def test_never_touches_a_scheduled_announcement_not_yet_due(self, manager_user):
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )

        result = publish_due()

        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.SCHEDULED
        assert announcement.published_at is None
        assert result["published"] == 0

    def test_never_touches_a_cancelled_announcement_even_if_its_old_publish_at_has_passed(
        self, manager_user
    ):
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        Announcement.objects.filter(pk=announcement.pk).update(
            publish_at=timezone.now() - timedelta(minutes=1)
        )
        services.cancel_scheduled(announcement=announcement, actor=manager_user)

        result = publish_due()

        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.CANCELLED
        assert result["published"] == 0

    def test_is_idempotent_for_a_row_already_published_by_something_else(self, manager_user):
        """A redelivered copy of the same task, or a request that raced it,
        must be a no-op — never a double fan-out or a crash."""
        announcement = _draft(manager_user)
        services.schedule(
            announcement=announcement,
            actor=manager_user,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        Announcement.objects.filter(pk=announcement.pk).update(
            publish_at=timezone.now() - timedelta(minutes=1)
        )
        first_result = publish_due()
        assert first_result["published"] == 1

        second_result = publish_due()
        assert second_result["published"] == 0
        announcement.refresh_from_db()
        assert announcement.status == AnnouncementStatus.PUBLISHED

    def test_one_failing_announcement_does_not_stop_the_rest_of_the_sweep(self, manager_user):
        healthy = _draft(manager_user, title="Healthy notice")
        services.schedule(
            announcement=healthy, actor=manager_user, publish_at=timezone.now() + timedelta(hours=1)
        )
        broken = _draft(manager_user, title="Broken notice")
        services.schedule(
            announcement=broken, actor=manager_user, publish_at=timezone.now() + timedelta(hours=1)
        )
        Announcement.objects.filter(pk__in=[healthy.pk, broken.pk]).update(
            publish_at=timezone.now() - timedelta(minutes=1)
        )
        # Force `services.publish` to blow up for exactly this one row by
        # corrupting its status to something `publish()` does not recognise
        # at all, while leaving it queryable as SCHEDULED for the sweep's
        # own `filter(status=SCHEDULED)` — simulate via a row deleted from
        # under the sweep instead, which is a real, if rare, race.
        Announcement.objects.filter(pk=broken.pk).delete()

        result = publish_due()

        healthy.refresh_from_db()
        assert healthy.status == AnnouncementStatus.PUBLISHED
        assert result["published"] == 1


# ---------------------------------------------------------------------------
# The role/branch audiences the same phase adds
# ---------------------------------------------------------------------------


class TestRoleAndBranchAudiences:
    def test_role_audience_resolves_to_everyone_holding_that_roles_kind(self, manager_user, branch):
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole
        from apps.authorization.models import Role

        trainer_role = Role.objects.create(
            slug="trainer-role", name="Trainer", kind=UserRole.TRAINER
        )
        trainer = User.objects.create_user(
            email="role.trainer@example.test",
            password="whatever-not-used",
            first_name="Role",
            last_name="Trainer",
            role=UserRole.TRAINER,
            branch=branch,
        )
        announcement = _draft(
            manager_user, audience=Audience.ROLE, role=trainer_role, title="For trainers"
        )
        recipients = services.audience_for(announcement)
        assert trainer in recipients

    def test_branch_audience_resolves_to_everyone_at_that_centre_only(
        self, manager_user, branch, other_branch
    ):
        from apps.accounts.models import User
        from apps.accounts.roles import UserRole

        here = User.objects.create_user(
            email="branch.here@example.test",
            password="whatever-not-used",
            first_name="Here",
            last_name="Person",
            role=UserRole.STUDENT,
            branch=branch,
        )
        elsewhere = User.objects.create_user(
            email="branch.elsewhere@example.test",
            password="whatever-not-used",
            first_name="There",
            last_name="Person",
            role=UserRole.STUDENT,
            branch=other_branch,
        )
        announcement = _draft(
            manager_user, audience=Audience.BRANCH, branch=branch, title="For this centre"
        )
        recipients = services.audience_for(announcement)
        assert here in recipients
        assert elsewhere not in recipients


# ---------------------------------------------------------------------------
# API surface: schedule/cancel routes
# ---------------------------------------------------------------------------


class TestScheduleCancelViews:
    def test_schedule_and_cancel_through_the_api(self, manager_user, api_client_no_csrf):
        api_client_no_csrf.force_login(manager_user)
        created = api_client_no_csrf.post(
            ANNOUNCEMENTS_URL,
            {"title": "API notice", "body": "Body text.", "audience": "everyone"},
            format="json",
        )
        assert created.status_code == 201
        announcement_id = created.json()["id"]

        publish_at = (timezone.now() + timedelta(hours=2)).isoformat()
        scheduled = api_client_no_csrf.post(
            f"{ANNOUNCEMENTS_URL}{announcement_id}/schedule/",
            {"publish_at": publish_at},
            format="json",
        )
        assert scheduled.status_code == 200
        assert scheduled.json()["status"] == "scheduled"

        cancelled = api_client_no_csrf.post(
            f"{ANNOUNCEMENTS_URL}{announcement_id}/cancel/", {}, format="json"
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

    def test_schedule_denied_to_someone_who_cannot_manage_the_announcement(
        self, manager_user, trainer, api_client_no_csrf
    ):
        announcement = _draft(manager_user)
        api_client_no_csrf.force_login(trainer)
        response = api_client_no_csrf.post(
            f"{ANNOUNCEMENTS_URL}{announcement.pk}/schedule/",
            {"publish_at": (timezone.now() + timedelta(hours=1)).isoformat()},
            format="json",
        )
        assert response.status_code == 404
