"""Trainer domain services."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user, resolve_branch_for_new_record
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
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
    branch=None,
    profile_fields: dict[str, Any] | None = None,
    password: str | None = None,
    send_invitation: bool = True,
) -> TrainerProfile:
    """Create the user account and the trainer profile as one unit.

    The centre is resolved once and written to both halves — see
    ``apps.students.services.create_student`` for why.
    """
    branch = resolve_branch_for_new_record(actor=actor, branch=branch)
    user = create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=UserRole.TRAINER,
        actor=actor,
        branch=branch,
        send_invitation=send_invitation,
    )

    profile = TrainerProfile(
        user=user,
        trainer_id=next_trainer_id(),
        branch=user.branch,
        **(profile_fields or {}),
    )
    profile.full_clean(exclude=["user", "trainer_id", "branch"])
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


#: Roles whose account may carry a trainer profile. A manager teaches some
#: batches (owner's call, 14 September 2026): one login, the profile created
#: the first time they are picked as a batch's trainer.
TEACHING_ROLES = (UserRole.TRAINER, UserRole.MANAGER)


def get_or_create_profile_for(user: User, *, actor: User | None = None) -> TrainerProfile:
    """Fetch the profile for a teaching account, creating it if it is missing."""
    if user.role not in TEACHING_ROLES:
        raise ConflictError("This account does not have a teaching role.")
    profile = TrainerProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile
    with transaction.atomic():
        profile = TrainerProfile.objects.create(
            user=user, trainer_id=next_trainer_id(), branch=user.branch
        )
        record(
            action=AuditAction.TRAINER_CREATED,
            actor=actor or user,
            resource_type="trainer",
            resource_id=profile.pk,
            context={"trainer_id": profile.trainer_id, "backfilled": True},
        )
    return profile


@transaction.atomic
def ensure_teaching_profile(*, user: User, actor: User) -> TrainerProfile:
    """Give a manager a trainer profile so they can be put on a batch.

    Idempotent: a second call returns the existing profile. Refused for any
    role outside ``TEACHING_ROLES`` — a counsellor or a student is not made a
    trainer by being picked in a search box. Audited as a trainer creation,
    because that is what it is; the account keeps its manager role.
    """
    from apps.accounts.roles import Capability, has_capability

    if not has_capability(actor, Capability.TRAINER_CREATE):
        raise AuthorityError("You do not have permission to add trainers.")
    if user.role not in TEACHING_ROLES:
        raise ApplicationError({"user_id": ["Only a trainer or a manager can teach a batch."]})
    if not user.is_active:
        raise ApplicationError({"user_id": ["That account is not active."]})
    existing = TrainerProfile.objects.filter(user=user).first()
    if existing is not None:
        return existing
    profile = TrainerProfile.objects.create(
        user=user, trainer_id=next_trainer_id(), branch=user.branch, is_accepting_assignments=True
    )
    record(
        action=AuditAction.TRAINER_CREATED,
        actor=actor,
        resource_type="trainer",
        resource_id=profile.pk,
        context={"trainer_id": profile.trainer_id, "user_id": str(user.pk), "role": user.role},
    )
    return profile
