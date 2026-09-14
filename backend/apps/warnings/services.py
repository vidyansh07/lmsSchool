"""Warnings: the things that go wrong quietly, said out loud before they do.

Every warning is computed from the caller's *visible* querysets — the same
access functions the screens use — so a manager is warned about their centre
and a trainer about their own classes, and nobody is told about a record
they could not open. Nothing is stored: a warning is true until the thing it
names is fixed, and a stored copy would only ever be stale.

The eight kinds the owner asked for (11, "all"):

- ``fees_overdue``           an expected date has passed, money still owed
- ``fees_missing``           enrolled more than a day ago, no fee agreed
- ``batch_no_trainer``       an upcoming or running batch with nobody teaching it
- ``batch_seats``            starting within three days with seats unfilled
- ``trainer_clash``          a trainer timetabled in two places at once
- ``dsr_missing``            a class finished, no daily report
- ``students_at_risk``       the risk engine has flagged them
- ``not_enrolled``           registered a week ago, still not on a batch
- ``account_no_centre``      a bounded account with no centre (sees nothing)
- ``email_unverified``       a staff account that never verified its email
- ``completions_pending``    eligible for completion, waiting for approval
- ``batch_overrun``          past its end date and still active

Each is a dict: kind, severity (``error`` needs doing today, ``warning``
this week, ``info`` worth knowing), label, count, href (where to fix it) and
up to five items with their own href.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.accounts.roles import Capability, UserRole, has_capability

ITEM_LIMIT = 5
CACHE_SECONDS = 60


def _person(user) -> str:
    return user.full_name or user.email


def _student_of(enrollment) -> str:
    return _person(enrollment.student.user)


def _warning(kind, severity, label, count, href, items=()) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "label": label,
        "count": count,
        "href": href,
        "items": list(items)[:ITEM_LIMIT],
    }


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


# ---------------------------------------------------------------------------


def _fee_warnings(user, enrollments) -> list[dict[str, Any]]:
    from apps.enrollments.models import LIVE_STATUSES
    from apps.fees.models import FeePlan

    out = []
    today = timezone.localdate()
    live = enrollments.filter(status__in=LIVE_STATUSES)
    overdue = [
        plan
        for plan in FeePlan.objects.filter(enrollment__in=live, next_due_on__lt=today)
        .select_related("enrollment__student__user")
        .with_totals()
        if plan.balance > 0
    ]
    if overdue:
        n = len(overdue)
        out.append(
            _warning(
                "fees_overdue",
                "error",
                f"{n} {_plural(n, 'student')} past the date a payment was expected",
                n,
                "/admin/students?fee_status=overdue",
                (
                    {
                        "label": (
                            f"{_student_of(p.enrollment)} · ₹{p.balance:,.0f} owed "
                            f"since {p.next_due_on:%d %b}"
                        ),
                        "href": f"/admissions/{p.enrollment.student_id}",
                    }
                    for p in overdue
                ),
            )
        )
    missing = list(
        live.filter(fee_plan__isnull=True, enrolled_at__lt=timezone.now() - timedelta(days=1))
        .select_related("student__user", "course")
        .order_by("enrolled_at")[: ITEM_LIMIT + 1]
    )
    missing_count = live.filter(
        fee_plan__isnull=True, enrolled_at__lt=timezone.now() - timedelta(days=1)
    ).count()
    if missing_count:
        out.append(
            _warning(
                "fees_missing",
                "warning",
                f"{missing_count} {_plural(missing_count, 'enrolment')} with no fee agreed",
                missing_count,
                "/admissions",
                (
                    {
                        "label": f"{_student_of(e)} · {e.course.title}",
                        "href": f"/admissions/{e.student_id}",
                    }
                    for e in missing
                ),
            )
        )
    return out


def _batch_warnings(user, batches) -> list[dict[str, Any]]:
    from apps.batches.conflicts import trainer_conflicts_for_batch
    from apps.batches.models import BatchStatus
    from apps.enrollments.models import LIVE_STATUSES

    out = []
    today = timezone.localdate()
    open_batches = batches.filter(status__in=(BatchStatus.UPCOMING, BatchStatus.ACTIVE))
    no_trainer = list(open_batches.filter(trainer__isnull=True).order_by("start_date"))
    if no_trainer:
        n = len(no_trainer)
        out.append(
            _warning(
                "batch_no_trainer",
                "error" if any(b.start_date <= today for b in no_trainer) else "warning",
                f"{n} {_plural(n, 'batch', 'batches')} with no trainer",
                n,
                "/admin/batches",
                (
                    {
                        "label": f"{b.name} ({b.code}) · starts {b.start_date:%d %b}",
                        "href": f"/admin/batches/{b.pk}",
                    }
                    for b in no_trainer
                ),
            )
        )
    soon = (
        open_batches.filter(status=BatchStatus.UPCOMING, start_date__lte=today + timedelta(days=3))
        .annotate(filled=Count("enrollments", filter=Q(enrollments__status__in=LIVE_STATUSES)))
        .filter(filled__lt=F("capacity"))
        .order_by("start_date")
    )
    seats = list(soon)
    if seats:
        n = len(seats)
        out.append(
            _warning(
                "batch_seats",
                "warning",
                f"{n} {_plural(n, 'batch', 'batches')} starting within 3 days with seats unfilled",
                n,
                "/admissions/batches",
                (
                    {
                        "label": (
                            f"{b.name} ({b.code}) · "
                            f"{b.capacity - b.filled} of {b.capacity} seats open"
                        ),
                        "href": f"/admin/batches/{b.pk}",
                    }
                    for b in seats
                ),
            )
        )
    clashes = []
    staffed = list(open_batches.filter(trainer__isnull=False).select_related("trainer__user")[:300])
    for batch in staffed:
        found = trainer_conflicts_for_batch(batch, batch.trainer)
        if found:
            clashes.append((batch, found[0]))
    if clashes:
        n = len(clashes)
        out.append(
            _warning(
                "trainer_clash",
                "error",
                f"{n} {_plural(n, 'batch', 'batches')} whose trainer is booked twice",
                n,
                "/admin/batches",
                (
                    {
                        "label": f"{_person(b.trainer.user)}: {b.code} clashes with {c.batch_code}",
                        "href": f"/admin/batches/{b.pk}",
                    }
                    for b, c in clashes
                ),
            )
        )
    overrun = list(
        batches.filter(status=BatchStatus.ACTIVE, end_date__lt=today).order_by("end_date")
    )
    if overrun:
        n = len(overrun)
        out.append(
            _warning(
                "batch_overrun",
                "warning",
                f"{n} {_plural(n, 'batch', 'batches')} past the end date and still active",
                n,
                "/admin/batches?status=active",
                (
                    {
                        "label": f"{b.name} ({b.code}) · ended {b.end_date:%d %b}",
                        "href": f"/admin/batches/{b.pk}",
                    }
                    for b in overrun
                ),
            )
        )
    return out


def _dsr_warnings(user, batches) -> list[dict[str, Any]]:
    from apps.dsr.models import DSR, DSRStatus
    from apps.sessions.models import ClassSession, SessionStatus

    reported = DSR.objects.exclude(status=DSRStatus.DRAFT).values_list("session_id", flat=True)
    missing = (
        ClassSession.objects.filter(
            batch__in=batches, status=SessionStatus.COMPLETED, trainer__isnull=False
        )
        .exclude(id__in=reported)
        .select_related("batch", "trainer__user")
        .order_by("-session_date")
    )
    count = missing.count()
    if not count:
        return []
    return [
        _warning(
            "dsr_missing",
            "error",
            f"{count} {_plural(count, 'class', 'classes')} finished with no daily report",
            count,
            "/dsr",
            (
                {
                    "label": f"{s.batch.code} · {s.session_date:%d %b} · {_person(s.trainer.user)}",
                    "href": f"/teaching/sessions/{s.pk}",
                }
                for s in missing[:ITEM_LIMIT]
            ),
        )
    ]


def _risk_warnings(user, enrollments) -> list[dict[str, Any]]:
    from apps.enrollments.models import EnrollmentStatus
    from apps.performance.engine import student_performance_bulk

    rows = list(
        enrollments.filter(status=EnrollmentStatus.ACTIVE).select_related(
            "course", "batch", "student__user"
        )
    )
    if not rows:
        return []
    bulk = student_performance_bulk(rows)
    flagged = [row for row in rows if bulk[row.pk]["risk"]["at_risk"]]
    if not flagged:
        return []
    n = len(flagged)
    return [
        _warning(
            "students_at_risk",
            "warning",
            f"{n} {_plural(n, 'student')} flagged at risk",
            n,
            "/manage/batches?attention=at_risk",
            (
                {
                    "label": f"{_student_of(e)} · {e.batch.code}",
                    "href": f"/manage/students/{e.pk}",
                }
                for e in flagged
            ),
        )
    ]


def _admissions_warnings(user, students) -> list[dict[str, Any]]:
    waiting = (
        students.filter(enrollments__isnull=True, created_at__lt=timezone.now() - timedelta(days=7))
        .select_related("user")
        .order_by("created_at")
    )
    count = waiting.count()
    if not count:
        return []
    return [
        _warning(
            "not_enrolled",
            "warning",
            f"{count} {_plural(count, 'student')} registered over a week ago and not on any batch",
            count,
            "/admissions/dashboard",
            (
                {
                    "label": f"{_person(s.user)} · registered {s.created_at:%d %b}",
                    "href": f"/admissions/{s.pk}",
                }
                for s in waiting[:ITEM_LIMIT]
            ),
        )
    ]


def _account_warnings(user, accounts) -> list[dict[str, Any]]:
    out = []
    bounded = (UserRole.MANAGER, UserRole.COUNSELLOR, UserRole.TRAINER, UserRole.STUDENT)
    no_centre = accounts.filter(role__in=bounded, branch__isnull=True, is_active=True).order_by(
        "email"
    )
    n = no_centre.count()
    if n:
        out.append(
            _warning(
                "account_no_centre",
                "error",
                f"{n} {_plural(n, 'account')} in no centre — they see nothing until placed",
                n,
                "/admin/users?branch=none",
                (
                    {
                        "label": f"{u.full_name or u.email} · {u.role}",
                        "href": f"/admin/users/{u.pk}",
                    }
                    for u in no_centre[:ITEM_LIMIT]
                ),
            )
        )
    staff = (UserRole.ADMIN, UserRole.MANAGER, UserRole.COUNSELLOR, UserRole.TRAINER)
    unverified = accounts.filter(role__in=staff, is_email_verified=False, is_active=True).order_by(
        "date_joined"
    )
    m = unverified.count()
    if m:
        out.append(
            _warning(
                "email_unverified",
                "info",
                f"{m} staff {_plural(m, 'account')} never verified their email",
                m,
                "/admin/users?is_email_verified=false",
                (
                    {
                        "label": f"{u.full_name or u.email} · {u.role}",
                        "href": f"/admin/users/{u.pk}",
                    }
                    for u in unverified[:ITEM_LIMIT]
                ),
            )
        )
    return out


def _completion_warnings(user, enrollments) -> list[dict[str, Any]]:
    from apps.progress.models import CompletionStatus, CourseCompletion

    eligible = (
        CourseCompletion.objects.filter(
            enrollment__in=enrollments, status=CompletionStatus.ELIGIBLE
        )
        .select_related("enrollment__student__user", "enrollment__course")
        .order_by("updated_at")
    )
    count = eligible.count()
    if not count:
        return []
    return [
        _warning(
            "completions_pending",
            "warning",
            f"{count} {_plural(count, 'student')} waiting for completion approval",
            count,
            "/admin/completions",
            (
                {
                    "label": f"{_student_of(c.enrollment)} · {c.enrollment.course.title}",
                    "href": "/admin/completions",
                }
                for c in eligible[:ITEM_LIMIT]
            ),
        )
    ]


# ---------------------------------------------------------------------------


SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def warnings_for(user) -> list[dict[str, Any]]:
    """Every warning this caller should act on, most urgent first."""
    from apps.accounts import access as accounts_access
    from apps.batches import access as batch_access
    from apps.students import access as students_access

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return []
    if user.role == UserRole.STUDENT:
        return []

    batches = batch_access.visible_batches(user)
    enrollments = batch_access.visible_enrollments(user)
    out: list[dict[str, Any]] = []
    if has_capability(user, Capability.FEE_VIEW_ANY):
        out += _fee_warnings(user, enrollments)
    if has_capability(user, Capability.BATCH_VIEW_ANY):
        out += _batch_warnings(user, batches)
    if has_capability(user, Capability.DSR_VIEW_ANY) or user.role == UserRole.TRAINER:
        out += _dsr_warnings(user, batches)
    if has_capability(user, Capability.PERFORMANCE_VIEW_ANY) or user.role == UserRole.TRAINER:
        out += _risk_warnings(user, enrollments)
    if has_capability(user, Capability.STUDENT_VIEW_ANY):
        out += _admissions_warnings(user, students_access.visible_students(user))
    if has_capability(user, Capability.USER_VIEW_ANY):
        out += _account_warnings(user, accounts_access.visible_accounts(user))
    if has_capability(user, Capability.COMPLETION_VIEW_ANY):
        out += _completion_warnings(user, enrollments)
    out.sort(key=lambda w: (SEVERITY_ORDER[w["severity"]], -w["count"]))
    return out


def cached_warnings_for(user) -> list[dict[str, Any]]:
    """The same, held for a minute per person: the strip is on every dashboard
    and the risk pass is the expensive part."""
    key = f"warnings:{user.pk}:{getattr(user, 'branch_id', None)}"
    found = cache.get(key)
    if found is not None:
        return found
    computed = warnings_for(user)
    cache.set(key, computed, CACHE_SECONDS)
    return computed


def digest_text(warnings: list[dict[str, Any]]) -> str:
    lines = [f"• {w['label']}" for w in warnings]
    return "\n".join(lines)
