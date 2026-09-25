"""Stage 1 — the institution itself, before anybody works in it.

Creates, through the services and idempotently:

* the **superadmin** ``owner@grras.com`` — the one account created with
  ``actor=None``, because nobody exists yet to grant the role; every later
  write in this stage is his;
* the **centres**: the migration-seeded ``MAIN`` renamed to *Grras Jaipur*
  (the code stays, so nothing referencing it breaks), a new ``PUNE`` *Grras
  Pune*, and ``UDR`` *Grras Udaipur* opened and then **closed** with a reason,
  so the closed-centre filter and the "not offered for new records" rule both
  have a row to show;
* the **institution settings** (``SystemSetting``) and **branding**
  (``BrandingSetting``: *Grras Solutions*, ``#EF7220``), so the settings
  screens show a saved row with an ``updated_by`` rather than code defaults;
* the **global academic policy** with every threshold set explicitly and the
  ``*_required_for_completion`` gates on, so the rules screen shows values
  somebody chose and completion eligibility has rules to evaluate;
* a few **policy overrides** — never a critical key (``authentication.
  mfa_required_roles``, ``password.*``, ``session.*``, ``deletion.*``), because
  a demo that forces its own reviewers into MFA after a week is a demo that
  locks its reviewers out — plus one branch-level override so the resolver's
  branch-then-global walk is visible;
* the **academic calendar**: the public holidays in the coming ninety days
  (Gandhi Jayanti, Dussehra, Diwali) and one already past, so class generation
  in stage 4 has dates to skip and the calendar has history. Idempotent by
  ``(name, start_date)``.

Leaves in ``ctx``: ``superadmin``, ``users["owner"]``, ``branches[MAIN|PUNE|UDR]``.

The find-or-create pattern every later stage should copy
--------------------------------------------------------
Look the row up by its natural key first (email, code, ``(name, date)``, or
the ``[showcase]`` marker on a note), count it with ``ctx.found_existing``
when it is there, create it through the service and count it with
``ctx.created`` when it is not. Services whose writes are already no-ops on
an unchanged value (``update_settings``, ``update_policy``, ``update_branch``)
are called unconditionally; the log line says which case happened.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.academics.models import (
    DEFAULT_GRADE_BANDS,
    AcademicEvent,
    AcademicEventKind,
    AcademicPolicy,
)
from apps.academics.models import PolicyScope as AcademicScope
from apps.academics.services import add_calendar_event, get_or_create_policy
from apps.academics.services import update_policy as update_academic_policy
from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user
from apps.branding.models import BrandingSetting
from apps.branding.services import update_branding
from apps.configuration.services import get_or_create_settings, update_settings
from apps.organisation.models import Branch
from apps.organisation.services import create_branch, set_branch_active, update_branch
from apps.policies.models import Policy
from apps.policies.services import update_policy as update_policy_key

from ..context import Context
from ..roster import MAIN, PUNE

UDR = "UDR"

#: (code, name, city, open?). MAIN already exists on every database this runs
#: against — the migration created it — so for MAIN this is a rename.
BRANCHES: list[tuple[str, str, str, bool]] = [
    (MAIN, "Grras Jaipur", "Jaipur", True),
    (PUNE, "Grras Pune", "Pune", True),
    (UDR, "Grras Udaipur", "Udaipur", False),
]

INSTITUTION_SETTINGS: dict[str, Any] = {
    "institution_name": "Grras Solutions",
    "support_email": "support@grras.com",
    "support_phone": "+911414034321",
    "export_retention_days": 30,
}

BRANDING: dict[str, Any] = {"display_name": "Grras Solutions", "brand_color": "#EF7220"}

#: Every rule set on purpose. The values are the code defaults where those are
#: already sensible — a showcase should look like a well-run institute, not an
#: unusual one — with three attempts on assignments so the resubmission path
#: is reachable, and every completion gate on so eligibility means something.
ACADEMIC_RULES: dict[str, Any] = {
    "minimum_attendance_percent": Decimal("75.00"),
    "attendance_required_for_completion": True,
    "passing_percent": Decimal("40.00"),
    "assignment_default_max_marks": Decimal("100.00"),
    "assignment_allow_late": True,
    "assignment_default_max_attempts": 3,
    "assignment_required_for_completion": True,
    "minimum_assignment_completion_percent": Decimal("80.00"),
    "test_default_max_marks": Decimal("100.00"),
    "tests_required_for_completion": True,
    "minimum_test_average_percent": Decimal("40.00"),
    "minimum_test_completion_percent": Decimal("80.00"),
    "lessons_required_for_completion": True,
    "minimum_lesson_completion_percent": Decimal("80.00"),
    "projects_required_for_completion": True,
    "final_exam_required_for_completion": False,
    "batch_directory_visible": True,
    "grade_bands": DEFAULT_GRADE_BANDS,
    "risk_attendance_percent": Decimal("75.00"),
    "risk_assessment_average_percent": Decimal("50.00"),
    "risk_missed_assignments": 2,
    "risk_progress_variance_percent": Decimal("15.00"),
}

#: (category, key, value, branch code or None). Non-critical keys only — see
#: the module docstring. Values are the schema's strict types: ints as int,
#: decimals as str, booleans as bool.
POLICY_OVERRIDES: list[tuple[str, str, Any, str | None]] = [
    ("authentication", "lockout_after", 5, None),
    ("communication", "guardian_alerts", True, None),
    ("export", "retention_days", 30, None),
    ("notification", "digest_frequency", "daily", None),
    # Pune runs a stricter attendance bar: a branch row for the resolver to prefer.
    ("risk", "risk_attendance_percent", "80.00", PUNE),
]

#: (name, month, day, length in days, in the past?). Fixed calendar dates roll
#: forward by year, so the "coming ninety days" stays true on every re-run.
#: Dussehra and Diwali move with the lunar calendar; they are pinned to their
#: 2026 dates because this is a showcase, not a panchang.
HOLIDAYS: list[tuple[str, int, int, int, bool]] = [
    ("Independence Day", 8, 15, 1, True),
    ("Gandhi Jayanti", 10, 2, 1, False),
    ("Dussehra", 10, 20, 1, False),
    ("Diwali", 11, 8, 2, False),
    ("Republic Day", 1, 26, 1, False),
]


def run(ctx: Context) -> None:
    owner = _ensure_owner(ctx)
    _ensure_branches(ctx, owner)
    _ensure_settings(ctx, owner)
    _ensure_branding(ctx, owner)
    _ensure_academic_policy(ctx, owner)
    _ensure_policy_overrides(ctx, owner)
    _ensure_holidays(ctx, owner)


# ---------------------------------------------------------------------------
# The boss
# ---------------------------------------------------------------------------


def _ensure_owner(ctx: Context) -> User:
    """The superadmin, created with no actor because there is nobody to be one.

    ``create_user`` refuses a role the actor cannot grant, and nobody can
    grant superadmin — so the very first account is the one write in the whole
    showcase that bypasses that check, by having no actor to check. Every
    account after it is created *by* him.
    """
    person = next(p for p in ctx.roster if p.role == UserRole.SUPERADMIN)
    user = User.objects.filter(email=person.email).first()
    if user is None:
        user = create_user(
            email=person.email,
            password=ctx.password,
            first_name=person.first_name,
            last_name=person.last_name,
            role=UserRole.SUPERADMIN,
            phone=person.flags.get("phone", ""),
            actor=None,
            branch=None,
            send_invitation=False,
        )
        # The Django admin is the one door `create_user` does not open; the
        # owner gets it, as `seed_demo_data`'s superadmin does.
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
        ctx.created("user")
        ctx.out(f"superadmin {person.email}: created")
    else:
        ctx.found_existing("user")
        ctx.out(f"superadmin {person.email}: found")
        ctx.ensure_password(user)

    # Pre-verified, whoever created him: a sign-in blocked behind a
    # verification email is a showcase nobody can open.
    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["is_email_verified", "email_verified_at"])

    ctx.superadmin = user
    ctx.users[person.local_part] = user
    return user


# ---------------------------------------------------------------------------
# Centres
# ---------------------------------------------------------------------------


def _ensure_branches(ctx: Context, owner: User) -> None:
    for code, name, city, is_open in BRANCHES:
        branch = Branch.objects.filter(code=code).first()
        if branch is None:
            branch = create_branch(actor=owner, code=code, name=name, city=city)
            ctx.created("branch")
            ctx.out(f"branch {code} '{name}': created")
        elif branch.name != name or branch.city != city:
            # The one deliberate upgrade of a row this stage did not create:
            # the migration's 'Main centre' becomes the Jaipur centre it is.
            update_branch(branch=branch, actor=owner, name=name, city=city)
            ctx.found_existing("branch")
            ctx.out(f"branch {code}: renamed to '{name}'")
        else:
            ctx.found_existing("branch")
            ctx.out(f"branch {code} '{name}': found")

        if branch.is_active != is_open:
            set_branch_active(
                branch=branch,
                is_active=is_open,
                actor=owner,
                reason=ctx.note("Udaipur centre closed; records kept for history."),
            )
            ctx.out(f"branch {code}: {'opened' if is_open else 'closed'}")

        ctx.branches[code] = branch


# ---------------------------------------------------------------------------
# Settings, branding, rules
# ---------------------------------------------------------------------------


def _ensure_settings(ctx: Context, owner: User) -> None:
    row = get_or_create_settings()
    unchanged = all(getattr(row, k) == v for k, v in INSTITUTION_SETTINGS.items())
    update_settings(settings_row=row, actor=owner, **INSTITUTION_SETTINGS)
    _report(ctx, "system_setting", "institution settings", found=unchanged)


def _ensure_branding(ctx: Context, owner: User) -> None:
    row = BrandingSetting.current()
    unchanged = all(getattr(row, k) == v for k, v in BRANDING.items())
    update_branding(actor=owner, **BRANDING)
    _report(ctx, "branding_setting", "branding", found=unchanged)


def _ensure_academic_policy(ctx: Context, owner: User) -> None:
    existed = AcademicPolicy.objects.filter(scope=AcademicScope.GLOBAL).exists()
    policy = get_or_create_policy()
    unchanged = existed and all(getattr(policy, k) == v for k, v in ACADEMIC_RULES.items())
    update_academic_policy(policy=policy, actor=owner, **ACADEMIC_RULES)
    _report(ctx, "academic_policy", "global academic policy", found=unchanged)


def _ensure_policy_overrides(ctx: Context, owner: User) -> None:
    for category, key, value, branch_code in POLICY_OVERRIDES:
        branch = ctx.branches[branch_code] if branch_code else None
        before = Policy.objects.filter(category=category, key=key, branch=branch).first()
        # `update_policy` is a no-op on an unchanged value, so calling it on
        # every run costs nothing and corrects a value somebody changed by hand.
        update_policy_key(
            actor=owner,
            category=category,
            key=key,
            value=value,
            branch=branch,
            reason=ctx.note("Showcase configuration."),
        )
        where = f" @ {branch_code}" if branch_code else ""
        _report(ctx, "policy", f"policy {category}.{key}{where}", found=before is not None)


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def _occurrence(ctx: Context, month: int, day: int, *, past: bool) -> date:
    """This year's date, moved a year forward or back so it lands on the
    wanted side of today. Keeps the calendar relative to *now* on re-runs."""
    this_year = date(ctx.today.year, month, day)
    if past:
        return this_year if this_year < ctx.today else this_year.replace(year=ctx.today.year - 1)
    return this_year if this_year >= ctx.today else this_year.replace(year=ctx.today.year + 1)


def _ensure_holidays(ctx: Context, owner: User) -> None:
    for name, month, day, length, past in HOLIDAYS:
        start = _occurrence(ctx, month, day, past=past)
        end = start + timedelta(days=length - 1)
        if AcademicEvent.objects.filter(name=name, start_date=start).exists():
            ctx.found_existing("academic_event")
            ctx.out(f"holiday {name} {start:%d %b %Y}: found")
            continue
        add_calendar_event(
            actor=owner,
            name=name,
            kind=AcademicEventKind.HOLIDAY,
            start_date=start,
            end_date=end,
            note=ctx.note("Public holiday; no classes are generated on it."),
        )
        ctx.created("academic_event")
        ctx.out(f"holiday {name} {start:%d %b %Y}: created")


def _report(ctx: Context, label: str, what: str, *, found: bool) -> None:
    if found:
        ctx.found_existing(label)
        ctx.out(f"{what}: found")
    else:
        ctx.created(label)
        ctx.out(f"{what}: created")
