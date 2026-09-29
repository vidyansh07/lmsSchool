"""Making imported contact details undeliverable, before mail is switched on.

The command exists for one reason: a staging database holds real students'
Gmail addresses and real phone numbers, and the moment SMTP credentials are
configured every announcement the showcase fans out would reach those people.
These tests assert the properties that make it safe to rely on — that it
rewrites everything reachable, keeps the accounts people sign in as, leaves no
trace of the old values, converges on a second run, and cannot write on a dry
run — rather than the exact wording of its report.
"""

from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.management.commands.anonymise_imported_contacts import (
    PLACEHOLDER_DOMAIN,
    UNDIALLABLE_PHONE,
    mask,
)
from apps.accounts.models import User, UserRole
from apps.audit.models import AuditLog
from apps.common.validators import PHONE_RE
from apps.notifications.models import EmailMessage, EmailStatus
from apps.students.models import StudentProfile
from tests.conftest import TEST_PASSWORD


def run(*args, expect_ok=True):
    out = StringIO()
    call_command("anonymise_imported_contacts", *args, stdout=out, stderr=out)
    return out.getvalue()


def make_imported_student(branch, *, email, roll_number, phone="+919812345678"):
    """A student shaped the way the SITP import leaves one: a real address."""
    user = User.objects.create_user(
        email=email,
        password=TEST_PASSWORD,
        first_name="Imported",
        last_name="Learner",
        role=UserRole.STUDENT,
        branch=branch,
        phone=phone,
    )
    user.is_email_verified = True
    user.whatsapp_opt_in = True
    user.save(update_fields=["is_email_verified", "whatsapp_opt_in"])
    StudentProfile.objects.create(
        user=user,
        branch=branch,
        student_id=f"GRS-{uuid.uuid4().hex[:8].upper()}",
        roll_number=roll_number,
        guardian_phone="+919800000001",
        emergency_contact_phone="+919800000002",
    )
    return user


@pytest.mark.django_db
def test_a_real_address_becomes_its_roll_number_on_the_placeholder_domain(branch):
    user = make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS123")

    run()

    user.refresh_from_db()
    assert user.email == f"rtu-21eskcs123@{PLACEHOLDER_DOMAIN}"
    # The address can no longer receive mail, and the account no longer claims
    # a verified one.
    assert user.is_email_verified is False
    assert user.email_verified_at is None


@pytest.mark.django_db
def test_every_phone_number_becomes_one_no_carrier_can_route(branch):
    user = make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS124")

    run()

    user.refresh_from_db()
    profile = user.student_profile
    profile.refresh_from_db()
    assert user.phone == UNDIALLABLE_PHONE
    assert profile.guardian_phone == UNDIALLABLE_PHONE
    assert profile.emergency_contact_phone == UNDIALLABLE_PHONE
    # Still a value the form would accept, so editing the record does not fail
    # validation on a field nobody touched.
    assert PHONE_RE.match(UNDIALLABLE_PHONE)
    # And not diallable: E.164 country codes never begin with a zero.
    assert UNDIALLABLE_PHONE.startswith("+0")


@pytest.mark.django_db
def test_consent_given_for_an_address_that_no_longer_exists_is_withdrawn(branch):
    user = make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS125")

    run()

    user.refresh_from_db()
    assert user.whatsapp_opt_in is False


@pytest.mark.django_db
def test_the_accounts_people_sign_in_as_are_left_alone(branch):
    kept = User.objects.create_user(
        email="trainer@grras.com",
        password=TEST_PASSWORD,
        first_name="Vikram",
        last_name="Shekhawat",
        role=UserRole.TRAINER,
        branch=branch,
        phone="+919811111111",
    )
    reserved = User.objects.create_user(
        email="rtu-21eskcs001@sitp.grras.invalid",
        password=TEST_PASSWORD,
        first_name="Already",
        last_name="Placeholder",
        role=UserRole.STUDENT,
        branch=branch,
    )

    run()

    kept.refresh_from_db()
    reserved.refresh_from_db()
    assert kept.email == "trainer@grras.com"
    assert kept.phone == "+919811111111"
    assert reserved.email == "rtu-21eskcs001@sitp.grras.invalid"


@pytest.mark.django_db
def test_keep_takes_the_domains_it_is_given_and_still_keeps_reserved_ones(branch):
    partner = User.objects.create_user(
        email="head@partnercollege.ac.in",
        password=TEST_PASSWORD,
        first_name="Partner",
        last_name="Head",
        role=UserRole.MANAGER,
        branch=branch,
    )
    grras = User.objects.create_user(
        email="admin@grras.com",
        password=TEST_PASSWORD,
        first_name="Anjali",
        last_name="Mehta",
        role=UserRole.ADMIN,
        branch=branch,
    )

    run("--keep", "partnercollege.ac.in")

    partner.refresh_from_db()
    grras.refresh_from_db()
    assert partner.email == "head@partnercollege.ac.in"
    # --keep replaces the default, so the roster's own domain is no longer kept
    # unless it is named. The report prints the kept list for exactly this.
    assert grras.email.endswith(f"@{PLACEHOLDER_DOMAIN}")


@pytest.mark.django_db
def test_two_students_sharing_a_roll_number_get_distinct_addresses(branch):
    first = make_imported_student(branch, email="one@gmail.com", roll_number="21ESKCS200")
    second = make_imported_student(branch, email="two@gmail.com", roll_number="21ESKCS200")

    output = run()

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.email != second.email
    assert {first.email, second.email} == {
        f"rtu-21eskcs200@{PLACEHOLDER_DOMAIN}",
        f"rtu-21eskcs200-2@{PLACEHOLDER_DOMAIN}",
    }
    assert "needing a suffix to stay unique: 1" in output


@pytest.mark.django_db
def test_a_collision_with_an_address_the_import_already_made_is_avoided(branch):
    User.objects.create_user(
        email=f"rtu-21eskcs300@{PLACEHOLDER_DOMAIN}",
        password=TEST_PASSWORD,
        first_name="Imported",
        last_name="Earlier",
        role=UserRole.STUDENT,
        branch=branch,
    )
    late = make_imported_student(branch, email="late@gmail.com", roll_number="21ESKCS300")

    run()

    late.refresh_from_db()
    assert late.email == f"rtu-21eskcs300-2@{PLACEHOLDER_DOMAIN}"


@pytest.mark.django_db
def test_an_account_with_no_student_profile_falls_back_to_its_primary_key(branch):
    staff = User.objects.create_user(
        email="someone.real@gmail.com",
        password=TEST_PASSWORD,
        first_name="Some",
        last_name="Body",
        role=UserRole.TRAINER,
        branch=branch,
    )

    run()

    staff.refresh_from_db()
    assert staff.email == f"user-{staff.pk.hex}@{PLACEHOLDER_DOMAIN}"


@pytest.mark.django_db
def test_a_profile_with_no_roll_number_falls_back_to_its_student_id(branch):
    user = make_imported_student(branch, email="noroll@gmail.com", roll_number="")
    student_id = user.student_profile.student_id

    run()

    user.refresh_from_db()
    assert user.email == f"{student_id.lower()}@{PLACEHOLDER_DOMAIN}".replace(
        "grs-", "student-grs-"
    )


@pytest.mark.django_db
def test_mail_already_queued_to_a_real_address_is_withdrawn_not_left_to_send(branch):
    make_imported_student(branch, email="queued@gmail.com", roll_number="21ESKCS400")
    pending = EmailMessage.objects.create(
        to_email="queued@gmail.com",
        subject="An announcement the showcase queued",
        body="…",
        status=EmailStatus.PENDING,
    )
    failed = EmailMessage.objects.create(
        to_email="someone.else@gmail.com",
        subject="A grade notification",
        body="…",
        status=EmailStatus.FAILED,
    )
    already_sent = EmailMessage.objects.create(
        to_email="history@gmail.com",
        subject="Sent before any of this",
        body="…",
        status=EmailStatus.SENT,
    )

    run()

    pending.refresh_from_db()
    failed.refresh_from_db()
    already_sent.refresh_from_db()
    # Nothing the worker would pick up still carries a real address.
    assert pending.status == EmailStatus.ABANDONED
    assert failed.status == EmailStatus.ABANDONED
    assert pending.to_email == f"withdrawn@{PLACEHOLDER_DOMAIN}"
    assert failed.to_email == f"withdrawn@{PLACEHOLDER_DOMAIN}"
    # A sent row is history. Rewriting it would falsify the record of what was
    # sent, and it cannot be sent again.
    assert already_sent.status == EmailStatus.SENT
    assert already_sent.to_email == "history@gmail.com"


@pytest.mark.django_db
def test_nothing_is_queued_for_the_worker_to_pick_up_afterwards(branch):
    make_imported_student(branch, email="queued@gmail.com", roll_number="21ESKCS401")
    EmailMessage.objects.create(
        to_email="queued@gmail.com", subject="s", body="b", status=EmailStatus.PENDING
    )

    run()

    assert not EmailMessage.objects.filter(
        status__in=[EmailStatus.PENDING, EmailStatus.FAILED]
    ).exists()


@pytest.mark.django_db
def test_a_dry_run_reports_the_whole_plan_and_writes_nothing(branch):
    user = make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS500")
    EmailMessage.objects.create(
        to_email="real.person@gmail.com", subject="s", body="b", status=EmailStatus.PENDING
    )

    output = run("--dry-run")

    user.refresh_from_db()
    assert user.email == "real.person@gmail.com"
    assert user.phone == "+919812345678"
    assert user.whatsapp_opt_in is True
    assert EmailMessage.objects.filter(status=EmailStatus.PENDING).count() == 1
    assert not AuditLog.objects.filter(context__operation="anonymise_imported_contacts").exists()
    assert "DRY RUN" in output
    assert "Accounts whose email would be rewritten: 1" in output


@pytest.mark.django_db
def test_a_second_run_finds_nothing_and_writes_no_audit_record(branch):
    make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS600")

    run()
    first = AuditLog.objects.filter(context__operation="anonymise_imported_contacts").count()
    output = run()

    assert first == 1
    assert AuditLog.objects.filter(context__operation="anonymise_imported_contacts").count() == 1
    assert "Nothing to do" in output


@pytest.mark.django_db
def test_the_audit_record_carries_counts_and_never_an_address(branch):
    make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS700")

    run()

    entry = AuditLog.objects.get(context__operation="anonymise_imported_contacts")
    assert entry.context["accounts"] == 1
    assert entry.context["phones_replaced"] == 3
    assert entry.context["kept_domains"] == ["grras.com"]
    assert "real.person" not in str(entry.context)
    assert "gmail" not in str(entry.context)


@pytest.mark.django_db
def test_the_report_never_prints_a_real_address_in_full(branch):
    make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS800")

    output = run("--dry-run")

    assert "real.person@gmail.com" not in output
    assert "r***@g***.com" in output


def test_masking_keeps_only_enough_to_recognise_a_kind_of_address():
    assert mask("sam.student@gmail.com") == "s***@g***.com"
    assert mask("a@b.co") == "a***@b***.co"
    # A malformed address must still not leak; it must not raise either.
    assert mask("nodomain") == "n***@***"


@pytest.mark.django_db
def test_it_refuses_outside_an_environment_that_allows_demo_data(branch, settings):
    settings.ALLOW_DEMO_SEED = False
    user = make_imported_student(branch, email="real.person@gmail.com", roll_number="21ESKCS900")

    with pytest.raises(CommandError, match="must never run against production data"):
        run()

    user.refresh_from_db()
    assert user.email == "real.person@gmail.com"


@pytest.mark.django_db
def test_the_placeholder_domain_matches_the_importer_that_created_the_records():
    """The two must agree, or an anonymised student is distinguishable from one
    the sheet had no address for — which is the property that makes this safe."""
    from apps.reporting.management.commands.import_sitp_workbooks import (
        PLACEHOLDER_DOMAIN as importer_domain,
    )

    assert PLACEHOLDER_DOMAIN == importer_domain
