"""`GET /students/{id}/360/` (ERP Phase 11, ADR-09/10/11, `API_CONTRACTS.md`).

One call composing what the Student 360 header and Overview tab need, across
domains that each keep their own scoping — the same reasoning
`apps.work.timeline` gives for the activity timeline: a screen that draws on
eight apps' data should not become eight round trips from the client, and no
source here bypasses its own domain's `visible_*`/access rule to get there.
Kept in its own module rather than `services.py` because this composes a read
model rather than carrying out a business rule (nothing here writes), the
same distinction `apps.work.timeline` draws from `apps.work.services`.

**`performance`** — ADR-10's weighted components (`{key, label, weight,
value, contribution, sources}` per component, a weighted `overall_score`),
computed for real by `apps.performance.engine.student_performance`
(ERP Phase 12), called on this student's `_most_relevant_enrollment` — the
same enrolment already resolved below for `batch`/`trainer`/`progress`,
never a second resolution. A student with no enrolment at all still gets the
inert `{"components": [], "overall_score": None}` shape rather than an
error, the same "real state, not a crash" rule every other enrolment-derived
field on this endpoint already follows.

**`risk`** — ADR-11's verdict: `level` (`none`/`warning`/`critical`) and
`triggered`, a list of full outcome objects (`{key, label, severity, detail,
numbers}`, exactly `apps.performance.risk.RiskOutcome.as_dict()`'s shape,
matching the frontend's `Student360RiskTrigger` type) — read from the same
`student_performance` call `performance` already made this request, not
reconstructed from the persisted `RiskState.triggered` (deliberately just
rule *keys*, per `DATA_MODEL.md`). `apps.performance.services.risk_state_for`
is still called, for its side effect: it persists a verdict on this
enrolment's very first read, so a brand-new enrolment's very first Student
360 view — and `/risk/summary/` right after it — never has to wait on the
debounced background task (`apps.performance.tasks`) to have already run.
A student with no enrolment at all gets the same neutral `{"level": "none",
"triggered": []}` any other enrolment-derived field here degrades to.

**Still a placeholder, not yet computed** — documented here so nobody
"fixes" it by guessing a formula ahead of the phase that owns it:

* `next_actions` — Phase 14's automation engine suggests these. Until then,
  always `[]`.

**"Counsellor"** has no dedicated field anywhere in the data model yet
(`AUTOMATION_CATALOG.md` names a future `created_by` on the *profile* itself
for Phase 14's automation context — not built, and out of scope here). The
closest thing that already exists is `Enrollment.created_by`: enrolments are
created by the counsellor who admits the student (`services.create_student`
records that, but the *profile* has nowhere to keep it). Reusing it is a
deliberate, documented choice rather than adding a new column this phase does
not otherwise need.

**"Enrollment"/"batch"/"trainer"** are the student's most relevant enrolment:
the newest *live* one (`LIVE_STATUS_LIST` — pending/active/suspended), or
failing that the newest of any status, chosen with one query (a `Case`
ordering rather than "try live, then fall back") so this never costs a second
round trip. `None` when the student has never been enrolled anywhere — every
field below degrades to `null`/`0`/neutral rather than raising.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Case, Count, IntegerField, Q, When

from apps.accounts.roles import Capability, has_capability
from apps.assessments import access as assessment_access
from apps.assignments import access as assignment_access
from apps.attendance.models import attendance_summary as _attendance_summary
from apps.authorization.scopes import ALL, BRANCH, effective_scope
from apps.enrollments.models import LIVE_STATUS_LIST, Enrollment
from apps.enrollments.serializers import EnrollmentSerializer
from apps.enrollments.services import course_progress
from apps.organisation.scoping import actor_branch_id
from apps.projects import access as project_access
from apps.work import access as work_access
from apps.work.models import OPEN_STATUSES, ActivityStatus

from .models import StudentProfile
from .serializers import AdminStudentProfileSerializer, StudentProfileSerializer


def viewer_scope_key(user) -> str:
    """Names the *shape of data* this caller would see on any student's 360 —
    never the caller's own identity where that identity does not change the
    answer, so the 1-minute cache (`API_CONTRACTS.md`: "per (student, viewer
    scope key)") can be shared by two callers whose effective view is
    genuinely identical, and never by two whose is not.

    `effective_scope` (ADR-02) already answers "how far does `student.view_any`
    reach for this person", for *every* role — including a trainer or a
    student, neither of whom holds that capability at all: their role's floor
    (`ASSIGNED`, `OWN`) still applies, unaffected by whether they hold the
    capability, which is exactly the tier this key needs to name.

    * `all` — every unbounded caller (admin, superadmin) sees the same thing
      for a given student, so one key per role name is enough.
    * `branch` — every caller bounded to the same centre sees the same thing
      *for a `student.view_any`-shaped reach*; keyed on the branch, not the
      person.
    * `assigned`/`own` — a trainer's reach is their own taught batches; a
      student's is their own record. Neither is shared with anyone else at
      that tier even nominally, so these anchor to the caller's own id rather
      than pretend two trainers' views are interchangeable.

    Residual, accepted imprecision: a custom role (ADR-02) can narrow a
    *different* capability (e.g. `activity.view_any`) to a tier tighter than
    `student.view_any`'s own configured scope, which this key does not
    separately encode — two same-branch managers configured that way could,
    in principle, share a cache entry despite one seeing fewer activities on
    this student than the other. Bounded by the 1-minute TTL either way, and
    narrower than the leak this function exists to prevent (a `branch`-tier
    caller never sharing with an `all`- or `assigned`-tier one).
    """
    scope = effective_scope(user, Capability.STUDENT_VIEW_ANY)
    if scope == ALL:
        return f"{user.role}:{ALL}"
    if scope == BRANCH:
        return f"{user.role}:{BRANCH}:{actor_branch_id(user)}"
    return f"{user.role}:{scope}:{user.pk}"


def _person_brief(user) -> dict[str, str] | None:
    if user is None:
        return None
    return {"id": str(user.pk), "name": user.full_name or user.email}


def _batch_summary(batch) -> dict[str, Any] | None:
    if batch is None:
        return None
    return {"id": str(batch.pk), "code": batch.code, "name": batch.name, "status": batch.status}


def _most_relevant_enrollment(student: StudentProfile) -> Enrollment | None:
    """The newest live enrolment, or failing that the newest of any status.

    One query: ordering by "is this row live" before recency, rather than a
    live-first query that falls back to a second one, keeps this flat
    regardless of how many enrolments the student has had.
    """
    return (
        Enrollment.objects.filter(student=student)
        .select_related("course", "batch__trainer__user", "created_by")
        .annotate(
            _live_first=Case(
                When(status__in=LIVE_STATUS_LIST, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("_live_first", "-enrolled_at")
        .first()
    )


def _neutral_attendance() -> dict[str, Any]:
    return {"percent": None, "attended": None, "total_sessions": None, "has_records": False}


def _attendance_summary_for(enrollment: Enrollment | None) -> dict[str, Any]:
    if enrollment is None:
        return _neutral_attendance()
    summary = _attendance_summary(enrollment)
    has_records = bool(
        summary["present"] + summary["late"] + summary["absent"] + summary["excused"]
    )
    return {
        "percent": summary["percentage"],
        "attended": summary["attended"],
        "total_sessions": summary["total_sessions"],
        "has_records": has_records,
    }


def _work_counts(user, student: StudentProfile) -> dict[str, int]:
    """`activities_open`/`activities_overdue`, one query via `aggregate` —
    through `apps.work.access.visible_activities`, never an unscoped count."""
    totals = (
        work_access.visible_activities(user)
        .filter(student=student)
        .aggregate(
            open=Count("id", filter=Q(status__in=OPEN_STATUSES)),
            overdue=Count("id", filter=Q(status=ActivityStatus.OVERDUE)),
        )
    )
    return {"activities_open": totals["open"] or 0, "activities_overdue": totals["overdue"] or 0}


def _course_work_counts(user, enrollment: Enrollment | None) -> dict[str, int]:
    """`assessments`/`assignments`/`projects`, each through that domain's own
    `visible_*`, filtered to this enrolment's batch (assessments — always
    batch-specific) or course-wide-or-this-batch (assignments/projects —
    the same "course-wide or set for this batch" reading their own
    `visible_*` already uses for a student's live enrolments)."""
    if enrollment is None:
        return {"assessments": 0, "assignments": 0, "projects": 0}

    assessments = (
        assessment_access.visible_assessments(user).filter(batch_id=enrollment.batch_id).count()
    )
    course_or_batch = Q(course_id=enrollment.course_id) & (
        Q(batch__isnull=True) | Q(batch_id=enrollment.batch_id)
    )
    assignments = assignment_access.visible_assignments(user).filter(course_or_batch).count()
    projects = project_access.visible_projects(user).filter(course_or_batch).count()
    return {"assessments": assessments, "assignments": assignments, "projects": projects}


_INERT_PERFORMANCE: dict[str, Any] = {"components": [], "overall_score": None}
_INERT_RISK: dict[str, Any] = {"level": "none", "triggered": []}


def _full_performance(enrollment: Enrollment | None) -> dict[str, Any] | None:
    """`apps.performance.engine.student_performance`'s whole output, computed
    once per request and shared by `_performance_for` (ADR-10) and
    `_risk_for` (ADR-11) — never a second engine run for the same enrolment
    on the same request. `None` for a student with no enrolment at all."""
    if enrollment is None:
        return None

    from apps.performance.engine import student_performance

    return student_performance(enrollment)


def _performance_for(performance: dict[str, Any] | None) -> dict[str, Any]:
    """ADR-10's `{components, overall_score}` shape, real for a student with
    an enrolment, inert for one without — never a third shape and never an
    error. `student_performance` returns a much larger dict (attendance,
    assessment breakdowns, risk, counts); this endpoint's contract is only
    the two ADR-10 keys, matching what the frontend's `Student360Performance`
    type already declares."""
    if performance is None:
        return dict(_INERT_PERFORMANCE)
    return {"components": performance["components"], "overall_score": performance["overall_score"]}


def _risk_for(enrollment: Enrollment | None, performance: dict[str, Any] | None) -> dict[str, Any]:
    """ADR-11's `{level, triggered}` shape — `triggered` is a list of full
    outcome objects (`{key, label, severity, detail, numbers}`), exactly
    `apps.performance.risk.RiskOutcome.as_dict()`'s shape, matching the
    frontend's `Student360RiskTrigger` type. Read from `performance["risk"]`
    (the same `risk.evaluate()` call `_full_performance` already made this
    request) rather than the persisted `RiskState.triggered` — that field is
    deliberately just rule *keys* (`DATA_MODEL.md`), and reconstructing
    `label`/`detail` text from it here would be exactly the "second,
    hand-maintained copy" `apps.performance.serializers`' own docstring
    warns against.

    `services.risk_state_for` is still called for its side effect: it
    persists a `RiskState` row on this enrolment's very first read, so
    `/risk/summary/` and a background recompute have a verdict to read
    without waiting on the debounced task — see that function's own
    docstring. `numbers` may differ from the stored row's by nothing at all
    (both come from this same instant's `evaluate()` call, deterministically)
    except in the one-time case where this *is* that first read, and the
    persisted row is written from a second, separately-gathered
    `student_performance` call inside `recompute_risk` — a bounded, one-time
    cost, not a per-request one.

    `level` itself, though, is *not* always this instant's live
    `risk_result["level"]`: while the persisted row carries a still-active
    manual override (`apps.automation.actions.flag_risk`,
    `RiskState.manual_override_active`), that override — not the engine's
    own live computation — is this enrolment's actual current verdict, the
    same one `/risk/summary/` already shows. Reading the live value instead
    here would make this the one screen where a manager-visible manual flag
    is invisible.
    """
    if enrollment is None or performance is None:
        return dict(_INERT_RISK)

    from apps.performance.services import risk_state_for

    state = risk_state_for(enrollment)

    risk_result = performance["risk"]
    triggered = [
        {
            "key": outcome["key"],
            "label": outcome["label"],
            "severity": outcome["severity"],
            "detail": outcome["detail"],
            "numbers": outcome["numbers"],
        }
        for outcome in risk_result["outcomes"]
        if outcome["triggered"]
    ]
    level = state.level if state.manual_override_active else risk_result["level"]
    return {"level": level, "triggered": triggered}


def _recent_activities(user, student: StudentProfile) -> list[dict[str, Any]]:
    """The last five activities the caller may see on this student — via
    `apps.work.access.visible_activities`, the same scoping Phase 9's review
    fixed on the sibling `StudentActivityListView`. Never a fresh, unscoped
    query: that regression is exactly what this line must not reintroduce."""
    rows = work_access.visible_activities(user).filter(student=student).order_by("-created_at")[:5]
    return [
        {
            "id": str(row.pk),
            "title": row.title,
            "href": f"/activities?id={row.pk}",
            "occurred_at": (row.completed_at or row.created_at).isoformat(),
            "due_at": row.due_at.isoformat() if row.due_at else None,
        }
        for row in rows
    ]


def build(user, student: StudentProfile) -> dict[str, Any]:
    """The full read model. Called only from behind the 1-minute cache
    (`views.Student360View`) — this itself does no caching of its own."""
    is_admin = has_capability(user, Capability.STUDENT_VIEW_ANY)
    profile_serializer = AdminStudentProfileSerializer if is_admin else StudentProfileSerializer

    enrollment = _most_relevant_enrollment(student)
    batch = enrollment.batch if enrollment else None
    trainer = batch.trainer.user if batch and batch.trainer_id else None
    counsellor = enrollment.created_by if enrollment else None
    performance = _full_performance(enrollment)

    return {
        "profile": profile_serializer(student).data,
        "enrollment": EnrollmentSerializer(enrollment).data if enrollment else None,
        "batch": _batch_summary(batch),
        "trainer": _person_brief(trainer),
        "counsellor": _person_brief(counsellor),
        "progress": course_progress(enrollment) if enrollment else None,
        "attendance_summary": _attendance_summary_for(enrollment),
        "performance": _performance_for(performance),
        "risk": _risk_for(enrollment, performance),
        "counts": {**_work_counts(user, student), **_course_work_counts(user, enrollment)},
        "fee_status": student.fee_status,
        "recent_activities": _recent_activities(user, student),
        # Phase 14 placeholder — see module docstring.
        "next_actions": [],
    }
