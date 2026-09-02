"""Trainer domain services."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_trainer_id

from .models import TrainerProfile


@transaction.atomic
def create_trainer(
    *,
    email: str,
    first_name: str,
    last_name: str = "",
    phone: str = "",
    actor: User,
    profile_fields: dict[str, Any] | None = None,
    password: str | None = None,
    send_invitation: bool = True,
) -> TrainerProfile:
    """Create the user account and the trainer profile as one unit."""
    user = create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=UserRole.TRAINER,
        actor=actor,
        send_invitation=send_invitation,
    )

    profile = TrainerProfile(user=user, trainer_id=next_trainer_id(), **(profile_fields or {}))
    profile.full_clean(exclude=["user", "trainer_id"])
    profile.save()

    record(
        action=AuditAction.TRAINER_CREATED,
        actor=actor,
        resource_type="trainer",
        resource_id=profile.pk,
        context={"trainer_id": profile.trainer_id, "user_id": str(user.pk)},
    )
    return profile


@transaction.atomic
def update_trainer_profile(
    *, profile: TrainerProfile, actor: User, allowed_fields: tuple[str, ...], **fields: Any
) -> TrainerProfile:
    """Apply an update restricted to an explicitly allowed field set.

    ``allowed_fields`` is derived from the caller's authorization level, never
    from the request body, so a trainer cannot widen it by sending extra keys.
    """
    rejected = sorted(set(fields) - set(allowed_fields))
    if rejected:
        raise ApplicationError(
            {field: ["This field cannot be changed here."] for field in rejected}
        )

    changed: list[str] = []
    for field, value in fields.items():
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)

    if not changed:
        return profile

    profile.full_clean(exclude=["user", "trainer_id"])
    profile.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.TRAINER_UPDATED,
        actor=actor,
        resource_type="trainer",
        resource_id=profile.pk,
        context={"trainer_id": profile.trainer_id, "changed_fields": sorted(changed)},
    )
    return profile


def get_or_create_profile_for(user: User, *, actor: User | None = None) -> TrainerProfile:
    """Fetch the profile for a trainer account, creating it if it is missing."""
    if user.role != UserRole.TRAINER:
        raise ConflictError("This account does not have the trainer role.")
    profile = TrainerProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile
    with transaction.atomic():
        profile = TrainerProfile.objects.create(user=user, trainer_id=next_trainer_id())
        record(
            action=AuditAction.TRAINER_CREATED,
            actor=actor or user,
            resource_type="trainer",
            resource_id=profile.pk,
            context={"trainer_id": profile.trainer_id, "backfilled": True},
        )
    return profile
