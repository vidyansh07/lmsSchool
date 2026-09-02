"""Student domain services."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.identifiers import next_student_id

from .models import StudentProfile


@transaction.atomic
def create_student(
    *,
    email: str,
    first_name: str,
    last_name: str = "",
    phone: str = "",
    actor: User,
    profile_fields: dict[str, Any] | None = None,
    password: str | None = None,
    send_invitation: bool = True,
) -> StudentProfile:
    """Create the user account and the student profile as one unit.

    Both happen in a single transaction: an account without a profile would be a
    student who cannot be found by student ID, and a profile without an account
    would be unreachable. Neither half is allowed to exist alone.
    """
    user = create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=UserRole.STUDENT,
        actor=actor,
        send_invitation=send_invitation,
    )

    profile = StudentProfile(user=user, student_id=next_student_id(), **(profile_fields or {}))
    profile.full_clean(exclude=["user", "student_id"])
    profile.save()

    record(
        action=AuditAction.STUDENT_CREATED,
        actor=actor,
        resource_type="student",
        resource_id=profile.pk,
        context={"student_id": profile.student_id, "user_id": str(user.pk)},
    )
    return profile


@transaction.atomic
def update_student_profile(
    *, profile: StudentProfile, actor: User, allowed_fields: tuple[str, ...], **fields: Any
) -> StudentProfile:
    """Apply an update restricted to an explicitly allowed field set.

    ``allowed_fields`` comes from the caller's authorization level, not from the
    request. A field outside it is refused rather than ignored, so an attempt to
    set ``fee_status`` or ``student_id`` from a self-service endpoint fails
    loudly instead of appearing to succeed.
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

    profile.full_clean(exclude=["user", "student_id"])
    profile.save(update_fields=[*changed, "updated_at"])

    record(
        action=AuditAction.STUDENT_UPDATED,
        actor=actor,
        resource_type="student",
        resource_id=profile.pk,
        context={"student_id": profile.student_id, "changed_fields": sorted(changed)},
    )
    return profile


@transaction.atomic
def set_fee_status(*, profile: StudentProfile, fee_status: str, actor: User, note: str = ""):
    """Change a student's fee status.

    Administrator-only and always audited: this is the one student field that
    carries a financial claim, so who changed it and when has to be answerable
    long after the fact.
    """
    if fee_status not in dict(profile._meta.get_field("fee_status").choices):
        raise ApplicationError({"fee_status": ["Unknown fee status."]})

    previous = profile.fee_status
    if previous == fee_status:
        return profile

    profile.fee_status = fee_status
    profile.fee_status_updated_at = timezone.now()
    profile.fee_status_updated_by = actor
    profile.save(
        update_fields=["fee_status", "fee_status_updated_at", "fee_status_updated_by", "updated_at"]
    )

    record(
        action=AuditAction.STUDENT_FEE_STATUS_CHANGED,
        actor=actor,
        resource_type="student",
        resource_id=profile.pk,
        context={
            "student_id": profile.student_id,
            "from": previous,
            "to": fee_status,
            "note": note,
        },
    )
    return profile


def get_or_create_profile_for(user: User, *, actor: User | None = None) -> StudentProfile:
    """Fetch the profile for a student account, creating it if it is missing.

    Covers accounts whose role was changed to student after creation. The
    profile is empty, not fabricated: only the identifier is allocated.
    """
    if user.role != UserRole.STUDENT:
        raise ConflictError("This account does not have the student role.")
    profile = StudentProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile
    with transaction.atomic():
        profile = StudentProfile.objects.create(user=user, student_id=next_student_id())
        record(
            action=AuditAction.STUDENT_CREATED,
            actor=actor or user,
            resource_type="student",
            resource_id=profile.pk,
            context={"student_id": profile.student_id, "backfilled": True},
        )
    return profile
