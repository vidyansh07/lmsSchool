"""A stale one-to-one profile must never grant access for the wrong role."""

from __future__ import annotations

import pytest

from apps.accounts.models import UserRole
from apps.accounts.serializers import CurrentUserSerializer
from apps.accounts.services import transition_user_role
from apps.announcements.services import teaching_staff_of
from apps.batches import access as batch_access
from apps.common.exceptions import ConflictError


@pytest.mark.django_db
def test_stale_student_profile_is_inert(student_profile):
    user = student_profile.user
    user.role = UserRole.MANAGER
    user.save(update_fields=["role"])

    assert batch_access.student_profile(user) is None
    body = CurrentUserSerializer(user).data
    assert body["profile_type"] is None
    assert body["profile_id"] is None
    assert not teaching_staff_of(user.branch_id).filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_stale_trainer_profile_is_inert(trainer_profile):
    user = trainer_profile.user
    user.role = UserRole.COUNSELLOR
    user.save(update_fields=["role"])

    assert batch_access.trainer_profile(user) is None
    body = CurrentUserSerializer(user).data
    assert body["profile_type"] is None
    assert body["profile_id"] is None
    assert not teaching_staff_of(user.branch_id).filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_a_teaching_manager_keeps_the_trainer_profile(trainer_profile):
    user = trainer_profile.user
    user.role = UserRole.MANAGER
    user.save(update_fields=["role"])

    assert batch_access.trainer_profile(user) == trainer_profile
    body = CurrentUserSerializer(user).data
    assert body["profile_type"] == "trainer"
    assert body["profile_id"] == str(trainer_profile.pk)
    assert teaching_staff_of(user.branch_id).filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_a_teaching_manager_with_open_batches_cannot_drop_the_manager_role(
    admin_user, trainer_profile, batch
):
    manager = trainer_profile.user
    manager.role = UserRole.MANAGER
    manager.save(update_fields=["role"])

    with pytest.raises(ConflictError, match=r"Reassign.*batches"):
        transition_user_role(
            user=manager,
            actor=admin_user,
            role=UserRole.COUNSELLOR,
            reason="Move to admissions.",
        )

    manager.refresh_from_db()
    assert manager.role == UserRole.MANAGER


@pytest.mark.django_db
def test_a_leftover_trainer_profile_cannot_be_given_classes(admin_user, trainer_profile, batch):
    """A manager who moved to admissions keeps the profile for history only."""
    from apps.batches.services import assign_trainer
    from apps.common.exceptions import ApplicationError

    user = trainer_profile.user
    user.role = UserRole.COUNSELLOR
    user.save(update_fields=["role"])

    with pytest.raises(ApplicationError, match="no longer has a teaching role"):
        assign_trainer(batch=batch, trainer=trainer_profile, actor=admin_user)


@pytest.mark.django_db
def test_a_slot_substitute_must_be_at_the_same_centre(admin_user, batch, other_branch):
    """A weekday slot's own trainer passes the same gate as the batch's."""
    from datetime import time

    from apps.batches.services import create_schedule
    from apps.common.exceptions import ApplicationError
    from apps.trainers.services import create_trainer

    elsewhere = create_trainer(
        actor=admin_user,
        email="pune-trainer@example.com",
        first_name="Pune",
        branch=other_branch,
    )
    with pytest.raises(ApplicationError, match="different centre"):
        create_schedule(
            batch=batch,
            actor=admin_user,
            weekday=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            trainer=elsewhere,
        )


@pytest.mark.django_db
def test_a_manager_cannot_edit_a_peer_managers_teaching_profile(
    api_client_no_csrf, manager_user, trainer_profile
):
    """`trainer.update_any` is the capability; the ladder is the reach."""
    peer = trainer_profile.user
    peer.role = UserRole.MANAGER
    peer.save(update_fields=["role"])

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/trainers/{trainer_profile.pk}/",
        {"is_accepting_assignments": False},
        format="json",
    )
    assert response.status_code == 403, response.json()
    trainer_profile.refresh_from_db()
    assert trainer_profile.is_accepting_assignments is True


@pytest.mark.django_db
def test_a_manager_can_still_pause_a_trainers_assignments(
    api_client_no_csrf, manager_user, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.patch(
        f"/api/v1/trainers/{trainer_profile.pk}/",
        {"is_accepting_assignments": False},
        format="json",
    )
    assert response.status_code == 200, response.json()
    trainer_profile.refresh_from_db()
    assert trainer_profile.is_accepting_assignments is False


@pytest.mark.django_db
def test_the_trainer_directory_lists_only_people_who_teach(manager_user, trainer_profile):
    from apps.trainers.access import reachable_trainers, visible_trainers

    assert visible_trainers(manager_user).filter(pk=trainer_profile.pk).exists()
    user = trainer_profile.user
    user.role = UserRole.COUNSELLOR
    user.save(update_fields=["role"])

    assert not visible_trainers(manager_user).filter(pk=trainer_profile.pk).exists()
    # Still reachable by its own address, for the history it carries.
    assert reachable_trainers(manager_user).filter(pk=trainer_profile.pk).exists()
