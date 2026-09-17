"""Student domain services."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.accounts.roles import Capability, has_capability
from apps.accounts.services import create_user, resolve_branch_for_new_record
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.common.identifiers import next_student_id

from . import access
from .models import MIN_FEE_AMOUNT, StudentProfile

#: How many candidate matches `find_duplicate_candidates` returns. A
#: mid-registration "does anyone match?" warning needs a short list to show,
#: not every row an ambiguous shared phone number might turn up.
DUPLICATE_MATCH_LIMIT = 5


def find_duplicate_candidates(
    *, user: User, email: str = "", phone: str = ""
) -> QuerySet[StudentProfile]:
    """Existing students who exact-match ``email`` or ``phone``, narrowed to
    what ``user`` may see.

    ``USER_JOURNEYS.md`` §4.2: "as soon as email or phone is complete, the
    wizard asks the server does anyone match?" — an *exact* match only, never
    fuzzy or similarity matching; the journey asks whether this exact contact
    information is already on file, not who looks similar.

    Scoped through :func:`apps.students.access.visible_students` — the same
    queryset the admissions list and Student 360 already resolve through —
    rather than a fresh unscoped query, so a match outside the caller's own
    reach (another branch, or a record this role cannot see at all) is not
    returned at all, never a redacted stub. A false negative here (a real
    duplicate the caller cannot see) is the correct, safe failure mode; a
    caller who is not otherwise allowed to see that student learning it
    exists is not.

    Email and phone live on the linked ``User`` (``apps.accounts.models``),
    not on ``StudentProfile`` itself.
    """
    email = (email or "").strip().lower()
    phone = (phone or "").strip()
    if not email and not phone:
        return StudentProfile.objects.none()

    condition = Q()
    if email:
        condition |= Q(user__email__iexact=email)
    if phone:
        condition |= Q(user__phone=phone)

    return access.visible_students(user).filter(condition).order_by("-created_at")


@transaction.atomic
def create_student(
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
    fee_amount: Decimal | None = None,
    override_reason: str = "",
) -> StudentProfile:
    """Create the user account and the student profile as one unit.

    Both happen in a single transaction: an account without a profile would be a
    student who cannot be found by student ID, and a profile without an account
    would be unreachable. Neither half is allowed to exist alone.

    ``fee_amount`` is the fee agreed at registration. Quoting one is a separate
    permission from creating the record — ``student.set_fee_status`` rather
    than ``student.create`` — and it is checked here, not only in the view, so
    a caller that reaches this function some other way is held to the same
    rule.

    The centre is resolved once and written to both halves, so an account and
    its profile can never disagree about where somebody is.

    ``override_reason`` is Phase 17's duplicate-check override
    (``USER_JOURNEYS.md`` §4.2): the same disclosure-safe
    :func:`find_duplicate_candidates` check the registration wizard's own
    warning step used is re-run here, from the server's own record of
    ``email``/``phone`` rather than trusting a client-supplied "a duplicate
    was shown" flag — a client that skips straight to this call, or edits the
    contact fields after the warning was shown, is held to the identical
    rule. When that recheck finds a candidate, a reason is required to
    proceed and is recorded against the resulting profile; when it finds
    none, the field is not needed at all and nothing is audited by it. There
    is no new column on ``StudentProfile`` for this — it is audit-only.
    """
    if fee_amount is not None:
        _check_fee_amount(fee_amount, actor=actor)

    duplicates = list(find_duplicate_candidates(user=actor, email=email, phone=phone))
    if duplicates and not override_reason.strip():
        raise ApplicationError(
            {
                "override_reason": [
                    "A possible existing student was found. Say why this is a "
                    "different person to continue."
                ]
            }
        )

    branch = resolve_branch_for_new_record(actor=actor, branch=branch)
    user = create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=UserRole.STUDENT,
        actor=actor,
        branch=branch,
        send_invitation=send_invitation,
    )

    profile = StudentProfile(
        user=user,
        student_id=next_student_id(),
        branch=user.branch,
        **(profile_fields or {}),
    )
    if fee_amount is not None:
        profile.fee_amount = fee_amount
        profile.fee_amount_updated_at = timezone.now()
        profile.fee_amount_updated_by = actor
    profile.full_clean(exclude=["user", "student_id", "branch"])
    profile.save()

    if duplicates:
        record(
            action=AuditAction.STUDENT_DUPLICATE_OVERRIDDEN,
            actor=actor,
            resource_type="student",
            resource_id=profile.pk,
            context={
                "student_id": profile.student_id,
                "reason": override_reason.strip(),
                "matched_student_ids": [str(candidate.pk) for candidate in duplicates],
            },
        )

    record(
        action=AuditAction.STUDENT_CREATED,
        actor=actor,
        resource_type="student",
        resource_id=profile.pk,
        context={
            "student_id": profile.student_id,
            "user_id": str(user.pk),
            "fee_amount": str(fee_amount) if fee_amount is not None else None,
            "referred_by": str(profile.referred_by_id) if profile.referred_by_id else None,
        },
    )
    return profile


def _check_fee_amount(fee_amount: Decimal, *, actor: User) -> None:
    """The two rules a quoted fee is held to, wherever it is quoted from."""
    if not has_capability(actor, Capability.STUDENT_SET_FEE_STATUS):
        raise AuthorityError("You do not have permission to set a student's fee.")
    if fee_amount < MIN_FEE_AMOUNT:
        raise ApplicationError(
            {"fee_amount": [f"The fee must be at least \u20b9{MIN_FEE_AMOUNT:,.0f}."]}
        )


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
def set_fee_amount(
    *, profile: StudentProfile, fee_amount: Decimal | None, actor: User, note: str = ""
) -> StudentProfile:
    """Set, change or clear the fee agreed with a student.

    ``None`` clears it — "not decided" — and is the only way to get back to
    that state; zero is refused, because a fee of nothing is a claim and a
    missing fee is not. Every change is audited with both values, since this
    is a number somebody will one day ask about.
    """
    if fee_amount is not None:
        _check_fee_amount(fee_amount, actor=actor)
    elif not has_capability(actor, Capability.STUDENT_SET_FEE_STATUS):
        raise AuthorityError("You do not have permission to set a student's fee.")

    previous = profile.fee_amount
    if previous == fee_amount:
        return profile

    profile.fee_amount = fee_amount
    profile.fee_amount_updated_at = timezone.now()
    profile.fee_amount_updated_by = actor
    profile.save(
        update_fields=["fee_amount", "fee_amount_updated_at", "fee_amount_updated_by", "updated_at"]
    )

    record(
        action=AuditAction.STUDENT_FEE_AMOUNT_CHANGED,
        actor=actor,
        resource_type="student",
        resource_id=profile.pk,
        context={
            "student_id": profile.student_id,
            "from": str(previous) if previous is not None else None,
            "to": str(fee_amount) if fee_amount is not None else None,
            "note": note,
        },
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
    profile is empty, not fabricated: only the identifier is allocated, and the
    centre is taken from the account rather than guessed.
    """
    if user.role != UserRole.STUDENT:
        raise ConflictError("This account does not have the student role.")
    profile = StudentProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile
    with transaction.atomic():
        profile = StudentProfile.objects.create(
            user=user, student_id=next_student_id(), branch=user.branch
        )
        record(
            action=AuditAction.STUDENT_CREATED,
            actor=actor or user,
            resource_type="student",
            resource_id=profile.pk,
            context={"student_id": profile.student_id, "backfilled": True},
        )
    return profile
