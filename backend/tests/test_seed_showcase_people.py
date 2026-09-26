"""Stage 2 of the showcase: every roster account exists once, in the state the
people screens need, and a second run creates nothing.

Runs the command up to and including ``people`` on the empty test database —
no SITP rows, no courses — so the course-dependent scope grant is exercised
only in its skipped form here; the real-data run on the staging clone covers
the other branch.
"""

from __future__ import annotations

import os
import re
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog, AuditResult
from apps.authorization.models import Role, RoleStatus, ScopeGrant
from apps.authorization.services import delete_role
from apps.common.showcase.context import MARKER, Context, hydrate
from apps.common.showcase.roster import DOMAIN, build_roster
from apps.common.showcase.stages import s02_people
from apps.courses.models import Category
from apps.courses.services import create_course
from apps.notifications.models import NotificationPreference
from apps.notifications.services import update_preferences
from apps.students.models import StudentProfile
from apps.trainers.models import TrainerProfile

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people"

#: One line of the table: label, created, found. The indentation is the
#: command's two spaces plus the finish stage's two, so it is not pinned.
ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks) -> str:
    """One run of the command up to ``people``, with every on_commit hook fired."""
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    return {
        "users": User.objects.count(),
        "students": StudentProfile.objects.count(),
        "trainers": TrainerProfile.objects.count(),
        "roles": Role.objects.count(),
        "grants": ScopeGrant.objects.count(),
        "preferences": NotificationPreference.objects.count(),
        "audit": AuditLog.objects.count(),
        "referrals": StudentProfile.objects.filter(referred_by__isnull=False).count(),
        "whatsapp": User.objects.filter(whatsapp_opt_in=True).count(),
    }


@pytest.fixture
def bystander(db):
    """An account the stage must not touch: a demo-domain student that
    happens to share a name with somebody on the roster."""
    user = User.objects.create_user(
        email="aarav.mehta@demo.grras.invalid",
        password="Not-The-Showcase-Passw0rd!",
        first_name="Aarav",
        last_name="Mehta",
        role=UserRole.STUDENT,
    )
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
def test_people_stage_creates_every_state_once(django_capture_on_commit_callbacks, bystander):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Every roster account, once, signing in with the shared password
    roster = build_roster()
    by_email = {u.email: u for u in User.objects.filter(email__endswith="@" + DOMAIN)}
    assert len(by_email) == len(roster)
    for person in roster:
        user = by_email[person.email]
        assert user.role == person.role
        assert user.check_password(SEED_PASSWORD), person.email
        assert user.is_active, "nobody is deactivated in stage 2; stage 4 does that"
        if person.branch_code:
            assert user.branch.code == person.branch_code
    assert by_email["admin@grras.com"].is_staff
    assert by_email["admin.pune@grras.com"].is_staff
    # The flag went through `update_user`, so each admin's row carries the
    # audit entry a raw save would have skipped.
    staffed = AuditLog.objects.filter(
        action=AuditAction.USER_UPDATED, context__changed_fields=["is_staff"]
    )
    assert {row.resource_id for row in staffed} == {
        str(by_email["admin@grras.com"].pk),
        str(by_email["admin.pune@grras.com"].pk),
    }
    assert all(row.actor.role == UserRole.SUPERADMIN for row in staffed)

    # --- Verification: everybody but the two the roster flags
    unverified = {p.email for p in roster if p.flags.get("unverified")}
    assert len(unverified) == 2
    assert {u.email for u in by_email.values() if not u.is_email_verified} == unverified
    assert all(u.email_verified_at for u in by_email.values() if u.is_email_verified)

    # --- Trainers: profiles that read like people; the flags on the profile
    trainers = {p.user.email: p for p in TrainerProfile.objects.select_related("user")}
    assert len(trainers) == 10, "nine roster trainers plus the manager who teaches"
    headline = trainers["trainer@grras.com"]
    assert headline.professional_title == "Senior Linux & DevOps Trainer"
    assert "RHCSA" in headline.skills
    assert headline.years_of_experience == 14
    assert headline.bio and headline.expertise and headline.qualifications
    assert headline.professional_links["github"].startswith("https://")
    assert headline.is_profile_complete
    assert trainers["sameer.bhatt@grras.com"].is_accepting_assignments is False
    assert trainers["deepak.purohit@grras.com"].user.is_active is True
    manager_profile = trainers["manager@grras.com"]
    assert manager_profile.user.role == UserRole.MANAGER
    assert manager_profile.branch.code == "MAIN"

    # --- Students: varied profiles, unique phones, both kinds of institution
    students = list(StudentProfile.objects.select_related("user", "branch"))
    assert len(students) == 101
    assert len({s.user.phone for s in students}) == 101
    assert {s.branch.code for s in students} == {"MAIN", "PUNE"}
    kinds = {s.institution_kind for s in students}
    assert kinds >= {"college", "employer"}
    assert any("Jaipur" in s.institution for s in students)
    assert any(s.job_title for s in students if s.institution_kind == "employer")
    assert all(s.city == "Jaipur" for s in students if s.branch.code == "MAIN")
    assert all(s.state == "Maharashtra" for s in students if s.branch.code == "PUNE")
    completion = {s.completion_percent for s in students}
    assert 100 in completion and len(completion) > 1, "the completion meter has a spread"
    headline_student = next(s for s in students if s.user.email == "student@grras.com")
    assert headline_student.is_profile_complete
    assert headline_student.referrals.count() == s02_people.HEADLINE_REFERRALS
    referred = [s for s in students if s.referred_by_id]
    assert len(referred) == s02_people.REFERRALS
    assert all(s.branch.code == "MAIN" for s in referred)
    assert all(s.referred_by_id != s.pk for s in referred)
    by_pk = {s.pk: s for s in students}
    assert all(by_pk[s.referred_by_id].branch.code == "MAIN" for s in referred), (
        "a MAIN counsellor must be able to open every referrer"
    )
    # Neither the referred nor the referrers are the pinned rows (inactive,
    # never-enrolled, unverified): stage 4 deactivates one of those, and a
    # Student 360 must not name a deactivated referrer.
    main_students = [p for p in roster if p.role == UserRole.STUDENT and p.branch_code == "MAIN"]
    plain = {p.email for p in main_students[s02_people.FIRST_PLAIN_MAIN_STUDENT :]}
    assert {s.user.email for s in referred} <= plain
    referrers = {by_pk[s.referred_by_id].user.email for s in referred}
    assert referrers <= plain | {"student@grras.com"}
    opted_in = User.objects.filter(whatsapp_opt_in=True)
    assert opted_in.count() == s02_people.WHATSAPP_OPT_INS
    assert all(u.role == UserRole.STUDENT for u in opted_in)
    assert not opted_in.filter(email="student@grras.com").exists()

    # --- Roles: one custom role on a user, one disabled with nobody on it
    placement = Role.objects.get(slug="placement-coordinator")
    assert placement.kind == UserRole.COUNSELLOR and placement.status == RoleStatus.ACTIVE
    assert not placement.is_system
    assert placement.grants.get(permission__code="attendance.view_any").scope == "assigned"
    assert "fee.view_any" not in placement.codes
    assert placement.grants.get(permission__code=s02_people.LOCKED_CODE).is_locked
    assert placement.grants.filter(is_locked=True).count() == 1
    assert by_email["placement@grras.com"].custom_role_id == placement.pk
    guest = Role.objects.get(slug="guest-lecturer")
    assert guest.kind == UserRole.TRAINER and guest.status == RoleStatus.DISABLED
    assert guest.users.count() == 0
    # No course exists on a fresh database, so the grant is skipped, not faked.
    assert ScopeGrant.objects.count() == 0
    assert "scope grant for counsellor2@grras.com: skipped" in first

    # --- Preferences and the refused action
    assert (
        NotificationPreference.objects.get(user__email="trainer@grras.com").email_announcements
        is False
    )
    assert (
        NotificationPreference.objects.get(user__email="student@grras.com").email_administrative
        is False
    )
    denied = AuditLog.objects.filter(action=AuditAction.PERMISSION_DENIED)
    assert denied.count() == 1
    assert denied.get().actor.email == "counsellor@grras.com"
    assert denied.get().result == AuditResult.DENIED
    assert denied.get().context["note"].startswith(MARKER)
    assert not User.objects.filter(email=s02_people.DENIED_EMAIL).exists()
    assert AuditLog.objects.filter(action=AuditAction.USER_CREATED, actor__isnull=True).count() == 1
    assert AuditLog.objects.filter(action=AuditAction.STUDENT_CREATED).count() == 101
    assert AuditLog.objects.filter(action=AuditAction.ROLE_CREATED).count() == 2

    # --- Idempotent: the second run made nothing and changed no count
    assert counts() == after_first
    first_rows, second_rows = rows(first), rows(second)
    assert first_rows["student"] == (101, 0)
    assert first_rows["trainer"] == (9, 0)
    assert first_rows["role"] == (2, 0)
    assert first_rows["referral"] == (12, 0)
    assert first_rows["whatsapp_opt_in"] == (10, 0)
    assert first_rows["audit_denied"] == (1, 0)
    for label in (
        "user",
        "trainer",
        "student",
        "role",
        "custom_role_assignment",
        "permission_lock",
        "teaching_profile",
        "notification_preference",
        "whatsapp_opt_in",
        "referral",
        "audit_denied",
    ):
        created, found = second_rows[label]
        assert created == 0, f"second run created {created} {label}"
        assert found == first_rows[label][0], label
    assert "student student@grras.com: created" in first
    assert "student student@grras.com: found" in second
    assert SEED_PASSWORD not in first + second

    # --- The bystander is exactly as it was
    untouched = User.objects.get(pk=bystander.pk)
    assert untouched.updated_at == bystander.updated_at
    assert untouched.is_email_verified is False
    assert not untouched.check_password(SEED_PASSWORD)
    assert (
        not hasattr(untouched, "student_profile")
        or not StudentProfile.objects.filter(user=untouched).exists()
    )


@pytest.mark.django_db
def test_found_accounts_get_the_rotated_password(django_capture_on_commit_callbacks):
    run(django_capture_on_commit_callbacks)
    rotated = "Rotated-Showcase-Passw0rd!"
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": rotated}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out)
    for email in ("admin@grras.com", "trainer@grras.com", "student@grras.com"):
        assert User.objects.get(email=email).check_password(rotated), email
    assert rotated not in out.getvalue()


@pytest.mark.django_db
def test_a_preference_changed_on_the_settings_screen_survives_a_rerun(
    django_capture_on_commit_callbacks,
):
    """The preference row is the natural key, not what it says: a second run
    neither re-saves the row nor puts back the switch the stage set."""
    run(django_capture_on_commit_callbacks)
    trainer = NotificationPreference.objects.get(user__email="trainer@grras.com")
    student = NotificationPreference.objects.get(user__email="student@grras.com")
    assert trainer.email_announcements is False
    # What a reviewer does on the settings screen between two runs.
    update_preferences(user=trainer.user, email_announcements=True)

    second = run(django_capture_on_commit_callbacks)

    trainer.refresh_from_db()
    assert trainer.email_announcements is True, "the re-run put the switch back"
    assert NotificationPreference.objects.get(pk=student.pk).updated_at == student.updated_at, (
        "a found row was re-saved"
    )
    assert rows(second)["notification_preference"] == (0, 2)
    assert "notification preferences for trainer@grras.com: found" in second


@pytest.mark.django_db
def test_stage_fills_the_slots_exactly_as_hydrate_does(django_capture_on_commit_callbacks):
    """A ``--only`` run and a full run must see the same people in the same
    order, or a later stage's rng-driven picks would differ between them."""
    run(django_capture_on_commit_callbacks)

    hydrated = Context(password=SEED_PASSWORD, out=lambda _: None)
    hydrate(hydrated)

    rerun = Context(password=SEED_PASSWORD, out=lambda _: None)
    hydrate(rerun)
    rerun.rng = rerun.rng_for("people")
    s02_people.run(rerun)

    def ids(mapping):
        return {
            k: [row.pk for row in v] if isinstance(v, list) else v.pk for k, v in mapping.items()
        }

    for slot in ("users", "admins", "managers", "counsellors", "trainers", "students"):
        assert ids(getattr(rerun, slot)) == ids(getattr(hydrated, slot)), slot
    assert set(rerun.roles) >= {"placement-coordinator", "guest-lecturer"}
    assert rerun.trainers["MAIN"][0].user.email == "trainer@grras.com"
    assert rerun.students["MAIN"][0].user.email == "student@grras.com"
    assert rerun.counsellors["MAIN"].email == "counsellor@grras.com"
    assert sum(rerun.counts.values()) == 0, "a second run creates nothing"


@pytest.mark.django_db
def test_a_binned_guest_lecturer_is_found_not_remade(django_capture_on_commit_callbacks):
    """Stage 8 soft-deletes the disabled role. ``Role.objects`` then hides it,
    and a lookup through that manager would let ``create_role`` make a twin
    per run; the stage must find the binned row and leave it in the bin."""
    run(django_capture_on_commit_callbacks)
    owner = User.objects.get(role=UserRole.SUPERADMIN)
    guest = Role.objects.get(slug="guest-lecturer")
    delete_role(actor=owner, role=guest, reason="showcase: the recycle bin state")
    assert not Role.objects.filter(slug="guest-lecturer").exists()

    second = run(django_capture_on_commit_callbacks)

    assert Role.all_objects.filter(slug="guest-lecturer").count() == 1
    binned = Role.all_objects.get(slug="guest-lecturer")
    assert binned.is_deleted, "the stage never restores what another stage binned"
    assert binned.status == RoleStatus.DISABLED
    assert rows(second)["role"] == (0, 2)
    assert "role guest-lecturer: found" in second
    assert AuditLog.objects.filter(action=AuditAction.ROLE_CREATED).count() == 2


@pytest.mark.django_db
def test_scope_grant_stays_put_when_a_newer_course_sorts_first(
    django_capture_on_commit_callbacks,
):
    """The grant's natural key is "any course grant on counsellor2", so a
    course stage 3 adds later — one that sorts before the granted one by
    slug — must not move the choice or add a second grant."""
    category = Category.objects.create(name="Linux", slug="linux")
    first = run(django_capture_on_commit_callbacks)
    assert ScopeGrant.objects.count() == 0
    assert "scope grant for counsellor2@grras.com: skipped" in first

    owner = User.objects.get(role=UserRole.SUPERADMIN)
    late_by_slug = create_course(
        actor=owner,
        title="Python Pro Programming",
        slug="python-pro-programming",
        category=category,
    )
    second = run(django_capture_on_commit_callbacks)
    assert rows(second)["scope_grant"] == (1, 0)
    grant = ScopeGrant.objects.get(user__email="counsellor2@grras.com")
    assert grant.course_id == late_by_slug.pk

    create_course(
        actor=owner,
        title="AWS Solutions Architect",
        slug="aws-solutions-architect",
        category=category,
    )
    third = run(django_capture_on_commit_callbacks)
    assert rows(third)["scope_grant"] == (0, 1)
    assert ScopeGrant.objects.count() == 1
    assert ScopeGrant.objects.get().course_id == late_by_slug.pk
    assert "scope grant for counsellor2@grras.com on python-pro-programming: found" in third
