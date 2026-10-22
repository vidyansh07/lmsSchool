"""Recording a placement, and changing one.

Every write goes through here rather than through a serializer's `save`, for
the reasons the rest of this codebase does it: the branch is derived rather
than accepted from the caller, the status rules are in one place, and each
change is audited with what changed.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditAction, record
from apps.common.exceptions import ApplicationError, AuthorityError

from . import access
from .models import Placement, PlacementStatus, company_key

#: The fields a caller may change on an existing offer. `student` is not one
#: of them: an offer recorded against the wrong person is withdrawn and
#: recorded again, rather than quietly moved, so the first student's record
#: keeps the history of what was done about them.
EDITABLE_FIELDS = frozenset(
    {
        "company",
        "role_title",
        "location",
        "status",
        "annual_package",
        "offered_on",
        "joined_on",
        "notes",
        "enrollment",
    }
)


def _check_status_dates(status: str, joined_on: Any) -> None:
    """`joined_on` and `status` must agree.

    Not a database constraint: both columns are set by people through two
    different writes, and a half-finished edit (status set to joined, date
    about to be typed) must fail with a message rather than an IntegrityError
    the API would show as a 500.
    """
    if status == PlacementStatus.JOINED and not joined_on:
        raise ApplicationError({"joined_on": ["Say when they joined."]})
    if joined_on and status in (PlacementStatus.DECLINED, PlacementStatus.WITHDRAWN):
        raise ApplicationError(
            {"joined_on": ["An offer that was declined or withdrawn has no joining date."]}
        )


@transaction.atomic
def record_placement(
    *,
    actor,
    student,
    company: str,
    role_title: str,
    offered_on,
    status: str = PlacementStatus.OFFERED,
    annual_package: Any = None,
    location: str = "",
    joined_on=None,
    notes: str = "",
    enrollment=None,
) -> Placement:
    """Record one offer made to one student.

    The centre comes from the student, never from the request: a caller who
    could name the branch could file an offer into a centre they cannot read,
    and it would then be invisible to the people who need it.
    """
    if not access.can_manage_placements(actor):
        raise AuthorityError("You do not have authority to record a placement.")

    name = (company or "").strip()
    role = (role_title or "").strip()
    if not name:
        raise ApplicationError({"company": ["Name the company."]})
    if not role:
        raise ApplicationError({"role_title": ["Name the role."]})
    if enrollment is not None and enrollment.student_id != student.pk:
        raise ApplicationError({"enrollment": ["That enrolment belongs to another student."]})
    _check_status_dates(status, joined_on)

    placement = Placement.objects.create(
        student=student,
        enrollment=enrollment,
        branch=student.branch,
        company=name,
        company_key=company_key(name),
        role_title=role,
        location=(location or "").strip(),
        status=status,
        annual_package=annual_package,
        offered_on=offered_on,
        joined_on=joined_on,
        notes=notes or "",
        created_by=actor,
    )
    record(
        action=AuditAction.PLACEMENT_RECORDED,
        actor=actor,
        resource_type="placement",
        resource_id=placement.pk,
        context={
            "student": str(student.pk),
            "company": placement.company,
            "status": placement.status,
        },
        durable=True,
    )
    return placement


@transaction.atomic
def update_placement(*, actor, placement: Placement, fields: dict[str, Any]) -> Placement:
    """Change an offer. Returns it as it now is."""
    if not access.can_manage_placements(actor):
        raise AuthorityError("You do not have authority to change a placement.")

    unknown = sorted(set(fields) - EDITABLE_FIELDS)
    if unknown:
        raise ApplicationError({name: ["This field cannot be changed here."] for name in unknown})

    locked = Placement.objects.select_for_update().get(pk=placement.pk)
    merged_status = fields.get("status", locked.status)
    merged_joined = fields["joined_on"] if "joined_on" in fields else locked.joined_on
    _check_status_dates(merged_status, merged_joined)

    enrollment = fields.get("enrollment")
    if enrollment is not None and enrollment.student_id != locked.student_id:
        raise ApplicationError({"enrollment": ["That enrolment belongs to another student."]})

    changed: list[str] = []
    for name, value in fields.items():
        if name == "company":
            value = (value or "").strip()
            if not value:
                raise ApplicationError({"company": ["Name the company."]})
            if locked.company_key != company_key(value):
                locked.company_key = company_key(value)
                changed.append("company_key")
        if name == "role_title":
            value = (value or "").strip()
            if not value:
                raise ApplicationError({"role_title": ["Name the role."]})
        if name == "enrollment":
            if locked.enrollment_id != getattr(value, "pk", None):
                locked.enrollment = value
                changed.append("enrollment")
            continue
        if getattr(locked, name) != value:
            setattr(locked, name, value)
            changed.append(name)

    if not changed:
        return locked

    locked.updated_by = actor
    locked.save()
    record(
        action=AuditAction.PLACEMENT_UPDATED,
        actor=actor,
        resource_type="placement",
        resource_id=locked.pk,
        context={"changed": sorted(changed), "status": locked.status},
        durable=True,
    )
    return locked


def summary(user) -> dict[str, Any]:
    """The numbers the placement workspace opens with, over what the caller
    may see — never the institute's when the caller is bounded to a centre.

    `placed` counts *students*, not offers: somebody who accepted one offer
    and joined another is one placed person, and counting rows would report
    two. Every other figure counts offers, which is what they are.
    """
    from django.db.models import Count, Q

    from .models import CLOSED_STATUSES, PLACED_STATUSES

    rows = access.visible_placements(user)
    totals = rows.aggregate(
        offers=Count("id"),
        open_offers=Count("id", filter=Q(status=PlacementStatus.OFFERED)),
        closed=Count("id", filter=Q(status__in=CLOSED_STATUSES)),
        placed_students=Count("student", filter=Q(status__in=PLACED_STATUSES), distinct=True),
    )
    this_month = rows.filter(
        offered_on__year=timezone.localdate().year, offered_on__month=timezone.localdate().month
    ).count()
    return {
        "offers": totals["offers"] or 0,
        "open_offers": totals["open_offers"] or 0,
        "closed_offers": totals["closed"] or 0,
        "placed_students": totals["placed_students"] or 0,
        "offers_this_month": this_month,
    }
