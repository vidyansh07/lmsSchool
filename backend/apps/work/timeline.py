"""One timeline, many sources (ERP Phase 10, ADR-09).

Same shape as `apps.dashboards.calendar` — deliberately: a calendar answers
"what happens in this window?" and a timeline answers "what already
happened?", and both are read models composed from sources that already have
their own access control. Adding a new domain to the timeline means writing
one function and appending it to :data:`TIMELINE_SOURCES`; nothing else
changes.

Every source is a function of ``(user, student, since, until, cursor_bound,
limit)`` returning a list of :class:`TimelineEntry`. It resolves its own
access control through that domain's own ``visible_*``/``access`` module —
never a raw unscoped query — the same rule `apps.dashboards.calendar`'s
sources follow. ``student`` is the profile the timeline is *about*; ``user``
is the caller, who may be staff, that student, or someone with a narrower
per-record reach than the top-level "can this caller see this student at
all?" check already passed (a scoped trainer, for one) — so every source
still intersects the caller's own domain-scoped queryset with
``student``, rather than assuming the top-level check already answered the
per-record question.

Registered sources, one per domain named in ADR-09's list:

* ``_enrolment_events`` (apps.enrollments, via apps.batches.access) —
  created / started / ended, and a transfer, which is an
  ``Enrollment.status`` transition to ``TRANSFERRED`` rather than a separate
  model (`apps/enrollments/models.py`).
* ``_attendance_day_events`` (apps.attendance) — one entry per day with a
  recorded session, not one per attendance row.
* ``_dsr_events`` (apps.dsr) — reuses ``apps.dsr.access.visible_dsrs``.
* ``_assessment_result_events`` (apps.assessments) — reuses
  ``apps.assessments.access.visible_results``.
* ``_assignment_submission_events`` (apps.assignments) — reuses
  ``apps.assignments.access.visible_submissions``.
* ``_project_state_events`` (apps.projects) — reuses
  ``apps.projects.access.visible_student_projects``.
* ``_activity_events`` (apps.work, this app) — reuses
  ``apps.work.access.visible_activities`` /
  ``student_visible_activities``. This also covers the "feedback" and
  "review" entries ADR-09 lists separately: both are
  ``ActivityType.category`` values, not separate domains.
* ``_certificate_events`` (apps.certificates) — reuses the existing
  ``visible_certificates`` helper in ``apps/certificates/views.py``.

Deliberately not built: a "communication delivery" source. The
``communication`` app does not exist yet (Phase 19, ADR-12). When it lands,
it registers its own source and appends it to :data:`TIMELINE_SOURCES` the
same additive way Phase 9 added a calendar source (`apps/work/services.py`'s
``_activity_events`` in ``apps.dashboards.calendar``) — no change needed
here.

Pagination is keyset (cursor) rather than page-number, because a timeline is
an append-only-by-date union of several tables and a page-number offset would
shift under a concurrently-created row the same way `apps.common.pagination`
warns page-number listings can. The cursor encodes ``(occurred_at, id)`` of
the last entry returned; a source pushes what filtering it cheaply can into
SQL (the window bound, and the cursor's ``occurred_at`` as an upper bound)
but the exact, tie-safe cut is always re-applied in Python across the merged
result, because two sources can share the same ``occurred_at`` down to the
second (see the pagination tests) and only the composed id ordering, not any
single source's own primary key, can break that tie consistently.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, Q

from apps.common.exceptions import ApplicationError

logger = logging.getLogger("grras.timeline")

#: How far back a caller may ask for at once, absent an explicit window.
DEFAULT_WINDOW_DAYS = 365

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

_UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class TimelineEntry:
    """One thing that happened, from any source.

    ``id`` is the source row's own id, prefixed with the source's name so it
    is unique across the whole composed timeline (an enrolment and an
    activity can otherwise share a UUID space by coincidence of testing, and
    even where they cannot, the prefix is what makes a day-level attendance
    "row" — which has no single underlying primary key — nameable at all).
    It is also the tie-breaker half of the pagination cursor, so it must
    sort consistently: a plain string compares the same way every time,
    which is all that is asked of it.
    """

    id: str
    occurred_at: datetime
    kind: str
    title: str
    summary: str
    href: str
    actor: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "occurred_at": self.occurred_at.isoformat(),
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "href": self.href,
            "actor": self.actor,
        }


@dataclass(frozen=True)
class _Source:
    name: str
    kinds: frozenset[str]
    fn: Any


def _actor(user) -> dict[str, Any] | None:
    """The small `{id, name, role}` shape every entry's actor uses.

    `None` means "nobody in particular" (a system job marking an activity
    overdue, an attendance day with no correction), never a dict with blank
    fields — the frontend contract is "no actor", not "an actor named
    nothing".
    """
    if user is None or getattr(user, "pk", None) is None:
        return None
    return {"id": str(user.pk), "name": user.full_name, "role": user.role}


def _as_datetime(value: datetime | Any) -> datetime:
    """A date or datetime, always returned timezone-aware.

    Several sources only have a date to offer (an access start date, an
    attendance day); midnight UTC on that day is the entry's moment, the same
    "all-day" convention `apps.dashboards.calendar` uses for a deadline.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=_UTC)
        return value
    return datetime.combine(value, time.min, tzinfo=_UTC)


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Cursor encoding
# ---------------------------------------------------------------------------


def encode_cursor(entry: TimelineEntry) -> str:
    raw = f"{entry.occurred_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(raw: str) -> tuple[datetime, str]:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        at_text, separator, entry_id = decoded.partition("|")
        if not separator or not at_text or not entry_id:
            raise ValueError("malformed cursor")
        occurred_at = datetime.fromisoformat(at_text)
        if occurred_at.tzinfo is None:
            raise ValueError("naive cursor timestamp")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ApplicationError({"cursor": ["This cursor is not valid."]}) from None
    return occurred_at, entry_id


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def _enrolment_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """Enrolment created / started / ended, and transfers.

    A transfer is `Enrollment.status == TRANSFERRED` (§ADR-09), not a
    separate model, so it is read off the same row as everything else here.

    One enrolment row can produce up to four entries, so this source cannot
    push a single-field cursor comparison into SQL the way a one-row-one-entry
    source can: it fetches a cursor/window-bounded batch of *rows* (still one
    query), expands each into its entries in Python, then sorts and trims to
    `limit` here so the composition step still sees at most `limit` candidates
    from this source — the documented Python-merge exception the phase brief
    allows for a source whose model doesn't support pushing cursor filtering
    into SQL cheaply.
    """
    from apps.batches import access as batch_access
    from apps.enrollments.models import EnrollmentStatus

    qs = (
        batch_access.visible_enrollments(user)
        .filter(student=student)
        .select_related("created_by", "transferred_to", "transferred_to__batch")
    )
    # A generous, cheap upper bound: any of the row's own timestamps that
    # could produce a visible entry must be no later than the cursor.
    bound = Q()
    if cursor_bound is not None:
        bound = (
            Q(enrolled_at__lte=cursor_bound)
            | Q(start_date__lte=cursor_bound.date())
            | Q(status_changed_at__lte=cursor_bound)
            | Q(completed_at__lte=cursor_bound)
            | Q(updated_at__lte=cursor_bound)
        )
    if bound:
        qs = qs.filter(bound)
    # A handful of rows per student in practice; capped generously rather than
    # tightly, since each row can yield several entries.
    rows = list(qs.order_by("-enrolled_at")[: max(limit, 1) * 4])

    entries: list[TimelineEntry] = []
    for enrollment in rows:
        created_at = _as_datetime(enrollment.enrolled_at)
        if since <= created_at <= until:
            entries.append(
                TimelineEntry(
                    id=f"enrolment:{enrollment.pk}:created",
                    occurred_at=created_at,
                    kind="enrollment_created",
                    title=f"Enrolled — {enrollment.course.title}",
                    summary=f"{enrollment.batch.code} ({enrollment.course.title})",
                    href=f"/manage/students/{enrollment.pk}",
                    actor=_actor(enrollment.created_by),
                )
            )

        if enrollment.start_date is not None:
            started_at = _as_datetime(enrollment.start_date)
            if since <= started_at <= until:
                entries.append(
                    TimelineEntry(
                        id=f"enrolment:{enrollment.pk}:started",
                        occurred_at=started_at,
                        kind="enrollment_started",
                        title=f"Access started — {enrollment.course.title}",
                        summary=f"{enrollment.batch.code} ({enrollment.course.title})",
                        href=f"/manage/students/{enrollment.pk}",
                        actor=None,
                    )
                )

        if enrollment.status == EnrollmentStatus.TRANSFERRED and enrollment.transferred_to_id:
            transferred_at = _as_datetime(
                _first_not_none(
                    enrollment.status_changed_at, enrollment.updated_at, enrollment.enrolled_at
                )
            )
            if since <= transferred_at <= until:
                destination = enrollment.transferred_to
                entries.append(
                    TimelineEntry(
                        id=f"enrolment:{enrollment.pk}:transferred",
                        occurred_at=transferred_at,
                        kind="enrollment_transferred",
                        title=f"Transferred — {enrollment.course.title}",
                        summary=f"Moved to {destination.batch.code}",
                        href=f"/manage/students/{destination.pk}",
                        actor=None,
                    )
                )
        elif enrollment.status in (EnrollmentStatus.COMPLETED, EnrollmentStatus.CANCELLED):
            ended_at = _as_datetime(
                _first_not_none(
                    enrollment.completed_at, enrollment.status_changed_at, enrollment.updated_at
                )
            )
            if since <= ended_at <= until:
                entries.append(
                    TimelineEntry(
                        id=f"enrolment:{enrollment.pk}:ended",
                        occurred_at=ended_at,
                        kind="enrollment_ended",
                        title=f"{enrollment.get_status_display()} — {enrollment.course.title}",
                        summary=f"{enrollment.batch.code} ({enrollment.course.title})",
                        href=f"/manage/students/{enrollment.pk}",
                        actor=None,
                    )
                )

    entries.sort(key=lambda e: (e.occurred_at, e.id), reverse=True)
    return entries[:limit]


ENROLMENT_KINDS = frozenset(
    {"enrollment_created", "enrollment_started", "enrollment_ended", "enrollment_transferred"}
)


def _attendance_day_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """One entry per day the student had a recorded session, not one per row.

    The grouping happens in SQL (`.values().annotate()`), so this is a single
    query that returns already-collapsed days, ordered and cursor/window
    bounded the same as any other SQL-pushed source.
    """
    from apps.attendance.models import COUNTS_AS_PRESENT, AttendanceRecord, AttendanceStatus
    from apps.batches import access as batch_access

    enrollment_ids = batch_access.visible_enrollments(user).filter(student=student).values("id")
    qs = AttendanceRecord.objects.filter(
        enrollment_id__in=enrollment_ids,
        session__session_date__gte=since.date(),
        session__session_date__lte=until.date(),
    )
    if cursor_bound is not None:
        qs = qs.filter(session__session_date__lte=cursor_bound.date())

    rows = (
        qs.values("session__session_date")
        .annotate(
            total=Count("id"),
            present=Count("id", filter=Q(status__in=COUNTS_AS_PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        )
        .order_by("-session__session_date")[:limit]
    )

    entries: list[TimelineEntry] = []
    for row in rows:
        day = row["session__session_date"]
        total = row["total"]
        present = row["present"]
        absent = row["absent"]
        summary = f"Present {present}/{total}" if total else "No sessions recorded"
        if absent and total:
            summary = f"{summary} ({absent} absent)"
        entries.append(
            TimelineEntry(
                id=f"attendance:{student.pk}:{day.isoformat()}",
                occurred_at=_as_datetime(day),
                kind="attendance_day",
                title="Attendance",
                summary=summary,
                href=f"/manage/students/attendance?student={student.pk}&date={day.isoformat()}",
                actor=None,
            )
        )
    return entries


ATTENDANCE_KINDS = frozenset({"attendance_day"})


def _dsr_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """Daily status reports covering a batch this student was ever on.

    `visible_dsrs` already returns nothing for a student caller (a report is
    staff correspondence about a class, never a student's own view) — this
    source's own scoping stays exactly that; only the "which batches does
    this apply to" filter is student-specific.
    """
    from apps.dsr import access as dsr_access
    from apps.enrollments.models import Enrollment

    batch_ids = Enrollment.objects.filter(student=student).values("batch_id")
    qs = dsr_access.visible_dsrs(user).filter(
        batch_id__in=batch_ids,
        submitted_at__isnull=False,
        submitted_at__gte=since,
        submitted_at__lte=until,
    )
    if cursor_bound is not None:
        qs = qs.filter(submitted_at__lte=cursor_bound)

    rows = qs.order_by("-submitted_at")[:limit]
    entries: list[TimelineEntry] = []
    for dsr in rows:
        entries.append(
            TimelineEntry(
                id=f"dsr:{dsr.pk}",
                occurred_at=dsr.submitted_at,
                kind="dsr_submitted",
                title=f"Daily status report — {dsr.batch.code}",
                summary=dsr.actual_topic or dsr.planned_topic or "",
                href=f"/dsr?id={dsr.pk}",
                actor=_actor(dsr.trainer.user) if dsr.trainer_id else None,
            )
        )
    return entries


DSR_KINDS = frozenset({"dsr_submitted"})


def _assessment_result_events(
    user, student, since, until, cursor_bound, limit
) -> list[TimelineEntry]:
    from apps.assessments import access as assessment_access

    qs = assessment_access.visible_results(user).filter(
        enrollment__student=student, recorded_at__gte=since, recorded_at__lte=until
    )
    if cursor_bound is not None:
        qs = qs.filter(recorded_at__lte=cursor_bound)

    rows = qs.order_by("-recorded_at")[:limit]
    entries: list[TimelineEntry] = []
    for result in rows:
        if result.is_absent:
            summary = "Absent"
        elif result.marks_obtained is not None:
            summary = f"{result.marks_obtained}/{result.assessment.max_marks}"
        else:
            summary = "Not recorded"
        entries.append(
            TimelineEntry(
                id=f"assessment_result:{result.pk}",
                occurred_at=result.recorded_at,
                kind="assessment_result",
                title=f"Result — {result.assessment.title}",
                summary=summary,
                href=f"/teaching/assessments/{result.assessment_id}",
                actor=_actor(result.recorded_by),
            )
        )
    return entries


ASSESSMENT_RESULT_KINDS = frozenset({"assessment_result"})


def _assignment_submission_events(
    user, student, since, until, cursor_bound, limit
) -> list[TimelineEntry]:
    from apps.assignments import access as assignment_access

    qs = (
        assignment_access.visible_submissions(user)
        # `visible_submissions` also prefetches `files` for the views that
        # display them; this source never touches `.files`, so that
        # prefetch would be a second query per page for nothing.
        .prefetch_related(None)
        .filter(enrollment__student=student, submitted_at__gte=since, submitted_at__lte=until)
    )
    if cursor_bound is not None:
        qs = qs.filter(submitted_at__lte=cursor_bound)

    rows = qs.order_by("-submitted_at")[:limit]
    entries: list[TimelineEntry] = []
    for submission in rows:
        if submission.marks_awarded is not None:
            summary = (
                f"{submission.get_status_display()} — "
                f"{submission.marks_awarded}/{submission.assignment.max_marks}"
            )
        else:
            summary = submission.get_status_display()
        entries.append(
            TimelineEntry(
                id=f"assignment_submission:{submission.pk}",
                occurred_at=submission.submitted_at,
                kind="assignment_submitted",
                title=f"Submitted — {submission.assignment.title}",
                summary=summary,
                href=f"/teaching/assignments/{submission.assignment_id}",
                actor=_actor(submission.enrollment.student.user),
            )
        )
    return entries


ASSIGNMENT_SUBMISSION_KINDS = frozenset({"assignment_submitted"})


def _project_state_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """State transitions, not every field edit — the last-touched moment of a
    student's project work, keyed on `updated_at` since `StudentProject` keeps
    no separate history table of its own status changes."""
    from apps.projects import access as project_access

    qs = (
        project_access.visible_student_projects(user)
        # `visible_student_projects` also prefetches `files` for the views
        # that display them; this source never touches `.files`, so that
        # prefetch would be a second query per page for nothing.
        .prefetch_related(None)
        .select_related("reviewer__user")
        .filter(enrollment__student=student, updated_at__gte=since, updated_at__lte=until)
    )
    if cursor_bound is not None:
        qs = qs.filter(updated_at__lte=cursor_bound)

    rows = qs.order_by("-updated_at")[:limit]
    entries: list[TimelineEntry] = []
    for student_project in rows:
        occurred_at = _first_not_none(
            student_project.reviewed_at, student_project.submitted_at, student_project.updated_at
        )
        actor = None
        if student_project.reviewed_at and student_project.reviewer_id:
            actor = _actor(student_project.reviewer.user)
        elif student_project.submitted_at:
            actor = _actor(student_project.enrollment.student.user)
        summary = student_project.get_status_display()
        if student_project.marks_awarded is not None:
            summary = f"{summary} — {student_project.marks_awarded}"
        entries.append(
            TimelineEntry(
                id=f"project_state:{student_project.pk}",
                occurred_at=occurred_at,
                kind="project_state_changed",
                title=f"Project — {student_project.project.title}",
                summary=summary,
                href=f"/teaching/projects/{student_project.project_id}",
                actor=actor,
            )
        )
    return entries


PROJECT_STATE_KINDS = frozenset({"project_state_changed"})

#: Which of the twelve activity statuses represent a timeline "moment", and
#: the field each one's `occurred_at` is read from. The rest (DRAFT, PLANNED,
#: ASSIGNED, IN_PROGRESS, UNDER_REVIEW) are mid-workflow, not events — the
#: same distinction `OPEN_STATUSES` draws for the calendar's due-date source.
_ACTIVITY_STATUS_TIMESTAMP: dict[str, str] = {
    "completed": "completed_at",
    "approved": "reviewed_at",
    "requires_action": "reviewed_at",
    "cancelled": "updated_at",
    "reopened": "updated_at",
    "missed": "updated_at",
}
#: Whose action each of those statuses is attributed to.
_ACTIVITY_STATUS_ACTOR: dict[str, str] = {
    "completed": "performed_by",
    "approved": "reviewed_by",
    "requires_action": "reviewed_by",
    "cancelled": "created_by",
    "reopened": "created_by",
}

ACTIVITY_KINDS = frozenset(f"activity_{status}" for status in _ACTIVITY_STATUS_TIMESTAMP)


def _activity_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """Activity state (ERP Phase 9), reusing exactly the two-branch visibility
    `StudentActivityListView` already uses: the student's own reduced view
    when the caller *is* this student, the scoped staff view otherwise — so a
    `student_visible=False` activity never appears in a student's own
    timeline, and a scoped trainer never sees more here than
    `visible_activities` already grants them elsewhere."""
    from apps.work import access as work_access

    caller_student = work_access.caller_student_profile(user)
    if caller_student is not None and caller_student.pk == student.pk:
        base = work_access.student_visible_activities(student)
    else:
        base = work_access.visible_activities(user).filter(student=student)

    qs = base.filter(
        status__in=_ACTIVITY_STATUS_TIMESTAMP.keys(), updated_at__gte=since, updated_at__lte=until
    )
    if cursor_bound is not None:
        qs = qs.filter(updated_at__lte=cursor_bound)

    rows = qs.order_by("-updated_at")[:limit]
    entries: list[TimelineEntry] = []
    for activity in rows:
        field = _ACTIVITY_STATUS_TIMESTAMP[activity.status]
        occurred_at = _first_not_none(getattr(activity, field), activity.updated_at)
        actor_field = _ACTIVITY_STATUS_ACTOR.get(activity.status)
        actor = _actor(getattr(activity, actor_field)) if actor_field else None
        entries.append(
            TimelineEntry(
                id=f"activity:{activity.pk}",
                occurred_at=occurred_at,
                kind=f"activity_{activity.status}",
                title=activity.title,
                summary=activity.summary or activity.activity_type.name,
                href=f"/activities?id={activity.pk}",
                actor=actor,
            )
        )
    return entries


def _certificate_events(user, student, since, until, cursor_bound, limit) -> list[TimelineEntry]:
    """Reuses `apps.certificates.views.visible_certificates` rather than a
    second copy of that query, per the phase brief."""
    from apps.certificates.views import visible_certificates

    qs = (
        visible_certificates(user)
        .select_related("issued_by")
        .filter(completion__enrollment__student=student, issued_at__gte=since, issued_at__lte=until)
    )
    if cursor_bound is not None:
        qs = qs.filter(issued_at__lte=cursor_bound)

    rows = qs.order_by("-issued_at")[:limit]
    entries: list[TimelineEntry] = []
    for certificate in rows:
        entries.append(
            TimelineEntry(
                id=f"certificate:{certificate.pk}",
                occurred_at=certificate.issued_at,
                kind="certificate_issued",
                title=f"Certificate issued — {certificate.course_title}",
                summary=certificate.number,
                href=f"/admin/certificates?id={certificate.pk}",
                actor=_actor(certificate.issued_by),
            )
        )
    return entries


CERTIFICATE_KINDS = frozenset({"certificate_issued"})


#: The registry. Append a `_Source` here to put a new domain on everyone's
#: timeline; nothing else changes (see the module docstring's note on
#: Phase 19's communication source).
TIMELINE_SOURCES: list[_Source] = [
    _Source("enrolment", ENROLMENT_KINDS, _enrolment_events),
    _Source("attendance_day", ATTENDANCE_KINDS, _attendance_day_events),
    _Source("dsr", DSR_KINDS, _dsr_events),
    _Source("assessment_result", ASSESSMENT_RESULT_KINDS, _assessment_result_events),
    _Source("assignment_submission", ASSIGNMENT_SUBMISSION_KINDS, _assignment_submission_events),
    _Source("project_state", PROJECT_STATE_KINDS, _project_state_events),
    _Source("activity", ACTIVITY_KINDS, _activity_events),
    _Source("certificate", CERTIFICATE_KINDS, _certificate_events),
]


def default_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    from django.utils import timezone

    now = now or timezone.now()
    return now - timedelta(days=DEFAULT_WINDOW_DAYS), now


def timeline_for(
    user,
    student,
    *,
    since: datetime,
    until: datetime,
    kinds: set[str] | None = None,
    cursor: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[TimelineEntry], str | None]:
    """Every entry the caller may see about `student` in `[since, until]`,
    newest first, one page at a time.

    A source whose kinds do not intersect `kinds` (when given) is not called
    at all — the query-budget rule is about queries never issued, not results
    discarded afterwards. A source that raises is logged and skipped, the
    same resilience `apps.dashboards.calendar.events_for` gives the calendar:
    one broken feed must not blank a person's whole history.
    """
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    cursor_tuple = decode_cursor(cursor) if cursor else None
    cursor_bound = cursor_tuple[0] if cursor_tuple else None

    candidates: list[TimelineEntry] = []
    for source in TIMELINE_SOURCES:
        if kinds is not None and not (source.kinds & kinds):
            continue
        try:
            entries = source.fn(user, student, since, until, cursor_bound, page_size)
        except Exception:
            logger.exception("Timeline source %s failed for student %s", source.name, student.pk)
            continue
        if kinds is not None:
            entries = [entry for entry in entries if entry.kind in kinds]
        candidates.extend(entries)

    if cursor_tuple is not None:
        candidates = [entry for entry in candidates if (entry.occurred_at, entry.id) < cursor_tuple]

    candidates.sort(key=lambda entry: (entry.occurred_at, entry.id), reverse=True)
    page = candidates[:page_size]
    next_cursor = encode_cursor(page[-1]) if len(page) == page_size else None
    return page, next_cursor
