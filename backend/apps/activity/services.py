"""The administrator's activity review: who did what, when.

Two readings of the same source. The **feed** is the audit log with the noise
taken out — sign-ins, listings, downloads, refusals — and each row given a
sentence and a link, so an administrator can read "Kiran recorded ₹5,000 from
Rahul at 11:42" rather than a JSON blob. The **scorecards** are the same rows
counted per person and turned into the figures each role is measured by: a
counsellor by registrations and money collected, a manager by reports and
trainers reviewed, a trainer by classes taken and reports submitted.

Nothing here is a second record of anything. The audit log is the record;
this module only reads it. "Changes only" was the owner's call (10b): views
are not logged, so they are not counted.

Scope: the caller must hold `audit.view`, which is an administrator's right,
and an administrator sees every centre (D-129 as amended). The optional
``branch`` filter narrows the picture to one centre for reading, not for
authority.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Max, Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog, AuditResult

#: Actions that are not *work*: reading, signing in, being refused. Left out of
#: the feed and never counted on a scorecard.
NOISE_ACTIONS = frozenset(
    {
        AuditAction.LOGIN_SUCCEEDED,
        AuditAction.LOGIN_FAILED,
        AuditAction.LOGOUT,
        AuditAction.SESSIONS_REVOKED,
        AuditAction.PASSWORD_RESET_REQUESTED,
        AuditAction.PASSWORD_RESET_FAILED,
        AuditAction.EMAIL_VERIFICATION_FAILED,
        AuditAction.USER_LISTED,
        AuditAction.SUBMISSION_FILE_DOWNLOADED,
        AuditAction.PROJECT_FILE_DOWNLOADED,
        AuditAction.CERTIFICATE_DOWNLOADED,
        AuditAction.CERTIFICATE_VERIFIED,
        AuditAction.EXPORT_DOWNLOADED,
        AuditAction.PERMISSION_DENIED,
        AuditAction.UPLOAD_REJECTED,
    }
)

#: What kind of work an action is, for the feed's filter. Anything unlisted
#: is "other" — visible, filterable, just not named.
KINDS: dict[str, tuple[str, ...]] = {
    "admissions": ("student.", "enrollment.", "batch.", "schedule."),
    "fees": ("fee.",),
    "teaching": (
        "session",
        "attendance.",
        "assignment.",
        "submission.",
        "assessment.",
        "result.",
        "project.",
        "exam.",
        "question.",
    ),
    "reviews": ("dsr.", "review.", "feedback.", "risk."),
    "courses": ("course.", "module.", "lesson.", "resource.", "category."),
    "outcomes": ("completion.", "certificate."),
    "accounts": ("user.", "trainer.", "profile.", "branch.", "password.", "email."),
    "communication": ("announcement.", "requirement.", "thread.", "reply."),
    "institution": ("branding.", "academic.", "system.", "record.", "export.", "data.", "report."),
}

KIND_LABELS = {
    "admissions": "Admissions",
    "fees": "Fees",
    "teaching": "Teaching",
    "reviews": "Reviews",
    "courses": "Courses",
    "outcomes": "Outcomes",
    "accounts": "Accounts",
    "communication": "Communication",
    "institution": "Institution",
    "other": "Other",
}


def kind_of(action: str) -> str:
    for kind, prefixes in KINDS.items():
        if any(action.startswith(prefix) for prefix in prefixes):
            return kind
    return "other"


# ---------------------------------------------------------------------------
# The feed
# ---------------------------------------------------------------------------


def _day_bounds(since: date | None, until: date | None) -> tuple[datetime | None, datetime | None]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(since, time.min), tz) if since else None
    end = timezone.make_aware(datetime.combine(until, time.max), tz) if until else None
    return start, end


def feed(
    *,
    since: date | None = None,
    until: date | None = None,
    actor_id: Any = None,
    role: str | None = None,
    kind: str | None = None,
    branch_id: Any = None,
    search: str = "",
) -> QuerySet[AuditLog]:
    """The audit log as an administrator reads it, newest first."""
    rows = (
        AuditLog.objects.exclude(action__in=NOISE_ACTIONS)
        .filter(result=AuditResult.SUCCESS)
        .select_related("actor", "actor__branch")
        .order_by("-created_at")
    )
    start, end = _day_bounds(since, until)
    if start:
        rows = rows.filter(created_at__gte=start)
    if end:
        rows = rows.filter(created_at__lte=end)
    if actor_id:
        rows = rows.filter(actor_id=actor_id)
    if role:
        rows = rows.filter(actor__role=role)
    if branch_id:
        rows = rows.filter(actor__branch_id=branch_id)
    if kind and kind in KINDS:
        query = Q()
        for prefix in KINDS[kind]:
            query |= Q(action__startswith=prefix)
        rows = rows.filter(query)
    elif kind == "other":
        for prefixes in KINDS.values():
            for prefix in prefixes:
                rows = rows.exclude(action__startswith=prefix)
    if search.strip():
        term = search.strip()
        rows = rows.filter(
            Q(actor_label__icontains=term)
            | Q(resource_id__icontains=term)
            | Q(context__icontains=term)
        )
    return rows


def _money(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    return f"₹{number:,.0f}" if number == number.to_integral_value() else f"₹{number:,.2f}"


def describe(entry: AuditLog) -> str:
    """One sentence for the feed, from what the service wrote into context."""
    c = entry.context or {}
    a = entry.action
    label = entry.get_action_display()
    who = c.get("student") or c.get("student_id") or c.get("code") or c.get("name") or ""
    if a == AuditAction.STUDENT_CREATED:
        return f"Registered student {c.get('student_id', '')}".strip()
    if a == AuditAction.ENROLLMENT_CREATED:
        return f"Enrolled {c.get('student', '')} on {c.get('batch', '')}".strip()
    if a == AuditAction.FEE_PAYMENT_RECORDED:
        return (
            f"Received {_money(c.get('amount', 0))} by {c.get('method', '')}"
            f" (receipt {c.get('receipt_number', '')}); balance {_money(c.get('balance_after', 0))}"
        )
    if a == AuditAction.FEE_PAYMENT_VOIDED:
        return (
            f"Voided {_money(c.get('amount', 0))} (receipt {c.get('receipt_number', '')}): "
            f"{c.get('reason', '')}"
        )
    if a == AuditAction.FEE_PLAN_SET:
        return (
            f"Agreed a fee of {_money(c.get('agreed_amount', 0))} "
            f"for {c.get('enrollment_code', '')}"
        )
    if a == AuditAction.FEE_PLAN_UPDATED:
        changes = c.get("changes") or {}
        parts = [f"{field} {v.get('from')} → {v.get('to')}" for field, v in changes.items()]
        return "Changed fee: " + "; ".join(parts) if parts else "Changed fee"
    if a == AuditAction.REQUIREMENT_RAISED:
        return f"Asked the trainers: {c.get('title', '')}".strip()
    if a == AuditAction.REQUIREMENT_REPLIED:
        return f"Answered on: {c.get('title', '')}".strip()
    if a == AuditAction.REQUIREMENT_CLOSED:
        who = c.get("fulfilled_by") or ""
        return f"Closed: {c.get('title', '')}" + (f" (fulfilled by {who})" if who else "")
    if a == AuditAction.BATCH_CREATED:
        return f"Opened batch {c.get('code', '')} {c.get('name', '')}".strip()
    if a == AuditAction.BATCH_TRAINER_ASSIGNED:
        return f"Assigned trainer on {c.get('code', c.get('batch', ''))}".strip()
    if a == AuditAction.ATTENDANCE_MARKED:
        return f"Marked attendance ({c.get('marked', c.get('count', ''))} students)".replace(
            " ()", ""
        )
    if a in (
        AuditAction.DSR_APPROVED,
        AuditAction.DSR_REJECTED,
        AuditAction.DSR_REVISION_REQUESTED,
    ):
        return f"{label}: {c.get('batch', c.get('code', ''))}".rstrip(": ")
    if a == AuditAction.TRAINER_CREATED:
        return f"Added trainer {c.get('trainer_id', '')}".strip()
    if a in (AuditAction.COURSE_CREATED, AuditAction.COURSE_UPDATED):
        return f"{label}: {c.get('title', c.get('code', ''))}".rstrip(": ")
    if a in (
        AuditAction.LESSON_CREATED,
        AuditAction.LESSON_UPDATED,
        AuditAction.MODULE_CREATED,
        AuditAction.MODULE_UPDATED,
    ):
        fields = c.get("changed_fields") or c.get("changes")
        tail = f" ({', '.join(fields)})" if isinstance(fields, list) and fields else ""
        return f"{label}: {c.get('title', '')}{tail}".rstrip(": ")
    if a == AuditAction.REVIEW_RECORDED:
        return f"Recorded a performance review ({c.get('subject_type', '')})".replace(" ()", "")
    if "changed_fields" in c and isinstance(c["changed_fields"], list):
        return f"{label} ({', '.join(c['changed_fields'])})"
    if "from" in c and "to" in c and not isinstance(c["from"], dict):
        return f"{label}: {c['from']} → {c['to']}"
    return f"{label} {who}".strip()


#: Where a feed row links to. Resource types are the strings the services
#: pass to `record(resource_type=...)`.
def link_for(entry: AuditLog) -> str | None:
    c = entry.context or {}
    rid = entry.resource_id
    t = entry.resource_type
    if t == "student":
        return f"/admissions/{rid}"
    if t in ("fee_plan", "fee_payment") and c.get("student_id"):
        return f"/admissions/{c['student_id']}"
    if t == "enrollment" and c.get("student_pk"):
        return f"/admissions/{c['student_pk']}"
    if t == "batch":
        return f"/admin/batches/{rid}"
    if t == "trainer":
        return f"/manage/trainers/{rid}"
    if t == "user":
        return f"/admin/users/{rid}"
    if t == "course":
        return f"/admin/courses/{rid}"
    if t == "dsr":
        return "/dsr"
    if t == "trainer_requirement":
        return f"/requirements?open={rid}"
    if t == "branch":
        return "/admin/branches"
    return None


# ---------------------------------------------------------------------------
# Scorecards
# ---------------------------------------------------------------------------

#: Which counted actions make up each figure. One action may feed one figure.
FIGURES: dict[str, tuple[str, tuple[str, ...]]] = {
    "students_registered": ("Students registered", (AuditAction.STUDENT_CREATED,)),
    "enrolments": ("Enrolments", (AuditAction.ENROLLMENT_CREATED,)),
    "payments_recorded": ("Payments recorded", (AuditAction.FEE_PAYMENT_RECORDED,)),
    "batches_opened": ("Batches opened", (AuditAction.BATCH_CREATED,)),
    "trainers_added": ("Trainers added", (AuditAction.TRAINER_CREATED,)),
    "attendance_marked": (
        "Registers marked",
        (AuditAction.ATTENDANCE_MARKED, AuditAction.ATTENDANCE_CORRECTED),
    ),
    "reports_submitted": ("Daily reports submitted", (AuditAction.DSR_SUBMITTED,)),
    "reports_reviewed": (
        "Daily reports reviewed",
        (AuditAction.DSR_APPROVED, AuditAction.DSR_REJECTED, AuditAction.DSR_REVISION_REQUESTED),
    ),
    "reviews_recorded": (
        "Performance reviews",
        (AuditAction.REVIEW_RECORDED, AuditAction.REVIEW_UPDATED),
    ),
    "work_graded": (
        "Work graded",
        (
            AuditAction.SUBMISSION_GRADED,
            AuditAction.RESULT_RECORDED,
            AuditAction.PROJECT_REVIEWED,
            AuditAction.EXAM_ATTEMPT_GRADED,
        ),
    ),
    "content_edited": (
        "Course content edits",
        (
            AuditAction.COURSE_CREATED,
            AuditAction.COURSE_UPDATED,
            AuditAction.MODULE_CREATED,
            AuditAction.MODULE_UPDATED,
            AuditAction.LESSON_CREATED,
            AuditAction.LESSON_UPDATED,
            AuditAction.RESOURCE_UPLOADED,
        ),
    ),
    "announcements": ("Announcements", (AuditAction.ANNOUNCEMENT_PUBLISHED,)),
}

#: Which figures lead on each role's card, in order. Everything else with a
#: non-zero count follows.
LEAD_FIGURES = {
    UserRole.COUNSELLOR: (
        "students_registered",
        "enrolments",
        "payments_recorded",
        "batches_opened",
    ),
    UserRole.MANAGER: ("reports_reviewed", "reviews_recorded", "trainers_added", "batches_opened"),
    UserRole.TRAINER: ("attendance_marked", "reports_submitted", "work_graded", "content_edited"),
    UserRole.ADMIN: ("reports_reviewed", "students_registered", "trainers_added", "content_edited"),
}

STAFF_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.COUNSELLOR, UserRole.TRAINER)


def scorecards(
    *, since: date, until: date, branch_id: Any = None, role: str | None = None
) -> list[dict[str, Any]]:
    """One card per staff member active in the period, busiest first."""
    from apps.fees.models import FeePayment

    start, end = _day_bounds(since, until)
    counted = (
        AuditLog.objects.exclude(action__in=NOISE_ACTIONS)
        .filter(result=AuditResult.SUCCESS, created_at__gte=start, created_at__lte=end)
        .filter(actor__role__in=STAFF_ROLES)
    )
    if branch_id:
        counted = counted.filter(actor__branch_id=branch_id)
    if role:
        counted = counted.filter(actor__role=role)
    per_action = counted.values("actor_id", "action").annotate(n=Count("id"))
    last_seen = {
        row["actor_id"]: row["last"]
        for row in counted.values("actor_id").annotate(last=Max("created_at"))
    }
    tallies: dict[Any, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[Any, int] = defaultdict(int)
    action_to_figure = {
        action: key for key, (_label, actions) in FIGURES.items() for action in actions
    }
    for row in per_action:
        totals[row["actor_id"]] += row["n"]
        figure = action_to_figure.get(row["action"])
        if figure:
            tallies[row["actor_id"]][figure] += row["n"]

    collected = {
        row["recorded_by_id"]: row["total"]
        for row in FeePayment.objects.filter(
            voided_at__isnull=True, paid_on__gte=since, paid_on__lte=until
        )
        .values("recorded_by_id")
        .annotate(total=Sum("amount"))
    }

    actor_ids = set(totals) | set(collected)
    users = {
        user.pk: user for user in User.objects.filter(pk__in=actor_ids).select_related("branch")
    }
    cards = []
    for actor_id in actor_ids:
        user = users.get(actor_id)
        if user is None or user.role not in STAFF_ROLES:
            continue
        if branch_id and user.branch_id != branch_id:
            continue
        if role and user.role != role:
            continue
        figures = []
        seen = set()
        for key in LEAD_FIGURES.get(user.role, ()):
            figures.append(
                {"key": key, "label": FIGURES[key][0], "value": tallies[actor_id].get(key, 0)}
            )
            seen.add(key)
        for key, (label, _actions) in FIGURES.items():
            value = tallies[actor_id].get(key, 0)
            if key not in seen and value:
                figures.append({"key": key, "label": label, "value": value})
        cards.append(
            {
                "user_id": user.pk,
                "name": user.full_name or user.email,
                "email": user.email,
                "role": user.role,
                "branch_name": user.branch.name if user.branch_id else None,
                "total_actions": totals.get(actor_id, 0),
                "fees_collected": collected.get(actor_id, Decimal("0")),
                "last_active_at": last_seen.get(actor_id),
                "figures": figures,
            }
        )
    cards.sort(key=lambda card: (-card["total_actions"], card["name"]))
    return cards


def period_bounds(preset: str, today: date | None = None) -> tuple[date, date]:
    """`today`, `week` (Monday to today), `month` (the 1st to today)."""
    today = today or timezone.localdate()
    if preset == "week":
        return today - timedelta(days=today.weekday()), today
    if preset == "month":
        return today.replace(day=1), today
    return today, today
