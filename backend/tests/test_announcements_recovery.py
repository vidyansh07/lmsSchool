"""Announcement soft-delete (Phase 7).

Deleting a notice is a genuine removal into the recycle bin, distinct from
`archive` — the editorial "off the board" transition the model already had.
The bin's own behaviour (listing, restoring, the closed-model-label defence)
is proved generically in ``test_recovery.py``; this file covers the two
things specific to this model: the delete endpoint itself, and the
branch-scoped restore guard now registered for it.
"""

from __future__ import annotations

import pytest

from apps.announcements.models import Announcement, AnnouncementStatus, Audience
from apps.announcements.services import create_announcement

BIN = "/api/v1/recovery/"
LABEL = "announcements.announcement"


@pytest.fixture
def notice(admin_user):
    return create_announcement(
        actor=admin_user,
        title="Holiday on Monday",
        body="The centre is closed for a public holiday.",
        audience=Audience.EVERYONE,
    )


@pytest.mark.django_db
def test_delete_removes_it_from_the_board(api_client_no_csrf, admin_user, notice):
    from apps.announcements.access import visible_announcements

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/announcements/{notice.pk}/delete/",
        {"reason": "Posted by mistake"},
        format="json",
    )

    assert response.status_code == 204
    assert not Announcement.objects.filter(pk=notice.pk).exists()
    assert notice.pk not in {a.pk for a in visible_announcements(admin_user)}
    assert Announcement.all_objects.dead().filter(pk=notice.pk).exists()


@pytest.mark.django_db
def test_delete_requires_a_reason(api_client_no_csrf, admin_user, notice):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/announcements/{notice.pk}/delete/", {"reason": ""}, format="json"
    )
    assert response.status_code == 400
    assert Announcement.objects.filter(pk=notice.pk).exists()


@pytest.mark.django_db
def test_delete_is_refused_to_someone_who_may_not_manage_it(
    api_client_no_csrf, other_branch_manager, notice
):
    """`manageable_announcements` is the gate — a manager at another centre
    cannot even find it (an institution-wide notice is readable, but writing
    to it is not, per `scope_board_management_to_branch`)."""
    api_client_no_csrf.force_login(other_branch_manager)
    response = api_client_no_csrf.post(
        f"/api/v1/announcements/{notice.pk}/delete/", {"reason": "Not mine"}, format="json"
    )
    assert response.status_code == 404
    assert Announcement.objects.filter(pk=notice.pk).exists()


@pytest.mark.django_db
def test_delete_is_distinct_from_archive(admin_user, notice):
    """Deleting does not touch the lifecycle status, and archiving does not
    soft-delete — two different concepts, not one collapsed into the other."""
    from apps.announcements import services

    services.publish(announcement=notice, actor=admin_user)
    archived = services.archive(announcement=notice, actor=admin_user)
    assert archived.status == AnnouncementStatus.ARCHIVED
    assert not archived.is_deleted

    services.delete_announcement(announcement=archived, actor=admin_user, reason="Cleanup")
    archived.refresh_from_db()
    assert archived.is_deleted
    assert archived.status == AnnouncementStatus.ARCHIVED


@pytest.mark.django_db
def test_an_administrator_restores_another_centres_notice(
    api_client_no_csrf, admin_user, unbounded_superadmin, other_branch_batch
):
    """An administrator sees every centre (D-129, amended 14 Sep 2026) — the
    same positive case every other `BRANCH_PATHS` entry proves in
    `test_branch_scoping_api.py`, restated for this model."""
    from apps.common.deletion import soft_delete

    batch_notice = create_announcement(
        actor=unbounded_superadmin,
        title="Extra class on Saturday",
        body="Room 4, 10am.",
        audience=Audience.BATCH,
        batch=other_branch_batch,
    )
    soft_delete(instance=batch_notice, actor=unbounded_superadmin, reason="Wrong batch")

    api_client_no_csrf.force_login(admin_user)
    restored = api_client_no_csrf.post(f"{BIN}{LABEL}/{batch_notice.pk}/restore/")
    assert restored.status_code == 200
    assert Announcement.objects.filter(pk=batch_notice.pk).exists()


@pytest.mark.django_db
def test_the_branch_path_itself_refuses_a_bounded_caller_outside_the_centre(
    admin_user, other_branch_manager, batch
):
    """`RECORD_RESTORE` today is held only by unbounded roles, so the guard's
    refusal branch is exercised directly here rather than through an HTTP
    round trip nothing bounded could reach in the first place — the same gap
    `_restorable_by`'s own unit-style coverage elsewhere in this suite closes
    for the other `BRANCH_PATHS` callables."""
    from apps.common.deletion import soft_delete
    from apps.common.recovery import _restorable_by

    batch_notice = create_announcement(
        actor=admin_user,
        title="Extra class on Saturday",
        body="Room 4, 10am.",
        audience=Audience.BATCH,
        batch=batch,
    )
    soft_delete(instance=batch_notice, actor=admin_user, reason="Wrong batch")
    batch_notice.refresh_from_db()

    assert _restorable_by(other_branch_manager, Announcement, batch_notice) is False
    assert _restorable_by(admin_user, Announcement, batch_notice) is True
