"""Writing academic configuration.

One entry point, because a rule change is a governance event: it moves pass
marks and attendance thresholds for people who have already been assessed
against the old ones. Every write is audited with the exact before and after.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError

from .models import POLICY_FIELDS, AcademicPolicy, PolicyScope
from .policies import forget_resolved_policies


def get_or_create_policy(*, course=None) -> AcademicPolicy:
    """The stored row for this scope, created empty if it does not exist.

    An empty row means "inherit everything", which is the same behaviour as no
    row at all — so creating one on demand changes nothing about the rules in
    force.
    """
    if course is None:
        policy, _ = AcademicPolicy.objects.get_or_create(
            scope=PolicyScope.GLOBAL, defaults={"course": None}
        )
        return policy
    policy, _ = AcademicPolicy.objects.get_or_create(scope=PolicyScope.COURSE, course=course)
    return policy


@transaction.atomic
def update_policy(*, policy: AcademicPolicy, actor: User, **fields: Any) -> AcademicPolicy:
    """Change the rules. Records what they were, and what they became."""
    unknown = sorted(set(fields) - set(POLICY_FIELDS))
    if unknown:
        raise ApplicationError({field: ["This is not a configurable rule."] for field in unknown})

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, value in fields.items():
        current = getattr(policy, field)
        if current != value:
            before[field] = None if current is None else str(current)
            after[field] = None if value is None else str(value)
            setattr(policy, field, value)

    if not after:
        return policy

    policy.updated_by = actor if getattr(actor, "pk", None) else None
    try:
        policy.full_clean(exclude=["course"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    policy.save()

    # The memo is per request; drop it so the response reflects the new rules
    # rather than the ones read a few milliseconds earlier.
    forget_resolved_policies()

    record(
        action=AuditAction.ACADEMIC_POLICY_UPDATED,
        actor=actor,
        resource_type="academic_policy",
        resource_id=policy.pk,
        context={
            "scope": policy.scope,
            "course_id": str(policy.course_id) if policy.course_id else None,
            "from": before,
            "to": after,
        },
        durable=False,
    )
    return policy


@transaction.atomic
def clear_course_policy(*, policy: AcademicPolicy, actor: User) -> None:
    """Remove a course override so the course inherits again."""
    if policy.scope != PolicyScope.COURSE:
        raise ApplicationError(
            {"policy": ["The institution-wide rules cannot be deleted, only changed."]}
        )
    course_id, pk = policy.course_id, policy.pk
    policy.delete()
    forget_resolved_policies()
    record(
        action=AuditAction.ACADEMIC_POLICY_UPDATED,
        actor=actor,
        resource_type="academic_policy",
        resource_id=pk,
        context={"scope": PolicyScope.COURSE, "course_id": str(course_id), "cleared": True},
        durable=False,
    )


# ---------------------------------------------------------------------------
# The academic calendar — §8.1
# ---------------------------------------------------------------------------


@transaction.atomic
def add_calendar_event(*, actor: User, **fields: Any):
    """Add a term, holiday or examination week.

    A holiday has behaviour attached — class generation skips it — so this is
    audited like any other rule change rather than treated as a note.
    """
    from .models import AcademicEvent

    event = AcademicEvent(created_by=actor if getattr(actor, "pk", None) else None, **fields)
    try:
        event.full_clean(exclude=["created_by"])
    except DjangoValidationError as exc:
        raise ApplicationError(exc.message_dict) from exc
    if event.end_date < event.start_date:
        raise ApplicationError({"end_date": ["The end date cannot precede the start date."]})
    event.save()

    record(
        action=AuditAction.ACADEMIC_POLICY_UPDATED,
        actor=actor,
        resource_type="academic_event",
        resource_id=event.pk,
        context={
            "name": event.name,
            "kind": event.kind,
            "from": event.start_date.isoformat(),
            "to": event.end_date.isoformat(),
        },
        durable=False,
    )
    return event


@transaction.atomic
def remove_calendar_event(*, event, actor: User) -> None:
    name, pk = event.name, event.pk
    event.delete()
    record(
        action=AuditAction.ACADEMIC_POLICY_UPDATED,
        actor=actor,
        resource_type="academic_event",
        resource_id=pk,
        context={"name": name, "removed": True},
        durable=False,
    )
