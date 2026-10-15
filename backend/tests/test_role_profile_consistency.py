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
