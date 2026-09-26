"""The showcase seed command is gated, idempotent and never prints the password."""

from __future__ import annotations

import os
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User, UserRole
from apps.common.showcase.stages import STAGE_KEYS
from apps.organisation.models import Branch

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"

EXPECTED_KEYS = [
    "organisation",
    "people",
    "courses",
    "batches",
    "fees",
    "academics",
    "teaching_ops",
    "work",
    "comms",
    "finish",
]


def run(*args: str, password: str = SEED_PASSWORD) -> str:
    """Run the command with the password in the environment; return its output.

    stdout and stderr are captured together because the promise under test is
    that the password appears in *neither*.
    """
    out = StringIO()
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": password}):
        call_command("seed_showcase", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
def test_refuses_where_demo_data_is_not_allowed(settings):
    settings.ALLOW_DEMO_SEED = False
    with pytest.raises(CommandError, match="must never run against production"):
        run("--list")


@pytest.mark.django_db
def test_refuses_without_a_password():
    with pytest.raises(CommandError, match="DEMO_USER_PASSWORD"):
        run("--only", "organisation", password="")


@pytest.mark.django_db
def test_refuses_a_weak_password():
    with pytest.raises(CommandError, match="password policy"):
        run("--only", "organisation", password="password")


@pytest.mark.django_db
def test_list_names_every_stage_in_order():
    assert STAGE_KEYS == EXPECTED_KEYS
    output = run("--list")
    positions = [output.index(f" {key} ") for key in EXPECTED_KEYS]
    assert positions == sorted(positions), "stages are listed out of order"


@pytest.mark.django_db
def test_unknown_stage_key_names_the_valid_ones():
    with pytest.raises(CommandError, match=r"Unknown stage.*organisation.*finish"):
        run("--only", "organisation,nonsense")
    with pytest.raises(CommandError, match=r"Unknown stage.*organisation.*finish"):
        run("--from", "nonsense")


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    before = Branch.objects.count(), User.objects.count()
    output = run("--dry-run")
    assert "Dry run" in output
    assert (Branch.objects.count(), User.objects.count()) == before


def listed_stages(output: str) -> list[str]:
    """The stage keys a ``--dry-run`` (or ``--list``) printed, in order."""
    return [key for key in EXPECTED_KEYS if f" {key} " in output]


@pytest.mark.django_db
def test_dry_run_from_lists_that_stage_and_everything_after():
    assert listed_stages(run("--dry-run", "--from", "comms")) == ["comms", "finish"]


@pytest.mark.django_db
def test_dry_run_only_lists_the_stage_and_the_finish():
    assert listed_stages(run("--dry-run", "--only", "people")) == ["people", "finish"]


@pytest.mark.django_db
def test_only_and_from_together_are_refused():
    with pytest.raises(CommandError, match="not both"):
        run("--dry-run", "--only", "people", "--from", "comms")


@pytest.mark.django_db
def test_organisation_stage_is_idempotent():
    """Twice over: one of each centre, one owner, and the second run creates nothing."""
    import re

    from apps.academics.models import AcademicEvent, AcademicEventKind
    from apps.policies.models import Policy

    first = run("--only", "organisation")
    holidays = AcademicEvent.objects.filter(kind=AcademicEventKind.HOLIDAY).count()
    policies = Policy.objects.count()
    # Somebody took the owner out of the Django admin between runs; the found
    # path must put him back, as it puts his verification back.
    User.objects.filter(email="owner@grras.com").update(is_staff=False, is_superuser=False)
    second = run("--only", "organisation")

    assert AcademicEvent.objects.filter(kind=AcademicEventKind.HOLIDAY).count() == holidays
    assert Policy.objects.count() == policies
    # The summary's total line: created 0 on the second run, whatever was found.
    assert re.search(r"^\s*total\s+0\s+\d+\s*$", second, re.MULTILINE), second

    assert Branch.objects.filter(code="MAIN").count() == 1
    assert Branch.objects.filter(code="PUNE").count() == 1
    assert Branch.objects.filter(code="UDR").count() == 1
    assert Branch.objects.get(code="MAIN").name == "Grras Jaipur"
    assert Branch.objects.get(code="PUNE").is_active is True
    assert Branch.objects.get(code="UDR").is_active is False

    owners = User.objects.filter(email="owner@grras.com")
    assert owners.count() == 1
    owner = owners.get()
    assert owner.role == UserRole.SUPERADMIN
    assert owner.is_email_verified is True
    assert owner.is_staff is True
    assert owner.is_superuser is True
    assert owner.branch_id is None
    assert owner.check_password(SEED_PASSWORD)

    assert "branch PUNE 'Grras Pune': created" in first
    assert "branch PUNE 'Grras Pune': found" in second
    assert "superadmin owner@grras.com: created" in first
    assert "superadmin owner@grras.com: found" in second
    assert "global academic policy: created" in first
    assert "global academic policy: found" in second
    assert "institution settings: found" in second
    assert "branding: found" in second


@pytest.mark.django_db
def test_organisation_stage_configures_the_institution():
    from apps.academics.models import AcademicEvent, AcademicPolicy, PolicyScope
    from apps.branding.models import BrandingSetting
    from apps.configuration.models import SystemSetting
    from apps.policies.models import Policy

    run("--only", "organisation")

    assert SystemSetting.objects.get().institution_name == "Grras Solutions"
    branding = BrandingSetting.current()
    assert (branding.display_name, branding.brand_color) == ("Grras Solutions", "#EF7220")
    policy = AcademicPolicy.objects.get(scope=PolicyScope.GLOBAL)
    assert policy.attendance_required_for_completion is True
    assert policy.minimum_attendance_percent == 75
    # Never a critical key: a demo must not force its reviewers into MFA.
    assert not Policy.objects.filter(category="authentication", key="mfa_required_roles").exists()
    assert Policy.objects.filter(category="risk", branch__code="PUNE").exists()
    assert AcademicEvent.objects.filter(name="Gandhi Jayanti").count() == 1
    assert AcademicEvent.objects.filter(name="Diwali").get().end_date.day == 9


@pytest.mark.django_db
def test_output_never_contains_the_password():
    for output in (run("--list"), run("--dry-run"), run("--only", "organisation"), run()):
        assert SEED_PASSWORD not in output


@pytest.mark.django_db
def test_finish_prints_the_sign_in_table_without_the_password():
    output = run("--only", "finish")
    assert "Sign in as" in output
    assert "superadmin   —        owner@grras.com" in output
    assert "student      MAIN     student@grras.com" in output
    assert "Password: the value of DEMO_USER_PASSWORD (printed nowhere)." in output
    assert SEED_PASSWORD not in output


@pytest.mark.django_db
def test_full_run_with_stubs_completes():
    """Today the stages after the first are stubs; the framework still runs end to end."""
    output = run()
    for key in EXPECTED_KEYS:
        assert f" {key} …" in output
    assert "Showcase data ready." in output


def test_roster_is_deterministic_and_well_formed():
    import re

    from apps.common.showcase.roster import DOMAIN, build_roster

    first, second = build_roster(), build_roster()
    assert [p.email for p in first] == [p.email for p in second]

    emails = [p.email for p in first]
    assert len(emails) == len(set(emails)), "duplicate email in the roster"
    phones = [p.flags["phone"] for p in first]
    assert len(phones) == len(set(phones)), "duplicate phone in the roster"
    for person in first:
        assert person.email.endswith("@" + DOMAIN)
        assert re.fullmatch(r"[a-z0-9.]+", person.local_part), person.local_part
        assert re.fullmatch(r"\+91[0-9]{10}", person.flags["phone"])

    by_role = {role: [p for p in first if p.role == role] for role in UserRole.values}
    assert len(by_role[UserRole.SUPERADMIN]) == 1
    assert len(by_role[UserRole.TRAINER]) == 9
    assert len(by_role[UserRole.STUDENT]) == 101
    assert first[0].local_part == "owner"
    assert any(p.flags.get("custom_role") == "placement-coordinator" for p in first)
    assert any(p.flags.get("is_accepting_assignments") is False for p in first)


@pytest.mark.django_db
def test_context_repr_never_contains_the_password():
    """Sentry captures local variables on an exception; ``repr(ctx)`` is one."""
    from apps.common.showcase.context import Context

    ctx = Context(password=SEED_PASSWORD, out=lambda _: None)
    assert SEED_PASSWORD not in repr(ctx)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "backend",
    [
        "django.core.mail.backends.smtp.EmailBackend",
        # An allow-list, not a block-list: a backend the gate has never heard
        # of is assumed to deliver until told otherwise.
        "anymail.backends.ses.EmailBackend",
    ],
)
def test_refuses_under_a_delivering_mail_backend(settings, backend):
    """The showcase fans notifications out to every account; with a delivering
    backend that is real mail to imported real addresses."""
    settings.EMAIL_BACKEND = backend
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        pytest.raises(CommandError, match="may deliver mail"),
    ):
        call_command("seed_showcase", "--list")
    # ... unless told in so many words.
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_showcase", "--list", "--allow-real-mail", stdout=StringIO())


@pytest.mark.django_db
def test_runs_under_the_console_mail_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    assert "organisation" in run("--list")


@pytest.mark.django_db
def test_each_stage_draws_the_same_sequence_alone_or_in_sequence():
    """``--only fees`` must pick the same rows the full run picked."""
    from apps.common.showcase.context import Context

    ctx = Context(password=SEED_PASSWORD, out=lambda _: None)
    alone = ctx.rng_for("fees").random()
    after_others = ctx.rng_for("batches")
    after_others.random()
    assert ctx.rng_for("fees").random() == alone
    assert ctx.rng_for("batches").random() != alone


@pytest.mark.django_db
def test_hydrate_refuses_a_roster_address_with_another_role():
    """An account on a roster address but with a different role was made by
    somebody else; filing it under the roster's role would misdirect writes."""
    from apps.common.showcase.context import Context, hydrate

    User.objects.create_user(
        email="admin@grras.com", password=SEED_PASSWORD, first_name="Not", role=UserRole.STUDENT
    )
    ctx = Context(password=SEED_PASSWORD, out=lambda _: None)
    with pytest.raises(RuntimeError, match=r"admin@grras\.com"):
        hydrate(ctx)


@pytest.mark.django_db
def test_hydrate_refuses_a_roster_address_at_another_branch():
    """The slots are keyed by the roster's centre; an account moved to another
    centre by hand would be filed under one and write into the other."""
    from apps.common.showcase.context import Context, hydrate

    run("--only", "organisation")  # the branches
    User.objects.create_user(
        email="admin@grras.com",
        password=SEED_PASSWORD,
        first_name="Anjali",
        role=UserRole.ADMIN,
        branch=Branch.objects.get(code="PUNE"),  # the roster says MAIN
    )
    ctx = Context(password=SEED_PASSWORD, out=lambda _: None)
    with pytest.raises(RuntimeError, match=r"admin@grras\.com exists at branch .*'PUNE'"):
        hydrate(ctx)


@pytest.mark.django_db
def test_found_owner_gets_the_current_password():
    """After the host rotates DEMO_USER_PASSWORD, a re-run must make the found
    accounts sign in with the new value, not the old hash."""
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}):
        call_command("seed_showcase", "--only", "organisation", stdout=StringIO())
    rotated = "Rotated-Showcase-Passw0rd!"
    with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": rotated}):
        call_command("seed_showcase", "--only", "organisation", stdout=StringIO())
    assert User.objects.get(email="owner@grras.com").check_password(rotated)


@pytest.mark.django_db
def test_finish_abandons_the_mail_this_run_queued():
    """The command's mail gate checks *its* backend; the worker and the retry
    sweep read their own, later. The finish stage takes this run's outbox rows
    off the table so neither can deliver them, and leaves earlier mail alone."""
    from apps.common.showcase.context import Context
    from apps.common.showcase.stages import s10_finish
    from apps.notifications.models import EmailMessage, EmailStatus

    def outbox(subject: str, status: str = EmailStatus.PENDING) -> EmailMessage:
        return EmailMessage.objects.create(
            to_email="student@grras.com", subject=subject, body="…", status=status
        )

    earlier = outbox("before the run")
    lines: list[str] = []
    ctx = Context(password=SEED_PASSWORD, out=lines.append)
    pending, failed, sent = (
        outbox("queued during the run"),
        outbox("failed once during the run", EmailStatus.FAILED),
        outbox("already sent", EmailStatus.SENT),
    )

    s10_finish.run(ctx)

    assert "queued mail abandoned: 2" in lines
    for message in (pending, failed):
        message.refresh_from_db()
        assert message.status == EmailStatus.ABANDONED
        assert message.last_error == "[showcase] not delivered: showcase run"
        assert not message.is_deliverable
    sent.refresh_from_db()
    assert sent.status == EmailStatus.SENT
    earlier.refresh_from_db()
    assert earlier.status == EmailStatus.PENDING, "mail queued before the run is the sweep's"

    # Idempotent: a second finish has nothing left to abandon.
    lines.clear()
    s10_finish.run(Context(password=SEED_PASSWORD, out=lines.append))
    assert "queued mail abandoned: 0" in lines


@pytest.mark.django_db
def test_finish_clears_the_cache_unless_it_is_also_the_broker(settings):
    """``cache.clear()`` on Redis is FLUSHDB; when the broker shares that
    database it would empty the Celery queue, so the clear is skipped."""
    from django.core.cache import cache

    from apps.common.showcase.context import Context
    from apps.common.showcase.stages import s10_finish

    settings.CACHE_URL = "redis://redis:6379/0"
    settings.CELERY_BROKER_URL = "redis://redis:6379/0"
    lines: list[str] = []
    cache.set("showcase-probe", "still here", 60)
    s10_finish.run(Context(password=SEED_PASSWORD, out=lines.append))
    assert cache.get("showcase-probe") == "still here"
    assert any("cache NOT cleared" in line and "task queue" in line for line in lines)

    settings.CELERY_BROKER_URL = "redis://redis:6379/1"
    lines.clear()
    s10_finish.run(Context(password=SEED_PASSWORD, out=lines.append))
    assert cache.get("showcase-probe") is None
    assert "cache cleared" in lines
