"""One staff member's record of work, over a span of dates.

What a counsellor did last quarter: who they admitted, what they collected,
the leads they worked, the follow-ups they ran. The same question of a
trainer is a different list — classes, registers, class reports, interviews —
and of a placement officer different again, which is why none of this is
hard-coded per role. It counts what the person actually did and leaves out
the rows that are zero, so the shape of the record tells you what the job
was without anybody declaring it.

Two sources, deliberately:

* **Counters** come from the domain tables through the caller's own visible
  querysets. `FeePayment.recorded_by`, `Admission.created_by`,
  `EnquiryNote.author` and the rest are the system's own record of who did
  the work, and counting them is the only way to say "₹8,40,000 across 31
  receipts" rather than "31 things happened".
* **The timeline** comes from `AuditLog` filtered by actor. It already has
  `audit_actor_time_idx` on `(actor, -created_at)` — this exact query — and
  it is the only table that holds every kind of act in one ordering, so a
  merged "what did they do" list needs no union of nine models.

Authority is `staff.view_record`, or being the person asked about. There is
no third path: a manager does not see this (owner's decision, 26 October
2026), and the capability sits in the administrator-only set.

This is also the engine behind the reports section's "who did what" mode, so
anything added here appears there without a second implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounts.roles import Capability, has_capability
from apps.common.exceptions import ApplicationError, AuthorityError

#: The longest span one request will build. A record is read a quarter or a
#: month at a time; a request for five years is a report, and the export
#: machinery is what answers that without holding it all in memory.
MAX_DAYS = 400

#: How much of the timeline one response carries. The counters describe the
#: whole span; this is the most recent slice of the detail behind them.
TIMELINE_LIMIT = 200


@dataclass
class Counter:
    """One line of "what they did": a label, a count, and the money if the
    thing being counted carries any."""

    key: str
    label: str
    count: int
    #: Only for the lines where a total means something — collections, not
    #: class reports. `None` elsewhere, so a screen can tell the difference
    #: between "no money" and "money is not the point of this row".
    amount: Decimal | None = None


@dataclass
class StaffRecord:
    person: dict[str, Any]
    start: date
    end: date
    counters: list[Counter] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    #: True when the timeline was cut at `TIMELINE_LIMIT`, so a screen can say
    #: "the most recent 200" rather than implying it is the whole span.
    timeline_truncated: bool = False


def can_view_record(actor, person) -> bool:
    """Administrators and superadmins for anybody; everybody for themselves.

    Ownership is not a capability. A counsellor who cannot see their own
    admissions count will ask somebody to read it to them, which is a worse
    outcome than the one the restriction is protecting against.
    """
    if getattr(actor, "pk", None) == getattr(person, "pk", None):
        return True
    return has_capability(actor, Capability.STAFF_VIEW_RECORD)


def _window(start: date | None, end: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    end = end or today
    start = start or (end - timedelta(days=30))
    if start > end:
        raise ApplicationError({"start": ["The first date is after the last one."]})
    if (end - start).days > MAX_DAYS:
        raise ApplicationError(
            {"start": [f"Ask for at most {MAX_DAYS} days at a time; export a longer span."]}
        )
    return start, end


def _moment(day: date, *, end: bool) -> datetime:
    """A date turned into the instant that bounds it, in the current zone —
    so "to 30 June" includes everything that happened on 30 June."""
    return timezone.make_aware(
        datetime.combine(day, time.max if end else time.min),
        timezone.get_current_timezone(),
    )


def build(*, actor, person, start: date | None = None, end: date | None = None) -> StaffRecord:
    """What `person` did between two dates, as `actor` is allowed to see it."""
    if not can_view_record(actor, person):
        raise AuthorityError("You do not have authority to read this person's record.")

    first, last = _window(start, end)
    since, until = _moment(first, end=False), _moment(last, end=True)

    record = StaffRecord(
        person={
            "id": str(person.pk),
            "name": person.full_name or person.email,
            "email": person.email,
            "role": person.role,
            "is_active": person.is_active,
        },
        start=first,
        end=last,
    )
    record.counters = _counters(actor=actor, person=person, since=since, until=until)
    record.timeline, record.timeline_truncated = _timeline(person=person, since=since, until=until)
    return record


def _counters(*, actor, person, since, until) -> list[Counter]:
    """Count what the person did, through the caller's own visible sets.

    Every queryset is narrowed by what `actor` may see before it is counted.
    An administrator's floor is every centre, so in practice this changes
    nothing for them — but a role an administrator composes can be narrower,
    and a count is as much a disclosure as a row: "41 admissions" tells you
    they exist even when you may not open one.

    A line that counts zero is dropped. A counsellor's record listing "0
    class reports" and a trainer's listing "0 receipts" is a form, not a
    record; what each person's record *contains* should say what their job
    is.
    """
    from apps.admissions.models import Admission
    from apps.batches import access as batch_access
    from apps.enquiries.models import EnquiryNote
    from apps.enrollments.models import Enrollment
    from apps.fees.models import LIVE_PAYMENT, FeePayment
    from apps.students import access as students_access
    from apps.work.models import Activity, ActivityStatus

    visible_students = students_access.visible_students(actor)
    visible_enrolments = batch_access.visible_enrollments(actor)

    counters: list[Counter] = []

    def add(key: str, label: str, count: int, amount: Decimal | None = None) -> None:
        if count:
            counters.append(Counter(key=key, label=label, count=count, amount=amount))

    admissions = Admission.objects.filter(
        created_by=person, student__in=visible_students, created_at__range=(since, until)
    )
    add("admissions", "Admissions taken", admissions.count())

    enrolments = Enrollment.objects.filter(
        created_by=person, pk__in=visible_enrolments, created_at__range=(since, until)
    )
    add("enrolments", "Students enrolled", enrolments.count())

    # Money is counted on live payments only, through the ledger's own
    # `LIVE_PAYMENT` rather than a hand-written pair of null checks: a voided
    # receipt is one that should never have existed, and a refunded one has
    # gone back. Crediting somebody for either would make voiding a receipt a
    # way to inflate a figure.
    payments = FeePayment.objects.filter(
        LIVE_PAYMENT,
        recorded_by=person,
        plan__enrollment__in=visible_enrolments,
        paid_on__range=(since.date(), until.date()),
    ).aggregate(total=Sum("amount"), rows=Count("id"))
    add("collected", "Collected", payments["rows"] or 0, payments["total"] or Decimal("0"))

    notes = EnquiryNote.objects.filter(author=person, created_at__range=(since, until))
    add("enquiry_notes", "Follow-ups written on leads", notes.count())

    activities = Activity.objects.filter(
        performed_by=person,
        completed_at__range=(since, until),
        status__in=(
            ActivityStatus.COMPLETED,
            ActivityStatus.UNDER_REVIEW,
            ActivityStatus.APPROVED,
        ),
    )
    add("activities", "Activities completed", activities.count())

    interviews = activities.filter(activity_type__category="interview")
    add("interviews", "Interviews run", interviews.count())

    # No guard for "this person is not a trainer": the join simply matches
    # nothing, and the line is dropped like any other zero.
    from apps.dsr.models import DSR

    reports = DSR.objects.filter(trainer__user=person, created_at__range=(since, until))
    add("class_reports", "Class reports written", reports.count())

    return counters


def _timeline(*, person, since, until) -> tuple[list[dict[str, Any]], bool]:
    """Everything they did, newest first, straight off the audit trail.

    One extra row is fetched so the caller can be told the list was cut
    rather than left to infer it from the length matching the limit exactly.
    """
    from apps.audit.models import AuditLog

    rows = list(
        AuditLog.objects.filter(actor=person, created_at__range=(since, until))
        .order_by("-created_at")
        .values("id", "action", "resource_type", "resource_id", "created_at", "result")[
            : TIMELINE_LIMIT + 1
        ]
    )
    truncated = len(rows) > TIMELINE_LIMIT
    return (
        [
            {
                "id": str(row["id"]),
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "result": row["result"],
                "at": row["created_at"],
            }
            for row in rows[:TIMELINE_LIMIT]
        ],
        truncated,
    )
