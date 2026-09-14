"""Trainer requirements (D-132): a manager's ask of the teaching staff.

- a manager raises one and every trainer at the centre is told; the counsellor
  cannot raise one; a student cannot even read the list;
- a trainer replies and the raiser is told; a closed one takes no replies;
- closing names who fulfilled it, and the trainers who answered are told;
- another centre's requirement is a 404, not a 403;
- a removed requirement sits in the bin like everything else;
- the activity feed describes the three events;
- a plain announcement to the trainers of a centre reaches them and nobody else.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification, NotificationKind
from apps.requirements.models import RequirementStatus, TrainerRequirement

URL = "/api/v1/requirements/"


def _raise(client, **overrides):
    payload = {"title": "Evening Python batch needs a trainer", "details": "From Monday."}
    payload.update(overrides)
    return client.post(URL, payload, format="json")


@pytest.mark.django_db
def test_a_manager_raises_one_and_the_trainers_are_told(
    api_client_no_csrf, manager_user, trainer_profile, trainer_profile_two, batch
):
    api_client_no_csrf.force_login(manager_user)
    needed = (timezone.localdate() + timedelta(days=7)).isoformat()
    response = _raise(api_client_no_csrf, batch=str(batch.id), needed_by=needed)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == RequirementStatus.OPEN
    assert body["batch_code"] == batch.code
    assert body["raised_by_name"] == manager_user.get_full_name()
    assert body["reply_count"] == 0 and body["replies"] == []

    told = Notification.objects.filter(kind=NotificationKind.REQUIREMENT_RAISED)
    assert set(told.values_list("recipient_id", flat=True)) == {
        trainer_profile.user_id,
        trainer_profile_two.user_id,
    }
    assert told.first().link_path == f"/requirements?open={body['id']}"


@pytest.mark.django_db
def test_a_date_in_the_past_is_refused(api_client_no_csrf, manager_user):
    api_client_no_csrf.force_login(manager_user)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    response = _raise(api_client_no_csrf, needed_by=yesterday)
    assert response.status_code == 400
    assert "needed_by" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_a_counsellor_cannot_raise_one_but_a_student_cannot_even_look(
    api_client_no_csrf, counsellor_user, student_profile
):
    api_client_no_csrf.force_login(counsellor_user)
    assert _raise(api_client_no_csrf).status_code == 403

    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(URL).status_code == 403


@pytest.mark.django_db
def test_a_trainer_replies_and_the_raiser_is_told(
    api_client_no_csrf, manager_user, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    requirement_id = _raise(api_client_no_csrf).json()["id"]

    api_client_no_csrf.force_login(trainer_profile.user)
    listed = api_client_no_csrf.get(URL).json()["results"]
    assert [row["id"] for row in listed] == [requirement_id]

    reply = api_client_no_csrf.post(
        f"{URL}{requirement_id}/replies/", {"message": "I can take it."}, format="json"
    )
    assert reply.status_code == 201, reply.json()
    assert reply.json()["author_name"] == trainer_profile.user.get_full_name()

    told = Notification.objects.filter(kind=NotificationKind.REQUIREMENT_REPLIED)
    assert list(told.values_list("recipient_id", flat=True)) == [manager_user.pk]

    detail = api_client_no_csrf.get(f"{URL}{requirement_id}/").json()
    assert detail["reply_count"] == 1
    assert detail["replies"][0]["message"] == "I can take it."


@pytest.mark.django_db
def test_closing_names_who_fulfilled_it_and_refuses_further_replies(
    api_client_no_csrf, manager_user, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    requirement_id = _raise(api_client_no_csrf).json()["id"]
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(
        f"{URL}{requirement_id}/replies/", {"message": "Happy to."}, format="json"
    )

    # A trainer cannot close it.
    assert (
        api_client_no_csrf.post(f"{URL}{requirement_id}/close/", {}, format="json").status_code
        == 403
    )

    api_client_no_csrf.force_login(manager_user)
    closed = api_client_no_csrf.post(
        f"{URL}{requirement_id}/close/",
        {"fulfilled_by": str(trainer_profile.id), "note": "Starts Monday."},
        format="json",
    )
    assert closed.status_code == 200, closed.json()
    assert closed.json()["status"] == RequirementStatus.FULFILLED
    assert closed.json()["fulfilled_by_name"] == trainer_profile.user.get_full_name()
    assert closed.json()["closed_by_name"] == manager_user.get_full_name()

    again = api_client_no_csrf.post(f"{URL}{requirement_id}/close/", {}, format="json")
    assert again.status_code == 409

    api_client_no_csrf.force_login(trainer_profile.user)
    late = api_client_no_csrf.post(
        f"{URL}{requirement_id}/replies/", {"message": "Too late?"}, format="json"
    )
    assert late.status_code == 409
    # The trainer who answered heard the outcome.
    assert Notification.objects.filter(
        kind=NotificationKind.REQUIREMENT_REPLIED, recipient=trainer_profile.user
    ).exists()


@pytest.mark.django_db
def test_another_centres_requirement_does_not_exist(
    api_client_no_csrf, manager_user, other_branch_manager, other_branch_trainer
):
    api_client_no_csrf.force_login(manager_user)
    requirement_id = _raise(api_client_no_csrf).json()["id"]

    for outsider in (other_branch_manager, other_branch_trainer.user):
        api_client_no_csrf.force_login(outsider)
        assert api_client_no_csrf.get(URL).json()["results"] == []
        assert api_client_no_csrf.get(f"{URL}{requirement_id}/").status_code == 404
        assert (
            api_client_no_csrf.post(
                f"{URL}{requirement_id}/replies/", {"message": "?"}, format="json"
            ).status_code
            == 404
        )
    # The other centre's trainer was not told either.
    assert not Notification.objects.filter(recipient=other_branch_trainer.user).exists()


@pytest.mark.django_db
def test_an_administrator_sees_every_centre(
    api_client_no_csrf, manager_user, other_branch_manager, admin_user
):
    api_client_no_csrf.force_login(manager_user)
    _raise(api_client_no_csrf, title="Jaipur ask")
    api_client_no_csrf.force_login(other_branch_manager)
    _raise(api_client_no_csrf, title="Pune ask")

    api_client_no_csrf.force_login(admin_user)
    titles = {row["title"] for row in api_client_no_csrf.get(URL).json()["results"]}
    assert titles == {"Jaipur ask", "Pune ask"}
    only_open = api_client_no_csrf.get(f"{URL}?status=closed").json()["results"]
    assert only_open == []


@pytest.mark.django_db
def test_a_removed_requirement_sits_in_the_bin(api_client_no_csrf, manager_user, admin_user):
    api_client_no_csrf.force_login(manager_user)
    requirement_id = _raise(api_client_no_csrf).json()["id"]
    gone = api_client_no_csrf.delete(
        f"{URL}{requirement_id}/", {"reason": "Raised twice."}, format="json"
    )
    assert gone.status_code == 204
    assert not TrainerRequirement.objects.filter(pk=requirement_id).exists()
    assert TrainerRequirement.all_objects.get(pk=requirement_id).delete_reason == "Raised twice."

    api_client_no_csrf.force_login(admin_user)
    rows = api_client_no_csrf.get("/api/v1/recovery/requirements.trainerrequirement/").json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert any(row["id"] == requirement_id for row in rows)


@pytest.mark.django_db
def test_the_activity_feed_describes_the_events(
    api_client_no_csrf, manager_user, trainer_profile, admin_user
):
    api_client_no_csrf.force_login(manager_user)
    requirement_id = _raise(api_client_no_csrf, title="Cover Linux next week").json()["id"]
    api_client_no_csrf.force_login(trainer_profile.user)
    api_client_no_csrf.post(f"{URL}{requirement_id}/replies/", {"message": "Yes."}, format="json")
    api_client_no_csrf.force_login(manager_user)
    api_client_no_csrf.post(
        f"{URL}{requirement_id}/close/", {"fulfilled_by": str(trainer_profile.id)}, format="json"
    )

    api_client_no_csrf.force_login(admin_user)
    feed = api_client_no_csrf.get("/api/v1/activity/feed/?kind=communication").json()
    rows = feed["results"] if isinstance(feed, dict) else feed
    texts = [row["summary"] for row in rows]
    assert "Asked the trainers: Cover Linux next week" in texts
    assert "Answered on: Cover Linux next week" in texts
    assert any(text.startswith("Closed: Cover Linux next week (fulfilled by") for text in texts)
    assert all(
        row["href"] == f"/requirements?open={requirement_id}"
        for row in rows
        if row["resource_type"] == "trainer_requirement"
    )


@pytest.mark.django_db
def test_an_announcement_to_the_trainers_reaches_the_centres_teaching_staff_only(
    api_client_no_csrf,
    manager_user,
    trainer_profile,
    other_branch_trainer,
    student_profile,
    enrollment,
):
    from apps.announcements.models import Audience

    api_client_no_csrf.force_login(manager_user)
    created = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {
            "title": "Staff meeting Friday",
            "body": "4 pm, room 1.",
            "audience": Audience.TRAINERS,
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    preview = api_client_no_csrf.get(f"/api/v1/announcements/{created.json()['id']}/audience/")
    assert preview.status_code == 200 and preview.json()["recipients"] == 1

    published = api_client_no_csrf.post(
        f"/api/v1/announcements/{created.json()['id']}/publish/", format="json"
    )
    assert published.status_code == 200
    told = Notification.objects.filter(kind=NotificationKind.ANNOUNCEMENT)
    assert list(told.values_list("recipient_id", flat=True)) == [trainer_profile.user_id]

    api_client_no_csrf.force_login(trainer_profile.user)
    board = api_client_no_csrf.get("/api/v1/announcements/").json()["results"]
    assert [row["title"] for row in board] == ["Staff meeting Friday"]

    for outsider in (other_branch_trainer.user, student_profile.user):
        api_client_no_csrf.force_login(outsider)
        board = api_client_no_csrf.get("/api/v1/announcements/").json()["results"]
        assert "Staff meeting Friday" not in [row["title"] for row in board]


@pytest.mark.django_db
def test_a_trainer_cannot_address_the_trainers(api_client_no_csrf, trainer_profile):
    from apps.announcements.models import Audience

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        "/api/v1/announcements/",
        {"title": "Hi all", "body": "…", "audience": Audience.TRAINERS},
        format="json",
    )
    assert response.status_code == 403
