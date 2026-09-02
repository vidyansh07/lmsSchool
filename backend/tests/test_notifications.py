"""Notifications, email and announcements — §7.1 to §7.3, and §7.9.

The recurring theme: a notification is a courtesy attached to something that
already happened, so nothing about it may break the thing it describes.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.announcements.models import Announcement, AnnouncementStatus, Audience
from apps.audit.models import AuditAction, AuditLog
from apps.notifications.models import (
    EmailMessage,
    EmailStatus,
    Notification,
    NotificationCategory,
    NotificationKind,
    NotificationPreference,
)


@pytest.fixture(autouse=True)
def _empty_outbox():
    mail.outbox.clear()
    yield
    mail.outbox.clear()


@pytest.fixture
def delivered(django_capture_on_commit_callbacks):
    """Run a block and then flush its on-commit callbacks.

    Notifications are delivered on commit — a notification for work that got
    rolled back is worse than a late one — and pytest-django rolls every test
    back, so the callbacks have to be drained by hand to observe delivery.
    """

    def run(action):
        with django_capture_on_commit_callbacks(execute=True):
            return action()

    return run


# ---------------------------------------------------------------------------
# §7.1 — notifications
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_notification_is_written_and_categorised(student_profile):
    from apps.notifications.services import notify

    notification = notify(
        recipient=student_profile.user,
        kind=NotificationKind.ASSIGNMENT_DUE,
        title="Something is due",
        link_path="/my-assignments",
    )

    assert notification is not None
    assert notification.category == NotificationCategory.SCHEDULE
    assert notification.is_read is False


@pytest.mark.django_db
def test_a_deactivated_account_is_not_notified(student_profile):
    """A suspended person must not learn anything from an email."""
    from apps.notifications.services import notify

    student_profile.user.is_active = False
    student_profile.user.save(update_fields=["is_active"])

    assert (
        notify(recipient=student_profile.user, kind=NotificationKind.ANNOUNCEMENT, title="Hello")
        is None
    )
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_notify_many_does_not_tell_anybody_twice(student_profile, other_student_profile):
    from apps.notifications.services import notify_many

    told = notify_many(
        recipients=[student_profile.user, other_student_profile.user, student_profile.user],
        kind=NotificationKind.ANNOUNCEMENT,
        title="Once each",
    )

    assert told == 2
    assert Notification.objects.count() == 2


@pytest.mark.django_db
def test_a_notification_failure_never_breaks_the_thing_it_describes(
    admin_user, trainer_profile, student_profile, published_course, batch, enrollment
):
    """Grading must succeed even if the notification cannot be written."""
    from apps.assignments.models import AssignmentStatus
    from apps.assignments.services import (
        create_assignment,
        grade_submission,
        set_assignment_status,
        submit_assignment,
    )

    work = create_assignment(
        actor=admin_user,
        course=published_course,
        batch=batch,
        title="Marked",
        max_marks=Decimal("10"),
    )
    set_assignment_status(assignment=work, actor=admin_user, status=AssignmentStatus.PUBLISHED)
    submission = submit_assignment(
        assignment=work,
        enrollment=enrollment,
        actor=student_profile.user,
        files=[SimpleUploadedFile("a.py", b"pass\n")],
    )

    with mock.patch(
        "apps.notifications.services.Notification.objects.create",
        side_effect=Exception("notification store is down"),
    ):
        graded = grade_submission(
            submission=submission, actor=trainer_profile.user, marks=Decimal("9")
        )

    graded.refresh_from_db()
    assert graded.marks_awarded == Decimal("9.00")


@pytest.mark.django_db
def test_a_student_reads_and_clears_their_own_notifications(api_client_no_csrf, student_profile):
    from apps.notifications.services import notify

    for index in range(3):
        notify(
            recipient=student_profile.user,
            kind=NotificationKind.ANNOUNCEMENT,
            title=f"Notice {index}",
        )

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/notifications/unread/").json()["unread"] == 3

    listing = api_client_no_csrf.get("/api/v1/notifications/").json()
    first = listing["results"][0]["id"]
    api_client_no_csrf.post(f"/api/v1/notifications/{first}/read/", format="json")
    assert api_client_no_csrf.get("/api/v1/notifications/unread/").json()["unread"] == 2

    api_client_no_csrf.post("/api/v1/notifications/read-all/", format="json")
    assert api_client_no_csrf.get("/api/v1/notifications/unread/").json()["unread"] == 0


@pytest.mark.django_db
def test_a_student_cannot_read_another_students_notifications(
    api_client_no_csrf, student_profile, other_student_profile
):
    """§7.9 permission boundaries."""
    from apps.notifications.services import notify

    mine = notify(
        recipient=student_profile.user, kind=NotificationKind.ANNOUNCEMENT, title="Private"
    )

    api_client_no_csrf.force_login(other_student_profile.user)
    assert api_client_no_csrf.get("/api/v1/notifications/").json()["count"] == 0
    assert (
        api_client_no_csrf.post(f"/api/v1/notifications/{mine.id}/read/", format="json").status_code
        == 404
    )


# ---------------------------------------------------------------------------
# §7.2 — email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_notification_sends_an_email_and_records_it(student_profile, delivered):
    from apps.notifications.services import notify

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.RESULT_PUBLISHED,
            title="Week 1 test",
            body="15 out of 20.",
        )
    )

    assert len(mail.outbox) == 1
    message = EmailMessage.objects.get()
    assert message.status == EmailStatus.SENT
    assert message.sent_at is not None
    assert message.to_email == student_profile.user.email
    assert message.template == "result_published"


@pytest.mark.django_db
def test_turning_a_category_off_stops_its_email_but_not_the_notification(
    student_profile, delivered
):
    from apps.notifications.services import notify, update_preferences

    update_preferences(user=student_profile.user, email_academic=False)

    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.ASSIGNMENT_GRADED,
            title="Graded",
        )
    )

    assert Notification.objects.count() == 1
    assert len(mail.outbox) == 0
    assert EmailMessage.objects.count() == 0


@pytest.mark.django_db
def test_another_category_still_arrives(student_profile, delivered):
    from apps.notifications.services import notify, update_preferences

    update_preferences(user=student_profile.user, email_academic=False)
    delivered(
        lambda: notify(
            recipient=student_profile.user,
            kind=NotificationKind.ANNOUNCEMENT,
            title="Announcement",
        )
    )

    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_a_send_failure_is_recorded_and_retried_later(student_profile, delivered):
    """§7.9 email failure handling."""
    from apps.notifications.services import notify

    with mock.patch(
        "django.core.mail.send_mail", side_effect=Exception("smtp: connection refused")
    ):
        delivered(
            lambda: notify(
                recipient=student_profile.user,
                kind=NotificationKind.ANNOUNCEMENT,
                title="Will fail",
            )
        )

    message = EmailMessage.objects.get()
    assert message.status == EmailStatus.FAILED
    assert message.attempts == 1
    assert message.next_attempt_at > timezone.now()
    # The notification itself is unaffected: the student still sees it.
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_a_failure_never_stores_a_secret(student_profile, delivered):
    """§7.2: failure logging without secrets."""
    from apps.notifications.services import notify

    leaky = Exception("auth failed for password=hunter2 token=abcd1234")
    with mock.patch("django.core.mail.send_mail", side_effect=leaky):
        delivered(
            lambda: notify(
                recipient=student_profile.user, kind=NotificationKind.ANNOUNCEMENT, title="Leaky"
            )
        )

    stored = EmailMessage.objects.get().last_error
    assert "hunter2" not in stored
    assert "abcd1234" not in stored


@pytest.mark.django_db
def test_the_retry_command_sends_what_is_due(student_profile, delivered):
    from django.core.management import call_command

    from apps.notifications.services import notify

    with mock.patch("django.core.mail.send_mail", side_effect=Exception("down")):
        delivered(
            lambda: notify(
                recipient=student_profile.user, kind=NotificationKind.ANNOUNCEMENT, title="Retry me"
            )
        )

    message = EmailMessage.objects.get()
    message.next_attempt_at = timezone.now() - timedelta(minutes=1)
    message.save(update_fields=["next_attempt_at"])

    call_command("send_pending_email")

    message.refresh_from_db()
    assert message.status == EmailStatus.SENT
    assert message.attempts == 2


@pytest.mark.django_db
def test_a_message_is_given_up_on_eventually(student_profile, delivered):
    """A provider that refuses four times will refuse a fifth."""
    from django.core.management import call_command

    from apps.notifications.channels import MAX_ATTEMPTS
    from apps.notifications.services import notify

    with mock.patch("django.core.mail.send_mail", side_effect=Exception("down")):
        delivered(
            lambda: notify(
                recipient=student_profile.user, kind=NotificationKind.ANNOUNCEMENT, title="Doomed"
            )
        )
        for _ in range(MAX_ATTEMPTS):
            message = EmailMessage.objects.get()
            message.next_attempt_at = timezone.now() - timedelta(minutes=1)
            message.save(update_fields=["next_attempt_at"])
            call_command("send_pending_email")

    message = EmailMessage.objects.get()
    assert message.status == EmailStatus.ABANDONED
    assert message.attempts == MAX_ATTEMPTS


@pytest.mark.django_db
def test_a_student_manages_their_own_email_settings(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    defaults = api_client_no_csrf.get("/api/v1/notifications/preferences/").json()
    assert defaults["email_announcements"] is True

    changed = api_client_no_csrf.patch(
        "/api/v1/notifications/preferences/", {"email_announcements": False}, format="json"
    )
    assert changed.status_code == 200
    assert changed.json()["email_announcements"] is False
    assert (
        NotificationPreference.objects.get(user=student_profile.user).email_announcements is False
    )


# ---------------------------------------------------------------------------
# §7.3 — announcements
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_admin_announces_to_a_batch_and_the_cohort_is_told(
    api_client_no_csrf, admin_user, batch, enrollment, other_enrollment
):
    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {
            "title": "Lab moved to room 2",
            "body": "From Monday, the morning lab is in room 2.",
            "audience": Audience.BATCH,
            "batch": str(batch.id),
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    assert created.json()["status"] == AnnouncementStatus.DRAFT
    # A draft tells nobody.
    assert Notification.objects.count() == 0

    published = api_client_no_csrf.post(
        f"/api/v1/announcements/{created.json()['id']}/publish/", format="json"
    )
    assert published.status_code == 200
    assert Notification.objects.filter(kind=NotificationKind.ANNOUNCEMENT).count() == 2


@pytest.mark.django_db
def test_a_trainer_may_announce_to_their_own_batch_only(
    api_client_no_csrf, trainer_profile, batch, upcoming_batch
):
    """§7.3: an *authorized* trainer, which means per batch."""
    api_client_no_csrf.force_login(trainer_profile.user)

    mine = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {
            "title": "Bring your laptop",
            "body": "For tomorrow.",
            "audience": Audience.BATCH,
            "batch": str(batch.id),
        },
        format="json",
    )
    assert mine.status_code == 201

    theirs = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {
            "title": "Not mine",
            "body": "…",
            "audience": Audience.BATCH,
            "batch": str(upcoming_batch.id),
        },
        format="json",
    )
    assert theirs.status_code in (403, 404)


@pytest.mark.django_db
def test_a_trainer_cannot_announce_to_everyone(api_client_no_csrf, trainer_profile, batch):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {"title": "Everyone listen", "body": "…", "audience": Audience.EVERYONE},
        format="json",
    )

    assert response.status_code == 403
    assert Announcement.objects.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_announce(api_client_no_csrf, student_profile, batch, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {
            "title": "No lessons today",
            "body": "…",
            "audience": Audience.BATCH,
            "batch": str(batch.id),
        },
        format="json",
    )

    assert response.status_code in (403, 404)
    assert Announcement.objects.count() == 0


@pytest.mark.django_db
def test_a_student_sees_only_what_is_addressed_to_them(
    api_client_no_csrf, admin_user, batch, upcoming_batch, student_profile, enrollment
):
    """§7.9 notification targeting."""
    from apps.announcements.services import create_announcement, publish

    mine = create_announcement(
        actor=admin_user, title="For my batch", body="…", audience=Audience.BATCH, batch=batch
    )
    publish(announcement=mine, actor=admin_user)

    theirs = create_announcement(
        actor=admin_user,
        title="For another batch",
        body="…",
        audience=Audience.BATCH,
        batch=upcoming_batch,
    )
    publish(announcement=theirs, actor=admin_user)

    everyone = create_announcement(
        actor=admin_user, title="For everyone", body="…", audience=Audience.EVERYONE
    )
    publish(announcement=everyone, actor=admin_user)

    api_client_no_csrf.force_login(student_profile.user)
    titles = {
        row["title"] for row in api_client_no_csrf.get("/api/v1/announcements/").json()["results"]
    }

    assert "For my batch" in titles
    assert "For everyone" in titles
    assert "For another batch" not in titles


@pytest.mark.django_db
def test_a_student_never_sees_a_draft(
    api_client_no_csrf, admin_user, batch, student_profile, enrollment
):
    from apps.announcements.services import create_announcement

    create_announcement(
        actor=admin_user, title="Still writing", body="…", audience=Audience.BATCH, batch=batch
    )

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/announcements/").json()["count"] == 0


@pytest.mark.django_db
def test_an_expired_announcement_drops_off_the_board(
    api_client_no_csrf, admin_user, batch, student_profile, enrollment
):
    from apps.announcements.services import create_announcement, publish

    stale = create_announcement(
        actor=admin_user,
        title="Last week",
        body="…",
        audience=Audience.BATCH,
        batch=batch,
        expires_at=timezone.now() - timedelta(days=1),
    )
    publish(announcement=stale, actor=admin_user)

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get("/api/v1/announcements/").json()["count"] == 0


@pytest.mark.django_db
def test_an_audience_without_its_target_is_refused(admin_user):
    from apps.announcements.services import create_announcement
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        create_announcement(actor=admin_user, title="To a batch", body="…", audience=Audience.BATCH)


@pytest.mark.django_db
def test_the_audience_cannot_change_after_publication(admin_user, batch, upcoming_batch):
    from apps.announcements.services import create_announcement, publish, update_announcement
    from apps.common.exceptions import ConflictError

    announcement = create_announcement(
        actor=admin_user, title="Fixed", body="…", audience=Audience.BATCH, batch=batch
    )
    publish(announcement=announcement, actor=admin_user)

    with pytest.raises(ConflictError):
        update_announcement(announcement=announcement, actor=admin_user, batch=upcoming_batch)


@pytest.mark.django_db
def test_publishing_is_audited(admin_user, batch, enrollment):
    from apps.announcements.services import create_announcement, publish

    announcement = create_announcement(
        actor=admin_user, title="Audited", body="…", audience=Audience.BATCH, batch=batch
    )
    publish(announcement=announcement, actor=admin_user)

    entry = AuditLog.objects.filter(action=AuditAction.ANNOUNCEMENT_PUBLISHED).first()
    assert entry is not None
    assert entry.context["notified"] == 1


@pytest.mark.django_db
def test_an_anonymous_caller_reaches_nothing(api_client_no_csrf):
    for url in (
        "/api/v1/notifications/",
        "/api/v1/notifications/unread/",
        "/api/v1/announcements/",
    ):
        assert api_client_no_csrf.get(url).status_code in (401, 403), url
